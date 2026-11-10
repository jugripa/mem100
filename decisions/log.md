# System Decisions Log

Append-only ledger of authorized system decisions, rule additions, and memory governance updates.

Format: `[YYYY-MM-DD] DECISION: ... | REASONING: ... | CONTEXT: ...`

---

[2026-10-26] DECISION: Initialize Unified Two-Tier Memory Architecture (memory/long-term.jsonl, memory/short-term.jsonl, and memory/leaf-files/) with 1-call batched TypeSafe Jev retrieval and local Okapi BM25 fallback. | REASONING: Eliminate rigid dimension silos, avoid redundant post-LLM Jev gatekeeping at ingestion, and guarantee sub-second semantic recall on task arrival. | CONTEXT: Initial Autonomous Memory Engine deployment.
