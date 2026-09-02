"""One real call against the Anthropic API, with one real tool use.

Verifies the things no test can: that the model id resolves, that `output_config`
is accepted, that the tool-use loop terminates, and that the tool registry actually
executes something. Costs a fraction of a cent.

    python scripts/smoke.py
"""

import asyncio
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from minion.agents import create_agent  # noqa: E402
from minion.config import load_config  # noqa: E402
from minion.tools import create_registry  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


async def main() -> int:
    config = load_config()

    if not config.anthropic_api_key:
        print(
            "No API key. Put `anthropic_api_key: sk-ant-...` in config/local.yml "
            "(gitignored) or set MINION_ANTHROPIC_API_KEY."
        )
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / "marker.txt"
        marker.write_text("the-secret-is-artichoke\n")

        config.tools.allowed_paths = [tmp]
        agent = create_agent(config, create_registry(config.tools))

        print(f"model={config.agent.model} effort={config.agent.effort}")
        print(f"backend={config.agent.backend}\n")

        answer = await agent.run(
            "You are a test harness. Use the tools you have; answer in one short line.",
            f"Read the file {marker} and tell me exactly what secret it contains.",
            max_rounds=5,
            label="smoke",
        )

    print(f"\n--- answer ---\n{answer}\n")

    if "artichoke" in answer.lower():
        print("PASS — the model called the tool and read the file.")
        return 0

    print("FAIL — the model answered without the file's contents.")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
