# Deployment

## What must persist

| Data | Local | Production |
|---|---|---|
| Sessions | `.data/sessions.sqlite` | Agent Engine sessions (`MEMORY_BACKEND=vertex`) or Cloud SQL via `--session_service_uri` |
| Episodic memory | `.data/episodic_memory.sqlite` | Vertex AI Memory Bank |
| Artifacts | `.data/artifacts` | GCS (`ARTIFACT_BUCKET`) |
| **Agent memory** (graph, glossary, facts, lessons, playbook) | `.data/agent_memory.sqlite` | A persistent volume shared by all replicas (one writer), or Postgres |
| Prompt versions | `.data/prompts` | The same volume |

!!! warning
    Cloud Run's container filesystem is temporary. Mount a volume (Cloud Storage FUSE or
    Filestore) at `AGENT_DATA_DIR`, or the agent forgets everything it learned on each restart.

## Cloud Run (ADK CLI)

```bash
adk deploy cloud_run procedural_agent \
  --project $PROJECT --region asia-south1 --service_name procedural-agent --with_ui \
  --session_service_uri "agentengine://$AGENT_ENGINE_ID" \
  --memory_service_uri "agentengine://$AGENT_ENGINE_ID" \
  --artifact_service_uri "gs://$ARTIFACT_BUCKET"
```

Then set the environment variables (models, `AGENT_DATA_DIR=/mnt/agent-data`, provider keys from
Secret Manager), mount the volume, and keep `--max-instances` small until the agent store is
shared safely.

## Agent Engine

```bash
adk deploy agent_engine procedural_agent --project $PROJECT --region us-central1
```

Set `MEMORY_BACKEND=vertex`, `GOOGLE_CLOUD_AGENT_ENGINE_ID`, `ARTIFACT_BUCKET` and
`AGENT_DATA_DIR` (a persistent path).

## Docker (any host)

```bash
adk deploy docker procedural_agent     # or write your own image:
```

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e ".[llms]"
ENV AGENT_DATA_DIR=/data
VOLUME /data
CMD ["adk", "api_server", ".", "--host", "0.0.0.0", "--port", "8080", \
     "--session_service_uri", "sqlite:////data/sessions.sqlite", \
     "--memory_service_uri", "sqlite:////data/episodic_memory.sqlite", \
     "--artifact_service_uri", "file:///data/artifacts"]
```

## Scheduled jobs

| Job | Schedule | Command |
|---|---|---|
| Consolidation | nightly | `python scripts/improve.py consolidate` |
| Report | weekly | `python scripts/improve.py report` (keep `.data/kg.mmd`) |
| Prompt optimisation | after eval-set or playbook changes | `python scripts/improve.py optimize` |
| Ingestion | when SOPs change | `python scripts/ingest.py docs/sops/` → review → `--apply-batch` |

Use Cloud Scheduler + Cloud Run Jobs, or cron, with the same image and volume.

## Through an LLM gateway (TrueFoundry)

Point every role at `truefoundry/...` specs and set `TFY_BASE_URL` / `TFY_API_KEY`. The gateway
then handles routing, rate limits, budgets and audit logs. Optional `TFY_EXTRA_HEADERS` carry
metadata such as the app name for cost attribution.
