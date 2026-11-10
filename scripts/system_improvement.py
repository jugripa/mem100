#!/usr/bin/env python3
"""
system_improvement.py
Weekly meta-improvement and cross-age memory consolidation audit script (JSONL-Native).

Responsibilities:
  1. Harvests multi-day conversation transcripts via routine-isolated differential cursors.
  2. Audits user friction points, corrections, and context discovery gaps.
  3. Audits the unified two-tier memory store (memory/short-term.jsonl and memory/long-term.jsonl)
     across ALL ages without redundant Jev API loops:
       - Detects cross-age overlap clusters (short-term + long-term) for joining (`manage_memory.py merge`).
       - Detects older memories touched by this week's sessions for enrichment (`manage_memory.py update`).
       - Identifies durable high-importance working memories for core graduation (`manage_memory.py graduate`).
       - Identifies stale/resolved short-term items for archival (`manage_memory.py archive`).
       - Audits the core memory token footprint so Turn-1 startup context stays lean.

Usage:
  python3 scripts/system_improvement.py [--days 7] [--date YYYY-MM-DD] [--workspace PATH_OR_NAME]
                                        [--catch-up] [--status] [--dry-run] [--output REPORT_MD]
"""
import os
import sys
import json
import re
import argparse
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.harvest_conversations import (
    harvest_window,
    DEFAULT_WORKSPACE,
    load_sync_state,
    save_sync_state,
    get_routine_state
)
from scripts.manage_memory import (
    read_jsonl,
    SHORT_TERM_PATH,
    LONG_TERM_PATH,
    AUDIT_DIR,
    RAW_AUDIT_LOG,
    compute_recency_score,
    tokenize
)

CORRECTION_TRIGGERS = [
    r"\bno,\s+", r"\bthat's wrong\b", r"\bthats wrong\b", r"\bdon't\b", r"\bdont\b",
    r"\byou didn't\b", r"\byou didnt\b", r"\bnot at all\b", r"\bthat's not\b", r"\bthats not\b",
    r"\bi'm getting confused\b", r"\bstop\b(?!\s*[-_]?\s*timer)", r"\binstead\b", r"\bwrong\b", r"\bnot what i\b",
    r"\bplease don't\b", r"\byou misunderstood\b"
]

FALSE_POSITIVE_TRIGGERS = [
    r"\bno problem\b", r"\bno worries\b", r"\bno rush\b", r"\bno blocker\b", r"\bno issues?\b", r"\bno pressure\b"
]

CONTEXT_GAP_TRIGGERS = [
    r"\bwhere is\b", r"\bdid you check\b", r"\blook in\b", r"\bin repo\b",
    r"\bin the spec\b", r"\bcheck my conversation\b", r"\brecover\b",
    r"\bfind (?:it|for it)\b", r"\byou missed\b", r"\byou forgot\b",
    r"\bthat's not where\b", r"\bthats not where\b", r"\byou didn't read\b",
    r"\byou didnt read\b", r"\bsearch for\b"
]


def parse_args():
    parser = argparse.ArgumentParser(description="Weekly System Improvement & Cross-Age Memory Consolidation Audit.")
    parser.add_argument("--days", type=int, default=None,
                        help="Number of days to audit. If omitted, dynamically audits all unharvested sessions since last run.")
    parser.add_argument("--date", type=str, default=datetime.now().strftime("%Y-%m-%d"),
                        help="Anchor date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--workspace", type=str, default=DEFAULT_WORKSPACE,
                        help="Workspace filter substring.")
    parser.add_argument("--catch-up", "--all-pending", action="store_true", dest="catch_up",
                        help="Audit all unharvested turns across all historical sessions.")
    parser.add_argument("--status", action="store_true",
                        help="Show when system improvement last ran, conversations gathered, and pending audit count.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Analyze without updating cursors.")
    parser.add_argument("--output", type=str, default=None,
                        help="Output path for the generated markdown report.")
    return parser.parse_args()


