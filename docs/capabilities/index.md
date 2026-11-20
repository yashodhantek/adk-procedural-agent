# Capabilities

Each page covers what the capability does, how it works, how to configure it, and a worked
example.

| Area | Capability | One line |
|---|---|---|
| **Reasoning over procedures** | [Planning & dependencies](planning.md) | One or many procedures per question; dependencies are added for you |
| | [Parallel execution](parallel-execution.md) | Independent steps run at the same time, level by level |
| | [Self-correction](self-correction.md) | Critic → accept / revise / re-plan, with bounded loops |
| **Memory** | [Procedural memory & skills](procedural-memory.md) | The graph, plan cache and reliability, exposed as ADK Skills |
| | [Glossary](glossary.md) | Users' words → canonical names and values |
| | [Memory](memory.md) | Working, session, user, episodic, semantic, artifacts |
| | [Context management](context-management.md) | Compaction, context filter, static/dynamic prompts |
| | [Reflection & playbook](reflection.md) | Lessons from mistakes; strategies that earn their place |
| **Getting better** | [Self-learning](self-learning.md) | New procedures induced, promoted and retired online |
| | [Self-improvement](self-improvement.md) | Consolidation, GEPA prompt optimisation, versioned prompts |
| | [Natural-language ingestion](ingestion.md) | SOPs → reviewed graph changes |
| **Models** | [Multiple LLM providers](multi-llm.md) | Gemini, OpenAI, Azure, TrueFoundry, Anthropic… with fallbacks |
| | [Reasoning](reasoning.md) | Thinking or reasoning effort per role, on every provider |
| | [Prompt caching](prompt-caching.md) | Stable prefixes and provider cache hints |
| **Tools & operations** | [Web search](web-search.md) | Google, Tavily, Exa, Brave or OpenAI behind one tool |
| | [Tools & MCP](tools-mcp.md) | Built-in tools, skills and any MCP server |
| | [MCP & LLM steps in procedures](mcp-procedures.md) | Any MCP tool or LLM prompt as a graph step: parallel, measured, learnable |
| | [Actions & approvals](actions-approvals.md) | Write steps are parked with an exact preview until you approve |
| | [Guardrails & safety](guardrails.md) | Allowlists, safe evaluation, budgets, staged writes |
| | [Observability & resumability](observability.md) | Logs, traces, reports, resumable runs |
