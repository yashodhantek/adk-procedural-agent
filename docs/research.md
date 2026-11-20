# Research behind the design

| Idea | Paper | Where it lives here |
|---|---|---|
| A tool/procedure graph fused with SOP knowledge to guide planning | *Bridging Tool Dependencies and Domain Knowledge* (Amazon, 2025), [arXiv:2510.24690](https://arxiv.org/abs/2510.24690) | Procedural KG + [ingestion](capabilities/ingestion.md) of SOPs + glossary |
| Schema-level dependencies between tools → task DAG | *HyperAgent: Planning and Acting over Tool-Schema Hypergraphs* (2026), [arXiv:2608.02650](https://arxiv.org/pdf/2608.02650) | `DEPENDS_ON` mappings (input ← output); I/O-matching edge inference |
| Planner emits a DAG; independent calls run in parallel; replanning | *LLMCompiler* (ICML 2024), [arXiv:2312.04511](https://www.arxiv.org/abs/2312.04511v1) | Planner → compiler → [parallel levels](capabilities/parallel-execution.md); re-plan route |
| Dependency-aware sub-task graphs, parallel vs serial | *GAP: Graph-Based Agent Planning* (2025), [arXiv:2510.25320](https://arxiv.org/abs/2510.25320) | Kahn levels in `compile()` |
| Request-specific tool graphs; predicting missing dependencies | *GTool* (ICLR 2026), [poster](https://iclr.cc/virtual/2026/poster/10008576) | Dependency closure; edge inference in ingestion |
| Inducing reusable workflows from successful runs, built on earlier ones | *Agent Workflow Memory* (2024) | [Self-learning](capabilities/self-learning.md) induction of composites |
| Building, retrieving and updating procedural memory | *Memp* (2025) | Candidate → active → deprecated lifecycle; consolidation |
| Verbal self-reflection after failures | *Reflexion* (2023) | [Lessons](capabilities/reflection.md) |
| An evolving, curated context playbook | *Agentic Context Engineering (ACE)* (2025) | [Playbook](capabilities/reflection.md#playbook) with helpful/harmful counters |
| Reflective prompt evolution | *GEPA* (2025), as shipped in ADK 2.x | [`improve.py optimize`](capabilities/self-improvement.md) |
| Plan-then-act prompting | *ReAct* and ADK's `PlanReActPlanner` | [Reasoning fallback](capabilities/reasoning.md) |
| Benchmarking node, chain and DAG tool use | *TaskBench* (NeurIPS 2024) | The eval cases cover single, chain, parallel and composite shapes |
| Memory split across orchestrator and agents | *LEGOMem* (Microsoft, 2025) | Planner-level (plan cache, lessons) vs synthesizer-level (skills) memory |

A visual research map is kept on the project whiteboard.
