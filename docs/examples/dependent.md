# 2. Dependent chain + glossary

The user says "euros" and "rupees". The planner passes those words straight through; the glossary fixes them before execution.

--8<-- "ex_dependent.md"

## What to notice

- **Glossary in the prompt:** the planner was told what "euros" and "rupees" mean.
- **Normalisation:** `compile_plan` rewrote the inputs to ISO codes (`EUR`, `INR`), so the FX API accepted them. The `normalized` list records every change.
- **A dependent chain:** `convert_amount` (a **compute** procedure: `round(amount * rate, 2)`) depends on `get_fx_rate`. The compiler added the rate lookup at level 0 and passed `rate` along the edge.
- **Safe evaluation:** the formula ran in the AST-whitelist evaluator, not `eval`.

Related: [Glossary](../capabilities/glossary.md) · [LLD: Executor call kinds](../architecture/lld-executor.md#call-kinds)
