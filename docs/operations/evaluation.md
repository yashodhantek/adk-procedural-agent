# Evaluation & optimisation

## Eval assets

| File | Purpose |
|---|---|
| `evals/workflow_realtime.evalset.json` | 6 cases for the full workflow (`adk eval procedural_agent …`) |
| `synthesizer_lab/realtime_basics.evalset.json` | The same 6 cases for the GEPA target |
| `evals/test_config.json` | Criteria: rubric-based final-response quality (threshold 0.7) and hallucinations (0.8) |
| `evals/sampler_config.json` | GEPA train/validation split (4 / 2 cases) |
| `evals/optimizer_config.json` | GEPA: optimiser model, 60 metric calls, minibatch size 3 |

### The cases

| id | Question | Exercises |
|---|---|---|
| `weather_single` | What's the weather in Hyderabad right now? | single procedure + closure |
| `fx_dependent` | Convert 250 EUR to INR at today's rate. | dependent chain |
| `multi_independent` | Air quality in Delhi and bitcoin in INR | parallel branches |
| `composite` | Is it a good day to go for a run in Bengaluru? | composite + concept |
| `multi_dependent` | Earthquakes near Kathmandu and the weather there | shared dependency |
| `missing_source` | Water level of Hussain Sagar lake? | no procedure: honesty |

### The rubrics

1. **grounded:** every number comes from a tool result
2. **complete:** every part of the question is answered
3. **dated:** units and measurement or publication time are stated
4. **honest:** data that couldn't be fetched is admitted

Real-time answers change, so exact-match metrics would be meaningless. Rubrics judge behaviour
instead.

## Running

```bash
pip install -e ".[optimize]"
adk eval procedural_agent evals/workflow_realtime.evalset.json \
  --config_file_path evals/test_config.json --print_detailed_results
python scripts/improve.py optimize
```

## Adding cases

Add a case per new procedure family, plus at least one "should admit it can't" case. Add your
domain's failure modes to the rubrics, such as "states the Jira query used". Keep the validation
split separate from training so GEPA can't overfit to what it's scored on.
