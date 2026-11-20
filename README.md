# ADK Procedural Agent

📖 **Documentation: https://yashodhantek.github.io/adk-procedural-agent/** (architecture, LLDs, capability guides, worked examples)

A self-learning agent for real-time data, built on **Google ADK 2.x** (tested on `google-adk==2.15.0`).
It turns a question into a plan over a **procedural memory knowledge graph**, fetches the data in
parallel, checks its own answer, and learns from every run.

```
recall ─▶ planner* ─▶ compile_plan ─▶ execute_plan ─▶ synthesizer* ─▶ prepare_review ─▶ critic* ─▶ gate
                                                          ▲                                       │
                                                          ├──────────── revise ◀──────────────────┤
           ▲                                                                                      │
           └────────────────────────────── replan ◀──────────────────────────────────────────────┤
                                                                       learn ◀─ respond ◀─ accept ┘
```
`*` = LLM agent. Every other node is plain Python (`FunctionNode`) in an ADK 2.x graph `Workflow`.

## Quick start

```bash
pip install -e ".[dev,llms]"
cp .env.example .env            # add GOOGLE_API_KEY (or Vertex settings)
python -m pytest                # 38 offline tests: scripted models, LiteLLM mocks, mock APIs, a local MCP server

# Option 1: CLI with persistent memory
python scripts/run_cli.py --user srini

# Option 2: ADK dev UI with persistent memory
adk web . --session_service_uri sqlite:///.data/sessions.sqlite \
          --memory_service_uri sqlite:///.data/episodic_memory.sqlite \
          --artifact_service_uri file://.data/artifacts
```

Questions to try:
- *What's the weather in Hyderabad and is the air OK for a run?* (composite procedure)
- *Convert 250 EUR to INR.* (dependent: `convert_amount` needs `get_fx_rate`)
- *Air quality in Delhi and the bitcoin price in INR.* (independent, so they run in parallel)
- *Earthquakes near Kathmandu this month, and the weather there?* (both share one geocode step)

## Models and providers

Every role has its own model setting (`AGENT_MODEL`, `PLANNER_MODEL`, `CRITIC_MODEL`, `LEARNER_MODEL`,
`SUMMARIZER_MODEL`), and each takes a model spec. `procedural_agent/llm.py` resolves the spec. Gemini runs
through ADK's native client; everything else goes through ADK's `LiteLlm` (`pip install -e ".[llms]"`).

| Spec | Provider | Settings |
|---|---|---|
| `gemini-3.5-flash` | Gemini (API key or Vertex AI) | `GOOGLE_API_KEY` or `GOOGLE_GENAI_USE_VERTEXAI` |
| `openai/gpt-4.1` | OpenAI | `OPENAI_API_KEY`, optional `OPENAI_BASE_URL` |
| `azure/<deployment>` | Azure OpenAI | `AZURE_API_KEY`, `AZURE_API_BASE`, `AZURE_API_VERSION` |
| `truefoundry/<provider-account>/<model>` | TrueFoundry AI Gateway (OpenAI-compatible) | `TFY_BASE_URL` (gateway = `/api/llm`) or `TFY_GATEWAY_URL`, `TFY_API_KEY`, optional `TFY_EXTRA_HEADERS` |
| `openai_compatible/<model>` | vLLM, LM Studio, LiteLLM proxy… | `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_KEY` |
| `anthropic/…`, `bedrock/…`, `ollama_chat/…` | anything LiteLLM supports | that provider's usual env vars |

Azure OpenAI through TrueFoundry is `truefoundry/<your-azure-account>/<model>`, using the provider-account name
shown in the TrueFoundry playground (for example `truefoundry/azure-openai-main/gpt-4o`).

**Fallback chains:** `AGENT_MODEL="azure/gpt-4o-prod|truefoundry/azure-openai-main/gpt-4o|gemini-3.5-flash"`.
`FallbackLlm` moves to the next model when one fails before producing output. Structured-output calls
(learning, ingestion) use the same chain.

**Mixing providers works**: for example, a strong planner on Azure, a cheap critic on OpenAI, and Gemini for search.

### Reasoning, caching and search on every provider

