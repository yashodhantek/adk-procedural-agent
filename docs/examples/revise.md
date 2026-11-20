# 5. Critic asks for a revision

The first draft is missing units and a timestamp. The critic rejects it, and the gate sends it back to the synthesizer with the issue.

--8<-- "ex_revise.md"

## What to notice

- **The loop:** the node path shows `synthesizer → prepare_review → critic → gate` twice. The second synthesizer call received the previous draft and the critic's issues.
- **Two verdicts:** a rejection at 0.55, then acceptance.
- **Reflexion:** because the first draft failed, `learn` wrote a lesson. Similar future questions get it in their prompts, so the first draft should pass.
- **Playbook credit:** the bullets in context were marked *harmful* this turn, because it wasn't a first-try success.

Related: [Self-correction](../capabilities/self-correction.md) · [Reflection & playbook](../capabilities/reflection.md)
