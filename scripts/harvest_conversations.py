#!/usr/bin/env python3
"""
harvest_conversations.py
Harvests Antigravity conversations across desktop, CLI, and IDE,
enforcing strict workspace isolation, excluding subagents, and parsing
structured turn-by-turn interactions across configurable day windows.
Supports cursor tracking (memory/sync_state.json) for differential harvesting
across continuing multi-day sessions.

Usage:
  python3 scripts/harvest_conversations.py [--date YYYY-MM-DD] [--days N] [--workspace PATH_OR_NAME]
                                          [--routine NAME] [--cursor] [--update-cursor] [--catch-up]
                                          [--strict-dates] [--include-subagents] [--status]
                                          [--output OUTPUT_JSON] [--summary] [--verbose]
"""
import os
import sys
import json
import re
import argparse
import sqlite3
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
SYNC_STATE_PATH = BASE_DIR / "memory" / "sync_state.json"
DEFAULT_WORKSPACE = os.environ.get("ANTIGRAVITY_WORKSPACE", str(BASE_DIR.resolve()))

ANTIGRAVITY_ROOTS = [
    Path.home() / ".gemini" / "antigravity",
    Path.home() / ".gemini" / "antigravity-cli",
    Path.home() / ".gemini" / "antigravity-ide"
]

