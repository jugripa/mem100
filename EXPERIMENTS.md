# MEM100: Experiments, Future Improvements & Research Roadmap

**Project:** MEM100 (Autonomous Agent Memory & Continuous Self-Improvement Engine)  
**Status:** Living Engineering Backlog & Research Testbed  
**Related Guides:** [`README.md`](./README.md), [`CHANGELOG.md`](./CHANGELOG.md), [`docs/ARCHITECTURE_GUIDE.md`](./docs/ARCHITECTURE_GUIDE.md)  
**Inspiration & Benchmark References:** Jev-Mem (*Jiang et al., UT Dallas, arXiv:2609.23986v1, Sep 2026*), LoCoMo Benchmark (*Maharana et al., 2024*).

---

## 1. Overview & Research Objective

**MEM100** provides a domain-agnostic, token-mindful two-tier memory system with 1-call TypeSafe Jev semantic retrieval, local Okapi BM25 backup, and deterministic cross-age consolidation. It solves the primary operational challenges of agent harnesses: eliminating dimension silos, ensuring persistent ambient context on Turn 1, and maintaining clean life-cycle hygiene without runaway token costs.

This document outlines experimental capabilities, algorithmic tests, and future improvements to be evaluated in future iterations of MEM100. The primary goal of these experiments is to test whether multi-relational graph primitives and closed-loop adaptive control can further improve reasoning accuracy for complex multi-hop and causal tasks without compromising our sub-second latency (`< 0.35s`), token efficiency, or operational simplicity.

---

## 2. Research Experiments & Test Specifications

### Experiment 1: Multi-Relational Dynamic Knowledge Graph ($M_t = (V_t, \{E_t^g\}, I_t^{vec}, I_t^{lex})$)

- **Problem Statement:**  
  Flat two-tier storage treats each memory record as an independent document. While enriched metadata (`atoms`, `pointers`, `questions`) enables fast competitive ranking, questions requiring multi-step causal or temporal chains (for example: *"Why did the architecture change after release 2.4, and which downstream services were impacted?"*) require the agent to synthesize links across disparate records.
- **Hypothesis:**  
  Superimposing a lightweight multi-relational graph on top of existing canonical leaf records ($V_t$) will improve multi-hop retrieval accuracy without creating rigid category silos.
- **Proposed Architecture:**
  - **Shared Memory Nodes ($V_t$):** All memories remain canonical records in `short-term.jsonl` and `long-term.jsonl` backed 1:1 by leaf dossiers (`memory/leaf-files/<id>.md`).
  - **Multi-Relational Edge Plane ($G$):** Four discrete edge sets over the same nodes:
    $$G = \{\text{semantic}, \text{temporal}, \text{causal}, \text{entity}\}$$
  - **System-One Dynamic Query Routing:** When a query arrives, TypeSafe Jev evaluates which graph views to activate:
    $$p(q) = \{p_{\text{semantic}}(q), p_{\text{temporal}}(q), p_{\text{causal}}(q), p_{\text{entity}}(q)\}$$
    A relation type is active when $p_g(q) \ge \theta_{\text{act}}$. Queries like *"Why did X fail?"* activate causal + temporal views, whereas *"What are the parameters for Y?"* activate only entity + semantic views.
  - **Traversal Budget ($B$):** Search effort is distributed across active views using Jev concentration weights:
    $$w_g(q) = \frac{p_g(q)^\gamma}{\sum_{j \in A(q)} p_j(q)^\gamma}$$
- **Test Protocol & Success Criteria:**
  - Construct a test suite of 30 complex multi-hop questions across domain historical decisions and architecture.
  - Baseline: Standard 1-call Jev retrieval over flat JSONL.
  - Treatment: Dynamic relational traversal seeded by hybrid anchors.
  - Target: $\ge 15\%$ improvement in multi-hop context recall, with total retrieval latency staying under $0.80\text{s}$.

---

### Experiment 2: Adaptive System-One Stopping Gates & Evidence Assessment

- **Problem Statement:**  
  Fixed top-$K$ retrieval either stops too early (missing necessary evidence when queries require several supporting records) or retrieves too many records (flooding the LLM context window with plausible distractors).
- **Hypothesis:**  
  Using lightweight System-One decisions to dynamically evaluate evidence completeness after each retrieval step allows the agent to terminate as soon as sufficient evidence is found, or abort when additional search is futile.
