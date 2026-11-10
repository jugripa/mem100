# Changelog - MEM100 (Autonomous Agent Memory & Continuous Self-Improvement Engine)

All architectural improvements, bug fixes, and governance refinements to the MEM100 engine are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [2.1.0] - 2026-11-09 (Lean Index Governance, `memory-management` Skill & Queue Retirement)

### Added
- **Dedicated On-Demand Memory Skill (`.agents/skills/memory-management/SKILL.md`):** Extracted the 3-part Pure Signal anatomy, JSONL/dossier schema specification, CLI write commands (`ingest`, `update`, `merge`, `graduate`, `archive`), and upstream maintainer sync protocol into an on-demand skill so normal read-only sessions do not carry write-path prompt bloat.

### Changed
- **Slimmed `.agents/rules/memory-governance.md` & `AGENTS.md` Integration:** Reduced `memory-governance.md` to a concise 12-line session rule enforcing Turn-1 `context` loading, task-arrival `query` retrieval, and the read-only session boundary, keeping host `AGENTS.md` files as pure 1-line indices.

### Removed
- **Retired `decisions/log.md`:** Removed standalone `decisions/log.md` ledger as all architectural, product, and rule decisions are stored natively with full context and pointers inside `memory/long-term.jsonl` and `memory/short-term.jsonl` (`atoms.decisions_and_why`).
- **Retired `memory/PENDING_REVIEW.md` & `memory-human-review`:** Removed `memory/PENDING_REVIEW.md`, `.agents/skills/memory-human-review/SKILL.md`, and the `stage-ambiguity` / `resolve-ambiguity` subcommands in `scripts/manage_memory.py` (obsolete since v2.0 eliminated post-LLM Jev gatekeeper quarantines and emergent dimension loops).

---

## [2.0.0] - 2026-10-26 (Unified Two-Tier Architecture & 1-Call Jev Retrieval)

### Added
- **Official Distribution Designation (MEM100):** Designated the autonomous memory and self-improvement engine as **MEM100** for standalone open-source distribution, accompanied by [`EXPERIMENTS.md`](./EXPERIMENTS.md) for long-horizon research tracking.
- **Unified Two-Tier Store (Zero Dimension or Facet Silos):** Consolidated `memory/company-pulse/`, `memory/decisions/`, and `memory/open-loops/` into unified `memory/long-term.jsonl` (Core Memory), `memory/short-term.jsonl` (Working Memory), and `memory/leaf-files/<id>.md` (Markdown dossiers).
- **Enriched Context Metadata & Search Surface:**
  - Added `questions` (natural-language retrieval trigger questions) to every memory record so semantic and lexical queries match how tasks are actually phrased.
  - Added structured `atoms` (`decisions_and_why`, `open_loops`, `commands_or_refs`), `entities`, `people`, and `pointers` (`conv:<id>`, `task:<id>`).
- **1-Call Batched TypeSafe Jev Retrieval (`jev_batch_score_records`):**
  - Evaluates all active memories in a single HTTP request (`~0.25s - 0.35s` total latency, default threshold `0.55`) by combining per-record `Choice` (`direct`, `related`, `irrelevant`) with competitive `primary_match` selection.
  - Combines semantic match (`0.65`), exponential recency (`0.20`, $\text{Recency} = e^{-\text{age\_days}/30.0}$ with $\tau = 30.0$ days), and importance (`0.15`), gated by a low-semantic filter (`P_sem < 0.25 -> 0.50 * P_sem`).
- **Local Okapi BM25 Offline Fallback (`bm25_rank_records`):**
  - Ranks memories locally (`< 5ms`, effective threshold `min(threshold, 0.45)`) when TypeSafe Jev is unreachable or `--offline` is set, using Okapi BM25 ($k_1 = 1.5, b = 0.75$) with `title` and `questions` weighted `2x` and a single-token specificity guard (`len(q_set) >= 3 and matched_q_terms <= 1 and bm25_val < 5.0 -> min(0.18, bm25_val * 0.04)`) so unrelated multi-word queries fall below the `0.25` semantic gate and return `0` matches.
- **Mandatory Two-Stage Retrieval Protocol:**
  - `manage_memory.py context`: Mandatory on Turn 1 of every session to load active `long-term.jsonl` core memories.
  - `manage_memory.py query --task "..."`: Mandatory whenever a task, feature, bug, or stakeholder topic arrives.
