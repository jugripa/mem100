#!/usr/bin/env python3
"""
manage_memory.py
Unified Two-Tier Harness Memory Manager for Autonomous AI Agents.

Architecture:
  - Unified stores (no dimension or facet silos):
      * memory/long-term.jsonl  (Core Memory: always loaded at conversation start)
      * memory/short-term.jsonl (Working Memory: queried on task/topic shifts)
      * memory/leaf-files/<id>.md (Rich Markdown context dossiers with pointers)
  - Enriched Record Schema:
      * Envelope: id, created_at, updated_at, tier, status, importance (0.0-1.0),
        pointers (conv:<id>, task:<id>, pr:<id>, etc.), entities, people
      * Distilled Search Surface: title, summary (3-part Pure Signal),
        questions (natural language retrieval triggers), atoms (decisions_and_why,
        open_loops, commands_or_refs)
  - Token-Mindful Execution:
      * Ingestion (dream-cycle): Direct LLM synthesis write (zero redundant Jev gatekeeping).
      * Retrieval (query): Single batched Jev API call (Choice across all active records
        weighted with Recency and Importance), with local Okapi BM25 + Recency + Importance
        fallback when Jev is offline.
      * Consolidation (system-improvement): First-class update, merge, graduate, and archive
        operations across both recent and older memories in short-term and long-term stores.

Usage:
  python3 scripts/manage_memory.py init
  python3 scripts/manage_memory.py context [--include-open-loops] [--json]
  python3 scripts/manage_memory.py query --task "..." [--tier {short-term,long-term,all}] [--threshold 0.55] [--offline] [--json]
  python3 scripts/manage_memory.py ingest --routine dream-cycle --title "..." --summary "..." [--importance 0.80] ...
  python3 scripts/manage_memory.py update --routine system-improvement --id <MEM_ID> [--summary "..."] ...
  python3 scripts/manage_memory.py merge --routine system-improvement --target-id <ID> --source-ids <ID1,ID2> ...
  python3 scripts/manage_memory.py graduate --routine system-improvement --id <MEM_ID>
  python3 scripts/manage_memory.py archive --routine system-improvement --id <MEM_ID> [--reason "..."]
  python3 scripts/manage_memory.py list [--tier {short-term,long-term,all}] [--status {active,archived,graduated,all}]
  python3 scripts/manage_memory.py audit [--limit 20]
"""
import os
import sys
import json
import math
import re
import uuid
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
MEMORY_DIR = BASE_DIR / "memory"
SHORT_TERM_PATH = MEMORY_DIR / "short-term.jsonl"
LONG_TERM_PATH = MEMORY_DIR / "long-term.jsonl"
LEAF_DIR = MEMORY_DIR / "leaf-files"
AUDIT_DIR = MEMORY_DIR / "audit"
RAW_AUDIT_LOG = AUDIT_DIR / "raw_events.jsonl"
API_URL = "https://api.typesafe.ai/v1/systemone"

STOP_WORDS = {
    "the", "a", "an", "in", "on", "of", "and", "or", "for", "with", "to", "at",
    "by", "from", "is", "are", "was", "were", "be", "been", "it", "this", "that",
    "as", "into", "about", "how", "what", "when", "where", "who", "why", "which",
    "should", "could", "would", "can", "will", "do", "does", "did", "have", "has",
    "had", "not", "no", "we", "our", "us", "you", "your"
}


class TypeSafeError(Exception):
    """Raised when TypeSafe API call fails or encounters an unhandled error."""
    pass


def load_dotenv():
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


load_dotenv()
API_KEY = os.environ.get("TYPESAFE_API_KEY", "").strip()


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        records.append(item)
                except Exception:
                    pass
    return records