- **Proposed Architecture:**
  - After retrieving candidate set $E_d$ at round $d$, TypeSafe Jev evaluates four bounded probabilistic judgments:
    1. $s_d$: Evidence sufficiency (does $E_d$ directly answer the query?)
    2. $u_d$: Expected utility of further retrieval (is searching more nodes likely to help?)
    3. $m_d$: Missing required evidence (are critical facets still absent?)
    4. $c_d$: Unresolved contradictions (do collected records present conflicting claims?)
  - **Adaptive Stopping Rule:**
    $$\text{Terminate if } (s_d \ge \theta_{\text{suff}} \land m_d < \theta_{\text{cont}} \land c_d < \theta_{\text{cont}}) \lor (u_d < \theta_{\text{cont}})$$
- **Test Protocol & Success Criteria:**
  - Evaluate on queries with varying complexity (single-fact lookup vs conflicting historical decisions vs multi-file bug investigations).
  - Target: Zero unnecessary second-round retrieval for single-hop queries; $> 90\%$ detection rate of unresolved contradictions before LLM response generation.

---

### Experiment 3: Reciprocal Rank Fusion (RRF) for Multi-Index Anchoring

- **Problem Statement:**  
  Our primary retrieval uses TypeSafe Jev, with local Okapi BM25 as an offline fallback. When scaling to heterogeneous knowledge sources (for example, combining code maps, commit logs, and memory leaf files), linear score combinations can be sensitive to score distribution scales.
- **Hypothesis:**  
  Reciprocal Rank Fusion provides a parameter-free, scale-invariant entry point to seed anchor memories before scoring.
- **Proposed Architecture:**
  - Fuse lexical ranking (BM25) and dense semantic ranking (or Jev candidate ranking) using the standard RRF formula:
    $$s_{RRF}(v, q) = \sum_{L \in \{L_{\text{lex}}, L_{\text{sem}}\}} \frac{1}{\kappa + \text{rank}_L(v)}$$
    where constant smoothing parameter $\kappa = 60$.
  - The top-$W$ RRF candidates initialize the active candidate set before full atom expansion.
- **Test Protocol & Success Criteria:**
  - Benchmark vocabulary-mismatch test cases (queries using colloquial user phrasing that does not appear verbatim in memory titles).
  - Target: Verify that RRF achieves equivalent or superior candidate selection compared to linear interpolation without requiring weight tuning.

---

### Experiment 4: Explicit Directional Causal Invalidation

- **Problem Statement:**  
  Decisions and technical constraints evolve over time. While periodic consolidation merges and updates records, agents handling multi-step tasks can mistakenly read an older constraint if a newer superseding record is retrieved alongside it.
- **Hypothesis:**  
  Explicit directional causal relationships ($A \xrightarrow{\text{supersedes}} B$, $C \xrightarrow{\text{invalidates}} D$) allow retrieval scoring to automatically suppress superseded memories or warn the agent of an active invalidation.
- **Proposed Architecture:**
  - Extend the JSONL schema to support optional directional edges:
    ```json
    {
      "relations": [
        {"type": "supersedes", "target_id": "mem_2026_09_12_legacy_auth", "status": "active"},
        {"type": "invalidated_by", "target_id": "mem_2026_10_20_auth_v2", "reason": "Replaced by OAuth2 PKCE"}
      ]
    }
    ```
  - During retrieval scoring, if record $B$ is flagged as `invalidated_by` another retrieved candidate $A$, candidate $B$'s ranking score is penalized or filtered out, preventing contradictory instructions from entering the agent's context.
- **Test Protocol & Success Criteria:**
  - Simulate deprecated configuration rules and superseded architecture decisions.
  - Target: $100\%$ suppression of invalidated records when the superseding record is active and present in the candidate set.

---

### Experiment 5: Candidate Relation Linking over $K_w$ Pairs on Ingestion

- **Problem Statement:**  
  Discovering connections between newly ingested memories and existing historical memories currently relies on deterministic string overlap (`entities`, `people`, `pointers`). Subtle semantic relationships across different naming conventions can be missed.
- **Hypothesis:**  
  Applying a bounded System-One candidate relation judgment over at most $K_w$ candidates during periodic maintenance can infer non-obvious links without running an open-ended LLM prompt.
- **Proposed Architecture:**
  - Step 1: Use deterministic hybrid search (BM25 + shared entities + temporal proximity) to retrieve at most $K_w = 5$ candidate memories.
  - Step 2: A single batched TypeSafe Jev call estimates directional relation probabilities $P(\text{causal} \mid v, u)$, $P(\text{semantic} \mid v, u)$, and $P(\text{temporal} \mid v, u)$.
  - Step 3: Insert inferred edge if $P(g \mid v, u) \ge \theta_{\text{rel}}$ (default $\theta_{\text{rel}} = 0.70$).
