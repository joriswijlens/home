"""What a run actually does.

A flow turns provider context into a prompt, runs the agent, and returns the result.
It never learns which system the work came from — claiming, labels, branches and PRs
all belong to the provider.
"""

from dataclasses import dataclass
from typing import Callable

from minion.agents import Agent, RunResult


@dataclass
class Flow:
    name: str
    system_prompt: str
    max_rounds: int
    build_prompt: Callable[[dict], str]

    async def run(self, agent: Agent, context: dict) -> tuple[dict, RunResult]:
        run = await agent.run(
            self.system_prompt,
            self.build_prompt(context),
            self.max_rounds,
            self.name,
            workdir=context.get("workdir"),
        )
        report = {
            "result": run.text,
            **{k: context[k] for k in ("branch",) if k in context},
        }
        return report, run


def registry() -> dict[str, Flow]:
    from minion.flows.implement import IMPLEMENT
    from minion.flows.plan import PLAN
    from minion.flows.triage import TRIAGE

    return {flow.name: flow for flow in (PLAN, IMPLEMENT, TRIAGE)}
