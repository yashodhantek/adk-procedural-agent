# Session state keys

| Key | Scope | Written by | Read by | Content |
|---|---|---|---|---|
| `temp:query` | turn | `recall` | nodes | The user's question |
| `temp:brief` | turn | `recall` | prompt builders | `{facts, episodes, glossary, procedures, cached_plan}` |
| `temp:playbook`, `temp:playbook_ids` | turn | `recall` | dynamic instructions, `learn` | Rendered bullets and their ids |
| `temp:lessons` | turn | `recall` | dynamic instructions | Relevant Reflexion lessons |
| `temp:plan` | turn | `compile_plan` | `learn` (plan cache) | The normalised planner output |
| `temp:compiled` | turn | `compile_plan` | executor, prompts, `learn` | Steps, levels, added steps, warnings, normalisations |
| `temp:results` | turn | `execute_plan` | prompts, `learn` | Step results |
| `temp:results_artifact` | turn | `execute_plan` | synthesizer prompt | `plan_results.json` |
| `temp:draft` | turn | `prepare_review` | `gate`, `learn` | Current draft |
| `temp:verdicts` | turn | `gate` | `learn` | Every verdict this turn |
| `temp:revision`, `temp:replans` | turn | `recall` (reset), `gate` | `gate` | Loop counters |
| `temp:unverified` | turn | `gate` | `respond` | Loops ran out |
| `temp:last_procedure_results` | turn | `run_procedure` | — | The last tool run |
| `plan` | session | planner `output_key` | — | Last plan |
| `draft` | session | synthesizer `output_key` | — | Last draft |
| `verdict` | session | critic `output_key` | — | Last verdict |
| `turns` | session | `recall` | — | Turn counter |
| `last_learning` | session | `learn` | `/learned`, UI | `{induced \| promoted \| deprecated \| lesson}` |
| `user:preferences` | user | `remember_fact` | synthesizer instruction | `{subject: fact}` |

ADK clears `temp:` keys at the end of each invocation, while `user:` keys follow the user across
sessions.
