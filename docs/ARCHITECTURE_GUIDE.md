# Advanced Memory & Continuous Self-Improvement Architecture (v2.0)

Technical specification for implementing a persistent, Git-friendly two-tier JSONL + Markdown memory store, routine-isolated differential cursor indexing, 1-call TypeSafe Jev semantic retrieval with local Okapi BM25 fallback, role-based ingestion authority, and cross-age weekly meta-improvement in autonomous AI agent harnesses.

---

## 1. System Overview

```text
[Raw Conversation Transcripts (~/.gemini/ across Desktop, CLI, IDE)]
              │
              ▼ (Harvest Window: Workspace URI Verification + Subagent Filter)
┌─────────────────────────────────────────────────────────────────────────┐
│                    Orchestrator Conversation Turns                      │
│   (Tracked via routine-isolated cursor: memory/sync_state.json)         │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼ (Consolidating LLM Synthesis in Dream-Cycle)
┌─────────────────────────────────────────────────────────────────────────┐
│             Enriched Pure Signal Candidate Memory Record                │
│  (3-Part Summary + Trigger Questions + Entities + People + Atoms)       │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼ (Role-Based Authority Guard: --routine)
┌─────────────────────────────────────────────────────────────────────────┐
│             Working Memory Tier (memory/short-term.jsonl)               │
│                 + memory/leaf-files/<id>.md dossier                     │
└──────────────────┬───────────────────────────────────┬──────────────────┘
                   │                                   │
 (On Task Arrival: │                                   │ (Weekly System-Improvement:
  1-Call Jev Query │                                   │  Cross-Age Merge, Update,
  or BM25 Backup)  │                                   │  Prune & Graduate)
                   ▼                                   ▼
      [Active Agent Turn Context]         ┌───────────────────────────────┐
      (Always Grounded on Turn 1 by       │       Core Memory Tier        │
       manage_memory.py context)          │   (memory/long-term.jsonl)    │
                                          │ + leaf-files/<id>.md dossier  │
                                          └───────────────────────────────┘
```

---

## 2. Transcript Ingestion & Workspace Isolation (`harvest_conversations.py`)

Antigravity stores conversation logs across three runtimes:
- Desktop: `~/.gemini/antigravity/`
- CLI: `~/.gemini/antigravity-cli/`
- IDE: `~/.gemini/antigravity-ide/`

### Primary Source: `transcript.jsonl`
Path: `~/.gemini/<instance>/brain/<conversation-id>/.system_generated/logs/transcript.jsonl`

Each JSONL line contains:
- `step_index`: Monotonically increasing step integer.
- `created_at`: ISO-8601 UTC timestamp string.
- `source`: `USER_EXPLICIT`, `MODEL`, or `SYSTEM`.
- `type`: `USER_INPUT`, `PLANNER_RESPONSE`, or `TOOL_CALL`.
- `content`: Message text and prompts.
- `tool_calls`: Tool names, arguments (`Cwd`, commands, paths), and outputs.

### Deterministic Workspace Verification
Before harvesting any conversation ID, `harvest_conversations.py` verifies its workspace URI against the target repository path using a 4-stage check:
1. Primary Check: Query `~/.gemini/<instance>/conversations/<conversation-id>.db`:
   ```sql
   SELECT data FROM trajectory_metadata_blob WHERE id = 'main';
   ```
   Inspect the binary blob for URI strings matching `file://<project-path>`.
2. Fallback 1: Query `~/.gemini/<instance>/conversation_summaries.db` (`workspace_uris` column in `conversation_summaries`).
3. Fallback 2: Inspect `tool_calls` in `transcript.jsonl` for `Cwd` arguments matching the project root.
4. Fallback 3: Scan the first 60 lines of `transcript.jsonl` for the target workspace substring.
5. Dynamic Workspace Resolution: Scripts inspect `os.environ.get("ANTIGRAVITY_WORKSPACE", BASE_DIR.name)` so the harvester is portable across any repository without hardcoded paths.

### Subagent Filtering
Subagent sessions are excluded from root harvesting so only orchestrator sessions (containing user prompts, decisions, and final outcomes) are consolidated:
- Check `~/.gemini/<instance>/brain/<conversation-id>/.system_generated/messages/` for `Message from Root Agent`, or check `parent_conversation_id` in `conversation_summaries.db`.

