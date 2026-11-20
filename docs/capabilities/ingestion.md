# Natural-language ingestion

**What it does.** Turns SOPs, runbooks and how-to notes into **procedures, dependency edges and
glossary terms**, with a review step before anything is saved. The design is in
[LLD: Ingestion pipeline](../architecture/lld-ingestion.md).

## Two input styles

=== "Free text (LLM extraction)"

    ```markdown
    # Treasury desk runbook
    To quote a foreign invoice in rupees, first look up today's ECB rate for the
    invoice currency, then multiply the amount by the rate and add our 1.5% bank margin.
    Rates come from https://api.frankfurter.app/latest?from={currency}&to=INR.
    "Margin" always means the bank's FX margin, not our sales margin.
    ```

    `LlmExtractor` (using `LEARNER_MODEL`) returns procedure drafts and terms. Here you'd expect
    something like `quote_invoice_in_inr`, with a dependency phrase "today's ECB rate" and a term
    `margin`. The resolver then maps that phrase to `get_fx_rate`, by name similarity and because
    `get_fx_rate` produces the `rate` input. The offline test
    `test_free_text_resolution_dedupe_and_cycles` checks this resolution, using a stand-in for the
    model's output.

=== "Procedure cards (deterministic)"

    ```markdown
    ## Procedure: get_uv_index
    Description: Today's maximum UV index for a city.
    Inputs: lat_deg, lng
    Outputs: uv_index_max
    Needs: geocode_city (lat_deg->latitude, lng->longitude)
    API: GET https://api.open-meteo.com/v1/forecast?latitude={lat_deg}&longitude={lng}&daily=uv_index_max
    Extract: uv_index_max = daily.uv_index_max.0
    Required: uv_index_max
    Sample: lat_deg=17.38; lng=78.46
    ```

    No model is needed. The format is in [Procedure cards](../reference/procedure-cards.md).

## Where it runs

| From | Stage | Apply |
|---|---|---|
| CLI | `python scripts/ingest.py docs/sops/` (.md .txt .pdf .docx) | `--apply-batch <id> [--approve "a->b" … \| all]` |
| Chat | The synthesizer calls `ingest_text(text, source)` and shows the review | After you confirm, it calls `apply_ingest(batch_id, approve_edges)` |
| Python | `await Ingestor(agent_memory()).stage(text, source)` | `.apply(batch_id, approve)` |

## What the review protects you from

| Risk | Safeguard |
|---|---|
| Duplicate procedures | Same name, or similar description with the same I/O, becomes an **update** (version + 1) |
| Wrong dependencies | Edges inferred only from matching inputs and outputs need **your approval** |
| Loops | Cycles are **rejected** |
| Unknown or unsafe hosts | Hosts must be in `HTTP_ALLOWLIST`; otherwise the call is **blocked** |
| Broken templates | Placeholders must be declared inputs |
| Broken APIs | `Sample:` values → one live test call; a failing call is dropped |
| Unproven knowledge | New procedures start as **candidates** |

## Real example

--8<-- "ex_ingest.md"