| Feature | Gemini | OpenAI / Azure / TrueFoundry | Anthropic (direct or Bedrock) |
|---|---|---|---|
| **Reasoning** (`PLANNER_REASONING`, `AGENT_REASONING`, `CRITIC_REASONING`) | `BuiltInPlanner` with `thinking_level` | `reasoning_effort` on the call | `reasoning_effort` (LiteLLM converts it to an extended-thinking budget) |
| No reasoning model | — | synthesizer gets `PlanReActPlanner` (prompted plan, act, answer; the plan is kept out of the answer) | same |
| **Prompt caching** | ADK `ContextCacheConfig` | automatic for a stable prefix of 1,024+ tokens, plus `prompt_cache_key` per role (sent in `extra_body` through TrueFoundry) | `cache_control` markers injected on the system prompt |
| **Web search** (`SEARCH_PROVIDER`) | Google Search grounding | Tavily / Exa / Brave, or `openai` (search models via `web_search_options`) | Tavily / Exa / Brave |

- **Reasoning levels:** `off | auto | minimal | low | medium | high`. `auto` turns reasoning on (medium) only when the
  model is known to reason, such as GPT-5, the o-series, Claude 4, or Gemini 2.5 and later. Azure and TrueFoundry deployment names
  often hide the model name, so set an explicit level for those.
- **Cacheable prompts:** each prompt is split at `<!-- dynamic -->`. The fixed part is sent as ADK's
  `static_instruction` (an identical system prefix every call). The learned playbook, lessons and preferences
  follow as user content, so learning doesn't break the cache.
- **Search:** `SEARCH_PROVIDER=auto` picks Gemini if a Gemini model is available (`SEARCH_MODEL` or `AGENT_MODEL`),
  then whichever of `TAVILY_API_KEY`, `EXA_API_KEY` or `BRAVE_API_KEY` is set, then `openai` if `SEARCH_MODEL` is an OpenAI
  model. The `web_search` tool returns `{title, url, snippet, published}` whatever the provider, and MCP search servers work alongside it.

The GEPA optimizer config (`evals/optimizer_config.json`) and the eval judges still use Gemini model names.

## How procedures and dependencies work

A **procedure** is a node in the graph. It has inputs, outputs, written steps, and optionally an
executable call spec (`http_json`, `compute` or `composite`). Its edges are:

| Edge | Meaning |
|---|---|
| `DEPENDS_ON {in: out}` | needs another procedure's outputs (for example, weather needs `latitude` from `geocode_city`) |
| `COMPOSED_OF` | a macro procedure made of other procedures (learned or seeded) |
| `USES_SOURCE` | which real-time source it reads, with reliability stats |

The planner only picks the procedures the question needs. `ProceduralKG.compile()` then:
1. expands composite procedures into their parts,
2. adds missing dependencies (dependency closure),
3. turns unknown procedures into `adhoc` steps, which the synthesizer handles with tools,
4. rejects cycles, and
5. groups steps into topological **levels**.

Steps in the same level run in parallel. If a step fails, the steps that depend on it are skipped,
but independent branches still finish.

Add your own domain in `procedural_agent/seed/procedures.json`. Users can also teach procedures in
chat (`teach_procedure`), and the agent induces new ones by itself.

## Glossary

`seed/glossary.json` (loaded once into SQLite) holds three kinds of entry:

```jsonc
{
  "parameters": [{"name": "longitude", "aliases": ["lon", "lng"], "unit": "degrees"},
                 {"name": "vs_currency", "format": "lower"}],          // canonical I/O names
  "values":     [{"canonical": "INR", "scope": ["from_currency", "to_currency", "vs_currency"],
                  "aliases": ["rupees", "₹", "rs"]}],                    // canonical values per parameter
  "concepts":   [{"term": "AQI", "aliases": ["air quality", "smog"],
                  "definition": "0-50 good, ...", "related_procedures": ["get_air_quality"]}]
}
```

- **recall** finds values and concepts in the question ("rupees", "go for a run") and gives the planner their meaning.
- **search** is expanded with canonical names and linked procedures, so "smog" finds `get_air_quality`.
- **compile_plan** normalises inputs (`base=dollars` → `from_currency=USD`), but never renames an input the procedure itself declares.
- **ingestion** canonicalises names in documents (`lat_deg`, `lng` → `latitude`, `longitude`) so dependencies can be matched.

You can add terms in four ways: edit the JSON, run `scripts/ingest.py glossary.json --glossary`, add `## Term:` cards to a document, or have users define them in chat (`define_term`). Parameter words such as "to" and "from" are ignored in prose, so they don't create false matches.

## Turning natural language into the graph