def audit_friction_and_corrections(harvested_sessions: list[dict]) -> list[dict]:
    """Finds turns where the user redirected or corrected the assistant."""
    corrections = []
    pattern = re.compile("|".join(CORRECTION_TRIGGERS), re.IGNORECASE)
    fp_pattern = re.compile("|".join(FALSE_POSITIVE_TRIGGERS), re.IGNORECASE)

    for session in harvested_sessions:
        conv_id = session["conversation_id"]
        for turn in session.get("turns", []):
            prompt = turn.get("user_prompt", "")
            if pattern.search(prompt):
                if fp_pattern.search(prompt) and len(prompt.split()) <= 6:
                    continue
                corrections.append({
                    "conversation_id": conv_id,
                    "date": session.get("mtime_date", ""),
                    "turn_index": turn.get("turn_index"),
                    "user_prompt": prompt,
                    "tools_used": turn.get("tools_used", []),
                    "preview": prompt[:160].replace("\n", " ")
                })
    return corrections


def audit_workflow_patterns(harvested_sessions: list[dict]) -> dict:
    """Analyzes frequently repeated tool operations and user intent patterns."""
    skill_mentions = {}
    tool_frequencies = {}

    for session in harvested_sessions:
        for turn in session.get("turns", []):
            prompt = turn.get("user_prompt", "")
            for word in prompt.split():
                clean_token = word.strip(",.:;\"'")
                if re.match(r"^/[a-z][a-z0-9_-]*$", clean_token, re.IGNORECASE) or "skill" in clean_token.lower():
                    clean_word = clean_token.strip("/")
                    if clean_word:
                        skill_mentions[clean_word] = skill_mentions.get(clean_word, 0) + 1
            for tool_call in turn.get("tools_used", []):
                tool_name = tool_call.split(":")[0].strip()
                tool_frequencies[tool_name] = tool_frequencies.get(tool_name, 0) + 1

    return {
        "frequent_tools": sorted(tool_frequencies.items(), key=lambda x: x[1], reverse=True)[:10],
        "skill_invocations": sorted(skill_mentions.items(), key=lambda x: x[1], reverse=True)[:10]
    }


def audit_context_discovery_effectiveness(harvested_sessions: list[dict], corrections: list[dict]) -> dict:
    """Evaluates whether user corrections indicate context discovery failures."""
    gap_pattern = re.compile("|".join(CONTEXT_GAP_TRIGGERS), re.IGNORECASE)
    discovery_gaps = []

    for c in corrections:
        prompt = c.get("user_prompt", "")
        if gap_pattern.search(prompt):
            p_lower = prompt.lower()
            if any(k in p_lower for k in ["repo", "architecture", "code", "file", "outline", "route", "service"]):
                gap_type = "repository_code_architecture"
            elif any(k in p_lower for k in ["spec", "prd", "story", "epic", "design", "doc"]):
                gap_type = "specifications_vault"
            elif any(k in p_lower for k in ["history", "session", "recover", "earlier", "previous", "transcript", "memory"]):
                gap_type = "session_history_memory"
            elif any(k in p_lower for k in ["team", "who is", "developer", "stakeholder", "engineer", "lead", "owner"]):
                gap_type = "team_stakeholder_context"
            elif any(k in p_lower for k in ["rule", "guideline", "standard"]):
                gap_type = "governance_rules"
            else:
                gap_type = "general_context_lookup"

            discovery_gaps.append({
                "date": c.get("date"),
                "conv_id": c.get("conversation_id", "")[:8],
                "turn": c.get("turn_index"),
                "gap_type": gap_type,
                "preview": c.get("preview", "")
            })

    agents_path = BASE_DIR / "AGENTS.md"
    indexed_sections = []
    if agents_path.exists():
        content = agents_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("## ") or line.startswith("### "):
                indexed_sections.append(line.strip("# ").strip())

    gaps_by_type = {}
    for g in discovery_gaps:
        gt = g["gap_type"]
        gaps_by_type[gt] = gaps_by_type.get(gt, 0) + 1

    return {
        "total_gaps_detected": len(discovery_gaps),
        "gaps_by_type": gaps_by_type,
        "sample_gaps": discovery_gaps[:6],
        "indexed_sections_in_agents_md": indexed_sections
    }