def load_sync_state() -> dict:
    if not SYNC_STATE_PATH.exists():
        return {
            "last_run": None,
            "last_routine": None,
            "conversations": {},
            "routines": {}
        }
    try:
        with open(SYNC_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("conversations", {})
                data.setdefault("routines", {})
                return data
    except Exception:
        pass
    return {"last_run": None, "last_routine": None, "conversations": {}, "routines": {}}

def get_routine_state(state: dict, routine: str) -> dict:
    routines = state.setdefault("routines", {})
    if routine not in routines:
        routines[routine] = {
            "last_run": None,
            "harvested_count": 0,
            "conversations": {},
            "history": []
        }
    return routines[routine]

def save_sync_state(state: dict):
    SYNC_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = SYNC_STATE_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    tmp_path.replace(SYNC_STATE_PATH)

def check_is_archived(root_dir: Path, conv_id: str) -> bool:
    """Checks whether a conversation is marked as archived in Antigravity."""
    annot_path = root_dir / "annotations" / f"{conv_id}.pbtxt"
    if annot_path.exists():
        try:
            txt = annot_path.read_text(encoding="utf-8", errors="ignore")
            if "archived:true" in txt.replace(" ", "").lower():
                return True
        except Exception:
            pass
    return False

def check_sandbox_masking() -> bool:
    """Checks whether the running process is inside an isolated sandbox container masking ~/.gemini/antigravity."""
    ag_brain = Path.home() / ".gemini" / "antigravity" / "brain"
    if ag_brain.exists():
        try:
            subdirs = [d for d in ag_brain.iterdir() if d.is_dir()]
            if len(subdirs) <= 1:
                mounts_path = Path("/proc/mounts")
                if mounts_path.exists():
                    mounts_txt = mounts_path.read_text(encoding="utf-8", errors="ignore")
                    if "deny1" in mounts_txt or ("tmpfs" in mounts_txt and "/.gemini/antigravity" in mounts_txt):
                        return True
        except Exception:
            pass
    return False

def parse_args():
    parser = argparse.ArgumentParser(description="Harvest Antigravity conversations across dates.")
    parser.add_argument("--date", type=str, default=datetime.now().strftime("%Y-%m-%d"),
                        help="Target anchor date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--days", type=int, default=1,
                        help="Number of days to look back including the target date. Default: 1.")
    parser.add_argument("--workspace", type=str, default=DEFAULT_WORKSPACE,
                        help="Workspace filter substring. Set to '' or 'all' to include all.")
    parser.add_argument("--include-subagents", action="store_true",
                        help="Include subagent conversations. Default: false (orchestrator only).")
    parser.add_argument("--cursor", action="store_true",
                        help="Use sync_state.json to differentially harvest only new turns.")
    parser.add_argument("--update-cursor", action="store_true",
                        help="Commit new conversation cursors to sync_state.json.")
    parser.add_argument("--routine", type=str, default="default",
                        help="Routine partition name for cursor isolation (e.g. dream-cycle, system-improvement).")
    parser.add_argument("--catch-up", "--all-pending", action="store_true", dest="catch_up",
                        help="Harvest all unharvested turns across all historical sessions, ignoring calendar date windows.")
    parser.add_argument("--strict-dates", action="store_true",
                        help="Force strict calendar date filtering even when cursor or catch-up is enabled.")
    parser.add_argument("--status", action="store_true",
                        help="Display sync state and watermark summary for routines.")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON file path for harvested bundle.")
    parser.add_argument("--summary", action="store_true",
                        help="Print human-readable summary to stdout.")
    parser.add_argument("--verbose", action="store_true",
                        help="Print verbose progress messages.")
    return parser.parse_args()

def check_workspace_match(root_dir: Path, conv_id: str, transcript_path: Path, filter_str: str) -> tuple[bool, str]:
    """
    Deterministically checks if a conversation belongs to the target workspace.
    Returns (matches_filter, detected_workspace_info).
    """
    if not filter_str or filter_str.lower() == "all":
        return True, "all"

    detected_ws = None

    # 1. Query individual conv database trajectory_metadata_blob
    conv_db = root_dir / "conversations" / f"{conv_id}.db"
    if conv_db.exists():
        conn = None
        try:
            conn = sqlite3.connect(f"file:{conv_db}?mode=ro", uri=True)
            c = conn.cursor()
            c.execute('SELECT data FROM trajectory_metadata_blob WHERE id="main"')
            row = c.fetchone()
            if row and row[0]:
                matches = re.findall(rb'file://[^\x00-\x1f\s]+', row[0])
                if matches:
                    detected_ws = [urllib.parse.unquote(m.decode(errors="ignore")) for m in matches]
        except Exception:
            pass
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # 2. Query conversation_summaries.db
    if not detected_ws:
        sum_db = root_dir / "conversation_summaries.db"
        if sum_db.exists():
            conn = None
            try:
                conn = sqlite3.connect(f"file:{sum_db}?mode=ro", uri=True)
                c = conn.cursor()
                c.execute('SELECT workspace_uris FROM conversation_summaries WHERE conversation_id = ?', (conv_id,))
                row = c.fetchone()
                if row and row[0]:
                    try:
                        detected_ws = [urllib.parse.unquote(u) for u in json.loads(row[0])]
                    except Exception:
                        detected_ws = [urllib.parse.unquote(row[0])]
            except Exception:
                pass
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    # 3. Fallback: inspect tool calls in transcript for Cwd
    if not detected_ws and transcript_path.exists():
        try:
            with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if '"Cwd"' in line:
                        step = json.loads(line)
                        for tc in step.get("tool_calls", []):
                            tc_args = tc.get("args") or {}
                            cwd = tc_args.get("Cwd") if isinstance(tc_args, dict) else None
                            if cwd:
                                detected_ws = [cwd]
                                break
                    if detected_ws:
                        break
        except Exception:
            pass

    if not detected_ws:
        if transcript_path.exists():
            boundary_token = "/" + filter_str.strip("/")
            try:
                with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
                    for _ in range(60):
                        line = f.readline()
                        if not line:
                            break
                        if boundary_token in line or urllib.parse.quote(boundary_token) in line:
                            return True, "transcript_content_match"
            except Exception:
                pass
        return False, "None"

    filter_norm = filter_str.replace("file://", "").rstrip("/")
    for ws in detected_ws:
        ws_unquoted = urllib.parse.unquote(ws).replace("file://", "").strip('"').rstrip("/")
        if "/" in filter_norm:
            if ws_unquoted == filter_norm or ws_unquoted.startswith(filter_norm + "/"):
                return True, str(detected_ws)
        else:
            if Path(ws_unquoted).name == filter_norm:
                return True, str(detected_ws)

    return False, str(detected_ws)

def is_subagent_conversation(root_dir: Path, conv_id: str, transcript_path: Path) -> bool:
    """Detects whether this conversation was spawned as a subagent."""
    # Check messages directory for parent message from root agent
    msg_dir = transcript_path.parent.parent / "messages"
    if msg_dir.exists():
        for mfile in msg_dir.glob("*.json"):
            try:
                mdata = json.loads(mfile.read_text(encoding="utf-8", errors="ignore"))
                if mdata.get("renderDetails", {}).get("messageTitle") == "Message from Root Agent":
                    return True
                if mdata.get("role") == "system" and "subagent" in mdata.get("content", "").lower():
                    return True
            except Exception:
                pass

    # Check conversation_summaries.db for parent_conversation_id or nesting_depth
    sum_db = root_dir / "conversation_summaries.db"
    if sum_db.exists():
        conn = None
        try:
            conn = sqlite3.connect(f"file:{sum_db}?mode=ro", uri=True)
            c = conn.cursor()
            c.execute("PRAGMA table_info(conversation_summaries)")
            cols = {r[1] for r in c.fetchall()}
            select_cols = []
            if "parent_conversation_id" in cols:
                select_cols.append("parent_conversation_id")
            if "nesting_depth" in cols:
                select_cols.append("nesting_depth")
            elif "depth" in cols:
                select_cols.append("depth")

            if select_cols:
                query = f"SELECT {', '.join(select_cols)} FROM conversation_summaries WHERE conversation_id = ?"
                c.execute(query, (conv_id,))
                row = c.fetchone()
                if row:
                    for val in row:
                        if isinstance(val, str) and val.strip():
                            return True
                        if isinstance(val, (int, float)) and val > 0:
                            return True
        except Exception:
            pass
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    return False

def clean_user_prompt(raw_content: str) -> str:
    """Extract clean user request text, stripping framework metadata tags."""
    if not raw_content:
        return ""
    m = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", raw_content, re.DOTALL)
    if m:
        return m.group(1).strip()
    content = re.sub(r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", raw_content, flags=re.DOTALL)
    content = re.sub(r"<USER_SETTINGS_CHANGE>.*?</USER_SETTINGS_CHANGE>", "", content, flags=re.DOTALL)
    return content.strip()

def summarize_tool_call(tc: dict) -> str:
    """Creates a concise 1-line representation of a tool call."""
    if not isinstance(tc, dict):
        return "Tool action"
    tool_name = tc.get("toolAction") or tc.get("toolSummary") or tc.get("name") or "Tool action"
    args = tc.get("args") or {}
    if not isinstance(args, dict):
        return str(tool_name)
    try:
        if "CommandLine" in args and isinstance(args["CommandLine"], str):
            cmd = args["CommandLine"].strip().replace("\n", " ")
            if len(cmd) > 100:
                cmd = cmd[:97] + "..."
            return f"{tool_name}: `{cmd}`"
        if "TargetFile" in args and isinstance(args["TargetFile"], str):
            return f"{tool_name}: {Path(args['TargetFile']).name}"
        if "AbsolutePath" in args and isinstance(args["AbsolutePath"], str):
            return f"{tool_name}: {Path(args['AbsolutePath']).name}"
    except Exception:
        pass
    return str(tool_name)

def parse_transcript(transcript_path: Path, start_step_index: int = -1) -> dict:
    """Parses transcript.jsonl into structured interaction turns, skipping turns up to start_step_index."""
    turns = []
    current_turn = None
    first_timestamp = None
    last_timestamp = None
    tool_calls_total = 0
    max_step_index = max(0, start_step_index)

    # Guard against compactor or step index resets
    effective_start_step = start_step_index
    if effective_start_step > 0:
        highest_in_file = -1
        try:
            with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        step_peek = json.loads(line)
                        idx_peek = step_peek.get("step_index")
                        if idx_peek is not None and idx_peek > highest_in_file:
                            highest_in_file = idx_peek
                    except Exception:
                        continue
            if highest_in_file >= 0 and highest_in_file < effective_start_step:
                # File was compacted or reset below cursor; reset cursor to start from beginning
                effective_start_step = -1
        except Exception:
            pass

    with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                step = json.loads(line)
            except Exception:
                continue

            step_idx = step.get("step_index", 0)
            if step_idx is not None and step_idx > max_step_index:
                max_step_index = step_idx

            created_at = step.get("created_at") or step.get("timestamp")
            if created_at:
                if not first_timestamp:
                    first_timestamp = created_at
                last_timestamp = created_at

            step_type = step.get("type")
            source = step.get("source")

            if step_type == "USER_INPUT" and source == "USER_EXPLICIT":
                if current_turn and current_turn.get("max_step", 0) > effective_start_step:
                    turns.append(current_turn)
                prompt_text = clean_user_prompt(step.get("content", ""))
                current_turn = {
                    "turn_index": len(turns) + 1,
                    "step_index": step_idx if step_idx is not None else 0,
                    "max_step": step_idx if step_idx is not None else 0,
                    "timestamp": created_at,
                    "user_prompt": prompt_text,
                    "tools_used": [],
                    "assistant_response": ""
                }
            elif current_turn:
                if step_idx is not None:
                    current_turn["max_step"] = max(current_turn.get("max_step", 0), step_idx)
                if "tool_calls" in step and isinstance(step["tool_calls"], list):
                    for tc in step["tool_calls"]:
                        tool_calls_total += 1
                        current_turn["tools_used"].append(summarize_tool_call(tc))
                if source == "MODEL" and step_type == "PLANNER_RESPONSE":
                    raw_content = step.get("content")
                    if isinstance(raw_content, str):
                        resp = raw_content.strip()
                        if resp:
                            current_turn["assistant_response"] = resp

    if current_turn and current_turn.get("max_step", 0) > effective_start_step:
        turns.append(current_turn)

    return {
        "start_time": first_timestamp,
        "end_time": last_timestamp,
        "max_step_index": max_step_index,
        "turns_count": len(turns),
        "tool_calls_count": sum(len(t.get("tools_used", [])) for t in turns),
        "turns": turns
    }

def get_target_date_set(anchor_date_str: str, days_count: int) -> set[str]:
    """Generates set of YYYY-MM-DD date strings for the requested window."""
    anchor = datetime.strptime(anchor_date_str, "%Y-%m-%d")
    dates = set()
    for d in range(days_count):
        target = anchor - timedelta(days=d)
        dates.add(target.strftime("%Y-%m-%d"))
    return dates

def print_status(workspace_filter: str = DEFAULT_WORKSPACE):
    state = load_sync_state()
    routines = state.get("routines", {})
    print("=== Antigravity Conversation Sync & Routine Watermark Status ===")
    print(f"Sync State File: {SYNC_STATE_PATH}")
    print(f"Global Last Run: {state.get('last_run')} (Routine: {state.get('last_routine')})")
    print(f"Legacy Tracked Conversations: {len(state.get('conversations', {}))}")
    print()

    if not routines:
        print("No routine-specific partitions recorded yet.")
    for r_name, r_info in routines.items():
        print(f"Routine: [{r_name}]")
        print(f"  Last Run: {r_info.get('last_run') or 'Never'}")
        print(f"  Tracked Conversations: {len(r_info.get('conversations', {}))}")
        history = r_info.get("history", [])
        if history:
            print(f"  Total Runs Recorded: {len(history)}")
            last_entry = history[-1]
            print(f"  Most Recent Run: {last_entry.get('timestamp')} ({last_entry.get('harvested_count')} conversations gathered)")
            convs = last_entry.get("conversation_ids", [])
            if convs:
                preview = ", ".join(c[:8] for c in convs[:5])
                if len(convs) > 5:
                    preview += f", ... (+{len(convs)-5} more)"
                print(f"  Gathered IDs: {preview}")
        print()

def harvest_window(anchor_date: str = None, days_count: int = 1, workspace_filter: str = DEFAULT_WORKSPACE,
                   include_subagents: bool = False, use_cursor: bool = False,
                   update_cursor: bool = False, routine_name: str = "default",
                   catch_up: bool = False, strict_dates: bool = False,
                   verbose: bool = False) -> list[dict]:
    """Scans and extracts all eligible conversations with routine-isolated cursor and archive support."""
    if check_sandbox_masking():
        print("[WARNING] Agent sandbox isolation is masking ~/.gemini/antigravity (only current session visible).")
        print("[WARNING] For full access across all host conversations, run this command with BypassSandbox: true or from host terminal.\n")

    target_dates = None
    if strict_dates or (not catch_up and not use_cursor):
        anchor_date_str = anchor_date or datetime.now().strftime("%Y-%m-%d")
        target_dates = get_target_date_set(anchor_date_str, days_count)

    results = []
    sync_state = load_sync_state() if (use_cursor or update_cursor) else None
    routine_state = get_routine_state(sync_state, routine_name) if sync_state else None

    for root in ANTIGRAVITY_ROOTS:
        brain_dir = root / "brain"
        if not brain_dir.exists():
            continue
        instance_name = root.name

        for conv_dir in brain_dir.iterdir():
            if not conv_dir.is_dir():
                continue
            conv_id = conv_dir.name
            transcript_path = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
            if not transcript_path.exists():
                continue

            mtime_epoch = transcript_path.stat().st_mtime
            mtime = datetime.fromtimestamp(mtime_epoch)
            mtime_str = mtime.strftime("%Y-%m-%d")

            is_archived = check_is_archived(root, conv_id)

            if target_dates is not None and mtime_str not in target_dates:
                continue

            start_step = -1
            if use_cursor and routine_state:
                conv_cursor = routine_state.get("conversations", {}).get(conv_id)
                if conv_cursor:
                    last_mtime = conv_cursor.get("last_mtime", 0)
                    last_step = conv_cursor.get("last_step_index", -1)
                    if mtime_epoch <= last_mtime and last_step >= 0:
                        if verbose:
                            print(f"Skipping {conv_id}: unchanged since cursor ({last_step} steps)")
                        continue
                    start_step = last_step

            matches, detected_ws = check_workspace_match(root, conv_id, transcript_path, workspace_filter)
            if not matches:
                if verbose:
                    print(f"Skipping {conv_id} ({instance_name}): external workspace ({detected_ws})")
                continue

            if not include_subagents and is_subagent_conversation(root, conv_id, transcript_path):
                if verbose:
                    print(f"Skipping {conv_id} ({instance_name}): subagent conversation")
                continue

            parsed = parse_transcript(transcript_path, start_step_index=start_step)
            if parsed["turns_count"] == 0:
                continue

            record = {
                "conversation_id": conv_id,
                "instance": instance_name,
                "mtime_epoch": mtime_epoch,
                "mtime_date": mtime_str,
                "is_archived": is_archived,
                "detected_workspace": detected_ws,
                "start_time": parsed["start_time"],
                "end_time": parsed["end_time"],
                "max_step_index": parsed["max_step_index"],
                "start_step_index": start_step,
                "is_differential": (start_step >= 0),
                "turns_count": parsed["turns_count"],
                "tool_calls_count": parsed["tool_calls_count"],
                "turns": parsed["turns"]
            }
            results.append(record)

    results.sort(key=lambda x: x["start_time"] or "")

    if update_cursor:
        if not sync_state:
            sync_state = load_sync_state()
        if not routine_state:
            routine_state = get_routine_state(sync_state, routine_name)

        now_iso = datetime.now().isoformat()
        routine_state["last_run"] = now_iso
        routine_state["harvested_count"] = len(results)
        routine_state.setdefault("history", []).append({
            "timestamp": now_iso,
            "harvested_count": len(results),
            "conversation_ids": [r["conversation_id"] for r in results]
        })

        for res in results:
            cid = res["conversation_id"]
            cursor_entry = {
                "last_mtime": res["mtime_epoch"],
                "last_step_index": res["max_step_index"],
                "last_processed_date": now_iso,
                "total_new_turns": res["turns_count"],
                "is_archived": res["is_archived"]
            }
            routine_state.setdefault("conversations", {})[cid] = cursor_entry
            sync_state.setdefault("conversations", {})[cid] = cursor_entry

        sync_state["last_run"] = now_iso
        sync_state["last_routine"] = routine_name
        save_sync_state(sync_state)

    return results

def main():
    args = parse_args()

    if args.status:
        print_status(args.workspace)
        return

    routine = args.routine
    mode_desc = "CATCH-UP (all pending unharvested turns)" if args.catch_up else ("CURSOR WATERMARK" if args.cursor else f"{args.days} day(s) ending {args.date}")
    if args.verbose:
        print(f"Harvesting window: {mode_desc} | Routine: '{routine}' | Workspace: '{args.workspace}'")

    harvested = harvest_window(
        anchor_date=args.date,
        days_count=args.days,
        workspace_filter=args.workspace,
        include_subagents=args.include_subagents,
        use_cursor=args.cursor,
        update_cursor=args.update_cursor,
        routine_name=routine,
        catch_up=args.catch_up,
        strict_dates=args.strict_dates,
        verbose=args.verbose
    )

    if args.output:
        out_p = Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(harvested, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(harvested)} conversations to {out_p}")

    if args.summary or not args.output:
        print(f"\n=== Harvested Conversations Summary ({mode_desc}) ===")
        print(f"Workspace Filter: {args.workspace or 'ALL'}")
        print(f"Routine Partition: {routine}")
        print(f"Include Subagents: {args.include_subagents}")
        print(f"Cursor Active: {args.cursor} | Updated: {args.update_cursor}")
        print(f"Total Eligible Sessions: {len(harvested)}\n")

        for idx, conv in enumerate(harvested, 1):
            diff_label = f" [DIFFERENTIAL from step {conv['start_step_index']}]" if conv['is_differential'] else ""
            arch_label = " [ARCHIVED]" if conv.get("is_archived") else " [ACTIVE]"
            print(f"{idx}. [{conv['instance']}]{arch_label} ID: {conv['conversation_id']} ({conv['mtime_date']}){diff_label}")
            print(f"   Time Window: {conv['start_time']} -> {conv['end_time']}")
            print(f"   New Turns: {conv['turns_count']} | Tool Actions: {conv['tool_calls_count']} | Max Step: {conv['max_step_index']}")
            print("   Turns Breakdown:")
            for turn in conv["turns"]:
                preview = turn["user_prompt"][:100].replace("\n", " ")
                tools_summary = f"{len(turn['tools_used'])} tool actions" if turn["tools_used"] else "No tools"
                print(f"     Turn {turn['turn_index']} (Step {turn.get('step_index')}): \"{preview}\" ({tools_summary})")
            print()

if __name__ == "__main__":
    main()
