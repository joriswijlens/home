"""Spins up one real NATS JetStream server for the whole test session.

There is no embedded/mock mode for JetStream, so this is Docker, not a fake. Each
test gets its own stream name (a uuid), so tests never see each other's events despite
sharing one server — the same isolation `tmp_path` gave the SQLite-backed store.
"""

import subprocess
import time
import uuid

import pytest

CONTAINER = "minion-pytest-nats"
PORT = 24222


def _docker_available() -> bool:
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@pytest.fixture(scope="session")
def nats_url():
    if not _docker_available():
        pytest.skip("Docker is required to run a JetStream server for these tests")

    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    subprocess.run(
        [
            "docker", "run", "-d", "--name", CONTAINER,
            "-p", f"{PORT}:4222",
            "nats:2-alpine", "-js",
        ],
        check=True,
        capture_output=True,
    )

    url = f"nats://localhost:{PORT}"
    _wait_for_ready(url)

    yield url

    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)


def _wait_for_ready(url: str, timeout: float = 10.0) -> None:
    import asyncio

    import nats as nats_client

    async def probe() -> None:
        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
            try:
                nc = await nats_client.connect(url)
                await nc.close()
                return
            except Exception as e:
                last_error = e
                await asyncio.sleep(0.2)
        raise RuntimeError(f"nats-server never became reachable: {last_error}")

    asyncio.run(probe())


@pytest.fixture
def stream_name():
    """A fresh stream per test — isolation without needing per-test cleanup."""
    return f"TEST_{uuid.uuid4().hex[:12].upper()}"
