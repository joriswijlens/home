import asyncio
import sys

if len(sys.argv) > 1 and sys.argv[1] == "run":
    from minion.cli import main

    sys.exit(main(sys.argv[2:]))

from minion.main import run

asyncio.run(run())