- **Test Protocol & Success Criteria:**
  - Run during the periodic consolidation pass.
  - Measure execution time (must add less than $3\text{s}$ total to the routine) and evaluate the precision of newly proposed links against human review.

---

### Experiment 6: Focused Memory Pods (Subject-Specific, Human-Gated Stores)

- **Problem Statement:**  
  As an agent accumulates deep domain history across distinct complex subjects (such as long-term product roadmaps, deep architecture specs, or client security policies), storing all specialized records inside a single general memory store introduces two risks:
  1. Context pollution: Specialized historical details dilute general daily task ranking and introduce distractors during everyday tasks.
  2. Unnecessary token consumption: Loading or querying deep specialized records during routine bug triage or quick status checks wastes context bandwidth.
- **Hypothesis:**  
  Creating isolated, subject-specific memory pods (e.g. `memory/focused/roadmap/`) governed by the same MEM100 engine but kept dormant until explicit human request preserves lean daily operations while unlocking deep historical recall when summoned.
- **Proposed Architecture:**
  - **Storage Namespaces:** Support isolated memory stores alongside the main store (e.g. `--store roadmap` pointing to `memory/focused/roadmap/` with its own `long-term.jsonl`, `short-term.jsonl`, and `leaf-files/`).
  - **Retrieval Gating (Human-in-the-Loop Gate):**
    - Unlike the ambient memory reflex (`context` on Turn 1 and task-triggered `query` for general operations), focused memory pods are **never automatically queried or loaded**.
    - They activate strictly upon:
      1. Direct human prompt or instruction (for example: *"Check roadmap memory for past decisions on multi-org billing"*).
      2. Explicit CLI invocation (`manage_memory.py query --store roadmap --task "..."`).
      3. Specialized domain workflows explicitly triggered by the user (such as `manage-roadmap`).
  - **Dream-Cycle Ingestion & Focused Session Detection:**
    - Memories of focused sessions are detected naturally during the end-of-day `dream-cycle` workflow.
    - When the consolidating LLM analyzes conversation transcripts, it identifies whether a session or turn block focused on a designated subject (such as a roadmap planning session, architectural review, or client strategy discussion).
    - Decisions, trade-offs, and open loops from that focused session are synthesized and routed directly into the designated focused pod (e.g. `manage_memory.py ingest --store roadmap`), keeping specialized records cleanly partitioned from the general operational store.
- **Test Protocol & Success Criteria:**
  - Implement a prototype roadmap memory pod (`memory/focused/roadmap/`).
  - Verify that general daily queries (`manage_memory.py query`) have zero latency degradation and zero distractor interference from roadmap records.
  - Test on-demand retrieval for 15 complex roadmap questions, verifying 100% precision when explicitly summoned.

---

## 3. Prioritized Experiment Backlog

| Priority | ID | Experiment Title | Complexity | Expected Value | Status |
| :---: | :---: | :--- | :---: | :---: | :---: |
| **P1** | `EXP-01` | **Directional Causal Invalidation (`supersedes` / `invalidated_by`)** | Low | High | Backlog |
| **P2** | `EXP-06` | **Focused Memory Pods (Subject-Specific, Human-Gated Stores)** | Low | High | Backlog |
| **P3** | `EXP-02` | **Adaptive Stopping & Contradiction Detection Gates ($s_d, u_d, c_d$)** | Medium | High | Backlog |
| **P4** | `EXP-03` | **Multi-Relational Graph Traversal ($M_t = (V_t, \{E_t^g\})$) Prototype** | High | High | Backlog |
| **P5** | `EXP-04` | **Reciprocal Rank Fusion (RRF) for Multi-Source Index Entries** | Low | Medium | Backlog |
| **P6** | `EXP-05` | **Bounded System-One Relation Linking on Ingestion ($K_w = 5$)** | Medium | Medium | Backlog |

---

## 4. Test Harness & Evaluation Metrics

To ensure every experimental feature is evaluated rigorously before graduating to production, all tests will be benchmarked using four standardized metrics:

1. **Retrieval Precision@K & Recall@K:** Accuracy in recovering reference ground-truth memories for single-hop, multi-hop, and causal benchmark questions.
2. **End-to-End Query Latency:** Total retrieval wall-clock time. Target constraint: remain under $0.50\text{s}$ for single-hop queries and under $0.80\text{s}$ for multi-hop graph traversals.
3. **Token Efficiency:** Total token consumption on both read and write paths. Ingestion must remain strictly zero extra tokens for standard operations; periodic maintenance must not exceed $5,000$ tokens per run.
4. **Distractor Resistance (Adversarial Accuracy):** Ability to score zero or suppress false-positive memories that share lexical overlap but represent irrelevant or invalidated topics.
