# Memory Governance & Mandatory Retrieval Reflex

* **Unified Two-Tier Store:** All operational, architectural, and strategic memories live in `memory/long-term.jsonl` (Core Memory), `memory/short-term.jsonl` (Working Memory), and `memory/leaf-files/<id>.md` (Context Dossiers). Separate `decisions/log.md` files or category folders are not used.
* **Mandatory Turn-1 Grounding (`context`):** At the start of every session, load core memory:
  ```bash
  python3 scripts/manage_memory.py context
  ```
* **Mandatory Task-Arrival Query (`query`):** Whenever a task, project, bug, question, or topic shift arrives, query memory before grepping raw logs or guessing:
  ```bash
  python3 scripts/manage_memory.py query --task "<specific topic, entity, or request>"
  ```
* **Read-Only Session Boundary:** Interactive conversational sessions are strictly read-only (`context`, `query`, `list`, `audit`). Memory mutations (`ingest`, `update`, `merge`, `graduate`, `archive`) are restricted to autonomous workflows (`.agents/workflows/dream-cycle.md`, `.agents/workflows/system-improvement.md`) and `.agents/skills/memory-management/SKILL.md`.