### Routine-Isolated Differential Cursor Tracking (`memory/sync_state.json`)
To allow multi-day conversations to continue without re-harvesting old turns or causing daily `dream-cycle` runs to blind weekly `system-improvement` runs:
- `memory/sync_state.json` maintains an independent cursor namespace under `routines.<routine_name>.conversations.<conv_id>` (`last_step_index` and `last_mtime`).
- Transcript parsing begins at `last_step_index + 1` (default `-1` so step `0` is captured) and emits normalized turn objects with keys `turn_index`, `step_index`, `max_step`, `timestamp`, `user_prompt`, `tools_used`, and `assistant_response`.
- If transcript compaction resets step numbers (`file_max_step < last_step_index`), the cursor resets safely to `-1`.
- All state writes use atomic temporary file swaps (`.tmp` -> `replace`).

---

## 3. Unified Two-Tier Storage Layer & Enriched Schema

### Why Zero Dimension Silos
Separating memories into category directories (`decisions/`, `open-loops/`, `company-pulse/`) creates artificial silos because a single operational event typically contains a decision, domain context, and an open follow-up at the same time. All memories are stored in two unified tiers:
1. **`memory/long-term.jsonl` (Core Memory):** Durable architectural truths, active roadmap commitments, domain constraints, and stakeholder policies. Kept curated (`~15-30` active records, `< 4,000` tokens) so it can be loaded at the start of every session.
2. **`memory/short-term.jsonl` (Working Memory):** Active sprint threads, evolving decisions, and unresolved open loops. Queried dynamically whenever a task or topic arrives.
3. **`memory/leaf-files/<id>.md` (Markdown Context Dossiers):** 1-to-1 human-readable dossiers containing frontmatter, full rationale, distilled atoms, and a chronological revision history.

### Directory Layout
```text
memory/
├── sync_state.json            # Routine-isolated cursors tracking session mtimes & step indexes
├── long-term.jsonl            # Active & archived core memories
├── short-term.jsonl           # Active, graduated & archived working memories
├── leaf-files/                # Full-context Markdown dossiers
│   └── <id>.md
└── audit/                     # Observability layer
    ├── raw_events.jsonl       # Machine telemetry for every memory lifecycle event
    └── YYYY-W%W.md            # Weekly Markdown audit ledger (e.g. 2026-W43.md)
```

### Enriched JSONL Record Schema
Every line in `short-term.jsonl` and `long-term.jsonl` is a self-contained JSON object:

```json
{
  "id": "mem_20261026090512_82f10b",
  "created_at": "2026-10-26T09:05:12.123456",
  "updated_at": "2026-10-26T09:15:30.654321",
  "tier": "short-term",
  "status": "active",
  "importance": 0.85,
  "title": "Auto-Save Scope Boundary: Org Edit vs Event Stepper",
  "summary": "Stakeholder expected auto-save inside the Event Creation Stepper, whereas in production auto-save only exists in Organization Edit. Created task TSK-104 to implement stepper auto-save. Product owner must define save triggers and error states before engineering starts.",
  "questions": [
    "Does the event creation stepper support auto-save?",
    "Why was auto-save missing from the event stepper workflow?",
    "What needs to be defined before implementing auto-save in TSK-104?"
  ],
  "entities": [
    "TSK-104",
    "Event Stepper",
    "Organization Edit",
    "Auto-Save"
  ],
  "people": [
    "Product Lead",
    "Stakeholder"
  ],
  "atoms": {
    "decisions_and_why": [
      "Scoped TSK-104 to bring Organization Edit auto-save behavior into the Event Stepper."
    ],
    "open_loops": [
      "Define auto-save trigger intervals and validation states on TSK-104."
    ],
    "commands_or_refs": [
      "TSK-104"
    ]
  },
  "pointers": [
    "conv:e1e8416f-99ab-48d1",
    "task:TSK-104"
  ],
  "leaf_path": "memory/leaf-files/mem_20261026090512_82f10b.md",
  "source_conv_id": "e1e8416f-99ab-48d1",
  "metadata": {
    "routine": "dream-cycle"
  }
}
```

### Markdown Leaf Dossier (`memory/leaf-files/<id>.md`)
Generated and updated by `write_leaf_dossier()` in `scripts/manage_memory.py`:

```markdown
# Auto-Save Scope Boundary: Org Edit vs Event Stepper

- **ID:** `mem_20261026090512_82f10b`
- **Tier:** `short-term`
- **Status:** `active`
- **Importance:** `0.85`
- **Created:** `2026-10-26T09:05:12.123456`
- **Updated:** `2026-10-26T09:15:30.654321`
- **Pointers:** `conv:e1e8416f-99ab-48d1`, `task:TSK-104`
- **Entities:** `TSK-104`, `Event Stepper`, `Organization Edit`, `Auto-Save`
- **People:** Product Lead, Stakeholder

---

## Summary (Pure Signal)
Stakeholder expected auto-save inside the Event Creation Stepper, whereas in production auto-save only exists in Organization Edit. Created task TSK-104 to implement stepper auto-save. Product owner must define save triggers and error states before engineering starts.

## Retrieval Trigger Questions
- Does the event creation stepper support auto-save?
- Why was auto-save missing from the event stepper workflow?
- What needs to be defined before implementing auto-save in TSK-104?

## Distilled Atoms
### Decisions & Rationale
- Scoped TSK-104 to bring Organization Edit auto-save behavior into the Event Stepper.

### Open Loops & Forward Links
- Define auto-save trigger intervals and validation states on TSK-104.

### References & Commands
- TSK-104

## Rationale & Context
...

## Revision History
- `2026-10-26`: Created via `dream-cycle` (Source: `e1e8416f-99ab-48d1`)
```

