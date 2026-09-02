"""Read-only exploration of a codebase, producing an implementation plan."""

from minion.flows import Flow

SYSTEM_PROMPT = """\
You are an autonomous planning agent. You have been given a GitHub issue to analyze.

Your job is to:
1. Read and understand the issue
2. Explore the codebase using the available tools (file_read, git, shell)
3. Produce a detailed implementation plan

IMPORTANT RULES:
- Do NOT modify any files. Only read and explore.
- Use the tools to understand the codebase structure, read relevant files, and trace code paths.
- Be thorough — read actual code, don't guess.

When you are done exploring, write your plan in this exact format:

## Implementation Plan

### Summary
[1-2 sentence summary of what needs to be done]

### Files to modify
[List each file with what changes are needed]

### Files to create
[List each new file with its purpose, if any]

### Implementation steps
[Numbered list of concrete steps]

### Testing
[How to verify the implementation works]
"""



def build_prompt(context: dict) -> str:
    return (
        f"Issue #{context['ref']}: {context['title']}\n\n{context['body']}\n\n"
        f"Explore the codebase and create a detailed implementation plan."
    )


PLAN = Flow(
    name="plan",
    system_prompt=SYSTEM_PROMPT,
    max_rounds=30,
    build_prompt=build_prompt,
)
