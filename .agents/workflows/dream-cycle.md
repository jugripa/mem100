# End-of-Day Dream Cycle Workflow

## Purpose
Like a human sleep cycle where the brain consolidates daily experiences into memory, the **Dream Cycle** runs at the end of each day to capture all work completed across sessions, extract high-signal memories with rich retrieval metadata into the unified memory store (`memory/short-term.jsonl`, `memory/long-term.jsonl`, and `memory/leaf-files/`), and update existing memories when newer data supersedes or enriches them.

---

## Workflow Steps

### Step 1: Harvest Daily Conversations & Inspect Existing Memory Index
1. Execute the conversation harvester using the routine-isolated differential cursor:
   ```bash
   python3 scripts/harvest_conversations.py --routine dream-cycle --cursor --update-cursor --summary
   ```
2. List the active memory index so you know which threads already exist in `long-term.jsonl` and `short-term.jsonl`:
   ```bash
   python3 scripts/manage_memory.py list
   ```

### Step 2: Candidate Extraction (Pure Signal + Enriched Search Surface)
Review the extracted conversation turns to identify high-signal operational events, expectation alignments, architectural or domain decisions, ruled-out proposals, and unresolved open loops.

**The Pure Signal Standard:**
Memory is not a duplication of issue trackers or Git commits. It provides the semantic bridge and the "why" that external tools lose. For every candidate, extract the 3-part Signal Anatomy in `--summary`:
1. **Expectation vs Reality:** What did the user, stakeholder, or engineer expect vs reality?
2. **Operational Action:** What concrete action was taken?
3. **Forward Link:** What follow-up remains?

**Enriched Metadata & Search Surface:**
For every candidate, synthesize:
- `--importance`: Float `0.0` to `1.0` (e.g. `0.75` for tactical threads, `0.85 - 0.95` for critical decisions, blockers, or policies). No discrete `horizon` classification is used.
- `--questions`: 2 to 4 semicolon-separated natural-language questions that someone or the agent would ask later when needing this memory.
- `--entities`: Comma-separated ticket IDs, repositories, services, or domain modules.
- `--people`: Comma-separated people or roles involved.
- `--decisions`, `--open-loops`, `--refs`: Semicolon-separated atomic bullets for `atoms`.
- `--pointers`: Source pointers (`conv:<id>`, `task:<id>`).

### Step 3: Update Existing Memories or Ingest New Records (Token-Mindful, Zero Jev Gatekeeper)
Because you (the consolidating LLM) have already read the full transcripts and synthesized the structured memory, `manage_memory.py` writes directly without making redundant Jev gatekeeping calls.

- **Case A: Evolves or Updates an Existing Memory (Recent or Older):**
  If today's work resolves an open loop, refines a rule, or advances an existing memory in `short-term.jsonl` or `long-term.jsonl`, update the existing record in place:
  ```bash
  python3 scripts/manage_memory.py update \
    --routine dream-cycle \
    --id "<existing_mem_id>" \
    --summary "<Updated 3-part Pure Signal summary>" \
    --content "<Updated detailed rationale and context>" \
    --questions "<Question 1>;<Question 2>" \
    --entities "<Entities>" \
    --people "<People>" \
    --decisions "<Decision 1>;<Decision 2>" \
    --open-loops "<Remaining open loop or empty if resolved>" \
    --replace-atoms \
    --conv-id "<source_conversation_id>"
  ```

- **Case B: Brand-New Operational Thread or Decision:**
  Invoke `manage_memory.py ingest` with `--routine dream-cycle`:
  ```bash
  python3 scripts/manage_memory.py ingest \
    --routine dream-cycle \
    --title "<Specific Operational Title>" \
    --summary "<3-part Pure Signal summary: Expectation vs Reality -> Action -> Forward Link>" \
    --content "<Detailed context, rationale, and evidence>" \
    --importance <0.00-1.00> \
    --tier short-term \
    --questions "<What question triggers this memory?>;<Second trigger phrasing>" \
    --entities "<Entities>" \
    --people "<People>" \
    --decisions "<Decision and why>" \
    --open-loops "<Unresolved follow-up>" \
    --refs "<Ticket/Repo/Doc refs>" \
    --pointers "<conv:<id>,task:<id>>" \
    --conv-id "<source_conversation_id>"
  ```
  *(Use `--flag-ambiguous "<reason>"` only if the conversation contains conflicting unverified facts that require manual human clarification in `memory/PENDING_REVIEW.md`).*

### Step 4: Memory Consolidation Verification
Verify that all ingestions and updates are logged in `memory/audit/raw_events.jsonl` and formatted in the weekly audit ledger (`memory/audit/YYYY-W%W.md`, e.g. `memory/audit/2026-W43.md`).
