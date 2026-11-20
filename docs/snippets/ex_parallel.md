**Question:** What's the air quality in Delhi, and the bitcoin price in INR?

**Node path:** `recall` → `planner` → `compile_plan` → `execute_plan` → `synthesizer` → `prepare_review` → `critic` → `gate` → `respond` → `learn`

??? note "What the planner was given: Glossary"
    ```text
    GLOSSARY (what the user's words mean; use the canonical values):
    [{"said": "air quality", "means": "AQI", "kind": "concept", "definition": "US AQI: 0-50 good, 51-100 moderate, 101-150 unhealthy for sensitive groups, 151-200 unhealthy, 201+ very unhealthy.", "procedures": ["get_air_quality"]}, {"said": "bitcoin", "means": "bitcoin", "kind": "value", "for": ["coin"]}, {"said": "inr", "means": "INR", "kind": "value", "for": ["from_currency", "to_currency", "vs_currency"]}]
    ```

**Plan from the planner (after glossary normalisation):**

```json
{
  "intent": "air quality and crypto price",
  "warnings": [],
  "normalized": [
    "s2: coin='Bitcoin' -> coin='bitcoin'",
    "s2: vs_currency='INR' -> vs_currency='inr'"
  ]
}
```

**Compiled execution levels:**

| Level | Steps (run in parallel) | Added by the compiler |
|---|---|---|
| 0 | `auto_geocode_city` → `geocode_city`, `s2` → `get_crypto_price` | `auto_geocode_city` |
| 1 | `s1` → `get_air_quality` | — |

**Step results:**

| Step | Procedure | Status | Latency | Outputs / error |
|---|---|---|---|---|
| `auto_geocode_city` | `geocode_city` | **ok** | 1 ms | `{"latitude": 28.65, "longitude": 77.23, "country": "India", "timezone": "Asia/Kolkata", "resolved_name": "Delhi"}` |
| `s2` | `get_crypto_price` | **ok** | 0 ms | `{"price": 7854210}` |
| `s1` | `get_air_quality` | **ok** | 1 ms | `{"us_aqi": 212, "pm2_5": 141.3, "pm10": 238.0}` |

**Critic verdicts:** `ok=True, score=0.92`

**Final answer:**

> Delhi's air is **very unhealthy**: US AQI 212 (PM2.5 141 µg/m³) at 14:00 IST. Bitcoin is ₹78,54,210 (CoinGecko spot).

**What the agent learned this turn:**

```json
{
  "induced": "air_quality_crypto_price_flow"
}
```
