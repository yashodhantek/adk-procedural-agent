"""Ingest SOPs / runbooks / glossaries into the procedural knowledge graph.

  python scripts/ingest.py docs/                       # stage every .md/.txt/.pdf/.docx, print review
  python scripts/ingest.py sop.md --apply              # stage and apply confirmed edges only
  python scripts/ingest.py sop.md --apply --approve "travel_budget_in_inr->get_fx_rate"
  python scripts/ingest.py sop.md --apply --approve all
  python scripts/ingest.py --apply-batch 8b054a6d6e --approve all   # apply an earlier staged batch
  python scripts/ingest.py glossary.json --glossary    # bulk-load glossary JSON (seed format)

Procedure-card files are parsed deterministically; anything else uses the LLM
extractor (needs model credentials). Call specs with sample inputs are test-run
against the live API unless --no-test is given.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from procedural_agent.config import settings  # noqa: E402
from procedural_agent.harness.ingest import Ingestor, render_report  # noqa: E402
from procedural_agent.memory import agent_memory  # noqa: E402

SUFFIXES = {".md", ".txt", ".pdf", ".docx"}


def read_text(path: Path) -> str:
  if path.suffix == ".pdf":
    from pypdf import PdfReader
    return "\n\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
  if path.suffix == ".docx":
    import docx
    d = docx.Document(str(path))
    lines = []
    for p in d.paragraphs:
      style = (p.style.name or "").lower()
      prefix = "## " if style.startswith("heading 2") else "# " if style.startswith("heading") else ""
      lines.append(prefix + p.text)
    return "\n".join(lines)
  return path.read_text(encoding="utf-8")


def files(paths: list[str]) -> list[Path]:
  out = []
  for p in map(Path, paths):
    out += sorted(f for f in p.rglob("*") if f.suffix.lower() in SUFFIXES) if p.is_dir() else [p]
  return out


async def main(a) -> None:
  mem = agent_memory()
  ing = Ingestor(mem, test_calls=not a.no_test)
  approve = "all" if a.approve == ["all"] else (a.approve or None)
  if a.apply_batch:
    print(json.dumps(ing.apply(a.apply_batch, approve), indent=2))
    return
  if a.glossary:
    for f in files(a.paths):
      print(f"{f}: {mem.glossary.load(json.loads(f.read_text()), origin='ingested')} glossary entries")
    return
  out_dir = settings.data_dir / "ingest"
  out_dir.mkdir(parents=True, exist_ok=True)
  for f in files(a.paths):
    report = await ing.stage(read_text(f), f.name)
    (out_dir / f"{report['batch_id']}.json").write_text(json.dumps(report, indent=2))
    print(render_report(report))
    if a.apply:
      print(json.dumps(ing.apply(report["batch_id"], approve), indent=2))
    else:
      print(f"Staged. Apply with: python scripts/ingest.py --apply-batch {report['batch_id']} [--approve all]\n")


if __name__ == "__main__":
  ap = argparse.ArgumentParser()
  ap.add_argument("paths", nargs="*")
  ap.add_argument("--apply", action="store_true")
  ap.add_argument("--apply-batch")
  ap.add_argument("--approve", nargs="*", help='"src->dst" edges to approve, or "all"')
  ap.add_argument("--no-test", action="store_true", help="do not test-run API call specs")
  ap.add_argument("--glossary", action="store_true", help="paths are glossary JSON files")
  asyncio.run(main(ap.parse_args()))
