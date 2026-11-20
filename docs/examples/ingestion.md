# 9. Ingesting an SOP

`examples/sop_travel_cards.md` adds a UV-index procedure (written in an older SOP's vocabulary), a budget calculation and a beach-day bundle, plus two glossary terms.

--8<-- "ex_ingest.md"

## What to notice

- **Glossary first:** the SOP's `lat_deg`/`lng` became `latitude`/`longitude`, including inside the API template.
- **Verified call:** the UV procedure's `Sample:` values triggered one test call, which succeeded.
- **Confirmed vs review:** the geocoding edge was stated in the text **and** matched by inputs (confirmed). The budget → FX edge was only an input match, so it needed approval, which we gave with `--approve`.
- **Composite:** `beach_day_check` *is made of* two procedures, so it got a `composite` call and ran immediately: four levels, with weather, air quality and UV in parallel.
- **Untested:** the budget formula had no samples, so it's kept but marked *untested*.

Related: [Natural-language ingestion](../capabilities/ingestion.md) · [Procedure cards](../reference/procedure-cards.md)
