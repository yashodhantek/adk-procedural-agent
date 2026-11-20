# Procedure cards

A Markdown format that the ingestion pipeline parses **deterministically**, with no model needed.
A file containing any `## Procedure:` or `## Term:` heading is treated as cards.

## Procedure

```markdown
## Procedure: <name>                    (becomes snake_case)
Description: <when to use it>
Domain: <domain>
Inputs: a, b, c
Outputs: x, y
Needs: other_proc (my_in->their_out, my_in2->their_out2); another_proc
Made of: part_a, part_b                 (composite: this procedure bundles others)
API: GET https://host/path?param={a}&other=fixed
Extract: x = json.path.0.field; y = items[*].name
Required: x
Compute: x = round(a * b, 2)            (instead of API, for a calculation)
MCP: server.tool arg={a} other="text"    (instead of API: call an MCP tool)
LLM: Summarise {a} and {x} in 3 bullets  (instead of API: a text step)
Side effect: read | write | destructive  (write/destructive run only after approval)
Sample: a=1; b=2                        (enables a live test call during ingestion)
Steps:
1. First step in plain words.
2. Second step.
```

| Field | Required | Notes |
|---|---|---|
| `Description` | recommended | Used for search and duplicate detection |
| `Inputs` / `Outputs` | recommended | Canonicalised by the glossary (`lng` → `longitude`) |
| `Needs` | — | Each entry becomes a **confirmed** `DEPENDS_ON` edge; the mapping in brackets is `my_input->their_output` |
| `Made of` | — | **Confirmed** `COMPOSED_OF` edges; the procedure becomes a `composite` |
| `API` | — | Query parameters are split out; `{input}` placeholders must be declared inputs; the host must be allow-listed |
| `Extract` | with `API` | `output = path` pairs, using the [path language](../architecture/lld-executor.md#path-language-extract) |
| `Required` | — | Outputs that must be non-empty for success |
| `Compute` | — | `out = expression`, run in the safe evaluator |
| `MCP` | — | `server.tool` plus `key=value` arguments (shell-style quoting); the server must be configured; read steps are test-called once during ingestion |
| `LLM` | — | A prompt; `{var}` takes inputs **and** dependency outputs; the output name is the first `Outputs` entry |
| `Side effect` | — | `write` / `destructive`: parked for [approval](../capabilities/actions-approvals.md); never test-called; never learned into composites |
| `Sample` | — | `name=value` pairs; with full coverage of the placeholders, one live test call is made |
| `Steps` | — | Lines after `Steps:` until the next heading; the synthesizer follows them when there's no call spec |

## Term

```markdown
## Term: <canonical>
Kind: parameter | value | concept
Aliases: alias one, alias two
Definition: What it means.
Applies to: from_currency, to_currency      (values: which parameters)
Related: procedure_a, procedure_b           (concepts: linked procedures)
```

A complete example is in
[`examples/sop_travel_cards.md`](https://github.com/yashodhantek/adk-procedural-agent/blob/main/examples/sop_travel_cards.md),
and its real ingestion output is in [Example 9](../examples/ingestion.md).
