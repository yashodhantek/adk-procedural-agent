# 4. Composite procedure

"Is today a good day to go for a run in Bangalore?" names no data at all; the glossary and a composite procedure do the work.

--8<-- "ex_composite.md"

## What to notice

- **Concept match:** "go for a run" is a glossary **concept** linked to `city_conditions_brief`, so that procedure ranked first in the candidates.
- **City alias:** "Bangalore" was normalised to `Bengaluru` (a value scoped to `city`).
- **Composite expansion:** `city_conditions_brief` is *made of* `get_weather_forecast` and `get_air_quality`. The compiler added both parts (`s1_…`) and their shared dependency, giving three levels: geocode, then both parts in parallel, then the composite merging their outputs.
- **Nothing new learned:** the plan used a single (composite) procedure, so there was nothing new to induce.

Related: [LLD: Procedural knowledge graph](../architecture/lld-procedural-graph.md)
