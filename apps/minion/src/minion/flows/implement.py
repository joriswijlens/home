"""Carry out an approved plan on a prepared branch."""

from minion.flows import Flow

SYSTEM_PROMPT = """\
You are an autonomous implementation agent. You have been given a GitHub issue with an approved plan.

Your job is to implement the plan exactly as described. You have access to tools for reading files, \
writing files, running shell commands, and git operations.

IMPORTANT RULES:
- Follow the plan closely. Do not deviate unless there's a clear technical reason.
- Write clean, well-structured code that matches existing patterns.
- Do NOT commit or push — that will be handled after you finish.
- Do NOT create unnecessary files or add extra features not in the plan.
"""



def build_prompt(context: dict) -> str:
    return (
        f"Issue #{context['ref']}: {context['title']}\n\n"
        f"Approved plan:\n\n{context['plan']}\n\n"
        f"Implement this plan now. The branch `{context['branch']}` is already "
        f"checked out."
    )


IMPLEMENT = Flow(
    name="implement",
    system_prompt=SYSTEM_PROMPT,
    max_rounds=50,
    build_prompt=build_prompt,
)
