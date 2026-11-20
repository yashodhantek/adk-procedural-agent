# 1. One procedure, one hidden dependency

The user asks for the weather. The planner picks only `get_weather_forecast`; it doesn't need to know that a forecast needs coordinates.

--8<-- "ex_single.md"

## What to notice

- **Dependency closure:** the compiler added `auto_geocode_city` from the graph edge `get_weather_forecast → geocode_city`, and ran it first (level 0).
- **Input wiring:** the edge mapping `{latitude: latitude, longitude: longitude}` passed the geocoder's outputs into the forecast call.
- **Candidates:** the planner got a ranked candidate list with each procedure's inputs, outputs, dependencies and reliability.
- **Grounding:** the answer states units and the observation time, which is what the critic checks for.
- **Nothing learned:** a single-procedure success adds a plan-cache entry and stats, but no new procedure.

Related: [Planning & dependencies](../capabilities/planning.md) · [LLD: compile algorithm](../architecture/lld-procedural-graph.md#the-compile-algorithm)
