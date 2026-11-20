"""Stand-alone synthesizer used as the target of ADK's GEPA prompt optimizer.

`adk optimize` tunes the instruction of a single root Agent. The production
root is a Workflow, so this lab exposes the synthesizer alone (same tools,
same prompt template). Template slots are written as <playbook>, <lessons>,
<preferences> so ADK's {state} templating leaves them alone; improve.py maps
them back to {{...}} before saving a new prompt version.
"""

from procedural_agent import prompts
from procedural_agent.agent import build_agents

LAB_PREAMBLE = ("No plan has been run for you in this mode: find procedures with "
                "find_procedures and execute them with run_procedure.\n\n")

_, synthesizer, _ = build_agents()
root_agent = synthesizer.model_copy(update={
    "name": "synthesizer_lab",
    "static_instruction": None,          # GEPA optimises one instruction string
    "planner": None,
    "instruction": LAB_PREAMBLE + prompts.load("synthesizer").replace(prompts.DYNAMIC_MARKER + "\n", "")
        .replace("{{playbook}}", "<playbook>").replace("{{lessons}}", "<lessons>")
        .replace("{{preferences}}", "<preferences>"),
})
