"""Service factory: one place that wires every memory/storage backend.

Local (default)          | Production (MEMORY_BACKEND=vertex)
-------------------------|-----------------------------------------------
SqliteSessionService     | VertexAiSessionService   (Agent Engine)
SqliteMemoryService      | VertexAiMemoryBankService (Memory Bank: LLM
  (episodic, FTS5)       |   extraction + consolidation of memories)
FileArtifactService      | GcsArtifactService (set ARTIFACT_BUCKET)
ProceduralKG / facts / reflections always live in the agent's own SQLite
(point AGENT_DATA_DIR at a mounted volume, or swap SqliteStore for Postgres).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from ..config import settings
from .approvals import Approvals
from .glossary import Glossary
from .procedural_kg import ProceduralKG
from .reflection import ReflectionMemory
from .semantic import SemanticMemory
from .store import SqliteStore


@dataclass
class AgentMemory:
  store: SqliteStore
  kg: ProceduralKG
  facts: SemanticMemory
  reflections: ReflectionMemory
  glossary: Glossary
  approvals: Approvals


@lru_cache(maxsize=1)
def agent_memory() -> AgentMemory:
  store = SqliteStore(settings.db_path)
  return AgentMemory(store=store, kg=ProceduralKG(store), facts=SemanticMemory(store),
                     reflections=ReflectionMemory(store), glossary=Glossary(store),
                     approvals=Approvals(store))


def build_services():
  """Returns (session_service, memory_service, artifact_service)."""
  if settings.memory_backend == "vertex":
    from google.adk.artifacts import GcsArtifactService
    from google.adk.memory import VertexAiMemoryBankService
    from google.adk.sessions import VertexAiSessionService
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    engine = settings.agent_engine_id
    return (
        VertexAiSessionService(project=project, location=location, agent_engine_id=engine),
        VertexAiMemoryBankService(project=project, location=location, agent_engine_id=engine),
        GcsArtifactService(bucket_name=os.environ["ARTIFACT_BUCKET"]),
    )
  from google.adk.artifacts import FileArtifactService
  from google.adk.memory import SqliteMemoryService
  from google.adk.sessions import SqliteSessionService
  return (
      SqliteSessionService(str(settings.data_dir / "sessions.sqlite")),
      SqliteMemoryService(settings.data_dir / "episodic_memory.sqlite"),
      FileArtifactService(str(settings.data_dir / "artifacts")),
  )
