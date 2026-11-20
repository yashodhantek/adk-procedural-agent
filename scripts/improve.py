"""Offline self-improvement for the procedural agent.

  python scripts/improve.py report                # memory stats + KG diagram (.data/kg.mmd)
  python scripts/improve.py consolidate           # Memp-style memory maintenance
  python scripts/improve.py optimize [--dry-run]  # GEPA prompt optimisation (ADK)
  python scripts/improve.py rollback synthesizer 0

Run `consolidate` on a schedule (nightly) and `optimize` after the eval set or
the playbook changes. Each optimised prompt is saved as a new version and is
only activated if it beats the current prompt on the validation cases.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from procedural_agent import prompts  # noqa: E402
from procedural_agent.config import settings  # noqa: E402
from procedural_agent.memory import agent_memory  # noqa: E402


def report() -> None:
  mem = agent_memory()
  print(json.dumps(mem.kg.stats(), indent=2))
  print("\nLeast reliable procedures:")
  for p in sorted(mem.kg.all(include_deprecated=True), key=lambda p: p.reliability)[:5]:
    print(f"  {p.name:32} {p.status:10} {p.success:>4}✓ {p.failure:>4}✗  {p.reliability:.0%}")
  print("\nSources:")
  for r in mem.store.query("SELECT * FROM sources ORDER BY failure DESC"):
    total = r["success"] + r["failure"]
    print(f"  {r['name']:32} {r['success']:>4}✓ {r['failure']:>4}✗ "
          f"{(r['total_latency_ms'] / total if total else 0):7.0f} ms avg")
  print("\nPlaybook:")
  print(mem.reflections.render(mem.reflections.playbook(50)))
  out = settings.data_dir / "kg.mmd"
  out.write_text(mem.kg.to_mermaid())
  print(f"\nKnowledge graph diagram written to {out}")


def consolidate(min_runs: int = 4, stale_days: int = 60) -> dict:
  mem = agent_memory()
  kg, db = mem.kg, mem.store
  changes = {"deprecated": [], "merged": [], "promoted": [], "playbook_pruned": 0,
             "lessons_dropped": 0, "plans_dropped": 0}
  # 1. deprecate unreliable procedures (never seed ones that have no runs)
  for p in kg.all():
    if p.success + p.failure >= min_runs and p.reliability < settings.deprecate_below:
      kg.set_status(p.name, "deprecated")
      changes["deprecated"].append(p.name)
    elif p.status == "candidate" and p.success >= settings.promote_after:
      kg.set_status(p.name, "active")
      changes["promoted"].append(p.name)
  # 2. merge learned composites with identical parts (keep the better one)
  groups: dict[frozenset, list] = {}
  for p in kg.all():
    parts = frozenset(kg.parts(p.name))
    if p.origin == "learned" and parts:
      groups.setdefault(parts, []).append(p)
  for dupes in groups.values():
    if len(dupes) > 1:
      dupes.sort(key=lambda p: (p.reliability, p.success), reverse=True)
      for loser in dupes[1:]:
        kg.set_status(loser.name, "deprecated")
        changes["merged"].append(f"{loser.name} -> {dupes[0].name}")
  # 3. playbook: drop bullets that hurt more than they help
  changes["playbook_pruned"] = mem.reflections.prune()
  # 4. forget lessons never retrieved for `stale_days`, and plans that mostly failed
  cutoff = time.time() - stale_days * 86400
  changes["lessons_dropped"] = db.execute("DELETE FROM lessons WHERE uses=0 AND created_at < ?", (cutoff,)).rowcount
  changes["plans_dropped"] = db.execute("DELETE FROM plan_cache WHERE failures > successes + 1").rowcount
  print(json.dumps(changes, indent=2))
  return changes


async def optimize(dry_run: bool) -> None:
  """Run ADK's GEPA optimizer on the synthesizer prompt and version the result."""
  try:
    from google.adk.cli.cli_eval import get_root_agent
    from google.adk.cli.utils import _eval_storage
    from google.adk.optimization.gepa_root_agent_prompt_optimizer import (
        GEPARootAgentPromptOptimizer, GEPARootAgentPromptOptimizerConfig)
    from google.adk.optimization.local_eval_sampler import LocalEvalSampler, LocalEvalSamplerConfig
  except ModuleNotFoundError as e:
    sys.exit(f"Install the extras first: pip install 'google-adk[eval]' gepa  ({e})")

  sampler_cfg = LocalEvalSamplerConfig.model_validate_json((ROOT / "evals/sampler_config.json").read_text())
  opt_cfg = GEPARootAgentPromptOptimizerConfig.model_validate_json((ROOT / "evals/optimizer_config.json").read_text())
  lab = ROOT / "synthesizer_lab"
  root_agent = await get_root_agent(str(lab))
  eval_sets_manager, _ = _eval_storage.create_eval_managers(None, str(ROOT))
  sampler = LocalEvalSampler(sampler_cfg, eval_sets_manager)
  result = await GEPARootAgentPromptOptimizer(opt_cfg).optimize(root_agent, sampler)
  if not result.gepa_result:
    sys.exit("GEPA returned no result")
  best = result.optimized_agents[result.gepa_result["best_idx"]]
  baseline = result.gepa_result.get("val_aggregate_scores", [None])[0]
  print(f"Best validation score {best.overall_score} (baseline {baseline})")
  from synthesizer_lab.agent import LAB_PREAMBLE
  text = (best.optimized_agent.instruction.replace(LAB_PREAMBLE, "")
          .replace("<playbook>", "{{playbook}}").replace("<lessons>", "{{lessons}}")
          .replace("<preferences>", "{{preferences}}"))
  improved = baseline is None or (best.overall_score or 0) > baseline
  if dry_run:
    print(text)
    return
  v = prompts.save_version("synthesizer", text, note=json.dumps({"score": best.overall_score, "baseline": baseline}),
                           activate=improved)
  print(f"Saved synthesizer v{v} ({'activated' if improved else 'kept inactive: no gain'})")


def main() -> None:
  ap = argparse.ArgumentParser()
  sub = ap.add_subparsers(dest="cmd", required=True)
  sub.add_parser("report")
  sub.add_parser("consolidate")
  o = sub.add_parser("optimize")
  o.add_argument("--dry-run", action="store_true")
  r = sub.add_parser("rollback")
  r.add_argument("prompt")
  r.add_argument("version", type=int)
  args = ap.parse_args()
  if args.cmd == "report":
    report()
  elif args.cmd == "consolidate":
    consolidate()
  elif args.cmd == "optimize":
    asyncio.run(optimize(args.dry_run))
  elif args.cmd == "rollback":
    prompts.rollback(args.prompt, args.version)
    print(f"{args.prompt} now at version {prompts.active_version(args.prompt)} (0 = shipped default)")


if __name__ == "__main__":
  main()