```
text → extract → canonicalise (glossary) → resolve & dedupe → infer edges → validate calls → stage → review → apply
```

```bash
python scripts/ingest.py docs/sops/                  # .md .txt .pdf .docx: prints a review, saves the batch
python scripts/ingest.py --apply-batch <id>          # apply confirmed edges only
python scripts/ingest.py --apply-batch <id> --approve "travel_budget_in_inr->get_fx_rate"   # or: --approve all
```
In chat, the agent uses `ingest_text`, shows you the review, and calls `apply_ingest` only after you confirm.

- **Extract.** Free text goes through Gemini with a strict schema. Files written as procedure cards are parsed deterministically, with no model needed (see `examples/sop_travel_cards.md`).
- **Resolve & dedupe.** A procedure that matches an existing one (same name, or similar description with the same inputs and outputs) becomes a new version of it, not a duplicate. Dependency phrases ("after looking up the coordinates") are mapped to procedures by name, text similarity and whether the candidate produces the inputs needed.
- **Infer edges.** An edge is *confirmed* when the text states it. It is marked *review* when the only evidence is an input matching another procedure's output. It is *rejected* if it would create a cycle.
- **Validate calls.** The host must be in `HTTP_ALLOWLIST`, and placeholders must be declared inputs. If the card gives `Sample:` values, the call is test-run against the live API (skip with `--no-test`). A call that fails the test is dropped, and the procedure is kept as written steps.
- **Apply.** Writes the terms, procedures (new ones start as `candidate`), sources and approved edges. A batch can be applied only once.

Procedure card format:
```markdown
## Procedure: get_uv_index
Description: Today's maximum UV index for a city.
Domain: weather
Inputs: lat_deg, lng
Outputs: uv_index_max
Needs: geocode_city (lat_deg->latitude, lng->longitude)
API: GET https://api.open-meteo.com/v1/forecast?latitude={lat_deg}&longitude={lng}&daily=uv_index_max
Extract: uv_index_max = daily.uv_index_max.0
Required: uv_index_max
Sample: lat_deg=17.38; lng=78.46
Steps:
1. Geocode the city.  2. Read today's max UV.

## Procedure: travel_budget_in_inr          (a calculation)
Inputs: amount, rate
Compute: budget_inr = round(amount * rate * 1.05, 2)

## Procedure: beach_day_check               (a bundle → composite)
Made of: city_conditions_brief, get_uv_index

## Term: latitude
Kind: parameter                             (parameter | value | concept)
Aliases: lat_deg, lat_degrees
Applies to: ...                             (values: which parameters)
Related: ...                                (concepts: procedure names)
```

## Memory techniques

| Memory | Implementation |
|---|---|
| Working / short-term | `temp:` session state per turn, plus session state (`turns`, `last_learning`) |
| Summarisation | ADK `EventsCompactionConfig` + `LlmEventSummarizer` (by interval and by token threshold) |
| Context window | `ContextFilterPlugin` cap + `ContextCacheConfig` (prompt prefix caching) |
| Episodic (long-term) | ADK memory service: `SqliteMemoryService` locally, `VertexAiMemoryBankService` in prod; written by `EpisodicMemoryPlugin`, read in `recall` and by the `load_memory` tool |
| Semantic | fact and preference store with FTS5 (`remember_fact` / `recall_facts` / `forget_fact`), mirrored to `user:` state |
| Procedural | the knowledge graph above, exposed as **ADK Skills** via a custom `SkillRegistry` (progressive disclosure: search, load, then resources) |
| Glossary | canonical parameter names, values and domain concepts with aliases; used to normalise plans, expand search and canonicalise ingested text |
| Plan memory | intent-signature plan cache, reused when a similar question comes back |
| Reflective | Reflexion lessons after a revised or failed run, injected into later prompts and skills |
| Strategic | ACE-style playbook bullets with helpful/harmful counters |
| Artifact | full raw payloads saved as artifacts, with only compacted data in prompts |
| Source/tool | per-source and per-tool reliability and latency, learned by `ToolLearningPlugin` |

## Harness features

