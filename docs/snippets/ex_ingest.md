**Review report** (`python scripts/ingest.py examples/sop_travel_cards.md`):

```text
Batch 45e6697ad3 from sop_travel_cards.md:
  [new] get_uv_index  in=['latitude', 'longitude'] out=['uv_index_max']  call: verified
        renamed via glossary: {'lat_deg': 'latitude', 'lng': 'longitude'}
  [new] travel_budget_in_inr  in=['amount', 'rate'] out=['budget_inr']  call: untested: no sample values for ['amount', 'rate']
  [new] beach_day_check  in=['city'] out=[]  call: composite
  ✓ get_uv_index -DEPENDS_ON-> geocode_city {'latitude': 'latitude', 'longitude': 'longitude'}  (stated in text and inputs match outputs)
  ? travel_budget_in_inr -DEPENDS_ON-> get_fx_rate {'rate': 'rate'}  (inputs ['rate'] match outputs of get_fx_rate; confirm)
  ✓ beach_day_check -COMPOSED_OF-> city_conditions_brief   (stated in text)
  ✓ beach_day_check -COMPOSED_OF-> get_uv_index   (stated in text)
  [new] term UV index (concept) aliases=['uv', 'sun strength', 'sunburn risk']
  [update] term latitude (parameter) aliases=['lat_deg', 'lat_degrees']
3 procedures, 2 terms, 4 edges (1 need confirmation).
```

**Apply** (`--apply-batch 45e6697ad3 --approve "travel_budget_in_inr->get_fx_rate"`):

```json
{
  "terms": 2,
  "procedures_new": [
    "get_uv_index",
    "travel_budget_in_inr",
    "beach_day_check"
  ],
  "procedures_updated": [],
  "edges": [
    "get_uv_index->geocode_city [DEPENDS_ON]",
    "travel_budget_in_inr->get_fx_rate [DEPENDS_ON]",
    "beach_day_check->city_conditions_brief [COMPOSED_OF]",
    "beach_day_check->get_uv_index [COMPOSED_OF]"
  ],
  "skipped_edges": []
}
```

**The new composite runs straight away** — `beach_day_check` for Bengaluru:

| Level | Steps (run in parallel) | Added by the compiler |
|---|---|---|
| 0 | `auto_geocode_city` → `geocode_city` | `auto_geocode_city` |
| 1 | `b_city_conditions_brief_get_air_quality` → `get_air_quality`, `b_city_conditions_brief_get_weather_forecast` → `get_weather_forecast`, `b_get_uv_index` → `get_uv_index` | `b_city_conditions_brief_get_air_quality`, `b_city_conditions_brief_get_weather_forecast`, `b_get_uv_index` |
| 2 | `b_city_conditions_brief` → `city_conditions_brief` | `b_city_conditions_brief` |
| 3 | `b` → `beach_day_check` | — |

| Step | Procedure | Status | Latency | Outputs / error |
|---|---|---|---|---|
| `auto_geocode_city` | `geocode_city` | **ok** | 0 ms | `{"latitude": 12.97, "longitude": 77.59, "country": "India", "timezone": "Asia/Kolkata", "resolved_name": "Bengaluru"}` |
| `b_city_conditions_brief_get_air_quality` | `get_air_quality` | **ok** | 0 ms | `{"us_aqi": 54, "pm2_5": 13.2, "pm10": 29.5}` |
| `b_city_conditions_brief_get_weather_forecast` | `get_weather_forecast` | **ok** | 0 ms | `{"current": {"time": "2026-11-20T14:15", "temperature_2m": 23.6, "relative_humidity_2m": 62, "wind_speed_10m": 11.2, "precipitation": 0.0}, "daily": {"time":…` |
| `b_get_uv_index` | `get_uv_index` | **ok** | 0 ms | `{"uv_index_max": 8.2}` |
| `b_city_conditions_brief` | `city_conditions_brief` | **ok** | 0 ms | `{"us_aqi": 54, "pm2_5": 13.2, "pm10": 29.5, "current": {"time": "2026-11-20T14:15", "temperature_2m": 23.6, "relative_humidity_2m": 62, "wind_speed_10m": 11.…` |
| `b` | `beach_day_check` | **ok** | 0 ms | `{"us_aqi": 54, "pm2_5": 13.2, "pm10": 29.5, "current": {"time": "2026-11-20T14:15", "temperature_2m": 23.6, "relative_humidity_2m": 62, "wind_speed_10m": 11.…` |