def audit_ingestion_ledger(days: int = 7) -> dict:
    """Inspects recent events from memory/audit/raw_events.jsonl within the window."""
    if not RAW_AUDIT_LOG.exists():
        return {"total_events": 0, "accepted": 0, "merged": 0, "updated": 0, "graduated": 0, "archived": 0}

    all_events = read_jsonl(RAW_AUDIT_LOG)
    cutoff = datetime.now() - timedelta(days=days)
    events = []
    for e in all_events:
        ts_str = e.get("timestamp")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is not None:
                    if ts >= cutoff.astimezone(ts.tzinfo):
                        events.append(e)
                else:
                    if ts >= cutoff:
                        events.append(e)
            except Exception:
                events.append(e)
        else:
            events.append(e)

    counts = {
        "total_events": len(events),
        "accepted": sum(1 for e in events if str(e.get("status", "")).startswith("ACCEPTED")),
        "merged": sum(1 for e in events if e.get("status") == "MERGED"),
        "updated": sum(1 for e in events if e.get("status") == "UPDATED"),
        "graduated": sum(1 for e in events if e.get("status") == "GRADUATED"),
        "archived": sum(1 for e in events if e.get("status") == "ARCHIVED"),
    }
    return counts


def audit_memory_consolidation(harvested_sessions: list[dict]) -> dict:
    """
    Audits both short-term.jsonl and long-term.jsonl across all ages without redundant Jev calls.
    Identifies:
      1. Cross-age overlap pairs (short-term + long-term) that should be joined via `manage_memory.py merge`.
      2. Existing memories (recent or older) touched by this week's sessions that should be enriched via `manage_memory.py update`.
      3. High-importance/multi-pointer short-term records eligible for graduation to long-term.jsonl.
      4. Stale short-term records (>30 days without update and untouched this week) eligible for archival.
    """
    short_active = [r for r in read_jsonl(SHORT_TERM_PATH) if r.get("status") == "active"]
    long_active = [r for r in read_jsonl(LONG_TERM_PATH) if r.get("status") in ("active", "graduated")]

    all_active = []
    for r in long_active:
        rc = dict(r)
        rc["tier"] = "long-term"
        all_active.append(rc)
    for r in short_active:
        rc = dict(r)
        rc["tier"] = "short-term"
        all_active.append(rc)

    # Estimate token footprint of active long-term core memory
    long_chars = sum(len(r.get("title", "")) + len(r.get("summary", "")) + 60 for r in long_active)
    est_long_tokens = int(long_chars / 3.8)

    # Extract tokens & entities from harvested sessions
    weekly_text_parts = []
    for s in harvested_sessions:
        for t in s.get("turns", []):
            weekly_text_parts.append(t.get("user_prompt", ""))
            weekly_text_parts.append(t.get("assistant_response", "")[:400])
    weekly_text = "\n".join(weekly_text_parts)
    weekly_tokens = set(tokenize(weekly_text))

    # 1. Detect Cross-Age Overlap Pairs (across both short-term and long-term)
    merge_candidates = []
    rec_tokens = {}
    rec_entities = {}
    for r in all_active:
        mid = r.get("id")
        toks = set(tokenize(f"{r.get('title', '')} {r.get('summary', '')}"))
        rec_tokens[mid] = toks
        stop_ents = {s.strip().lower() for s in os.environ.get("MEMORY_STOP_ENTITIES", "").split(",") if s.strip()}
        ents = {str(e).lower() for e in r.get("entities", []) if str(e).lower() not in stop_ents}
        rec_entities[mid] = ents

    for i in range(len(all_active)):
        for j in range(i + 1, len(all_active)):
            r1 = all_active[i]
            r2 = all_active[j]
            id1, id2 = r1.get("id"), r2.get("id")
            t1, t2 = rec_tokens[id1], rec_tokens[id2]
            if not t1 or not t2:
                continue
            jaccard = len(t1 & t2) / max(1, len(t1 | t2))
            shared_ents = rec_entities[id1] & rec_entities[id2]
            ticket_prefixes = ("tsk-", "task-", "pr-", "gh-", "jira-", "issue-", "lin-", "cu-", "hs-")
            shared_cu = [e for e in shared_ents if e.startswith(ticket_prefixes)]
            if jaccard >= 0.28 or shared_cu or (len(shared_ents) >= 2 and jaccard >= 0.16):
                merge_candidates.append({
                    "id_a": id1,
                    "tier_a": r1.get("tier"),
                    "title_a": r1.get("title"),
                    "id_b": id2,
                    "tier_b": r2.get("tier"),
                    "title_b": r2.get("title"),
                    "similarity": round(jaccard, 2),
                    "shared_entities": sorted(shared_ents)
                })
    merge_candidates.sort(key=lambda x: (len(x["shared_entities"]), x["similarity"]), reverse=True)

    # 2. Detect Older & Existing Memories Touched by This Week's Sessions
    update_candidates = []
    if weekly_tokens:
        for r in all_active:
            mid = r.get("id")
            t_set = rec_tokens[mid]
            overlap = t_set & weekly_tokens
            coverage = len(overlap) / max(1, len(t_set))
            ents = rec_entities[mid]
            matched_ents = [e for e in ents if e in weekly_text.lower()]
            if matched_ents or coverage >= 0.45:
                update_candidates.append({
                    "id": mid,
                    "tier": r.get("tier"),
                    "title": r.get("title"),
                    "updated_at": str(r.get("updated_at") or r.get("created_at") or "")[:10],
                    "matched_entities": matched_ents,
                    "token_coverage": round(coverage, 2)
                })
    update_candidates.sort(key=lambda x: (len(x["matched_entities"]), x["token_coverage"]), reverse=True)

    # 3. Graduation & 4. Pruning Candidates in Short-Term Memory
    graduation_candidates = []
    prune_candidates = []
    for r in short_active:
        mid = r.get("id")
        imp = float(r.get("importance", 0.75) or 0.75)
        rec = compute_recency_score(r)
        ptrs = r.get("pointers", [])
        open_loops = r.get("atoms", {}).get("open_loops", []) if isinstance(r.get("atoms"), dict) else []
        # Durable rules/decisions without unresolved transient open loops
        if (imp >= 0.88 or (imp >= 0.85 and len(ptrs) >= 2)) and not open_loops:
            graduation_candidates.append({
                "id": mid,
                "title": r.get("title"),
                "importance": imp,
                "pointers_count": len(ptrs),
                "summary": r.get("summary")
            })
        elif rec < 0.35 and imp < 0.85 and not any(u["id"] == mid for u in update_candidates):
            prune_candidates.append({
                "id": mid,
                "title": r.get("title"),
                "recency": rec,
                "updated_at": str(r.get("updated_at") or r.get("created_at") or "")[:10],
                "summary": r.get("summary")
            })

    return {
        "long_term_count": len(long_active),
        "short_term_count": len(short_active),
        "est_long_term_tokens": est_long_tokens,
        "merge_candidates": merge_candidates[:10],
        "update_candidates": update_candidates[:12],
        "graduation_candidates": graduation_candidates[:10],
        "prune_candidates": prune_candidates[:10]
    }