- **First-Class Cross-Age Consolidation Commands:**
  - Added `update`, `merge`, `graduate`, and `archive` commands in `scripts/manage_memory.py` operating across both `short-term.jsonl` and `long-term.jsonl` regardless of record age.
- **Deterministic Consolidation Brief in `scripts/system_improvement.py`:**
  - Added `audit_memory_consolidation()` to deterministically surface cross-age overlap pairs, older memories touched by recent sessions, graduation candidates (`(importance >= 0.88 or (importance >= 0.85 and len(pointers) >= 2))` with zero unresolved `open_loops`), and stale pruning candidates (`recency < 0.35` and `importance < 0.85`) without calling Jev in a per-record loop.

### Changed
- **Continuous Importance Weight Only (`0.0 - 1.0`):** Removed discrete `decay_horizon` (`fleeting`, `tactical`, `foundational`) classification at ingestion.
- **Token-Mindful Direct LLM Ingestion:** Removed redundant post-LLM Jev gatekeeper calls (`score_candidate`, `classify_horizon`, `route_dimension`) from `manage_memory.py ingest` since the consolidating LLM in `dream-cycle` has already synthesized the record.

### Fixed
- **Rescued 26 Quarantined Memories Caused by `int(val)` Truncation Bug:** Fixed the root cause where the legacy `score_candidate` function ran `int_val = int(val)` on continuous `[0.0, 2.0]` Jev scores, truncating scores in `[1.0, 1.99]` to `1` (`0.62 < 0.70`) and trapping 26 valid memories in `memory/PENDING_REVIEW.md`.
- **Cross-Tier Graduated Stub Shadowing:** Fixed `find_record_across_tiers`, `cmd_ingest`, `cmd_update`, and `cmd_graduate` to prioritize `status == "active"` records in `long-term.jsonl` first, and synchronize graduated stubs in `short-term.jsonl` when core records are updated.

### Removed
- Retired `memory/dimensions.json`, `memory/rejected_dimensions.json`, and per-dimension `rubric.json` files.

---

## [1.3.0] - 2026-10-25 (Ingestion Authority Guard, Pure Signal & Routine Cursors)

### Added
- **Role-Based Ingestion Authority Guard:** Restricted memory write operations (`ingest`, `update`, `merge`, `graduate`, `archive`, `stage-ambiguity`) to authorized consolidation routines (`--routine {dream-cycle,system-improvement,manual-review}`), keeping ad-hoc conversational agents strictly read-only (`context`, `query`, `list`, `audit`).
- **3-Part Pure Signal Anatomy Standard:** Defined the required memory summary structure:
  1. `Stakeholder Expectation vs Reality`
  2. `Operational Action`
  3. `Forward Link`
- **Routine-Isolated Cursors in `memory/sync_state.json`:** Separated high-water mark cursors (`routines.dream-cycle` vs `routines.system-improvement`) in `scripts/harvest_conversations.py` so daily `dream-cycle` runs no longer advance the cursor used by weekly `system-improvement` runs.

### Fixed
- **Eliminated Infinite Emergent Dimension Loops:** Stopped `dream-cycle` and `system-improvement` from repeatedly re-proposing rejected dimension silos in `memory/PENDING_REVIEW.md`.

---

## [1.1.0] - 2026-10-06 (Observability Ledgers & Programmatic Queue Resolution)

### Added
- **Weekly Audit Ledgers (`memory/audit/YYYY-W%W.md`, e.g. `2026-W43.md`):** Added human-readable weekly markdown audit tables alongside `memory/audit/raw_events.jsonl`.
- **Programmatic Human Review Resolution:** Added `resolve-ambiguity` to `scripts/manage_memory.py` and created `.agents/skills/memory-human-review/SKILL.md` to approve or reject staged items in `memory/PENDING_REVIEW.md`.

---

## [1.0.0] - 2026-09-25 (Initial Autonomous Memory Engine)

### Added
- Initial dual-surface storage architecture combining Git-friendly JSONL indices (`short-term.jsonl`, `long-term.jsonl`) with Markdown dossiers (`leaf-files/<id>.md`).
- Multi-runtime transcript harvester (`scripts/harvest_conversations.py`) scanning Desktop, CLI, and IDE transcripts with deterministic workspace URI verification and subagent filtering.
- Daily `dream-cycle` and weekly `system-improvement` autonomous workflows.
