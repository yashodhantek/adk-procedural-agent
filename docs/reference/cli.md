# Command line

## `scripts/run_cli.py`: chat

```bash
python scripts/run_cli.py [--user ID] [--session ID]
```

Uses persistent services (`build_services()`). In-chat commands: `/graph` prints the Mermaid
graph; `/learned` prints the last learning report. Ctrl-D quits.

In-chat approvals: `/pending`, `/approve CODE`, `/reject CODE`.

## `scripts/run_procedure.py`: run one procedure

```bash
python scripts/run_procedure.py techintel_brief --user srini
python scripts/run_procedure.py get_weather_forecast city=Hyderabad --json
```

Compiles the procedure with its dependencies and runs it with no chat loop, which suits cron or
launchd. Write steps are parked and their approval code is printed.

## `scripts/approve.py`: decide on parked actions

```bash
python scripts/approve.py --list [--user ID]
python scripts/approve.py CODE [--user ID]
python scripts/approve.py CODE --reject
```

## `scripts/ingest.py`: documents → graph

```bash
python scripts/ingest.py PATH...                 # stage .md .txt .pdf .docx (files or folders) and print reviews
python scripts/ingest.py PATH --apply            # stage and apply confirmed edges
python scripts/ingest.py PATH --apply --approve "a->b" "c->d"
python scripts/ingest.py PATH --apply --approve all
python scripts/ingest.py --apply-batch ID [--approve ...]
python scripts/ingest.py --no-test PATH          # skip live test calls
python scripts/ingest.py glossary.json --glossary
```

Reports are also saved to `$AGENT_DATA_DIR/ingest/<batch>.json`.

## `scripts/improve.py`: offline improvement

```bash
python scripts/improve.py report
python scripts/improve.py consolidate
python scripts/improve.py optimize [--dry-run]
python scripts/improve.py rollback <prompt> <version>     # 0 = shipped default
```

## `scripts/generate_doc_examples.py`

Regenerates `docs/snippets/*.md` (the worked examples) from real runs. Run it after changing
behaviour, then rebuild the docs.

## ADK commands

```bash
adk web . --session_service_uri sqlite:///.data/sessions.sqlite \
          --memory_service_uri sqlite:///.data/episodic_memory.sqlite \
          --artifact_service_uri file://.data/artifacts
adk run procedural_agent
adk eval procedural_agent evals/workflow_realtime.evalset.json --config_file_path evals/test_config.json
```

## Docs

```bash
pip install mkdocs-material
mkdocs serve            # http://127.0.0.1:8000
mkdocs build --strict
```
