# MEM100: Autonomous Agent Memory & Continuous Self-Improvement Engine

![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Version](https://img.shields.io/badge/Version-v2.0.0-purple.svg)
![Environment](https://img.shields.io/badge/Harnesses-Antigravity%20%7C%20Claude%20Code%20%7C%20Cursor-orange.svg)
![Technologies](https://img.shields.io/badge/Tech-Python%203.10%2B%20%7C%20TypeSafe%20Jev%20%7C%20Okapi%20BM25-green.svg)

A domain-agnostic, zero-dependency Python memory and self-improvement engine for AI coding and operational agents (Antigravity, Claude Code, Cursor, Windsurf, or custom LLM harnesses).

Designed so that **any engineer or AI agent can replicate or drop in the entire memory architecture simply by reading this repository**.

- **Full Technical Specification:** [`docs/ARCHITECTURE_GUIDE.md`](./docs/ARCHITECTURE_GUIDE.md)
- **Version History & Design Rationale:** [`CHANGELOG.md`](./CHANGELOG.md)
- **Future Experiments & Research Roadmap:** [`EXPERIMENTS.md`](./EXPERIMENTS.md)

---

## 1. Why This Architecture Works

Most agent memory systems fail in one of three ways:
1. **Dimension Silos:** Splitting memories into rigid folders (`decisions/`, `open-loops/`, `facts/`) fragments context because a single real-world event usually contains a decision, domain context, and an open follow-up simultaneously.
2. **Retrieval Blindspots:** Relying on the agent to "remember to search memory" means memory is almost never consulted unless the user explicitly prompts for it. Or worse, naive keyword search misses relevant memories when phrasing differs.
3. **Token Bloat at Ingestion:** Running secondary LLM/classifier loops after an LLM has already synthesized a memory wastes tokens and falsely rejects valid context.

### The Unified Two-Tier Solution (v2.0)
- **Unified Two-Tier JSONL + Markdown Store (Zero Silos):**
  - `memory/long-term.jsonl` (**Core Memory**): Durable domain truths, architectural constraints, active commitments, and policies. Loaded automatically on Turn 1 of every session (`< 4,000` tokens).
  - `memory/short-term.jsonl` (**Working Memory**): Active sprint/work threads, recent decisions, and unresolved open loops. Queried automatically whenever a task or topic arrives.
  - `memory/leaf-files/<id>.md` (**Context Dossiers**): 1-to-1 Markdown dossiers with full rationale, primary-source pointers, and revision history.
- **Enriched Retrieval Metadata:**
  - Continuous `importance` weight (`0.0 - 1.0`, no brittle decay horizon labels).
  - 3-part Pure Signal `summary` (`Expectation vs Reality -> Operational Action -> Forward Link`).
  - Natural-language trigger `questions` (3-4 phrasings a user or agent would ask when needing this memory).
  - Structured `atoms` (`decisions_and_why`, `open_loops`, `commands_or_refs`), `entities`, `people`, and `pointers`.
- **1-Call Batched TypeSafe Jev Retrieval (`~0.25s - 0.35s`) + Local Okapi BM25 Backup (`< 5ms`):**
  - Evaluates all active memories in a single HTTP request to TypeSafe Jev (`Choice` per record + competitive `primary_match`, default threshold `0.55`), weighted with exponential recency ($\text{Recency} = e^{-\text{age\_days}/30.0}$, $\tau = 30.0$ days) and importance, gated by a low-semantic filter (`P_sem < 0.25 -> 0.50 * P_sem`):
    $$\text{Score}(m_i) = \begin{cases} 0.50 \cdot P_{\text{sem}}(m_i), & \text{if } P_{\text{sem}}(m_i) < 0.25 \\ \min\left(1.0,\; 0.65 \cdot P_{\text{sem}}(m_i) + 0.20 \cdot e^{-\text{age\_days}/30.0} + 0.15 \cdot \text{Importance}(m_i)\right), & \text{if } P_{\text{sem}}(m_i) \ge 0.25 \end{cases}$$
  - Automatically falls back to local **Okapi BM25 ($k_1 = 1.5, b = 0.75$) + Recency + Importance** (effective threshold `min(threshold, 0.45)`) when offline or when `TYPESAFE_API_KEY` is not configured.
- **Cross-Age Consolidation (`dream-cycle` & `system-improvement`):**
  - Direct LLM ingestion during end-of-day consolidation (zero redundant post-LLM Jev gatekeeping).
  - First-class `update`, `merge`, `graduate`, and `archive` commands that work across both `short-term.jsonl` and `long-term.jsonl` regardless of record age.

---

## 2. Repository Structure

```text
.
├── .agents/
│   ├── rules/
│   │   └── memory-governance.md          # Mandatory retrieval & write-authority rules
│   ├── skills/
│   │   ├── memory-human-review/SKILL.md  # Interactive resolution for PENDING_REVIEW.md
│   │   └── system-review/SKILL.md        # Interactive review for weekly consolidation
│   └── workflows/
│       ├── dream-cycle.md                # Daily end-of-day memory consolidation workflow
│       └── system-improvement.md         # Weekly cross-age consolidation & friction audit
├── decisions/
│   └── log.md                            # Append-only ledger of system/rule decisions
├── docs/
│   └── ARCHITECTURE_GUIDE.md             # Deep-dive technical specification & math
├── memory/
│   ├── audit/                            # raw_events.jsonl + YYYY-W%W.md weekly ledgers
│   ├── leaf-files/                       # Full-context Markdown dossiers (<id>.md)
│   ├── long-term.jsonl                   # Core Memory (loaded at session start)
│   ├── short-term.jsonl                  # Working Memory (queried on task arrival)
│   └── PENDING_REVIEW.md                 # Human review queue for ambiguous facts
├── scripts/
│   ├── harvest_conversations.py          # Multi-runtime differential transcript harvester
│   ├── manage_memory.py                  # Core two-tier memory & retrieval CLI engine
│   └── system_improvement.py             # Deterministic weekly audit & consolidation brief
├── .env.example                          # Optional TYPESAFE_API_KEY configuration
├── CHANGELOG.md                          # Architectural evolution & bug fixes
└── README.md                             # Installation & replication guide
```

---

## 3. Quickstart & Installation (Drop-In to Any Project)

### Step 1: Copy Files into Your Agent Workspace
Copy `scripts/`, `.agents/`, `memory/`, `decisions/`, `docs/`, and `.env.example` into the root of your project repository:

```bash
cp -r scripts .agents memory decisions docs .env.example /path/to/your-agent-repo/
cd /path/to/your-agent-repo/
```

### Step 2: Configure Environment (Optional)
The engine requires **Python 3.10+** and uses only the Python standard library.
If you want 1-call TypeSafe Jev semantic retrieval, copy `.env.example` to `.env` and set `TYPESAFE_API_KEY`:

```bash
cp .env.example .env
# Edit .env and set TYPESAFE_API_KEY=ts_...
```
*(If `TYPESAFE_API_KEY` is omitted, `manage_memory.py query` automatically uses the built-in local Okapi BM25 + Recency + Importance engine).*

### Step 3: Initialize the Unified Memory Store
```bash
python3 scripts/manage_memory.py init
```

### Step 4: Add the Memory Reflex to Your `AGENTS.md` / `CLAUDE.md`
Paste the following section into your root `AGENTS.md` (or `CLAUDE.md` / system prompt):

```markdown
## Memory Architecture (The Memory Reflex)

This workspace uses a unified two-tier memory system (`scripts/manage_memory.py`) governed by `.agents/rules/memory-governance.md`:
- `memory/long-term.jsonl` (Core Memory: durable truths, architectural constraints, active commitments, policies).
- `memory/short-term.jsonl` (Working Memory: active work threads, recent decisions, open loops).
- `memory/leaf-files/<id>.md` (Markdown context dossiers with source pointers and revision history).

### Mandatory Retrieval Protocol
1. **Always at Conversation Start (`long-term.jsonl`):** Load core memory on Turn 1 of every session:
   ```bash
   python3 scripts/manage_memory.py context
   ```
2. **On Every Task or Topic Arrival (`short-term.jsonl` + `long-term.jsonl`):** Whenever a task, feature, bug, or question arrives (or shifts mid-session), query memory before grepping raw logs or guessing:
   ```bash
   python3 scripts/manage_memory.py query --task "<specific topic, entity, or request>"
   ```
3. **Read-Only Session Boundary:** Normal conversational sessions are strictly read-only (`context`, `query`, `list`, `audit`). Memory writes (`ingest`, `update`, `merge`, `graduate`, `archive`) are restricted to consolidation routines (`.agents/workflows/dream-cycle.md` and `.agents/workflows/system-improvement.md`).
```

---

## 4. Complete CLI Reference (`scripts/manage_memory.py`)

### Initialization & Read Operations (Available in All Sessions)
```bash
# 0. Initialize Unified Memory Store
python3 scripts/manage_memory.py init

# 1. Load Core Memory at Conversation Start
python3 scripts/manage_memory.py context [--include-open-loops] [--json]

# 2. Query Working + Core Memory on Task Arrival (1-call Jev or local BM25 backup)
python3 scripts/manage_memory.py query --task "how should webhook retries be handled?" \
  [--tier {short-term,long-term,all}] [--threshold 0.55] [--top-k 8] [--no-fallback-long] [--offline] [--json]

# 3. List Stored Memories Across Tiers
python3 scripts/manage_memory.py list [--tier {short-term,long-term,all}] [--status {active,archived,graduated,all}]

# 4. Inspect Telemetry Audit Events
python3 scripts/manage_memory.py audit [--limit 20]
```

### Consolidation Write Operations (Restricted to `--routine` or `--allow-adhoc`)
```bash
# 5. Ingest a New Pure Signal Memory (or auto-update if title matches an active record)
python3 scripts/manage_memory.py ingest \
  --routine dream-cycle \
  --title "Webhook Retry Idempotency Standard" \
  --summary "Expected Stripe webhooks to be delivered once, but network timeouts caused duplicate POSTs. Added idempotency key check in payment handler. Must verify Redis TTL before production deploy." \
  --content "Full technical context and evidence..." \
  --importance 0.85 \
  --tier short-term \
  --questions "How do we prevent duplicate webhook processing?;Where is webhook idempotency enforced?" \
  --entities "PR-204,payment-service,Stripe" \
  --people "Alex,Sam" \
  --decisions "Enforce idempotency keys on all incoming Stripe webhooks" \
  --open-loops "Verify Redis TTL expiration under load" \
  --refs "PR-204" \
  --pointers "conv:e1e8416f-99ab-48d1,pr:PR-204" \
  --conv-id "e1e8416f-99ab-48d1"

# 6. Update an Existing Memory Across Any Tier or Age
python3 scripts/manage_memory.py update \
  --routine system-improvement \
  --id mem_20261026090512_82f10b \
  --summary "Updated 3-part Pure Signal summary..." \
  --open-loops "" \
  --replace-atoms

# 7. Merge Overlapping Memories Across Any Tier or Age
python3 scripts/manage_memory.py merge \
  --routine system-improvement \
  --target-id mem_primary_id \
  --source-ids "mem_dup_1,mem_dup_2" \
  --title "Consolidated Title" \
  --summary "Consolidated 3-part Pure Signal summary..." \
  --replace-atoms

# 8. Graduate a Durable Working Memory to Core Long-Term Memory
python3 scripts/manage_memory.py graduate \
  --routine system-improvement \
  --id mem_20261026090512_82f10b

# 9. Archive a Resolved or Obsolete Memory
python3 scripts/manage_memory.py archive \
  --routine system-improvement \
  --id mem_20261026090512_82f10b \
  --reason "Open loop resolved and merged in PR-204."

# 10. Stage or Resolve Factual Ambiguities in memory/PENDING_REVIEW.md
python3 scripts/manage_memory.py stage-ambiguity \
  --routine dream-cycle \
  --title "Candidate Title" \
  --summary "Candidate 3-part summary" \
  --reason "Conflicting SLA numbers in session transcript" \
  --question "Is the SLA 24h or 48h?"

python3 scripts/manage_memory.py resolve-ambiguity \
  --id MEM-REV-20261026120000_a1b2c3 \
  --action approve \
  --tier short-term \
  --importance 0.85 \
  --title "Optional Corrected Title" \
  --summary "Optional Corrected 3-Part Summary" \
  --content "Verified 24h SLA with engineering lead." \
  --notes "Approved during weekly review."
```

---

## 5. Adapting to Different Domains & Harnesses

### Adapting Across Domains
The schema (`title`, `summary`, `questions`, `entities`, `people`, `atoms`, `pointers`) is domain-agnostic. Only the semantic content of your fields changes by domain:
- **Software Engineering / DevOps:**
  - `entities`: Service names, PR numbers, database tables, error codes.
  - `atoms.decisions_and_why`: Architectural invariants, library choices, schema migrations.
  - `atoms.commands_or_refs`: File paths, CLI diagnostic commands, PR URLs.
- **Product Management / Operations:**
  - `entities`: Epic IDs, customer accounts, product modules, support tickets.
  - `atoms.decisions_and_why`: Scope cuts, SLA commitments, stakeholder sign-offs.
  - `atoms.open_loops`: Pending stakeholder approvals, unverified requirements.
- **Research / Data Science:**
  - `entities`: Datasets, experiment IDs, model checkpoints, papers.
  - `atoms.decisions_and_why`: Hyperparameter selections, falsified hypotheses, benchmark baselines.

### Adapting `harvest_conversations.py` to Non-Antigravity Harnesses
By default, `scripts/harvest_conversations.py` reads Antigravity JSONL transcripts (`~/.gemini/antigravity*/brain/<id>/.system_generated/logs/transcript.jsonl`).
To connect another harness (such as Claude Code `~/.claude/projects/` or Cursor SQLite state):
1. Point `harvest_conversations.py` at your harness's session log directory.
2. Emit the same normalized turn dictionary (`turn_index`, `step_index`, `max_step`, `timestamp`, `user_prompt`, `tools_used`, `assistant_response`).
3. Everything downstream (`manage_memory.py`, `system_improvement.py`, `dream-cycle.md`, and `system-improvement.md`) works without modification.
