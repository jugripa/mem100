# Weekly System Improvement & Memory Consolidation Workflow

## Purpose
A scheduled, autonomous weekly meta-improvement routine over past conversation transcripts and the unified memory store. It audits user friction points, detects repeated workflows for potential new skills, and executes cross-age memory consolidation across `memory/short-term.jsonl` and `memory/long-term.jsonl` (joining related memories, updating older memories with newer data, archiving resolved transient items, and graduating durable core truths to `long-term.jsonl`), compiling a comprehensive dossier at `sessions/system-improvement-YYYY-MM-DD.md`.

This workflow runs autonomously without requiring redundant per-record Jev API loops.

---

## Invocation Modes
1. **Dynamic Scheduled Mode (Recommended):** Audits all unharvested sessions since the previous system improvement run using routine watermark tracking.
2. **Status & History Inspection:**
   ```bash
   python3 scripts/system_improvement.py --status
   ```
3. **Catch-up Mode:**
   ```bash
   python3 scripts/system_improvement.py --catch-up --output sessions/system-improvement-$(date +%F).md
   ```
4. **Fixed Lookback Window:**
   ```bash
   python3 scripts/system_improvement.py --days 7 --output sessions/system-improvement-$(date +%F).md
   ```

---

## Weekly Execution Routine

### Step 1: Run the Deterministic Audit & Consolidation Brief
```bash
python3 scripts/system_improvement.py --output sessions/system-improvement-$(date +%F).md
```

This script runs instantaneously with zero redundant Jev token spend and generates `sessions/system-improvement-YYYY-MM-DD.md` containing:
- User corrections and friction triggers.
- Context discovery gaps.
- **Cross-Age Memory Consolidation Brief:**
  - `A. Cross-Age Overlap Pairs`: Candidate pairs across `short-term.jsonl` and `long-term.jsonl` (regardless of age) sharing entities, pointers, or lexical overlap.
  - `B. Existing & Older Memories Touched by This Week's Activity`: Memories from previous days, weeks, or months referenced or evolved in recent sessions.
  - `C. Core Graduation Candidates`: High-importance (`>= 0.88`, or `>= 0.85` with `>= 2` pointers) working memories with zero unresolved open loops ready to graduate to `long-term.jsonl`.
  - `D. Stale / Decayed Pruning Candidates`: Older working memories (`recency < 0.35`, `importance < 0.85`) untouched by recent work.

### Step 2: Review, Modify, Join, Clean & Graduate Memories (`manage_memory.py`)
Using the generated consolidation brief and `python3 scripts/manage_memory.py list`, review only the specific leaf dossiers (`memory/leaf-files/<id>.md`) flagged in the brief and execute the appropriate consolidation operations with `--routine system-improvement`:

1. **Join & Merge Related Memories Across Any Age (`merge`):**
   ```bash
   python3 scripts/manage_memory.py merge \
     --routine system-improvement \
     --target-id "<primary_id>" \
     --source-ids "<id_2,id_3>" \
     --title "<Consolidated Title>" \
     --summary "<Consolidated 3-part Pure Signal summary>" \
     --questions "<Trigger question 1>;<Trigger question 2>" \
     --decisions "<Consolidated decisions>" \
     --open-loops "<Remaining open loops>" \
     --replace-atoms
   ```
2. **Update Older Memories with Newer Data (`update`):**
   ```bash
   python3 scripts/manage_memory.py update \
     --routine system-improvement \
     --id "<mem_id>" \
     --summary "<Updated summary>" \
     --decisions "<Updated decisions>" \
     --open-loops "<Updated open loops>" \
     --replace-atoms
   ```
3. **Graduate Durable Core Truths (`graduate`):**
   ```bash
   python3 scripts/manage_memory.py graduate \
     --routine system-improvement \
     --id "<mem_id>"
   ```
4. **Clean & Archive Obsolete or Resolved Loops (`archive`):**
   ```bash
   python3 scripts/manage_memory.py archive \
     --routine system-improvement \
     --id "<mem_id>" \
     --reason "<Why resolved or superseded>"
   ```