def print_system_improvement_status(workspace: str):
    state = load_sync_state()
    routine_info = get_routine_state(state, "system-improvement")
    last_run = routine_info.get("last_run")
    tracked = routine_info.get("conversations", {})
    history = routine_info.get("history", [])

    print("=== System Improvement Audit Status & Log ===")
    print(f"Last Run: {last_run or 'Never'}")
    print(f"Tracked Conversations: {len(tracked)}")
    print(f"Audit Runs Recorded: {len(history)}")
    print()
    if history:
        print("--- Past Audit Runs History ---")
        for idx, h in enumerate(reversed(history[-5:]), 1):
            ts = h.get("timestamp", "Unknown")
            c_cnt = h.get("harvested_count", 0)
            f_cnt = h.get("friction_events_count", 0)
            rep = h.get("report_path", "N/A")
            print(f"{idx}. [{ts}] Harvested: {c_cnt} sessions | Friction Events: {f_cnt} | Report: {rep}")
        print()

    print("Checking pending un-audited conversations...")
    pending = harvest_window(
        workspace_filter=workspace,
        use_cursor=True,
        update_cursor=False,
        routine_name="system-improvement",
        catch_up=True
    )
    print(f"Total Pending Sessions Awaiting Audit: {len(pending)}")


def generate_report(args, sessions, corrections, patterns, mem_audit, ledger_audit, context_discovery: dict = None, mode_desc: str = "") -> str:
    """Formats the weekly system improvement & cross-age memory consolidation report in clean Markdown."""
    lines = [
        "# Weekly System Improvement & Memory Consolidation Audit",
        "",
        f"**Audit Mode:** `{mode_desc}`  ",
        f"**Audit Date:** `{args.date}`  ",
        f"**Harvested Sessions:** {len(sessions)}  ",
        f"**User Friction / Correction Events:** {len(corrections)}  ",
        f"**Memory Store Footprint:** {mem_audit['long_term_count']} Long-Term Core (~{mem_audit['est_long_term_tokens']} tokens) | {mem_audit['short_term_count']} Short-Term Working  ",
        f"**Audit Ledger Operations:** {ledger_audit.get('total_events', 0)} ({ledger_audit.get('accepted', 0)} ingested, {ledger_audit.get('merged', 0)} merged, {ledger_audit.get('updated', 0)} updated, {ledger_audit.get('graduated', 0)} graduated, {ledger_audit.get('archived', 0)} archived)",
        "",
        "---",
        "",
        "## Harvested Sessions in this Audit Round",
        ""
    ]

    if not sessions:
        lines.append("_No new sessions harvested in this audit round._\n")
    else:
        for idx, s in enumerate(sessions, 1):
            arch = " `[ARCHIVED]`" if s.get("is_archived") else " `[ACTIVE]`"
            diff = f" (differential from step {s['start_step_index']})" if s.get("is_differential") else ""
            lines.append(f"- **{idx}. Session `{s['conversation_id'][:8]}`**{arch} ({s.get('mtime_date')}): {s.get('turns_count')} turns, {s.get('tool_calls_count')} tools{diff}")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 1. User Corrections & Friction Points",
        ""
    ])

    if not corrections:
        lines.append("_No critical user friction or correction triggers detected in this harvest window._\n")
    else:
        for c in corrections[:10]:
            lines.append(f"- **[{c['date']}] Session `{c['conversation_id'][:8]}` (Turn {c['turn_index']}):**")
            lines.append(f"  > \"{c['preview']}\"")
            if c["tools_used"]:
                lines.append(f"  _Tools active:_ {', '.join(c['tools_used'][:2])}")
            lines.append("")

    lines.extend([
        "---",
        "",
        "## 2. Cross-Age Memory Consolidation & Lifecycle Brief",
        "",
        f"- **Active Long-Term Core Memories:** {mem_audit['long_term_count']} (~{mem_audit['est_long_term_tokens']} tokens loaded at session start)",
        f"- **Active Short-Term Working Memories:** {mem_audit['short_term_count']}",
        f"- **Cross-Age Overlap / Merge Candidates:** {len(mem_audit['merge_candidates'])}",
        f"- **Existing/Older Memories Touched This Week (Update Candidates):** {len(mem_audit['update_candidates'])}",
        f"- **Core Graduation Candidates:** {len(mem_audit['graduation_candidates'])}",
        f"- **Stale / Decayed Pruning Candidates:** {len(mem_audit['prune_candidates'])}",
        ""
    ])

    if mem_audit["merge_candidates"]:
        lines.append("### A. Cross-Age Overlap Pairs (`manage_memory.py merge`):")
        for mc in mem_audit["merge_candidates"]:
            ents = ", ".join(mc["shared_entities"]) if mc["shared_entities"] else "lexical overlap"
            lines.append(
                f"- `[{mc['id_a']}]` ({mc['tier_a']}) **{mc['title_a']}** <-> "
                f"`[{mc['id_b']}]` ({mc['tier_b']}) **{mc['title_b']}** "
                f"(Sim: {mc['similarity']:.2f} | Shared: {ents})"
            )
        lines.append("")

    if mem_audit["update_candidates"]:
        lines.append("### B. Existing & Older Memories Touched by This Week's Activity (`manage_memory.py update`):")
        for uc in mem_audit["update_candidates"]:
            ents = ", ".join(uc["matched_entities"]) if uc["matched_entities"] else f"coverage {uc['token_coverage']:.2f}"
            lines.append(f"- `[{uc['id']}]` ({uc['tier']}, last updated {uc['updated_at']}) **{uc['title']}** (Matched: {ents})")
        lines.append("")

    if mem_audit["graduation_candidates"]:
        lines.append("### C. Core Graduation Candidates (`manage_memory.py graduate`):")
        for gc in mem_audit["graduation_candidates"]:
            lines.append(f"- `[{gc['id']}]` **{gc['title']}** (Importance: {gc['importance']:.2f}, Pointers: {gc['pointers_count']})")
        lines.append("")

    if mem_audit["prune_candidates"]:
        lines.append("### D. Stale / Decayed Pruning Candidates (`manage_memory.py archive`):")
        for pc in mem_audit["prune_candidates"]:
            lines.append(f"- `[{pc['id']}]` **{pc['title']}** (Recency: {pc['recency']:.2f}, Updated: {pc['updated_at']})")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 3. Workflow Patterns & Tool Frequency",
        ""
    ])

    frequent_tools = patterns.get("frequent_tools", [])
    if frequent_tools:
        lines.append("### Top Active Tools & Operations:")
        for t_name, count in frequent_tools:
            lines.append(f"- **`{t_name}`**: {count} operation(s)")
        lines.append("")
    else:
        lines.append("No tool activity recorded in the harvest window.\n")

    skill_invocations = patterns.get("skill_invocations", [])
    if skill_invocations:
        lines.append("### Detected Skills & Command Keywords:")
        for s_name, count in skill_invocations:
            lines.append(f"- **`{s_name}`**: {count} invocation(s)")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 4. Context Discovery & Indexer Effectiveness",
        ""
    ])

    if not context_discovery or context_discovery.get("total_gaps_detected", 0) == 0:
        lines.append("No context discovery failures detected in this harvest window.\n")
    else:
        lines.append(f"- **Context Discovery Gaps Detected:** {context_discovery['total_gaps_detected']}")
        for gt, count in sorted(context_discovery.get("gaps_by_type", {}).items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  - `{gt}`: {count} incident(s)")
        lines.append("")
        lines.append("### Key Context Discovery Gaps Identified:")
        for sg in context_discovery.get("sample_gaps", []):
            lines.append(f"- **[{sg['date']}] Session `{sg['conv_id']}` (Turn {sg['turn']}) - `{sg['gap_type']}`:**")
            lines.append(f"  > \"{sg['preview']}\"\n")
        lines.append("")

    return "\n".join(lines)


def main():
    args = parse_args()

    if args.status:
        print_system_improvement_status(args.workspace)
        return

    is_dynamic = (args.days is None)
    days_count = args.days if args.days is not None else 7
    mode_desc = "Catch-up across all unharvested turns" if args.catch_up else ("Dynamic (since last system-improvement run)" if is_dynamic else f"Fixed window ({days_count} days ending {args.date})")

    print(f"=== Running Weekly System Improvement & Memory Consolidation Audit ({mode_desc}) ===")
    sessions = harvest_window(
        anchor_date=args.date,
        days_count=days_count,
        workspace_filter=args.workspace,
        use_cursor=True,
        update_cursor=(not args.dry_run),
        routine_name="system-improvement",
        catch_up=args.catch_up or is_dynamic,
        strict_dates=(not is_dynamic and not args.catch_up)
    )
    print(f"Harvested {len(sessions)} eligible sessions.")

    corrections = audit_friction_and_corrections(sessions)
    patterns = audit_workflow_patterns(sessions)
    ledger_audit = audit_ingestion_ledger(days=(days_count if not args.catch_up else 30))
    context_discovery = audit_context_discovery_effectiveness(sessions, corrections)
    mem_audit = audit_memory_consolidation(sessions)

    report_content = generate_report(
        args, sessions, corrections, patterns, mem_audit, ledger_audit,
        context_discovery=context_discovery, mode_desc=mode_desc
    )

    if args.dry_run and not args.output:
        print("[DRY RUN] Report generated in memory. Skipping file write.")
    else:
        out_path = Path(args.output) if args.output else BASE_DIR / "sessions" / f"system-improvement-{args.date}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_content, encoding="utf-8")
        rel_str = out_path.relative_to(BASE_DIR) if out_path.is_relative_to(BASE_DIR) else out_path
        print(f"Audit report generated at: {rel_str}")

        if not args.dry_run:
            sync_state = load_sync_state()
            routine_state = get_routine_state(sync_state, "system-improvement")
            routine_state.setdefault("history", []).append({
                "timestamp": datetime.now().isoformat(),
                "report_path": str(rel_str),
                "harvested_count": len(sessions),
                "conversation_ids": [s["conversation_id"] for s in sessions],
                "turns_count": sum(s["turns_count"] for s in sessions),
                "friction_events_count": len(corrections),
                "context_gaps_count": context_discovery.get("total_gaps_detected", 0),
                "merge_candidates_count": len(mem_audit.get("merge_candidates", [])),
                "update_candidates_count": len(mem_audit.get("update_candidates", []))
            })
            save_sync_state(sync_state)


if __name__ == "__main__":
    main()