---

## 4. The Pure Signal Standard & Direct LLM Ingestion

### The 3-Part Pure Signal Anatomy
Memory is not a copy of issue trackers or Git commit logs; it captures the semantic context that external tools lose:
1. **Expectation vs Reality:** What did the stakeholder, user, or engineer expect, and what was the actual system state or mental model mismatch?
2. **Operational Action:** What concrete action was taken (e.g. task created, spec updated, option ruled out)?
3. **Forward Link:** What follow-up, verification, or definition remains open?

### Why Ingestion Writes Directly Without Post-LLM Jev Gatekeeping
During `dream-cycle`, a frontier LLM is already reading the session transcript to extract the memory. Calling Jev *after* the LLM synthesized the candidate creates two problems:
1. **Redundant Token & Latency Overhead:** Paying a second model to grade text just written by a larger model.
2. **False Quarantines:** Small rubric wording mismatches can reject high-value context.

Instead, `manage_memory.py ingest` enforces a **Role-Based Write Authority Guard** (`--routine {dream-cycle,system-improvement,manual-review}` or `--allow-adhoc`) and writes directly to the unified store. If an active memory already shares the exact normalized title (or `--update-id` is passed), `ingest` automatically updates the existing record in place (`cmd_update`), prioritizing active `long-term.jsonl` records over graduated stubs.

---

## 5. Mandatory Retrieval Protocol & 1-Call Jev Engine (`manage_memory.py`)

### Mandatory Retrieval Rules
1. **Session Start (`context`):** Every session loads `long-term.jsonl` on Turn 1:
   ```bash
   python3 scripts/manage_memory.py context [--include-open-loops] [--json]
   ```
2. **Task Arrival (`query`):** Every incoming task, feature, bug, or topic shift queries working and core memory (default `--threshold 0.55` for Jev, lowered automatically to `min(threshold, 0.45)` during `bm25_fallback`):
   ```bash
   python3 scripts/manage_memory.py query --task "<topic, entity, or request>" [--tier {short-term,long-term,all}] [--threshold 0.55] [--top-k 8] [--no-fallback-long] [--offline] [--json]
   ```

### Primary Retrieval: 1-Call Batched TypeSafe Jev (`jev_batch_score_records`)
Instead of making $N$ sequential HTTP requests (`3s - 8s` latency) or pre-filtering with keywords (which drops semantically valid memories when wording differs), `manage_memory.py query` sends all active records in a **single batched HTTP request** (`~0.25s - 0.35s` total latency):
1. Each candidate memory `m_i` is formatted using its distilled search surface (`title`, `summary`, `entities`, `people`, `questions`, `decisions_and_why`, `open_loops`).
2. The single Jev payload asks:
   - Per-record `Choice` (`m_i`): `direct`, `related`, or `irrelevant`.
   - Competitive catalog `Choice` (`primary_match`): which single memory is the strongest match.
3. Semantic probability for each memory `m_i`:
   $$P_{\text{jev}}(m_i) = \min\left(1.0,\; P_{\text{direct}}(m_i) + 0.75 \cdot P_{\text{related}}(m_i) + 0.25 \cdot P_{\text{primary}}(m_i)\right)$$
4. Final composite score combining semantic probability $P_{\text{sem}}$ (`0.65`), exponential recency (`0.20`, $\text{Recency}(m_i) = e^{-\text{age\_days} / 30.0}$ with time constant $\tau = 30.0$ days), and importance (`0.15`), gated by a low-semantic filter (`P_sem < 0.25`):
   $$\text{Score}(m_i) = \begin{cases} 0.50 \cdot P_{\text{sem}}(m_i), & \text{if } P_{\text{sem}}(m_i) < 0.25 \\ \min\left(1.0,\; 0.65 \cdot P_{\text{sem}}(m_i) + 0.20 \cdot e^{-\text{age\_days} / 30.0} + 0.15 \cdot \text{Importance}(m_i)\right), & \text{if } P_{\text{sem}}(m_i) \ge 0.25 \end{cases}$$

