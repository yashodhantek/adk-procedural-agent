# Self-improvement (offline)

Online learning changes **memory**. Offline improvement maintains that memory and improves the
**prompts** themselves, on a schedule and behind a validation gate.

```bash
python scripts/improve.py report        # stats, least reliable procedures and sources, playbook, KG diagram
python scripts/improve.py consolidate   # memory maintenance
python scripts/improve.py optimize      # GEPA prompt optimisation
python scripts/improve.py rollback synthesizer 0
```

## `report`

*Illustrative output:*

```text
{ "procedures": 13, "learned": 4, "candidates": 6, "deprecated": 0, "edges": 25, "cached_plans": 8 }

Least reliable procedures:
  geocode_city          active     12✓    1✗  87%
  ...
Sources:
  open_meteo_geocoding    12✓    1✗     161 ms avg
  tool:http_get_json       3✓    0✗     420 ms avg
...
Knowledge graph diagram written to .data/kg.mmd
```

## `consolidate` (run nightly)

| Action | Rule |
|---|---|
| Retire | Reliability below `DEPRECATE_BELOW` after ≥ 4 runs |
| Promote | Candidates at `PROMOTE_AFTER` successes |
| Merge duplicates | Learned composites with identical parts: keep the best, deprecate the rest |
| Prune the playbook | `helpful − harmful ≤ −2` |
| Forget | Lessons never retrieved in 60 days; cached plans with `failures > successes + 1` |

It prints a JSON change log, so you can schedule it and keep the output.

## `optimize` (GEPA prompt optimisation)

ADK 2.x ships a **GEPA** optimiser (`google.adk.optimization`). It runs an agent on training
cases, scores the answers, reflects on the failures and proposes better instructions.

1. `synthesizer_lab/` exposes the synthesizer as a single root `Agent`, with the same tools and the
   full prompt (slots written as `<playbook>`, so ADK's templating leaves them alone).
2. `evals/sampler_config.json` splits `synthesizer_lab/realtime_basics.evalset.json` into 4
   training and 2 validation cases. They cover a single procedure, a dependent chain, independent
   needs, a composite, a dependent pair, and a source that doesn't exist.
3. `evals/test_config.json` scores answers with rubric-based final-response quality (grounded,
   complete, dated, honest) and a hallucination check.
4. The best candidate is saved as `prompts/synthesizer/vN.md`, and is **activated only if its
   validation score beats the baseline**.

```bash
pip install -e ".[optimize]"
python scripts/improve.py optimize --dry-run   # print the candidate without saving it
python scripts/improve.py optimize
```

!!! note
    The optimiser and the eval judges use Gemini model names (`evals/optimizer_config.json`,
    `evals/test_config.json`). Set them to models you have access to.

## Prompt versions

```text
.data/prompts/synthesizer/
  v1.md   v1.note   ({"score": 0.81, "baseline": 0.74})
  v2.md   v2.note
  active.json       ({"version": 1})
```

`prompts.load(name)` serves the active version, or the shipped default when none is active.
Rolling back takes one command and needs no redeploy.