- **Graph workflow** (ADK 2.x `Workflow`): routed loops for revise and replan, with per-node `RetryConfig`.
- **Self-correction**: critic → gate (accept / revise / replan), `ReflectAndRetryToolPlugin`, `ReflectAndRetryModelPlugin`.
- **Planning**: `BuiltInPlanner` (thinking) on the planner, with structured `Plan` output.
- **Guardrails**: HTTP host allowlist, safe expression evaluator, per-turn LLM budget (`BudgetGuardPlugin`), optional HMAC tool-call integrity.
- **Resumability**: `ResumabilityConfig(is_resumable=True)`.
- **Observability**: `LoggingPlugin` (`ADK_LOGGING=1`), `AutoTracingPlugin` OpenTelemetry (`ENABLE_TRACING=1`).
- **Tools**: executable procedures, generic JSON GET, `load_web_page`, Google Search (as an agent-tool), MCP servers (`MCP_SERVERS`), Skills.

## Self-learning and self-improvement

**Online (every turn, in `learn`):**
1. Execution stats update procedure and source reliability, which feeds search ranking.
2. A successful multi-procedure run is induced as a new composite procedure (Agent Workflow Memory).
   It starts as `candidate`, is promoted to `active` after `PROMOTE_AFTER` successes, and is
   deprecated if its reliability drops (Memp update).
3. Successful plans are cached for similar questions.
4. A draft that needed revision becomes a Reflexion lesson.
5. Playbook bullets are credited or blamed, and new bullets are curated (ACE).

**Offline (`scripts/improve.py`):**
- `report`: stats, the least reliable procedures and sources, and a Mermaid diagram of the graph.
- `consolidate`: deprecates weak procedures, merges duplicate composites, prunes the playbook, and drops stale lessons and plans. Run it nightly.
- `optimize`: runs **ADK's GEPA prompt optimizer** (`synthesizer_lab/` + `evals/`). The result is saved as a new prompt version and is activated only if its validation score beats the baseline. `rollback` reverts it.
  Needs `pip install -e ".[optimize]"`.

## Production

Set `MEMORY_BACKEND=vertex` plus `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_AGENT_ENGINE_ID` and
`ARTIFACT_BUCKET`. Sessions then go to Agent Engine, episodic memory to Memory Bank (LLM extraction
and consolidation), and artifacts to GCS. The graph, facts and reflections stay in SQLite under
`AGENT_DATA_DIR`. Put that on a persistent volume, or swap `SqliteStore` for Postgres.

## Layout

```
procedural_agent/
  agent.py            root_agent (Workflow) + app (App: plugins, compaction, cache, resumability)
  llm.py              model specs -> Gemini / LiteLlm / FallbackLlm; provider-agnostic JSON calls
  config.py           every setting, all overridable from env
  schemas.py          Plan / Verdict structured outputs
  prompts/            versioned prompt templates (planner, synthesizer, critic)
  memory/             procedural_kg, skill_registry, semantic, reflection, services, store
  harness/            nodes (workflow), executor (parallel DAG), learner, plugins, tools, ingest, search
  memory/glossary.py  glossary store (parameters, values, concepts)
  seed/               procedures.json, glossary.json
synthesizer_lab/      GEPA optimisation target + eval set
evals/                eval config, sampler/optimizer config, workflow eval set
scripts/              run_cli.py, improve.py, ingest.py, generate_doc_examples.py
docs/ + mkdocs.yml    documentation site (published to GitHub Pages by .github/workflows/docs.yml)
examples/             sop_travel_cards.md (procedure + term cards)
tests/                offline end-to-end and unit tests
```

## MCP procedures, LLM steps and approvals

Procedure steps can call any MCP tool (local stdio or remote HTTP) and run LLM prompts. Steps with
`Side effect: write` are parked with an exact preview until you approve them. See
`packs/techintel/` for a working pack (the Signal intelligence platform) and the docs pages
*MCP & LLM steps in procedures* and *Actions & approvals*.

```bash
cp packs/techintel/mcp_servers.json.example mcp_servers.json
python scripts/ingest.py packs/techintel/procedures.md --apply
python scripts/run_procedure.py techintel_brief --user srini
python scripts/approve.py --list
```

## Documentation

Published at https://yashodhantek.github.io/adk-procedural-agent/. To preview locally:

```bash
pip install -r requirements-docs.txt
python scripts/generate_doc_examples.py   # refresh the worked examples from real runs
mkdocs serve
```

## Notes

- Model names default to `gemini-3.5-flash` and `gemini-3.1-pro`. Check them against the current
  model list and change them in `.env`.
- The seed sources need no API keys (Open-Meteo, Frankfurter, USGS, CoinGecko).
