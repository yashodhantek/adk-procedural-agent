# 11. Signal brief through MCP (live)

This example ran against a **live, local Signal (techintel) instance**: Go backend + PostgreSQL 16,
started with its built-in demo corpus. The new
[techintel MCP server](https://github.com/yashodhantek/adk-procedural-agent/tree/main/packs/techintel)
was the only connection, run as a local stdio process. Nothing was mocked except the LLM step's
model: no model key was available, so the brief's text was written from the step's actual input
data.

!!! warning "Demo corpus"
    Signal's demo corpus is synthetic (articles on `example.org`). The *pipeline* is real; the
    *intelligence* reflects that corpus. Point `TECHINTEL_URL` at intel.yashodhantek.com for real
    data.

## 1. Ingest the pack

```text
$ python scripts/ingest.py packs/techintel/procedures.md
  [new] techintel_trends  in=[] out=['top', 'rising', 'falling', 'by_category', 'shifts', 'as_of']  call: verified
  [new] techintel_radar  in=[] out=['rings', 'entries']  call: verified
  [new] techintel_recommendations  in=[] out=['recommendations', 'generated_at']  call: verified
  [new] techintel_top_concepts  in=[] out=['concepts', 'top_slug']  call: verified
  [new] techintel_concept_details  in=['slug'] out=['concept']  call: untested: no sample values for ['slug']
  [new] techintel_top_concept_details  in=['slug'] out=['concept']  call: untested: no sample values for ['slug']
  [new] techintel_reports  in=[] out=['reports']  call: verified
  [new] techintel_brief  in=[] out=['brief_md']  call: llm step
  [new] techintel_save_brief  in=['brief_md'] out=['saved']  call: write: not test-run (runs only after approval)  ⚠ side effect: write
  ✓ techintel_top_concept_details -DEPENDS_ON-> techintel_top_concepts {'slug': 'top_slug'}  (stated in text)
  ✓ techintel_brief -DEPENDS_ON-> techintel_trends   (stated in text)
  ... (5 more confirmed edges)
  [new] term Signal (concept) ...   [new] term hot topics (concept) ...
9 procedures, 2 terms, 7 edges (0 need confirmation).
```

Five tools were **called live** during ingestion and verified.

## 2. Run `techintel_save_brief`

The compiler pulled in the whole chain: five MCP reads in parallel, then the dependent
deep-dive, then the LLM step, then the parked write.

```text
levels: [radar, recommendations, reports, top_concepts, trends] → [top_concept_details] → [brief] → [main]
```

--8<-- "ex_signal_results.md"

The five parallel MCP calls took about 0.75 s **in total**, including starting the server
process. The deep-dive reused the open session (16 ms).

## 3. Approve

```text
$ python scripts/approve.py --list --user srini
EU2WFR  [write]  techintel_save_brief: techintel.save_brief({"markdown": "# Signal brief: AI technology intelligence…", "title": "Signal brief"})

$ python scripts/approve.py EU2WFR --user srini
{"ok": true, "code": "EU2WFR", "procedure": "techintel_save_brief",
 "outputs": {"saved": "/tmp/ti_briefs/2026-11-21-signal-brief.md", "bytes": 4576}}

$ python scripts/approve.py EU2WFR --user srini
Action EU2WFR is already executed
```

## 4. The brief

The saved file is in the repository:
[`packs/techintel/sample-brief-demo-corpus.md`](https://github.com/yashodhantek/adk-procedural-agent/blob/main/packs/techintel/sample-brief-demo-corpus.md).
After the run, the graph showed:

- every techintel procedure with 2 successes and 0 failures
- source `mcp:techintel` with 12 successful calls

## Run it yourself

```bash
cp packs/techintel/mcp_servers.json.example mcp_servers.json
export TECHINTEL_URL=https://intel.yashodhantek.com TECHINTEL_EMAIL=... TECHINTEL_PASSWORD=...
python scripts/ingest.py packs/techintel/procedures.md --apply
python scripts/run_procedure.py techintel_brief --user srini      # needs LLM_STEP_MODEL access
python scripts/run_cli.py --user srini                            # or ask: "What's hot on Signal this week?"
```