def write_jsonl(path: Path, records: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    temp_path.replace(path)


def append_jsonl(path: Path, record: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def call_typesafe(state: str, questions: dict, model: str = "jev-latest") -> dict:
    if not API_KEY:
        raise TypeSafeError("TYPESAFE_API_KEY is not set in environment or .env")
    payload = {
        "state": state,
        "model": model,
        "questions": questions
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise TypeSafeError(f"TypeSafe API request failed: {e}") from e


def parse_list_arg(val, sep_pattern: str = r"[;,]") -> list[str]:
    """Parses a CLI argument that may be a JSON array, a Python list, or a delimited string."""
    if not val:
        return []
    if isinstance(val, list):
        out = []
        for item in val:
            out.extend(parse_list_arg(item, sep_pattern=sep_pattern))
        return [x for x in out if x]
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except Exception:
                pass
        return [p.strip() for p in re.split(sep_pattern, s) if p.strip()]
    return [str(val).strip()]


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        s = str(item).strip()
        if not s:
            continue
        k = s.lower()
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out


def synthesize_default_questions(title: str, summary: str, entities: list[str], people: list[str]) -> list[str]:
    """Generates natural-language retrieval questions if none were explicitly provided."""
    questions = []
    if title:
        questions.append(f"What is the status, decision, or context regarding {title}?")
    if entities:
        ent_str = ", ".join(entities[:3])
        questions.append(f"What did we decide or need to follow up on for {ent_str}?")
    if people:
        ppl_str = ", ".join(people[:2])
        questions.append(f"What are the open loops or expectations involving {ppl_str}?")
    if not questions and summary:
        questions.append(summary[:120])
    return dedupe_preserve_order(questions)[:4]


def build_atoms(args_or_dict, existing_atoms: dict = None) -> dict:
    """Builds or merges the structured atoms dictionary (decisions_and_why, open_loops, commands_or_refs)."""
    base = {
        "decisions_and_why": [],
        "open_loops": [],
        "commands_or_refs": []
    }
    if isinstance(existing_atoms, dict):
        for k in base:
            if isinstance(existing_atoms.get(k), list):
                base[k] = list(existing_atoms[k])

    raw_atoms = getattr(args_or_dict, "atoms", None) if not isinstance(args_or_dict, dict) else args_or_dict.get("atoms")
    if raw_atoms:
        if isinstance(raw_atoms, str):
            try:
                raw_atoms = json.loads(raw_atoms)
            except Exception:
                raw_atoms = {}
        if isinstance(raw_atoms, dict):
            for k in base:
                if k in raw_atoms and isinstance(raw_atoms[k], list):
                    base[k].extend(str(x).strip() for x in raw_atoms[k] if str(x).strip())

    if not isinstance(args_or_dict, dict):
        decisions = parse_list_arg(getattr(args_or_dict, "decisions", None), sep_pattern=r"[;\n]")
        open_loops = parse_list_arg(getattr(args_or_dict, "open_loops", None), sep_pattern=r"[;\n]")
        refs = parse_list_arg(getattr(args_or_dict, "refs", None), sep_pattern=r"[;,\n]")
        if getattr(args_or_dict, "replace_atoms", False):
            if decisions:
                base["decisions_and_why"] = decisions
            if open_loops is not None and getattr(args_or_dict, "open_loops", None) is not None:
                base["open_loops"] = open_loops
            if refs:
                base["commands_or_refs"] = refs
        else:
            base["decisions_and_why"].extend(decisions)
            base["open_loops"].extend(open_loops)
            base["commands_or_refs"].extend(refs)

    for k in base:
        base[k] = dedupe_preserve_order(base[k])
    return base


def write_leaf_dossier(record: dict, extended_content: str = None, history_notes: list[str] = None) -> str:
    """Writes or updates the standalone Markdown dossier in memory/leaf-files/<id>.md."""
    LEAF_DIR.mkdir(parents=True, exist_ok=True)
    mem_id = record["id"]
    leaf_file = LEAF_DIR / f"{mem_id}.md"

    # Preserve existing Rationale & Context and History if updating without explicit content override
    existing_body = ""
    existing_history = []
    if leaf_file.exists() and extended_content is None:
        try:
            old_txt = leaf_file.read_text(encoding="utf-8")
            m_rat = re.search(r"## Rationale & Context\n([\s\S]*?)(?=\n## Revision History|\Z)", old_txt)
            if m_rat:
                existing_body = m_rat.group(1).strip()
            m_hist = re.search(r"## Revision History\n([\s\S]*?)\Z", old_txt)
            if m_hist:
                existing_history = [line.strip() for line in m_hist.group(1).strip().splitlines() if line.strip()]
        except Exception:
            pass

    body = extended_content or existing_body or record.get("summary", "")
    pointers_str = ", ".join(f"`{p}`" for p in record.get("pointers", [])) or "`manual`"
    entities_str = ", ".join(f"`{e}`" for e in record.get("entities", [])) or "None"
    people_str = ", ".join(record.get("people", [])) or "None"
    questions = record.get("questions", [])
    atoms = record.get("atoms", {})

    lines = [
        f"# {record.get('title', 'Untitled Memory')}",
        "",
        f"- **ID:** `{mem_id}`",
        f"- **Tier:** `{record.get('tier', 'short-term')}`",
        f"- **Status:** `{record.get('status', 'active')}`",
        f"- **Importance:** `{float(record.get('importance', 0.75)):.2f}`",
        f"- **Created:** `{record.get('created_at', '')}`",
        f"- **Updated:** `{record.get('updated_at', '')}`",
        f"- **Pointers:** {pointers_str}",
        f"- **Entities:** {entities_str}",
        f"- **People:** {people_str}",
        "",
        "---",
        "",
        "## Summary (Pure Signal)",
        record.get("summary", ""),
        ""
    ]

    if questions:
        lines.append("## Retrieval Trigger Questions")
        for q in questions:
            lines.append(f"- {q}")
        lines.append("")

    if any(atoms.get(k) for k in ("decisions_and_why", "open_loops", "commands_or_refs")):
        lines.append("## Distilled Atoms")
        if atoms.get("decisions_and_why"):
            lines.append("### Decisions & Rationale")
            for d in atoms["decisions_and_why"]:
                lines.append(f"- {d}")
        if atoms.get("open_loops"):
            lines.append("### Open Loops & Forward Links")
            for ol in atoms["open_loops"]:
                lines.append(f"- {ol}")
        if atoms.get("commands_or_refs"):
            lines.append("### References & Commands")
            for ref in atoms["commands_or_refs"]:
                lines.append(f"- {ref}")
        lines.append("")

    lines.extend([
        "## Rationale & Context",
        body,
        ""
    ])

    all_history = list(existing_history)
    if history_notes:
        for hn in history_notes:
            entry = hn if hn.startswith("-") else f"- {hn}"
            if entry not in all_history:
                all_history.append(entry)

    if all_history:
        lines.append("## Revision History")
        lines.extend(all_history)
        lines.append("")

    leaf_file.write_text("\n".join(lines), encoding="utf-8")
    return str(leaf_file.relative_to(BASE_DIR))


def log_observability_event(action: str, title: str, summary: str, status: str,
                            importance: float = 0.75, mem_id: str = None,
                            leaf_path: str = None, conv_id: str = None,
                            tier: str = "short-term", details: dict = None):
    """Logs raw telemetry to raw_events.jsonl and formatted markdown entry to YYYY-WW.md."""
    now = datetime.now()
    now_iso = now.isoformat()
    week_str = now.strftime("%Y-W%W")
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    event = {
        "timestamp": now_iso,
        "action": action,
        "title": title,
        "summary": summary,
        "status": status,
        "importance": importance,
        "tier": tier,
        "memory_id": mem_id,
        "leaf_path": leaf_path,
        "source_conv_id": conv_id,
        "details": details or {}
    }
    append_jsonl(RAW_AUDIT_LOG, event)

    weekly_md = AUDIT_DIR / f"{week_str}.md"
    if not weekly_md.exists():
        weekly_md.write_text(f"# Memory Operations Audit: Week {week_str}\n\n", encoding="utf-8")

    md_entry = (
        f"### `[{action.upper()} | {tier.upper()}]` {title}\n"
        f"- **Timestamp:** `{now_iso}`\n"
        f"- **Outcome:** **{status}** | **Importance:** `{importance:.2f}`\n"
        f"- **Memory ID:** `{mem_id or 'N/A'}` | **Source:** `{conv_id or 'manual'}`\n"
        f"- **Summary:** {summary}\n"
    )
    if leaf_path:
        md_entry += f"- **Dossier:** [{Path(leaf_path).name}](file://{BASE_DIR / leaf_path})\n"
    md_entry += "\n"

    with open(weekly_md, "a", encoding="utf-8") as f:
        f.write(md_entry)


def enforce_write_authority(args, operation_name: str = "write"):
    """Enforces that memory mutations are only performed by authorized consolidation routines."""
    if not getattr(args, "routine", None) and not getattr(args, "allow_adhoc", False):
        print(f"[ERROR] Memory {operation_name.capitalize()} Authority Violation:", file=sys.stderr)
        print("  Ad-hoc session agents are prohibited from mutating memories directly.", file=sys.stderr)
        print("  Memory writes are restricted to consolidation routines (dream-cycle, system-improvement).", file=sys.stderr)
        print("  Pass --routine <name> or --allow-adhoc if explicitly authorized.", file=sys.stderr)
        sys.exit(1)


def compute_recency_score(record: dict, half_life_days: float = 30.0) -> float:
    """Computes exponential recency weight in (0.0, 1.0] based on updated_at or created_at."""
    ts_str = record.get("updated_at") or record.get("created_at") or ""
    if not ts_str:
        return 0.50
    try:
        ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        now = datetime.now(ts.tzinfo) if ts.tzinfo else datetime.now()
        days = max(0.0, (now - ts).total_seconds() / 86400.0)
        return round(math.exp(-days / half_life_days), 4)
    except Exception:
        return 0.50


def build_search_surface(record: dict) -> str:
    """Builds the compact, high-signal text representation of a memory for Jev and BM25."""
    title = record.get("title", "")
    summary = record.get("summary", "")
    questions = "; ".join(record.get("questions", []))
    entities = ", ".join(record.get("entities", []))
    people = ", ".join(record.get("people", []))
    atoms = record.get("atoms", {})
    atom_parts = []
    if isinstance(atoms, dict):
        if atoms.get("decisions_and_why"):
            atom_parts.append("Decisions: " + "; ".join(atoms["decisions_and_why"]))
        if atoms.get("open_loops"):
            atom_parts.append("Open Loops: " + "; ".join(atoms["open_loops"]))
        if atoms.get("commands_or_refs"):
            atom_parts.append("Refs: " + "; ".join(atoms["commands_or_refs"]))
    parts = [f"Title: {title}", f"Summary: {summary}"]
    if questions:
        parts.append(f"Questions: {questions}")
    if entities or people:
        parts.append(f"Entities/People: {', '.join(x for x in (entities, people) if x)}")
    if atom_parts:
        parts.append(" | ".join(atom_parts))
    return "\n".join(parts)


def tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9_]+", text.lower()) if w not in STOP_WORDS and len(w) > 1]


def bm25_rank_records(records: list[dict], query: str) -> dict[str, float]:
    """Computes normalized [0.0, 1.0] Okapi BM25 + lexical coverage scores for offline fallback."""
    q_tokens = tokenize(query)
    if not q_tokens or not records:
        return {r.get("id", ""): 0.0 for r in records}

    docs = []
    doc_freqs = {}
    for r in records:
        atoms_dict = r.get("atoms") if isinstance(r.get("atoms"), dict) else {}
        atom_values_str = " ".join(
            str(v)
            for vals in atoms_dict.values()
            if isinstance(vals, list)
            for v in vals
        )
        # Weight title and questions 2x in term frequency (never serialize JSON keys)
        weighted_text = (
            f"{r.get('title', '')} {r.get('title', '')} "
            f"{' '.join(r.get('questions', []))} {' '.join(r.get('questions', []))} "
            f"{' '.join(r.get('entities', []))} {' '.join(r.get('people', []))} "
            f"{r.get('summary', '')} {atom_values_str}"
        )
        tokens = tokenize(weighted_text)
        docs.append((r.get("id", ""), tokens))
        for ut in set(tokens):
            doc_freqs[ut] = doc_freqs.get(ut, 0) + 1

    n_docs = len(docs)
    avgdl = sum(len(t) for _, t in docs) / max(1, n_docs)
    k1 = 1.5
    b = 0.75

    raw_scores = {}
    q_set = set(q_tokens)
    for mem_id, tokens in docs:
        if not tokens:
            raw_scores[mem_id] = (0.0, 0.0, 0)
            continue
        tf_map = {}
        for t in tokens:
            tf_map[t] = tf_map.get(t, 0) + 1
        dl = len(tokens)
        score = 0.0
        matched_q_terms = 0
        for qt in q_set:
            tf = tf_map.get(qt, 0)
            if tf > 0:
                matched_q_terms += 1
                df = doc_freqs.get(qt, 0)
                idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
                denom = tf + k1 * (1.0 - b + b * (dl / max(1.0, avgdl)))
                score += idf * ((tf * (k1 + 1.0)) / denom)
        coverage = matched_q_terms / len(q_set)
        raw_scores[mem_id] = (score, coverage, matched_q_terms)

    max_bm25 = max((s for s, _, _ in raw_scores.values()), default=0.0)
    normalized = {}
    for mem_id, (bm25_val, coverage, matched_q_terms) in raw_scores.items():
        if bm25_val <= 0.0 or coverage <= 0.0:
            normalized[mem_id] = 0.0
        elif len(q_set) >= 3 and matched_q_terms <= 1 and bm25_val < 5.0:
            # Guard against single-token incidental overlap on multi-word unrelated queries
            normalized[mem_id] = round(min(0.18, bm25_val * 0.04), 4)
        else:
            # Blend absolute saturation with relative batch normalization so weak matches are not inflated to 1.0
            abs_bm25 = bm25_val / (bm25_val + 3.5)
            rel_bm25 = bm25_val / max(max_bm25, 4.0)
            norm_bm25 = 0.50 * abs_bm25 + 0.50 * rel_bm25
            normalized[mem_id] = round(min(1.0, 0.65 * norm_bm25 + 0.35 * min(1.0, coverage * 1.35)), 4)
    return normalized


def jev_batch_score_records(records: list[dict], task: str, batch_size: int = 55) -> dict[str, float]:
    """
    Evaluates all candidate memories in a single batched TypeSafe Jev call (or chunks of 55).
    Combines per-memory direct/related Choice probabilities with a competitive primary_match Choice
    so multiple relevant memories can all score high while top matches get sharpened.
    """
    if not records:
        return {}

    scores = {}
    for start in range(0, len(records), batch_size):
        batch = records[start:start + batch_size]
        catalog_lines = []
        choice_criteria = {"none": "None of the stored memories are directly relevant to this task."}
        questions = {}

        for idx, r in enumerate(batch):
            key = f"m_{idx}"
            title = r.get("title", "")
            surface = build_search_surface(r)
            catalog_lines.append(f"[{key}] {surface}")
            choice_criteria[key] = f"{title}: {r.get('summary', '')[:110]}"
            questions[key] = {
                "type": "choice",
                "instructions": f"Evaluate whether memory [{key}] ({title}) provides relevant context, decisions, constraints, or open loops for the task: \"{task}\"",
                "criteria": {
                    "direct": "Directly relevant: addresses the same feature, bug, workflow, stakeholder request, or architectural rule",
                    "related": "Related context in the same workstream, epic, or domain",
                    "irrelevant": "Unrelated topic"
                }
            }

        questions["primary_match"] = {
            "type": "choice",
            "instructions": f"Which single memory is the strongest match for the task: \"{task}\"?",
            "criteria": choice_criteria
        }

        state = f"Task / Query: {task}\n\nStored Memories Catalog:\n\n" + "\n\n".join(catalog_lines)
        res = call_typesafe(state, questions)
        answers = res.get("answers", {})
        primary_probs = answers.get("primary_match", {}).get("probabilities", {})

        for idx, r in enumerate(batch):
            key = f"m_{idx}"
            mem_id = r.get("id", key)
            probs = answers.get(key, {}).get("probabilities", {})
            p_direct = float(probs.get("direct", 0.0))
            p_related = float(probs.get("related", 0.0))
            p_primary = float(primary_probs.get(key, 0.0))
            jev_prob = min(1.0, p_direct + 0.75 * p_related + 0.25 * p_primary)
            scores[mem_id] = round(jev_prob, 4)

    return scores


def find_record_across_tiers(mem_id: str) -> tuple[str, int, dict, list[dict]]:
    """
    Finds a memory record by ID across long-term.jsonl and short-term.jsonl.
    Prioritizes active records so graduated stubs in short-term.jsonl never shadow
    active records in long-term.jsonl.
    """
    tier_sources = [
        ("long-term", LONG_TERM_PATH, read_jsonl(LONG_TERM_PATH)),
        ("short-term", SHORT_TERM_PATH, read_jsonl(SHORT_TERM_PATH))
    ]
    # Pass 1: strictly active records (long-term first, then short-term)
    for tier_name, _, records in tier_sources:
        for idx, r in enumerate(records):
            if r.get("id") == mem_id and r.get("status") == "active":
                return tier_name, idx, r, records
    # Pass 2: fallback to any status (e.g. graduated or archived)
    for tier_name, _, records in tier_sources:
        for idx, r in enumerate(records):
            if r.get("id") == mem_id:
                return tier_name, idx, r, records
    return None, -1, None, []


def cmd_init(args):
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    LEAF_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    for p in (SHORT_TERM_PATH, LONG_TERM_PATH):
        if not p.exists():
            p.touch()
        print(f"  Verified {p.relative_to(BASE_DIR)}")
    print("Unified memory JSONL stores initialized.")


def cmd_context(args):
    """Loads active long-term.jsonl core memories for mandatory session startup grounding."""
    long_recs = [r for r in read_jsonl(LONG_TERM_PATH) if r.get("status") in ("active", "graduated")]
    long_recs.sort(key=lambda r: (float(r.get("importance", 0.75)), r.get("updated_at", "")), reverse=True)

    open_loop_recs = []
    if getattr(args, "include_open_loops", False):
        short_recs = [r for r in read_jsonl(SHORT_TERM_PATH) if r.get("status") == "active"]
        for r in short_recs:
            atoms = r.get("atoms", {})
            if isinstance(atoms, dict) and atoms.get("open_loops"):
                open_loop_recs.append(r)

    if getattr(args, "json", False):
        out = {"long_term": long_recs}
        if getattr(args, "include_open_loops", False):
            out["active_open_loops"] = open_loop_recs
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return

    print(f"=== Core Long-Term Memory ({len(long_recs)} active records) ===")
    for r in long_recs:
        imp = float(r.get("importance", 0.75))
        upd = str(r.get("updated_at") or r.get("created_at") or "")[:10]
        print(f"- [{r.get('id')}] (Importance: {imp:.2f} | Updated: {upd}) **{r.get('title')}**")
        print(f"  Summary: {r.get('summary')}")
        atoms = r.get("atoms", {})
        if isinstance(atoms, dict) and atoms.get("open_loops"):
            print(f"  Open Loops: {'; '.join(atoms['open_loops'])}")
    if open_loop_recs:
        print(f"\n=== Active Working Memory Open Loops ({len(open_loop_recs)} records) ===")
        for r in open_loop_recs:
            print(f"- [{r.get('id')}] **{r.get('title')}**")
            for ol in r.get("atoms", {}).get("open_loops", []):
                print(f"  * {ol}")


def cmd_ingest(args):
    enforce_write_authority(args, "ingest")

    # Check if --update-id was passed or if an active record has the exact same normalized title
    target_update_id = getattr(args, "update_id", None)
    if not target_update_id:
        norm_title = args.title.strip().lower()
        for p in (LONG_TERM_PATH, SHORT_TERM_PATH):
            for r in read_jsonl(p):
                if r.get("status") == "active" and r.get("title", "").strip().lower() == norm_title:
                    target_update_id = r.get("id")
                    break
            if target_update_id:
                break

    if target_update_id:
        print(f"  Existing memory [{target_update_id}] matches. Updating in place with newer context...")
        args.id = target_update_id
        cmd_update(args)
        return

    tier = getattr(args, "tier", "short-term") or "short-term"
    target_path = LONG_TERM_PATH if tier == "long-term" else SHORT_TERM_PATH
    importance = round(min(max(float(args.importance if args.importance is not None else 0.75), 0.0), 1.0), 2)

    mem_id = f"mem_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    now_iso = datetime.now().isoformat()

    entities = dedupe_preserve_order(parse_list_arg(args.entities, sep_pattern=r"[;,]"))
    people = dedupe_preserve_order(parse_list_arg(args.people, sep_pattern=r"[;,]"))
    questions = dedupe_preserve_order(parse_list_arg(args.questions, sep_pattern=r"[;\n]"))
    if not questions:
        questions = synthesize_default_questions(args.title, args.summary, entities, people)

    pointers = parse_list_arg(args.pointers, sep_pattern=r"[;,]")
    if args.conv_id and args.conv_id != "manual":
        ptr = args.conv_id if ":" in args.conv_id else f"conv:{args.conv_id}"
        pointers.append(ptr)
    pointers = dedupe_preserve_order(pointers)

    atoms = build_atoms(args)

    meta_dict = {}
    if getattr(args, "metadata", None):
        try:
            meta_dict = json.loads(args.metadata) if isinstance(args.metadata, str) else dict(args.metadata)
        except Exception:
            meta_dict = {"raw": str(args.metadata)}
    meta_dict["routine"] = getattr(args, "routine", None) or "adhoc"

    record = {
        "id": mem_id,
        "created_at": now_iso,
        "updated_at": now_iso,
        "tier": tier,
        "status": "active",
        "importance": importance,
        "title": args.title.strip(),
        "summary": args.summary.strip(),
        "questions": questions,
        "entities": entities,
        "people": people,
        "atoms": atoms,
        "pointers": pointers,
        "leaf_path": f"memory/leaf-files/{mem_id}.md",
        "source_conv_id": args.conv_id or "manual",
        "metadata": meta_dict
    }

    leaf_rel_path = write_leaf_dossier(
        record,
        extended_content=args.content or args.summary,
        history_notes=[f"`{now_iso[:10]}`: Created via `{meta_dict['routine']}` (Source: `{args.conv_id or 'manual'}`)"]
    )
    record["leaf_path"] = leaf_rel_path

    append_jsonl(target_path, record)

    log_observability_event(
        action="ingest",
        title=record["title"],
        summary=record["summary"],
        status="ACCEPTED",
        importance=importance,
        mem_id=mem_id,
        leaf_path=leaf_rel_path,
        conv_id=args.conv_id,
        tier=tier
    )
    print(f"  ACCEPTED and stored as [{mem_id}] in memory/{tier}.jsonl (Importance: {importance:.2f}).")


def cmd_update(args):
    enforce_write_authority(args, "update")
    mem_id = args.id.strip()
    tier_name, idx, record, records = find_record_across_tiers(mem_id)
    if record is None:
        print(f"Error: Memory ID '{mem_id}' not found in short-term.jsonl or long-term.jsonl.", file=sys.stderr)
        sys.exit(1)

    now_iso = datetime.now().isoformat()
    old_summary = record.get("summary", "")

    if getattr(args, "title", None):
        record["title"] = args.title.strip()
    if getattr(args, "summary", None):
        record["summary"] = args.summary.strip()
    if getattr(args, "importance", None) is not None:
        record["importance"] = round(min(max(float(args.importance), 0.0), 1.0), 2)
    if getattr(args, "status", None):
        record["status"] = args.status

    new_entities = parse_list_arg(getattr(args, "entities", None), sep_pattern=r"[;,]")
    if new_entities:
        record["entities"] = dedupe_preserve_order(record.get("entities", []) + new_entities)

    new_people = parse_list_arg(getattr(args, "people", None), sep_pattern=r"[;,]")
    if new_people:
        record["people"] = dedupe_preserve_order(record.get("people", []) + new_people)

    new_questions = parse_list_arg(getattr(args, "questions", None), sep_pattern=r"[;\n]")
    if new_questions:
        if getattr(args, "replace_atoms", False):
            record["questions"] = dedupe_preserve_order(new_questions)
        else:
            record["questions"] = dedupe_preserve_order(record.get("questions", []) + new_questions)
    elif not record.get("questions"):
        record["questions"] = synthesize_default_questions(
            record.get("title", ""), record.get("summary", ""),
            record.get("entities", []), record.get("people", [])
        )

    new_pointers = parse_list_arg(getattr(args, "pointers", None), sep_pattern=r"[;,]")
    if getattr(args, "conv_id", None) and args.conv_id != "manual":
        ptr = args.conv_id if ":" in args.conv_id else f"conv:{args.conv_id}"
        new_pointers.append(ptr)
    if new_pointers:
        record["pointers"] = dedupe_preserve_order(record.get("pointers", []) + new_pointers)

    record["atoms"] = build_atoms(args, existing_atoms=record.get("atoms"))
    record["updated_at"] = now_iso
    record["tier"] = tier_name

    hist_note = f"`{now_iso[:10]}`: Updated via `{getattr(args, 'routine', None) or 'manual'}`"
    if getattr(args, "conv_id", None):
        hist_note += f" (Pointer: `{args.conv_id}`)"
    if getattr(args, "summary", None) and args.summary.strip() != old_summary:
        hist_note += f" | Previous summary: {old_summary[:140]}"

    leaf_rel = write_leaf_dossier(record, extended_content=getattr(args, "content", None), history_notes=[hist_note])
    record["leaf_path"] = leaf_rel

    records[idx] = record
    target_path = LONG_TERM_PATH if tier_name == "long-term" else SHORT_TERM_PATH
    write_jsonl(target_path, records)

    if tier_name == "long-term":
        short_recs = read_jsonl(SHORT_TERM_PATH)
        short_changed = False
        for sr in short_recs:
            if sr.get("id") == mem_id and sr.get("status") == "graduated":
                for field in ("title", "summary", "importance", "questions", "entities", "people", "atoms", "pointers", "updated_at"):
                    sr[field] = record[field]
                short_changed = True
        if short_changed:
            write_jsonl(SHORT_TERM_PATH, short_recs)

    log_observability_event(
        action="update",
        title=record["title"],
        summary=record["summary"],
        status="UPDATED",
        importance=float(record.get("importance", 0.75)),
        mem_id=mem_id,
        leaf_path=leaf_rel,
        conv_id=getattr(args, "conv_id", None),
        tier=tier_name
    )
    print(f"  UPDATED [{mem_id}] in memory/{tier_name}.jsonl.")


def cmd_merge(args):
    enforce_write_authority(args, "merge")
    target_id = args.target_id.strip()
    source_ids = [s.strip() for s in parse_list_arg(args.source_ids, sep_pattern=r"[;,]") if s.strip() and s.strip() != target_id]
    if not source_ids:
        print("Error: Provide at least one distinct --source-ids to merge into --target-id.", file=sys.stderr)
        sys.exit(1)

    t_tier, t_idx, target_rec, _ = find_record_across_tiers(target_id)
    if target_rec is None:
        print(f"Error: Target memory '{target_id}' not found.", file=sys.stderr)
        sys.exit(1)

    short_recs = read_jsonl(SHORT_TERM_PATH)
    long_recs = read_jsonl(LONG_TERM_PATH)

    found_sources = []
    for sid in source_ids:
        s_tier, s_idx, s_rec, _ = find_record_across_tiers(sid)
        if s_rec is None:
            print(f"Error: Source memory '{sid}' not found.", file=sys.stderr)
            sys.exit(1)
        found_sources.append((s_tier, s_rec))

    now_iso = datetime.now().isoformat()

    # Combine envelope metadata & search surfaces across target + sources
    all_questions = list(target_rec.get("questions", []))
    all_entities = list(target_rec.get("entities", []))
    all_people = list(target_rec.get("people", []))
    all_pointers = list(target_rec.get("pointers", []))
    if target_rec.get("source_conv_id") and target_rec["source_conv_id"] != "manual":
        p = target_rec["source_conv_id"]
        all_pointers.append(p if ":" in p else f"conv:{p}")

    merged_atoms = build_atoms({}, existing_atoms=target_rec.get("atoms"))
    history_notes = []
    max_imp = float(target_rec.get("importance", 0.75))

    for s_tier, s_rec in found_sources:
        sid = s_rec.get("id")
        all_questions.extend(s_rec.get("questions", []))
        all_entities.extend(s_rec.get("entities", []))
        all_people.extend(s_rec.get("people", []))
        all_pointers.extend(s_rec.get("pointers", []))
        if s_rec.get("source_conv_id") and s_rec["source_conv_id"] != "manual":
            p = s_rec["source_conv_id"]
            all_pointers.append(p if ":" in p else f"conv:{p}")
        s_atoms = s_rec.get("atoms", {})
        if isinstance(s_atoms, dict):
            for k in merged_atoms:
                merged_atoms[k].extend(s_atoms.get(k, []))
        max_imp = max(max_imp, float(s_rec.get("importance", 0.75)))
        history_notes.append(f"`{now_iso[:10]}`: Merged `[{sid}]` ({s_rec.get('title', '')}): {s_rec.get('summary', '')}")

    if getattr(args, "title", None):
        target_rec["title"] = args.title.strip()
    if getattr(args, "summary", None):
        target_rec["summary"] = args.summary.strip()
    if getattr(args, "importance", None) is not None:
        target_rec["importance"] = round(min(max(float(args.importance), 0.0), 1.0), 2)
    else:
        target_rec["importance"] = round(max_imp, 2)

    explicit_questions = parse_list_arg(getattr(args, "questions", None), sep_pattern=r"[;\n]")
    if explicit_questions and getattr(args, "replace_atoms", False):
        all_questions = explicit_questions
    else:
        all_questions.extend(explicit_questions)
    all_entities.extend(parse_list_arg(getattr(args, "entities", None), sep_pattern=r"[;,]"))
    all_people.extend(parse_list_arg(getattr(args, "people", None), sep_pattern=r"[;,]"))
    all_pointers.extend(parse_list_arg(getattr(args, "pointers", None), sep_pattern=r"[;,]"))

    target_rec["questions"] = dedupe_preserve_order(all_questions)
    if not target_rec["questions"]:
        target_rec["questions"] = synthesize_default_questions(
            target_rec["title"], target_rec["summary"], all_entities, all_people
        )
    target_rec["entities"] = dedupe_preserve_order(all_entities)
    target_rec["people"] = dedupe_preserve_order(all_people)
    target_rec["pointers"] = dedupe_preserve_order(all_pointers)
    target_rec["atoms"] = build_atoms(args, existing_atoms=merged_atoms)
    target_rec["updated_at"] = now_iso
    target_rec["status"] = "active"

    meta = target_rec.get("metadata") if isinstance(target_rec.get("metadata"), dict) else {}
    merged_from = list(meta.get("merged_from", []))
    merged_from.extend(source_ids)
    meta["merged_from"] = dedupe_preserve_order(merged_from)
    target_rec["metadata"] = meta

    dest_tier = getattr(args, "tier", None) or t_tier
    target_rec["tier"] = dest_tier

    leaf_rel = write_leaf_dossier(target_rec, extended_content=getattr(args, "content", None), history_notes=history_notes)
    target_rec["leaf_path"] = leaf_rel

    # Update short_recs and long_recs
    source_id_set = set(source_ids)
    for r in short_recs:
        if r.get("id") in source_id_set:
            r["status"] = "archived"
            r["updated_at"] = now_iso
            r.setdefault("metadata", {})["superseded_by"] = target_id
            write_leaf_dossier(r, history_notes=[f"`{now_iso[:10]}`: Archived and merged into `[{target_id}]`."])
        elif r.get("id") == target_id:
            if dest_tier == "short-term":
                r.update(target_rec)
            else:
                r["status"] = "graduated"
                r["updated_at"] = now_iso

    for r in long_recs:
        if r.get("id") in source_id_set:
            r["status"] = "archived"
            r["updated_at"] = now_iso
            r.setdefault("metadata", {})["superseded_by"] = target_id
            write_leaf_dossier(r, history_notes=[f"`{now_iso[:10]}`: Archived and merged into `[{target_id}]`."])
        elif r.get("id") == target_id:
            if dest_tier == "long-term":
                r.update(target_rec)
            else:
                r["status"] = "archived"
                r["updated_at"] = now_iso

    if dest_tier == "long-term" and not any(r.get("id") == target_id for r in long_recs):
        long_recs.append(target_rec)
    elif dest_tier == "short-term" and not any(r.get("id") == target_id for r in short_recs):
        short_recs.append(target_rec)

    write_jsonl(SHORT_TERM_PATH, short_recs)
    write_jsonl(LONG_TERM_PATH, long_recs)

    log_observability_event(
        action="merge",
        title=target_rec["title"],
        summary=target_rec["summary"],
        status="MERGED",
        importance=float(target_rec.get("importance", 0.75)),
        mem_id=target_id,
        leaf_path=leaf_rel,
        tier=dest_tier,
        details={"merged_from": source_ids}
    )
    print(f"  MERGED {source_ids} into [{target_id}] ({dest_tier}).")


def cmd_graduate(args):
    enforce_write_authority(args, "graduate")
    mem_id = args.id.strip()
    short_recs = read_jsonl(SHORT_TERM_PATH)
    long_recs = read_jsonl(LONG_TERM_PATH)

    if any(r.get("id") == mem_id and r.get("status") == "active" for r in long_recs):
        print(f"  Memory [{mem_id}] is already active in long-term.jsonl.")
        return

    target = None
    for r in short_recs:
        if r.get("id") == mem_id:
            target = r
            break

    if target is None:
        print(f"Error: Memory [{mem_id}] not found in short-term.jsonl.", file=sys.stderr)
        sys.exit(1)

    now_iso = datetime.now().isoformat()
    target["status"] = "graduated"
    target["updated_at"] = now_iso

    grad_rec = dict(target)
    grad_rec["tier"] = "long-term"
    grad_rec["status"] = "active"
    if getattr(args, "importance", None) is not None:
        grad_rec["importance"] = round(min(max(float(args.importance), 0.0), 1.0), 2)
    if getattr(args, "summary", None):
        grad_rec["summary"] = args.summary.strip()

    leaf_rel = write_leaf_dossier(
        grad_rec,
        extended_content=getattr(args, "content", None),
        history_notes=[f"`{now_iso[:10]}`: Graduated to `long-term.jsonl`."]
    )
    grad_rec["leaf_path"] = leaf_rel

    existing_idx = next((i for i, lr in enumerate(long_recs) if lr.get("id") == mem_id), None)
    if existing_idx is not None:
        long_recs[existing_idx] = grad_rec
    else:
        long_recs.append(grad_rec)

    write_jsonl(SHORT_TERM_PATH, short_recs)
    write_jsonl(LONG_TERM_PATH, long_recs)

    log_observability_event(
        action="graduate",
        title=grad_rec.get("title", ""),
        summary=grad_rec.get("summary", ""),
        status="GRADUATED",
        importance=float(grad_rec.get("importance", 0.85)),
        mem_id=mem_id,
        leaf_path=leaf_rel,
        tier="long-term"
    )
    print(f"  GRADUATED [{mem_id}] '{grad_rec.get('title')}' to memory/long-term.jsonl.")


def cmd_archive(args):
    enforce_write_authority(args, "archive")
    mem_id = args.id.strip()
    found = False
    now_iso = datetime.now().isoformat()
    reason = getattr(args, "reason", None) or "Operational relevance resolved or superseded."

    for tier_name, path in (("short-term", SHORT_TERM_PATH), ("long-term", LONG_TERM_PATH)):
        recs = read_jsonl(path)
        changed = False
        for r in recs:
            if r.get("id") == mem_id and r.get("status") != "archived":
                r["status"] = "archived"
                r["updated_at"] = now_iso
                r.setdefault("metadata", {})["archive_reason"] = reason
                write_leaf_dossier(r, history_notes=[f"`{now_iso[:10]}`: Archived ({reason})"])
                changed = True
                found = True
                log_observability_event(
                    action="archive",
                    title=r.get("title", ""),
                    summary=r.get("summary", ""),
                    status="ARCHIVED",
                    importance=float(r.get("importance", 0.5)),
                    mem_id=mem_id,
                    leaf_path=r.get("leaf_path"),
                    tier=tier_name,
                    details={"reason": reason}
                )
        if changed:
            write_jsonl(path, recs)

    if not found:
        print(f"Error: Active memory [{mem_id}] not found.", file=sys.stderr)
        sys.exit(1)
    print(f"  ARCHIVED [{mem_id}] ({reason}).")


def cmd_query(args):
    """
    Retrieves memories relevant to an agent task/topic.
    Primary: 1-call batched TypeSafe Jev semantic selection + Recency + Importance.
    Backup: Local Okapi BM25 + Recency + Importance when Jev is unavailable or --offline is set.
    """
    tier_arg = getattr(args, "tier", "all") or "all"
    threshold = float(args.threshold if args.threshold is not None else 0.55)
    top_k = int(getattr(args, "top_k", 8) or 8)
    force_offline = getattr(args, "offline", False)

    candidates = []
    seen_ids = set()

    if tier_arg in ("short-term", "all"):
        for r in read_jsonl(SHORT_TERM_PATH):
            if r.get("status") == "active" and r.get("id") not in seen_ids:
                r_copy = dict(r)
                r_copy["tier"] = "short-term"
                candidates.append(r_copy)
                seen_ids.add(r.get("id"))

    if tier_arg in ("long-term", "all") or (not candidates and getattr(args, "fallback_long", True)):
        for r in read_jsonl(LONG_TERM_PATH):
            if r.get("status") in ("active", "graduated") and r.get("id") not in seen_ids:
                r_copy = dict(r)
                r_copy["tier"] = "long-term"
                candidates.append(r_copy)
                seen_ids.add(r.get("id"))

    if not candidates:
        if args.json:
            print("[]")
        else:
            print(f"\n=== Memory Query Results for Task: '{args.task}' ===\nMatches found: 0\n")
        return

    engine = "jev_batched"
    semantic_scores = {}

    if not force_offline:
        try:
            semantic_scores = jev_batch_score_records(candidates, args.task)
        except TypeSafeError as e:
            print(f"[WARN] TypeSafe Jev unavailable ({e}). Falling back to BM25 + Recency + Importance.", file=sys.stderr)
            engine = "bm25_fallback"
            semantic_scores = bm25_rank_records(candidates, args.task)
    else:
        engine = "bm25_fallback"
        semantic_scores = bm25_rank_records(candidates, args.task)

    effective_threshold = min(threshold, 0.45) if engine == "bm25_fallback" else threshold

    matching = []
    for r in candidates:
        mem_id = r.get("id", "unknown")
        sem_prob = float(semantic_scores.get(mem_id, 0.0))
        recency = compute_recency_score(r)
        importance = float(r.get("importance", r.get("relevance_score", 0.75)) or 0.75)

        # Gate so irrelevant records (sem_prob < 0.25) cannot pass threshold via recency/importance alone
        if sem_prob < 0.25:
            final_score = round(sem_prob * 0.50, 3)
        else:
            final_score = round(min(1.0, 0.65 * sem_prob + 0.20 * recency + 0.15 * importance), 3)

        if final_score >= effective_threshold:
            matching.append({
                "id": mem_id,
                "tier": r.get("tier", "short-term"),
                "title": r.get("title", ""),
                "summary": r.get("summary", ""),
                "importance": round(importance, 2),
                "recency": round(recency, 2),
                "semantic_score": round(sem_prob, 3),
                "task_relevance": final_score,
                "questions": r.get("questions", []),
                "entities": r.get("entities", []),
                "people": r.get("people", []),
                "atoms": r.get("atoms", {}),
                "pointers": r.get("pointers", []),
                "leaf_path": r.get("leaf_path"),
                "updated_at": r.get("updated_at") or r.get("created_at"),
                "engine": engine
            })

    matching.sort(key=lambda x: (x["task_relevance"], x["semantic_score"], x["recency"]), reverse=True)
    if top_k > 0:
        matching = matching[:top_k]

    if args.json:
        print(json.dumps(matching, indent=2, ensure_ascii=False))
    else:
        print(f"\n=== Memory Query Results for Task: '{args.task}' (Engine: {engine}) ===")
        print(f"Matches found: {len(matching)} (Threshold: {effective_threshold:.2f})\n")
        for m in matching:
            print(
                f"- [{m['id']} | {m['tier']} | Score: {m['task_relevance']:.2f} "
                f"(Sem: {m['semantic_score']:.2f}, Rec: {m['recency']:.2f}, Imp: {m['importance']:.2f})] "
                f"**{m['title']}**"
            )
            print(f"  Summary: {m['summary']}")
            atoms = m.get("atoms") or {}
            if isinstance(atoms, dict):
                if atoms.get("decisions_and_why"):
                    print(f"  Decisions: {'; '.join(atoms['decisions_and_why'][:3])}")
                if atoms.get("open_loops"):
                    print(f"  Open Loops: {'; '.join(atoms['open_loops'][:3])}")
            if m.get("pointers"):
                print(f"  Pointers: {', '.join(m['pointers'][:4])}")
            if m.get("leaf_path"):
                print(f"  Dossier: file://{BASE_DIR / m['leaf_path']}")
            print()


def cmd_list(args):
    tier_filter = getattr(args, "tier", "all") or "all"
    status_filter = getattr(args, "status", "active") or "active"

    tiers = []
    if tier_filter in ("long-term", "all"):
        tiers.append(("Long-Term Core Memory", "memory/long-term.jsonl", LONG_TERM_PATH))
    if tier_filter in ("short-term", "all"):
        tiers.append(("Short-Term Working Memory", "memory/short-term.jsonl", SHORT_TERM_PATH))

    for label, rel, path in tiers:
        recs = read_jsonl(path)
        if status_filter != "all":
            if status_filter == "active" and path == LONG_TERM_PATH:
                recs = [r for r in recs if r.get("status") in ("active", "graduated")]
            else:
                recs = [r for r in recs if r.get("status") == status_filter]
        print(f"\n=== {label} ({len(recs)} records in {rel}) ===")
        for r in recs:
            imp = float(r.get("importance", r.get("relevance_score", 0.75)) or 0.75)
            upd = str(r.get("updated_at") or r.get("created_at") or "")[:10]
            print(
                f"  - [{r.get('id', 'unknown')}] {r.get('title', '')} "
                f"(Imp: {imp:.2f} | Status: {r.get('status')} | Updated: {upd})"
            )


def cmd_audit(args):
    if not RAW_AUDIT_LOG.exists():
        print("No audit events recorded yet.")
        return

    events = read_jsonl(RAW_AUDIT_LOG)
    display_events = events[-args.limit:] if args.limit > 0 else []

    print(f"\n=== Memory Audit Ledger (Showing last {len(display_events)} of {len(events)} events) ===")
    for e in display_events:
        status = e.get("status", "EVENT")
        action = e.get("action") or e.get("dimension") or "memory"
        ts = str(e.get("timestamp", ""))[:19]
        print(f"[{status}] {ts} | [{action}] {e.get('title')}")
        print(f"   Summary: {e.get('summary')}")
        if e.get("leaf_path"):
            print(f"   Dossier: file://{BASE_DIR / e['leaf_path']}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Unified Two-Tier Harness Memory Manager (JSONL-Native).")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    subparsers.add_parser("init", help="Initialize unified short-term.jsonl, long-term.jsonl, and leaf-files/.")

    # context
    p_ctx = subparsers.add_parser("context", help="Load active long-term core memory for mandatory conversation startup grounding.")
    p_ctx.add_argument("--include-open-loops", action="store_true", help="Also include active open loops from short-term memory.")
    p_ctx.add_argument("--json", action="store_true", help="Output JSON format.")

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Ingest a distilled memory record directly into the unified store.")
    p_ingest.add_argument("--routine", choices=["dream-cycle", "system-improvement"], default=None,
                          help="Consolidation routine authorizing this ingestion (required unless --allow-adhoc).")
    p_ingest.add_argument("--allow-adhoc", action="store_true", default=False,
                          help="Explicit override for authorized ad-hoc ingestion.")
    p_ingest.add_argument("--title", required=True, help="Specific operational memory title.")
    p_ingest.add_argument("--summary", required=True, help="3-part Pure Signal summary (Expectation vs Reality -> Action -> Forward Link).")
    p_ingest.add_argument("--content", default=None, help="Detailed context, rationale, and evidence for the leaf dossier.")
    p_ingest.add_argument("--importance", type=float, default=0.75, help="Importance weight (0.0 to 1.0, default: 0.75).")
    p_ingest.add_argument("--tier", choices=["short-term", "long-term"], default="short-term", help="Destination tier (default: short-term).")
    p_ingest.add_argument("--questions", default=None, help="Semicolon-separated or JSON list of natural-language trigger questions.")
    p_ingest.add_argument("--entities", default=None, help="Comma-separated or JSON list of entities, task IDs, or repos.")
    p_ingest.add_argument("--people", default=None, help="Comma-separated or JSON list of people/stakeholders.")
    p_ingest.add_argument("--decisions", default=None, help="Semicolon-separated list of key decisions and why.")
    p_ingest.add_argument("--open-loops", dest="open_loops", default=None, help="Semicolon-separated list of unresolved open loops.")
    p_ingest.add_argument("--refs", default=None, help="Semicolon/comma-separated list of commands or references.")
    p_ingest.add_argument("--atoms", default=None, help="JSON object with decisions_and_why, open_loops, commands_or_refs.")
    p_ingest.add_argument("--pointers", default=None, help="Comma-separated list of source pointers (e.g. conv:<id>, task:<id>, pr:<id>).")
    p_ingest.add_argument("--conv-id", default=None, help="Source conversation ID.")
    p_ingest.add_argument("--update-id", default=None, help="If provided, updates this existing memory ID in place instead of creating a new entry.")
    p_ingest.add_argument("--metadata", default=None, help="Optional JSON string for metadata.")
    # Legacy no-op arguments kept for CLI backward compatibility
    p_ingest.add_argument("--dimension", default=None, help=argparse.SUPPRESS)
    p_ingest.add_argument("--fallback-score", type=float, default=None, help=argparse.SUPPRESS)
    p_ingest.add_argument("--fallback-horizon", default=None, help=argparse.SUPPRESS)

    # update
    p_upd = subparsers.add_parser("update", help="Update an existing memory (short-term or long-term, any age) with newer data.")
    p_upd.add_argument("--routine", choices=["dream-cycle", "system-improvement"], default=None)
    p_upd.add_argument("--allow-adhoc", action="store_true", default=False)
    p_upd.add_argument("--id", required=True, help="Existing memory ID to update.")
    p_upd.add_argument("--title", default=None)
    p_upd.add_argument("--summary", default=None)
    p_upd.add_argument("--content", default=None)
    p_upd.add_argument("--importance", type=float, default=None)
    p_upd.add_argument("--status", choices=["active", "archived", "graduated"], default=None)
    p_upd.add_argument("--questions", default=None)
    p_upd.add_argument("--entities", default=None)
    p_upd.add_argument("--people", default=None)
    p_upd.add_argument("--decisions", default=None)
    p_upd.add_argument("--open-loops", dest="open_loops", default=None)
    p_upd.add_argument("--refs", default=None)
    p_upd.add_argument("--atoms", default=None)
    p_upd.add_argument("--replace-atoms", action="store_true", help="Replace atoms lists instead of appending.")
    p_upd.add_argument("--pointers", default=None)
    p_upd.add_argument("--conv-id", default=None)

    # merge
    p_merge = subparsers.add_parser("merge", help="Join and merge multiple memories across any age/tier into a single lean record.")
    p_merge.add_argument("--routine", choices=["dream-cycle", "system-improvement"], default=None)
    p_merge.add_argument("--allow-adhoc", action="store_true", default=False)
    p_merge.add_argument("--target-id", required=True, help="Primary memory ID to retain and enrich.")
    p_merge.add_argument("--source-ids", required=True, help="Comma-separated memory IDs to merge into target and archive.")
    p_merge.add_argument("--title", default=None, help="Updated consolidated title.")
    p_merge.add_argument("--summary", default=None, help="Updated consolidated Pure Signal summary.")
    p_merge.add_argument("--content", default=None, help="Updated consolidated dossier content.")
    p_merge.add_argument("--importance", type=float, default=None, help="Updated importance weight.")
    p_merge.add_argument("--tier", choices=["short-term", "long-term"], default=None, help="Target tier override.")
    p_merge.add_argument("--questions", default=None)
    p_merge.add_argument("--entities", default=None)
    p_merge.add_argument("--people", default=None)
    p_merge.add_argument("--decisions", default=None)
    p_merge.add_argument("--open-loops", dest="open_loops", default=None)
    p_merge.add_argument("--refs", default=None)
    p_merge.add_argument("--atoms", default=None)
    p_merge.add_argument("--replace-atoms", action="store_true")
    p_merge.add_argument("--pointers", default=None)

    # graduate
    p_grad = subparsers.add_parser("graduate", help="Promote an active short-term memory to long-term core memory.")
    p_grad.add_argument("--routine", choices=["dream-cycle", "system-improvement"], default=None)
    p_grad.add_argument("--allow-adhoc", action="store_true", default=False)
    p_grad.add_argument("--id", required=True, help="Memory ID to graduate.")
    p_grad.add_argument("--importance", type=float, default=None)
    p_grad.add_argument("--summary", default=None)
    p_grad.add_argument("--content", default=None)

    # archive
    p_arch = subparsers.add_parser("archive", help="Archive a resolved or obsolete memory.")
    p_arch.add_argument("--routine", choices=["dream-cycle", "system-improvement"], default=None)
    p_arch.add_argument("--allow-adhoc", action="store_true", default=False)
    p_arch.add_argument("--id", required=True, help="Memory ID to archive.")
    p_arch.add_argument("--reason", default=None, help="Reason for archiving.")

    # query
    p_query = subparsers.add_parser("query", help="Retrieve memories relevant to a task via 1-call Jev (with BM25+Recency backup).")
    p_query.add_argument("--task", required=True, help="Task description, topic, or request to match against.")
    p_query.add_argument("--tier", choices=["short-term", "long-term", "all"], default="all", help="Tier to search (default: all).")
    p_query.add_argument("--threshold", type=float, default=0.55, help="Relevance score threshold (default: 0.55).")
    p_query.add_argument("--top-k", type=int, default=8, help="Max results to return (default: 8).")
    p_query.add_argument("--fallback-long", action="store_true", default=True, help="Check long-term if short-term empty.")
    p_query.add_argument("--no-fallback-long", action="store_false", dest="fallback_long")
    p_query.add_argument("--offline", action="store_true", help="Force local BM25 + Recency + Importance fallback without calling Jev.")
    p_query.add_argument("--json", action="store_true", help="Output JSON format.")
    p_query.add_argument("--dimension", default=None, help=argparse.SUPPRESS)

    # list
    p_list = subparsers.add_parser("list", help="List memories across tiers.")
    p_list.add_argument("--tier", choices=["short-term", "long-term", "all"], default="all")
    p_list.add_argument("--status", choices=["active", "archived", "graduated", "all"], default="active")
    p_list.add_argument("--dimension", default=None, help=argparse.SUPPRESS)

    # audit
    p_audit = subparsers.add_parser("audit", help="Inspect recent memory operations audit telemetry.")
    p_audit.add_argument("--limit", type=int, default=20, help="Max entries to show.")
    p_audit.add_argument("--dimension", default=None, help=argparse.SUPPRESS)

    args = parser.parse_args()
    if args.command == "init":
        cmd_init(args)
    elif args.command == "context":
        cmd_context(args)
    elif args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "update":
        cmd_update(args)
    elif args.command == "merge":
        cmd_merge(args)
    elif args.command == "graduate":
        cmd_graduate(args)
    elif args.command == "archive":
        cmd_archive(args)
    elif args.command == "query":
        cmd_query(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "audit":
        cmd_audit(args)


if __name__ == "__main__":
    main()
