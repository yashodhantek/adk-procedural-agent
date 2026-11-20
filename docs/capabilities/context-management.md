# Context management

**What it does.** Keeps every model call small, relevant and cacheable, however long the
conversation runs.

| Technique | Where | Effect |
|---|---|---|
| **Per-node prompts** | `nodes._planner_prompt`, `_synth_prompt` | Workflow agents see only the context their job needs, not the whole chat |
| **Event compaction** | `EventsCompactionConfig` + `LlmEventSummarizer` | Older turns become summaries, by interval and by token threshold |
| **Context filter** | `ContextFilterPlugin` | Hard cap on past invocations sent to a model |
| **Result compaction** | `executor.compact()` | Lists cut to 5 items, strings to 400 characters; full data saved as artifacts |
| **Static/dynamic split** | `static_instruction` + instruction provider | A stable, cacheable prefix; learned content kept separate |
| **Progressive disclosure** | ADK Skills over the graph | Procedure detail loaded only on demand |
| **Targeted retrieval** | `recall` | Top-k procedures, top-4 episodes, relevant facts and lessons, top-N playbook |

## Event compaction

```python
EventsCompactionConfig(
    summarizer=LlmEventSummarizer(llm=build_model(SUMMARIZER_MODEL, role="summarizer")),
    compaction_interval=6,          # summarise every 6 invocations…
    overlap_size=1,                 # …overlapping one, so nothing falls between summaries
    token_threshold=60000,          # …or as soon as the prompt passes 60k tokens
    event_retention_size=12,        # keep the last 12 raw events after a token-triggered compaction
)
```

The summarizer can be any provider. Use a cheap model.

## Static and dynamic prompt parts

```markdown title="prompts/synthesizer.md"
You are the SYNTHESIZER of a real-time data agent ...        ← static_instruction
...rules...
<!-- dynamic -->
Playbook (learned strategies; follow them):                  ← instruction provider, every call
{{playbook}}
Lessons from past mistakes:
{{lessons}}
User preferences: {{preferences}}
```

With `static_instruction` set, ADK sends the dynamic part as user content. The system prefix
therefore stays byte-identical across calls, which is what provider prompt caches need. The offline
test `test_static_prefix_is_stable_and_cache_key_sent` checks that the system message is identical
across two sessions with different playbooks. See [Prompt caching](prompt-caching.md).

## Configuration

`COMPACTION_INTERVAL`, `COMPACTION_OVERLAP`, `COMPACTION_TOKEN_THRESHOLD`, `COMPACTION_KEEP_EVENTS`,
`CONTEXT_KEEP_INVOCATIONS`, `SUMMARIZER_MODEL`. Details are in
[Configuration](../getting-started/configuration.md#context-management).
