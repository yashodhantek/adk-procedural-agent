# Installation

## Requirements

- Python **3.11+**
- SQLite with FTS5. This is standard in CPython builds; the agent falls back to plain lexical search without it.
- Model access: one of a Gemini API key, Vertex AI, OpenAI, Azure OpenAI, TrueFoundry, or any LiteLLM provider.

## Install

```bash
git clone https://github.com/yashodhantek/adk-procedural-agent
cd adk-procedural-agent
python -m venv .venv && source .venv/bin/activate

pip install -e ".[dev,llms]"      # core + tests + LiteLLM (OpenAI, Azure, TrueFoundry, Anthropic...)
cp .env.example .env              # then edit .env
```

| Extra | Adds | Install when |
|---|---|---|
| *(none)* | `google-adk`, `httpx`, `python-dotenv` | You only use Gemini |
| `llms` | `litellm` | You use OpenAI, Azure OpenAI, TrueFoundry, Anthropic, Bedrock, Ollama… |
| `optimize` | `google-adk[eval]`, `gepa` | You run the [GEPA prompt optimiser](../capabilities/self-improvement.md) |
| `vertex` | `google-adk[extensions]` | You use Agent Engine sessions and Memory Bank |
| `dev` | `pytest`, `litellm` | You run the tests |

## Verify

```bash
python -m pytest -q
# 38 passed
```

The tests drive the real ADK 2.x workflow end to end with a scripted model and mock HTTP APIs, so
they need no keys and no network.

## Project layout

```text
procedural_agent/
  agent.py          root_agent (Workflow) + app (App: plugins, compaction, cache, resumability)
  llm.py            model specs -> Gemini / LiteLlm / FallbackLlm; reasoning & caching parameters
  config.py         every setting, read from the environment
  schemas.py        Plan / Verdict structured outputs
  prompts/          versioned prompt templates (planner, synthesizer, critic)
  memory/           procedural_kg, glossary, semantic, reflection, skill_registry, services, store
  harness/          nodes, executor, learner, plugins, tools, ingest, search
  seed/             procedures.json, glossary.json
synthesizer_lab/    target agent for the GEPA optimiser + eval set
evals/              eval criteria, sampler and optimiser configs
examples/           sop_travel_cards.md
scripts/            run_cli.py, ingest.py, improve.py, generate_doc_examples.py
tests/              38 offline tests
docs/               this site
```
