# Prompt caching

**What it does.** Makes repeated calls cheaper and faster by keeping a **byte-identical prefix**
that providers can cache, and by sending each provider the hint it needs.

## The prefix

```text
system:  [static_instruction: role rules]        ← identical on every call, so cacheable
         [tool declarations]                      ← identical while the tool set is unchanged
user:    [dynamic instruction: playbook, lessons, preferences]
user:    [this call's prompt: question, plan, results]
```

The prompt files are split at `<!-- dynamic -->`. Learning changes only the dynamic part, so a
growing playbook never invalidates the cache.

## Per provider

| Provider | What happens | What the agent sends |
|---|---|---|
| OpenAI | Automatic caching of a stable prefix of 1,024+ tokens | `prompt_cache_key="procedural-agent:<role>"` to improve hit rates |
| Azure OpenAI | Automatic for GPT-4o and later on a stable 1,024-token prefix | `prompt_cache_key` |
| TrueFoundry | Forwarded to the model behind the gateway | `prompt_cache_key` inside `extra_body` |
| Anthropic / Bedrock Claude | Explicit markers required | `cache_control_injection_points=[{"location": "message", "role": "system"}]` |
| Gemini | ADK `ContextCacheConfig` (explicit context cache) | `cache_intervals=10, ttl_seconds=1800, min_tokens=2048`, when `AGENT_MODEL` is Gemini |

Turn the hints off with `PROMPT_CACHE_HINTS=false` and the Gemini cache with `CONTEXT_CACHE=false`.

## Checking it works

- OpenAI/Azure responses report `usage.prompt_tokens_details.cached_tokens`.
- Anthropic reports `cache_read_input_tokens`.
- `ADK_LOGGING=1` or tracing shows the usage per call.

The offline test `test_static_prefix_is_stable_and_cache_key_sent` checks three things: the system
message is identical across sessions with different learned playbooks, it contains no learned
content, and `prompt_cache_key` is sent.
