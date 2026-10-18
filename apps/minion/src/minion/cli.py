"""One flow, once, from the terminal.

`python -m minion run <flow> key=value ...` builds a context from the arguments, runs
the flow through the configured backend and prints the result and what it cost. No
store, no worker, no provider: this is how a flow, a model, an MCP server or a skill
gets tried on one real input before anything is deployed to Venus.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from minion.agent_definition import load_agent
from minion.agents import create_agent
from minion.config import load_config
from minion.flows import registry
from minion.tools import create_registry


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="minion run")
    parser.add_argument("flow", nargs="?", help="flow name, see `minion run --list`")
    parser.add_argument("pairs", nargs="*", metavar="key=value", help="context fields")
    parser.add_argument("--workdir", default=".", help="directory the agent works in")
    parser.add_argument("--context", type=Path, help="JSON file with context fields")
    parser.add_argument(
        "--agent", type=Path, help="agent definition directory, e.g. agents/triage"
    )
    parser.add_argument("--list", action="store_true", help="list flows and exit")
    # Intermixed: `key=value` pairs may follow `--workdir` and friends.
    return parser.parse_intermixed_args(argv)


def build_context(args: argparse.Namespace) -> dict:
    context: dict = {}
    if args.context:
        context.update(json.loads(args.context.read_text()))
    for pair in args.pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            sys.exit(f"expected key=value, got {pair!r}")
        # `key=@file` reads the value from a file — a log line or issue body is
        # easier pasted into a file than escaped on a command line.
        context[key] = Path(value[1:]).read_text() if value.startswith("@") else value
    context["workdir"] = str(Path(args.workdir).resolve())
    return context


async def run_once(argv: list[str]) -> int:
    args = parse_args(argv)
    flows = registry()
    if args.list:
        for name, flow in flows.items():
            print(f"{name:20} {flow.max_rounds:3} rounds")
        return 0
    if not args.flow or args.flow not in flows:
        sys.exit(f"unknown flow {args.flow!r}; one of {', '.join(flows)}")

    config = load_config()
    definition = load_agent(args.agent) if args.agent else None
    agent = create_agent(config, create_registry(config.tools), definition)
    report, run = await flows[args.flow].run(agent, build_context(args))

    print(report["result"])
    print(f"\n-- {run.total_tokens} tokens {json.dumps(run.usage())}", file=sys.stderr)
    return 0


def main(argv: list[str]) -> int:
    return asyncio.run(run_once(argv))
