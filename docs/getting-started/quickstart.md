# Quickstart

## 1. Configure one model

=== "Gemini (default)"

    ```bash title=".env"
    GOOGLE_API_KEY=your-key
    ```

=== "Azure OpenAI"

    ```bash title=".env"
    AGENT_MODEL=azure/gpt-4o-prod
    PLANNER_MODEL=azure/gpt-4o-prod
    CRITIC_MODEL=azure/gpt-4o-mini-prod
    LEARNER_MODEL=azure/gpt-4o-mini-prod
    SUMMARIZER_MODEL=azure/gpt-4o-mini-prod
    AZURE_API_KEY=...
    AZURE_API_BASE=https://<resource>.openai.azure.com
    AZURE_API_VERSION=2024-10-21
    TAVILY_API_KEY=tvly-...          # web search without Gemini (optional)
    ```

=== "TrueFoundry gateway"

    ```bash title=".env"
    AGENT_MODEL=truefoundry/azure-openai-main/gpt-4o
    PLANNER_MODEL=truefoundry/openai-main/gpt-5
    CRITIC_MODEL=truefoundry/openai-main/gpt-4o-mini
    LEARNER_MODEL=truefoundry/openai-main/gpt-4o-mini
    SUMMARIZER_MODEL=truefoundry/openai-main/gpt-4o-mini
    TFY_BASE_URL=https://<org>.truefoundry.cloud
    TFY_API_KEY=...
    ```

## 2. Chat

```bash
python scripts/run_cli.py --user srini
```

```text
you> Is today a good day to go for a run in Bangalore?
  · synthesizer → load_skill
agent> Yes. Bengaluru is 23.6 °C with a light breeze ...

you> /learned          # what the agent learned from that turn
you> /graph            # the procedure graph as Mermaid
```

Prefer a UI? ADK's dev UI shows every node, tool call and state change:

```bash
adk web . --session_service_uri sqlite:///.data/sessions.sqlite \
          --memory_service_uri sqlite:///.data/episodic_memory.sqlite \
          --artifact_service_uri file://.data/artifacts
```

## 3. Try the capabilities

| Ask | What happens | Read more |
|---|---|---|
| *What's the weather in Hyderabad?* | One procedure; the compiler adds `geocode_city` first | [Example 1](../examples/single.md) |
| *Convert 250 euros to rupees* | Glossary turns "euros"/"rupees" into `EUR`/`INR`; `get_fx_rate` runs before `convert_amount` | [Example 2](../examples/dependent.md) |
| *Air quality in Delhi and bitcoin in INR?* | Two independent branches in parallel | [Example 3](../examples/parallel.md) |
| *Good day for a run in Bangalore?* | Composite procedure, expanded into its parts | [Example 4](../examples/composite.md) |
| Ask the same multi-part question three times | A new procedure is learned, then promoted | [Example 8](../examples/learning.md) |
| *Remember I'm based in Hyderabad* | Semantic memory + `user:` state | [Memory](../capabilities/memory.md) |

## 4. Add your own knowledge

```bash
python scripts/ingest.py examples/sop_travel_cards.md        # review
python scripts/ingest.py --apply-batch <id> --approve all     # apply
```

See [Natural-language ingestion](../capabilities/ingestion.md).

## 5. Keep it improving

```bash
python scripts/improve.py report        # what's reliable, what isn't, the graph diagram
python scripts/improve.py consolidate   # nightly memory maintenance
python scripts/improve.py optimize      # GEPA prompt optimisation (needs the optimize extra)
```
