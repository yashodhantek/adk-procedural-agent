# 3. Independent needs in parallel

Two unrelated needs in one question: air quality in Delhi, and the bitcoin price in rupees.

--8<-- "ex_parallel.md"

## What to notice

- **Parallelism:** `get_crypto_price` needs nothing, so it ran at level 0 **alongside** the geocoder. Air quality waited only for the coordinates.
- **Value formatting:** `vs_currency` is a lower-case parameter for CoinGecko, so `INR` became `inr` and `Bitcoin` became `bitcoin`.
- **Self-learning:** two procedures worked together and the answer passed review, so `learn` **induced** `air_quality_crypto_price_flow` as a candidate composite. If this question pattern recurs, the planner can reuse it (see Example 8).

Related: [Parallel execution](../capabilities/parallel-execution.md) · [Self-learning](../capabilities/self-learning.md)
