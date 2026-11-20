# Architecture

| Page | Covers |
|---|---|
| [High-level design](hld.md) | Context, components, deployment views, key design decisions |
| [Request lifecycle](request-lifecycle.md) | One question end to end, as a sequence diagram |
| [LLD: Workflow & nodes](lld-workflow.md) | The ADK 2.x graph, each node's contract, routing rules |
| [LLD: Procedural knowledge graph](lld-procedural-graph.md) | Nodes, edges, search ranking, the compile algorithm |
| [LLD: DAG executor](lld-executor.md) | Call kinds, templating, the path language, parallelism, failure handling |
| [LLD: Memory stores](lld-memory.md) | Every store, its schema and who reads or writes it |
| [LLD: Learning & improvement](lld-learning.md) | The `learn` node, distillers, consolidation, GEPA |
| [LLD: Ingestion pipeline](lld-ingestion.md) | Extract, canonicalise, resolve, infer, validate, stage, apply |
| [LLD: Model provider layer](lld-models.md) | Spec parsing, fallback, reasoning and caching parameters |
| [LLD: Plugins & tools](lld-plugins.md) | Built-in and custom plugins, the tool surface |
