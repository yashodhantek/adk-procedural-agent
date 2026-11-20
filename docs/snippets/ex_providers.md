| Role | Spec | Provider | LiteLLM model | Reasoning | Extra call parameters |
|---|---|---|---|---|---|
| planner | `truefoundry/openai-main/gpt-5` | truefoundry | `openai/openai-main/gpt-5` | medium | `{"extra_body": {"prompt_cache_key": "procedural-agent:planner"}}` |
| synthesizer | `azure/gpt-4o-prod` | azure | `azure/gpt-4o-prod` | off | `{"prompt_cache_key": "procedural-agent:synthesizer"}` |
| ↳ fallback | `truefoundry/azure-openai-main/gpt-4o` | truefoundry | `openai/azure-openai-main/gpt-4o` | off | `{"extra_body": {"prompt_cache_key": "procedural-agent:synthesizer"}}` |
| ↳ fallback | `gemini-3.5-flash` | gemini | `gemini-3.5-flash` | medium | `—` |
| critic | `anthropic/claude-sonnet-4-5` | litellm | `anthropic/claude-sonnet-4-5` | low | `{"cache_control_injection_points": [{"location": "message", "role": "system"}]}` |
| learner | `openai/gpt-4.1-mini` | openai | `openai/gpt-4.1-mini` | off | `{"prompt_cache_key": "procedural-agent:learner"}` |
| summarizer | `gemini-3.5-flash` | gemini | `gemini-3.5-flash` | medium | `—` |
