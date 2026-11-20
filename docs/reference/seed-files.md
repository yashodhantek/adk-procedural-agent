# Seed files

Loaded once, when the database is empty. Edit them before the first run, or use
[ingestion](../capabilities/ingestion.md) afterwards.

## `seed/procedures.json`

```json
{
  "sources": [
    {"name": "frankfurter", "kind": "http_json", "base_url": "https://api.frankfurter.app",
     "description": "ECB reference FX rates (no key)"}
  ],
  "procedures": [
    {
      "name": "get_fx_rate",
      "domain": "finance",
      "description": "Latest exchange rate between two currencies (ISO codes such as USD, INR, EUR).",
      "inputs": ["from_currency", "to_currency"],
      "outputs": ["rate", "date"],
      "steps_md": "1. Normalise currency names to ISO-4217 codes. ...",
      "uses_source": "frankfurter",
      "call": {
        "kind": "http_json", "source": "frankfurter",
        "url": "https://api.frankfurter.app/latest",
        "params": {"from": "{from_currency}", "to": "{to_currency}"},
        "extract": {"rate": "rates.{to_currency}", "date": "date"},
        "required": ["rate"]
      }
    },
    {
      "name": "convert_amount",
      "inputs": ["amount", "from_currency", "to_currency", "rate"],
      "outputs": ["converted"],
      "depends_on": {"get_fx_rate": {"rate": "rate"}},
      "call": {"kind": "compute", "expr": "round(amount * rate, 2)", "output": "converted"}
    },
    {
      "name": "city_conditions_brief",
      "composed_of": ["get_weather_forecast", "get_air_quality"],
      "call": {"kind": "composite"}
    }
  ]
}
```

| Key | Meaning |
|---|---|
| `depends_on` | `{procedure: {my_input: their_output}}` → `DEPENDS_ON` edges |
| `composed_of` | `[procedure, …]` → `COMPOSED_OF` edges |
| `uses_source` | → `USES_SOURCE` edge |
| `call` | `http_json` / `compute` / `composite`; omit it for written-steps-only procedures |

### Shipped procedures

| Procedure | Kind | Needs | Source |
|---|---|---|---|
| `geocode_city` | http_json | — | Open-Meteo geocoding |
| `get_weather_forecast` | http_json | geocode_city | Open-Meteo forecast |
| `get_air_quality` | http_json | geocode_city | Open-Meteo air quality |
| `get_recent_earthquakes` | http_json | geocode_city | USGS |
| `get_fx_rate` | http_json | — | Frankfurter (ECB) |
| `convert_amount` | compute | get_fx_rate | — |
| `get_crypto_price` | http_json | — | CoinGecko |
| `city_conditions_brief` | composite | weather + air quality | — |

All the seed sources are free and need no API key.

## `seed/glossary.json`

```json
{
  "parameters": [{"name": "longitude", "aliases": ["lon", "lng", "long"], "unit": "degrees"},
                 {"name": "vs_currency", "aliases": ["fiat"], "format": "lower"}],
  "values":     [{"canonical": "INR", "scope": ["from_currency", "to_currency", "vs_currency"],
                  "aliases": ["rupee", "rupees", "₹", "rs", "inr"]}],
  "concepts":   [{"term": "AQI", "aliases": ["air quality", "smog"], "domain": "environment",
                  "definition": "US AQI: 0-50 good, ...", "related_procedures": ["get_air_quality"]}]
}
```

The shipped glossary covers 11 parameters, 10 values (currencies, coins, Indian city aliases) and
5 concepts (AQI, FX rate, "good day outside", earthquake, coordinates).
