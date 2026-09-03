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

        # Deliberately the cheapest run that still proves the path works: lowest
        # effort, and a small ceiling so a rambling answer cannot cost real money.
        config.agent.effort = "low"
        config.agent.max_tokens = 2000

        agent = create_agent(config, create_registry(config.tools))

        print(f"model={config.agent.model} effort={config.agent.effort} "
              f"max_tokens={config.agent.max_tokens}")
        print(f"backend={config.agent.backend}\n")

        run = await agent.run(
            "You are a test harness. Use the tools you have; answer in one short line.",
            f"Read the file {marker} and tell me exactly what secret it contains.",
            max_rounds=5,
            label="smoke",
        )

    print(f"\n--- answer ---\n{run.text}\n")

    # Sonnet 5: $2 / $10 per MTok; cache reads 0.1x, writes 1.25x.
    cost = (
        run.input_tokens * 2.0
        + run.output_tokens * 10.0
        + run.cache_read_tokens * 0.20
        + run.cache_write_tokens * 2.50
    ) / 1_000_000
    print(
        f"tokens: in={run.input_tokens} out={run.output_tokens} "
        f"cache_read={run.cache_read_tokens} cache_write={run.cache_write_tokens}"
        f"  ≈ ${cost:.4f}"
    )
    if run.cache_read_tokens:
        saved = run.cache_read_tokens * (2.0 - 0.20) / 1_000_000
        print(f"caching works — read {run.cache_read_tokens} tokens, saved ${saved:.4f}")
    elif run.cache_write_tokens:
        print(
            "cache written but not read back — expected on a single round; a longer "
            "run should show reads."
        )
    else:
        print(
            "NO CACHING — prefix likely below the model's minimum cacheable size, "
            "or something upstream of the breakpoint changes per request."
        )

    if "artichoke" in run.text.lower():
        print("PASS — the model called the tool, read the file, and usage was recorded.")
        return 0

    print("FAIL — the model answered without the file's contents.")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
