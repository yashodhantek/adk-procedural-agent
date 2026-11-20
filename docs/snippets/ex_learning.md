### Turn 1: a successful multi-procedure run is induced as a new procedure

**Question:** Weather and air quality in Hyderabad, and 100 USD in INR?

**Node path:** `recall` → `planner` → `compile_plan` → `execute_plan` → `synthesizer` → `prepare_review` → `critic` → `gate` → `respond` → `learn`

**Plan from the planner (after glossary normalisation):**

```json
{
  "intent": "weather air quality and currency conversion",
  "warnings": [],
  "normalized": []
}
```

**Compiled execution levels:**

| Level | Steps (run in parallel) | Added by the compiler |
|---|---|---|
| 0 | `auto_geocode_city` → `geocode_city`, `auto_get_fx_rate` → `get_fx_rate` | `auto_geocode_city`, `auto_get_fx_rate` |
| 1 | `s1` → `get_weather_forecast`, `s2` → `get_air_quality`, `s3` → `convert_amount` | — |

**Step results:**

| Step | Procedure | Status | Latency | Outputs / error |
|---|---|---|---|---|
| `auto_geocode_city` | `geocode_city` | **ok** | 1 ms | `{"latitude": 17.38, "longitude": 78.46, "country": "India", "timezone": "Asia/Kolkata", "resolved_name": "Hyderabad"}` |
| `auto_get_fx_rate` | `get_fx_rate` | **ok** | 0 ms | `{"rate": 84.36, "date": "2026-11-20"}` |
| `s1` | `get_weather_forecast` | **ok** | 0 ms | `{"current": {"time": "2026-11-20T14:15", "temperature_2m": 29.4, "relative_humidity_2m": 41, "wind_speed_10m": 9.7, "precipitation": 0.0}, "daily": {"time": …` |
| `s2` | `get_air_quality` | **ok** | 0 ms | `{"us_aqi": 78, "pm2_5": 24.6, "pm10": 51.0}` |
| `s3` | `convert_amount` | **ok** | 0 ms | `{"converted": 8436.0}` |

**Critic verdicts:** `ok=True, score=0.92`

**Final answer:**

> Hyderabad 29.4 °C, AQI 78 (moderate). 100 USD = ₹8,436.00.

**What the agent learned this turn:**

```json
{
  "induced": "weather_air_quality_currency_flow"
}
```

New node in the graph:

```json
{
  "name": "weather_air_quality_currency_flow",
  "domain": "travel",
  "description": "Learned workflow for requests like: weather air quality and currency conversion. Combines get_weather_forecast, get_air_quality, convert_amount.",
  "inputs": [
    "amount",
    "city",
    "from_currency",
    "to_currency"
  ],
  "outputs": [
    "converted",
    "country",
    "current",
    "daily",
    "date",
    "latitude",
    "longitude",
    "pm10",
    "pm2_5",
    "rate",
    "resolved_name",
    "timezone"
  ],
  "status": "candidate",
  "origin": "learned",
  "reliability": 0.67,
  "executable": true,
  "composed_of": [
    "convert_amount",
    "get_air_quality",
    "get_weather_forecast"
  ],
  "steps_md": "1. Run `get_weather_forecast`.\n2. Run `get_air_quality`.\n3. Run `convert_amount`.\n4. Combine the results: summarise."
}
```

### Turn 2: the planner reuses `weather_air_quality_currency_flow`

- Planner prompt contained a cached plan: `{"query": "Weather and air quality in Hyderabad, and 100 USD in INR?", "plan": {"intent": "weather air quality and currency conversion", "do…`
- Compiled levels: [auto_geocode_city, auto_get_fx_rate] → [s1_convert_amount, s1_get_air_quality, s1_get_weather_forecast] → [s1]
- `weather_air_quality_currency_flow` now: status **candidate**, successes 2, failures 0, reliability 75%
- Learning report: `{}`

### Turn 3: the planner reuses `weather_air_quality_currency_flow`

- Planner prompt contained a cached plan: `{"query": "Weather and air quality in Hyderabad, and 100 USD in INR?", "plan": {"intent": "same request", "domain": "travel", "steps": [{"id…`
- Compiled levels: [auto_geocode_city, auto_get_fx_rate] → [s1_convert_amount, s1_get_air_quality, s1_get_weather_forecast] → [s1]
- `weather_air_quality_currency_flow` now: status **active**, successes 3, failures 0, reliability 80%
- Learning report: `{"promoted": "weather_air_quality_currency_flow"}`

### Turn 4: the planner reuses `weather_air_quality_currency_flow`

- Planner prompt contained a cached plan: `{"query": "Weather and air quality in Hyderabad, and 100 USD in INR?", "plan": {"intent": "same request", "domain": "travel", "steps": [{"id…`
- Compiled levels: [auto_geocode_city, auto_get_fx_rate] → [s1_convert_amount, s1_get_air_quality, s1_get_weather_forecast] → [s1]
- `weather_air_quality_currency_flow` now: status **active**, successes 4, failures 0, reliability 83%
- Learning report: `{}`
