# 10. Mixing model providers

A realistic mixed setup: GPT-5 through TrueFoundry for planning, Azure first (falling back to TrueFoundry, then Gemini) for answers, Claude as critic, a small OpenAI model for learning, and Gemini for summaries.

--8<-- "ex_providers.md"

## What to notice

- **TrueFoundry** specs become OpenAI-compatible LiteLLM calls to `$TFY_BASE_URL/api/llm` with the model id `<account>/<model>`, and the cache key travels in `extra_body`.
- **Reasoning `auto`** switched on for GPT-5 (a known reasoning model) and stayed off for the Azure deployment name `gpt-4o-prod`. That synthesizer therefore gets `PlanReActPlanner` instead.
- **Claude** with `CRITIC_REASONING=low` gets `reasoning_effort=low` (an extended-thinking budget) and system-prompt cache markers.
- **Gemini** roles use ADK's native client: thinking through `BuiltInPlanner`, caching through the context cache.

Related: [Multiple LLM providers](../capabilities/multi-llm.md) · [Reasoning](../capabilities/reasoning.md) · [Prompt caching](../capabilities/prompt-caching.md)