### Offline Backup: Local Okapi BM25 + Recency + Importance (`bm25_rank_records`)
When `TYPESAFE_API_KEY` is absent, unreachable, or `--offline` is passed:
1. `bm25_rank_records` tokenizes each record's weighted text (`title` and `questions` repeated `2x`, `entities`, `people`, `summary`, and `atoms` list values included `1x`, never serializing JSON keys).
2. Computes Okapi BM25 ($k_1 = 1.5, b = 0.75$). For standard matches, it blends absolute saturation (`bm25_val / (bm25_val + 3.5)`) and batch-relative normalization (`bm25_val / max(max_bm25, 4.0)`) `50/50`, then combines `0.65 * norm_bm25 + 0.35 * min(1.0, coverage * 1.35)`.
3. **Single-Token Specificity Guard:** When a multi-word query (`len(q_set) >= 3`) matches only a single query term (`matched_q_terms <= 1`) with `bm25_val < 5.0`, the lexical probability is dampened to `min(0.18, bm25_val * 0.04)`. This falls below the `P_sem < 0.25` gate (`final_score <= 0.09 < 0.45`), ensuring unrelated multi-word queries return `0` matches.

---

## 6. Cross-Age Memory Consolidation & Weekly `system-improvement`

Memories across any age (`short-term.jsonl` and `long-term.jsonl`) can be modified, joined, graduated, or archived via first-class CLI commands:

```bash
# 1. Update an existing short-term or long-term record in place
python3 scripts/manage_memory.py update --routine system-improvement --id <MEM_ID> --summary "..." --open-loops "..." --replace-atoms

# 2. Merge overlapping memories (across any tier or age) into a primary target record
python3 scripts/manage_memory.py merge --routine system-improvement --target-id <TARGET_ID> --source-ids <ID1,ID2> --summary "..." --replace-atoms

# 3. Graduate a durable working memory to long-term.jsonl
python3 scripts/manage_memory.py graduate --routine system-improvement --id <MEM_ID>

# 4. Archive a resolved or obsolete memory
python3 scripts/manage_memory.py archive --routine system-improvement --id <MEM_ID> --reason "Resolved in PR #42"
```

### Deterministic Consolidation Brief (`scripts/system_improvement.py`)
Running `python3 scripts/system_improvement.py` executes in `< 100ms` with zero Jev API calls and generates a structured markdown report containing:
1. **User Friction & Redirection Audit:** Detects user corrections across harvested sessions.
2. **Context Discovery Gaps:** Flags repeated file searches where `AGENTS.md` or context docs lacked pointers.
3. **Cross-Age Memory Consolidation Brief:**
   - **A. Cross-Age Overlap Pairs:** Pairs across `short-term` and `long-term` sharing entities, ticket/PR prefixes, or lexical Jaccard similarity (`>= 0.28`, or `>= 2` shared entities with Jaccard `>= 0.16`).
   - **B. Existing & Older Memories Touched by Recent Activity:** Older records whose entities or token coverage (`>= 0.45`) appeared in recent session transcripts.
   - **C. Core Graduation Candidates:** Active `short-term` records with `(importance >= 0.88 or (importance >= 0.85 and len(pointers) >= 2))` and zero unresolved `open_loops`.
   - **D. Stale / Decayed Pruning Candidates:** Older `short-term` records (`recency < 0.35`, `importance < 0.85`) untouched by recent sessions.

---

## 7. Implementation Checklist for Any Agent Harness

- [x] `scripts/harvest_conversations.py`: Multi-runtime transcript harvester with workspace URI verification, subagent filtering, and routine-isolated differential cursors (`memory/sync_state.json`).
- [x] `scripts/manage_memory.py`: Unified two-tier JSONL + Markdown dossier engine with `init`, `context`, `query` (1-call Jev + Okapi BM25 fallback), `ingest`, `update`, `merge`, `graduate`, `archive`, `list`, and `audit`.
- [x] `scripts/system_improvement.py`: Weekly friction auditor and deterministic cross-age memory consolidation analyzer.
- [x] `.agents/rules/memory-governance.md`: Lean mandatory startup `context` + task-arrival `query` protocol and read-only session boundary.
- [x] `.agents/skills/memory-management/SKILL.md`: On-demand write/consolidation operations, 3-part Pure Signal schema standard, and upstream repository maintenance protocol.
- [x] `.agents/workflows/dream-cycle.md`: End-of-day consolidation workflow.
- [x] `.agents/workflows/system-improvement.md`: Weekly cross-age memory consolidation and system tuning workflow.
- [x] `.agents/skills/system-review/SKILL.md`: Interactive human-in-the-loop review skill.
