# Memory System Governance, Retrieval Protocol & Ingestion Authority

Strict rules governing when, how, and by whom the harness memory system is consulted, updated, and consolidated.

---

## 1. Unified Two-Tier Architecture (Zero Dimension Silos)

- **No Dimension or Facet Silos:**
  All memories live in a unified two-tier JSONL architecture backed by Markdown dossiers:
  1. `memory/long-term.jsonl` (Core Memory): Durable domain truths, active commitments, architectural constraints, and stakeholder policies.
  2. `memory/short-term.jsonl` (Working Memory): Active work threads, evolving decisions, and unresolved open loops.
  3. `memory/leaf-files/<id>.md` (Context Dossiers): Full rationale, primary-source evidence, and chronological revision history.
- **Enriched Record Metadata (Importance Only, No Horizon):**
  Every record carries:
  - **Envelope:** `id`, `created_at`, `updated_at`, `tier`, `status`, `importance` (`0.0` to `1.0`), `pointers` (`conv:<id>`, `task:<id>`), `entities`, `people`.
  - **Distilled Search Surface:** `title`, `summary` (3-part Pure Signal), `questions` (natural-language retrieval triggers), and `atoms` (`decisions_and_why`, `open_loops`, `commands_or_refs`).

---

## 2. Mandatory Retrieval Protocol (When Memory Is Consulted)

1. **Always Consult Long-Term Memory at Conversation Start:**
   At the beginning of every session, load core memory so foundational context is present on Turn 1:
   ```bash
   python3 scripts/manage_memory.py context
   ```
2. **Consult Short-Term Memory Whenever a Task or Topic Arrives:**
   Do not wait for the user to ask you to check memory. Whenever a task, feature, bug, question, or topic shift comes through, immediately query working memory before grepping raw logs or guessing:
   ```bash
   python3 scripts/manage_memory.py query --task "<specific topic, entity, or request>"
   ```
3. **1-Call Jev Retrieval with BM25 + Recency Backup:**
   `manage_memory.py query` evaluates all active records in a single batched TypeSafe Jev call (`Choice` across the distilled search surface, weighted with `0.20 * Recency` and `0.15 * Importance`) so semantic inference is never lost when keywords differ. When Jev is unreachable or offline, it falls back automatically to local `Okapi BM25 + Recency + Importance`.

---

## 3. Strict Ingestion Authority Boundary & Token Mindfulness

- **Ad-Hoc Conversational Agents are Read-Only:**
  Agents running normal interactive sessions are strictly prohibited from mutating memory directly. They may only run `context`, `query`, `list`, and `audit`.
- **Consolidation Routines Only:**
  Writing or mutating memory (`ingest`, `update`, `merge`, `graduate`, `archive`) is strictly restricted to designated consolidation routines via `--routine <name>`:
  1. `dream-cycle` (End-of-day workflow consolidating daily turns)
  2. `system-improvement` (Weekly cross-age consolidation, joining, cleaning, and graduation)
  3. `manual-review` / `memory-human-review` (Interactive resolution of staged factual ambiguities)
- **Zero Redundant Double-Processing (LLM vs Jev):**
  During `dream-cycle` and `system-improvement`, the consolidating LLM is already reading the transcripts and memory index to synthesize text. Do not run redundant Jev gatekeeping loops after LLM synthesis. Reserve Jev for fast mid-conversation `query` retrieval where it prevents loading the entire short-term store into the main LLM context.

---

## 4. Pure Signal Standard (The 3-Part Anatomy)

Memory is not a dump of raw ticket numbers, git commits, or shell logs. It is the semantic bridge that captures the human and strategic context that software tools lose:
1. **Expectation vs Reality:** What did the stakeholder, user, or engineer expect, and what was the actual reality or mental model mismatch?
2. **Operational Action:** What concrete action was taken to address it?
3. **Forward Link:** What follow-up, verification, or definition remains open?

Never reject or discard a candidate solely because a ticket exists in an external tracker or code exists in Git.

---

## 5. Cross-Age Joining, Updating & Lifecycle Hygiene

- **Update & Join Across All Ages:**
  When newer data supersedes, resolves, or enriches an existing memory (whether created yesterday in `short-term.jsonl` or weeks ago in `long-term.jsonl`), update or merge the existing record in place (`manage_memory.py update` or `manage_memory.py merge`) rather than appending a disconnected duplicate.
- **Conversational Feedback Settling:**
  When the user provides verbal guidance during a work session, apply it immediately to the task at hand; do not run ad-hoc memory ingestion mid-turn.
