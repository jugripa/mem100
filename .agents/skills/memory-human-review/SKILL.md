---
name: memory-human-review
description: Asynchronously review ambiguous memory candidates staged in memory/PENDING_REVIEW.md.
---

# Memory Human Review Skill

## Purpose
This skill serves as the **human-in-the-loop bridge** for the unified memory system. Whenever daily harvesting (`dream-cycle`) or weekly meta-reviews (`system-improvement`) detect factual ambiguities or conflicting signals that cannot be verified from primary sources, they stage them in `memory/PENDING_REVIEW.md` rather than guessing.

---

## Workflow Playbook

### Step 1: Inspect the Pending Review Queue
Open and read `memory/PENDING_REVIEW.md`.

If the file contains only the placeholder (`_No ambiguous memories currently pending review._`), report that the memory queue is clean and no action is required.

---

### Step 2: Review Ambiguous Memories One by One
If there are items under **## 1. Ambiguous Memories Awaiting Clarification**, present them to the user **one by one**:

1. Display the item's:
   - **Title**
   - **Source Session**
   - **The Ambiguity Detected**
   - **Candidate Summary & Rationale**
   - **The Specific Question for Human Reviewer**
2. Ask the user for their directive:
   - **Option A: Confirm (Approve):** Memory is verified as valid (`short-term` or `long-term`).
   - **Option B: Eject (Reject):** Candidate is invalid, exploratory noise, or discarded.
   - **Option C: Enrich (Clarify):** User provides ground-truth context, corrects the facts, or sets the exact policy.

#### Handling the Action:
- **If Confirmed or Enriched:**
  ```bash
  python3 scripts/manage_memory.py resolve-ambiguity \
    --ambiguity-id "<ID>" \
    --action approve \
    --tier short-term \
    --importance 0.85 \
    --title "<Optional Corrected Title>" \
    --summary "<Optional Corrected 3-Part Summary>" \
    --content "<Enriched Rationale>" \
    --notes "<Optional Review Notes>"
  ```

- **If Ejected:**
  ```bash
  python3 scripts/manage_memory.py resolve-ambiguity \
    --ambiguity-id "<ID>" \
    --action reject \
    --notes "<Reason for rejection>"
  ```
