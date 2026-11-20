# Python API

## Build and run

```python
from procedural_agent.agent import build_workflow, build_app, app, root_agent
from procedural_agent.memory import build_services
from google.adk import Runner

sessions, memory, artifacts = build_services()
runner = Runner(app=app, session_service=sessions, memory_service=memory,
                artifact_service=artifacts, auto_create_session=True)
```

`build_workflow(model=None, planner_model=None, critic_model=None, with_tools=True)` lets you
inject any `BaseLlm`; the tests use this to pass scripted models.

## Memory

```python
from procedural_agent.memory import agent_memory
mem = agent_memory()                       # singleton: store, kg, facts, reflections, glossary

mem.kg.search("air quality in a city")     # [Procedure]
mem.kg.compile(plan_dict)                  # {steps, levels, added, warnings}
mem.kg.closure("convert_amount")           # ['get_fx_rate']
mem.kg.add_edge("a", "b", "DEPENDS_ON", {"x": "y"})
mem.kg.to_mermaid(); mem.kg.stats()

mem.glossary.resolve("50 dollars to rupees")    # terms found in text
mem.glossary.normalize_value("to_currency", "₹")  # 'INR'
mem.glossary.canonical_param("lng")             # 'longitude'
mem.glossary.define("MRR", "concept", "…", ["monthly recurring revenue"])

mem.facts.remember(user_id, "home_city", "User is based in Hyderabad", "preference")
mem.reflections.add_lesson(cue, lesson); mem.reflections.playbook()
```

## Execution

```python
from procedural_agent.harness.executor import run_plan, execute_call, extract, safe_eval
results = await run_plan(mem.kg, compiled)            # {step_id: result}
```

## Ingestion

```python
from procedural_agent.harness.ingest import Ingestor, render_report
ing = Ingestor(mem, test_calls=True)
report = await ing.stage(text, "runbook.md")
print(render_report(report))
ing.apply(report["batch_id"], approve=["a->b"])       # or "all"
```

## Models

```python
from procedural_agent import llm
llm.parse("truefoundry/azure-openai-main/gpt-4o")     # ModelSpec
llm.build_model("azure/x|gemini-3.5-flash", role="synthesizer", reasoning="auto")
await llm.complete_json("openai/gpt-4.1-mini", prompt, MyPydanticModel)
llm.describe(spec)                                    # resolution, with secrets masked
```

## Prompts

```python
from procedural_agent import prompts
prompts.split("planner")          # (static, dynamic template)
prompts.save_version("synthesizer", text, note="…", activate=True)
prompts.rollback("synthesizer", 0)
```
