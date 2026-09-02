"""Subprocess helpers shared by git-backed providers."""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def run(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        error = stderr.decode().strip()
        logger.error("%s failed: %s", " ".join(args[:3]), error)
        raise RuntimeError(f"{' '.join(args[:3])} failed: {error}")
    return stdout.decode().strip()


async def try_run(*args: str) -> bool:
    """Run a command, reporting success instead of raising.

    Used where failure is a legitimate answer rather than an error — losing a claim
    race, most of all.
    """
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.debug("%s did not succeed: %s", " ".join(args[:3]), stderr.decode().strip())
        return False
    return True


async def git(repo: str, *args: str) -> str:
    return await run("git", "-C", repo, *args)
