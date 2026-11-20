# 7. A data source is down

The geocoding service returns 503 Service Unavailable for this run. The user asked for weather (which needs geocoding) **and** a currency conversion (which doesn't).

--8<-- "ex_failure.md"

## What to notice

- **Retries first:** the executor retried with backoff (the ~1.5 s latency) before marking the step **failed**.
- **Skipped, not failed:** `get_weather_forecast` was **skipped**, because its input never arrived. Skipped steps don't count against a procedure's reliability.
- **Graceful degradation:** the independent FX branch still ran, and the answer gives what it could, plus an honest note about the rest.
- **Reliability learned:** the geocoding source now has a recorded failure (the success count includes the earlier examples' runs). Ranking and `improve.py report` use this.
- **No bad learning:** the turn was accepted, but **not every procedure ran ok**, so no composite was induced (`learned this turn: {}`). This gate was added after these generated examples exposed the gap.

Related: [Parallel execution](../capabilities/parallel-execution.md) · [Guardrails](../capabilities/guardrails.md)
