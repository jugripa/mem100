---
name: memory-management
description: Manage the unified two-tier memory store (ingest, update, merge, graduate, archive), enforce Pure Signal schema standards, and maintain the MEM100 engine.
---

# Memory Management & Consolidation Skill

## Purpose
This skill governs write operations, schema standards, cross-age consolidation, and engine maintenance for the **MEM100** unified two-tier memory system (`scripts/manage_memory.py`). Normal conversational sessions remain strictly read-only (`context` and `query`); load this skill whenever executing memory mutations, auditing memory hygiene, or maintaining the `mem100` repository.

---

## 1. Unified Two-Tier Schema & Pure Signal Standard

### Storage Tiers (Zero Dimension Silos)
1. **`memory/long-term.jsonl` (Core Memory):** Durable domain truths, active commitments, architectural constraints, and stakeholder policies (`~15-30` active records, `< 4,000` tokens).
2. **`memory/short-term.jsonl` (Working Memory):** Active work threads, evolving decisions, and unresolved open loops.
3. **`memory/leaf-files/<id>.md` (Context Dossiers):** 1-to-1 Markdown dossiers with full rationale, primary-source pointers, and chronological revision history.
4. **`memory/audit/` (Observability):** `raw_events.jsonl` telemetry and weekly Markdown ledgers (`YYYY-W%W.md`).

### The 3-Part Pure Signal Anatomy
Every `--summary` must capture the semantic context that issue trackers and Git commits lose:
1. **Expectation vs Reality:** What did the stakeholder, user, or engineer expect, and what was the actual system state or mental model mismatch?
2. **Operational Action:** What concrete action or decision was taken to address it?
3. **Forward Link:** What follow-up, verification, or definition remains open?

### Enriched Metadata Surface
- `importance`: Continuous float (`0.0` to `1.0`; e.g., `0.75` tactical thread, `0.85 - 0.95` critical decision or durable policy).
- `questions`: 2 to 4 natural-language trigger questions a user or agent would ask when needing this memory.
- `entities`: Task IDs, repositories, services, or domain modules.
- `people`: People or roles involved.
- `atoms`: Structured lists for `decisions_and_why`, `open_loops`, and `commands_or_refs` (replaces standalone `decisions/log.md` files).
- `pointers`: Source references (`conv:<id>`, `task:<id>`, `pr:<id>`).

---

## 2. CLI Write & Consolidation Reference (`scripts/manage_memory.py`)

### Ingest a New Memory (or Auto-Update Matching Title)
```bash
python3 scripts/manage_memory.py ingest \
  --routine dream-cycle \
  --title "<Specific Operational Title>" \
  --summary "<3-part Pure Signal: Expectation vs Reality -> Action -> Forward Link>" \
  --content "<Detailed context, rationale, and evidence>" \
  --importance 0.85 \
  --tier short-term \
  --questions "<Trigger question 1>;<Trigger question 2>" \
  --entities "<Entities>" \
  --people "<People>" \
  --decisions "<Decision and why>" \
  --open-loops "<Unresolved follow-up>" \
  --refs "<Commands or doc refs>" \
  --pointers "<conv:<id>,task:<id>>" \
  --conv-id "<source_conversation_id>"
```
*(Pass `--allow-adhoc` if executing an explicit user-authorized manual memory write outside a scheduled workflow).*

### Update an Existing Memory Across Any Tier or Age
```bash
python3 scripts/manage_memory.py update \
  --routine system-improvement \
  --id "<mem_id>" \
  --summary "<Updated 3-part Pure Signal summary>" \
  --decisions "<Updated decisions>" \
  --open-loops "<Remaining open loops or empty string if resolved>" \
  --replace-atoms
```

### Merge Overlapping Memories Across Any Tier or Age
```bash
python3 scripts/manage_memory.py merge \
  --routine system-improvement \
  --target-id "<primary_id>" \
  --source-ids "<dup_id_1,dup_id_2>" \
  --title "<Consolidated Title>" \
  --summary "<Consolidated 3-part Pure Signal summary>" \
  --replace-atoms
```

### Graduate a Durable Working Memory to Core Long-Term Memory
```bash
python3 scripts/manage_memory.py graduate \
  --routine system-improvement \
  --id "<mem_id>"
```

### Archive a Resolved or Obsolete Memory
```bash
python3 scripts/manage_memory.py archive \
  --routine system-improvement \
  --id "<mem_id>" \
  --reason "<Why resolved or superseded>"
```

---

## 3. Upstream Repository Maintenance (`projects/mem100` -> `jugripa/mem100`)

When maintaining or upgrading the MEM100 engine inside a host workspace that tracks `projects/mem100/`:
1. **Domain-Agnostic Sanitization:** Keep all code and documentation in `projects/mem100/` 100% free of personal, client, or company-specific names, tokens, and `.env` secrets.
2. **Bidirectional Sync:** Synchronize improvements across `scripts/{manage_memory.py,harvest_conversations.py,system_improvement.py}`, `.agents/rules/memory-governance.md`, `.agents/skills/{memory-management,system-review}`, `.agents/workflows/{dream-cycle.md,system-improvement.md}`, and `docs/ARCHITECTURE_GUIDE.md`.
3. **Changelog & Release:** Document architectural changes in `projects/mem100/CHANGELOG.md` (and experimental findings in `projects/mem100/EXPERIMENTS.md`), commit, and push to `https://github.com/jugripa/mem100`.
