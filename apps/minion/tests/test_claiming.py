from unittest.mock import AsyncMock, MagicMock

import pytest

from minion.claiming import TaskClaimer


@pytest.fixture
def claimer() -> TaskClaimer:
    return TaskClaimer("mars.local", 1883, "minion", "venus")


async def test_claim_without_client(claimer: TaskClaimer) -> None:
    result = await claimer.try_claim("task-1")
    assert result is True


async def test_claim_with_mock_client(claimer: TaskClaimer) -> None:
    mock_client = MagicMock()
    mock_client.publish = AsyncMock()
    claimer.set_client(mock_client)

    result = await claimer.try_claim("task-1")
    assert result is True
    mock_client.publish.assert_called_once()

    call_args = mock_client.publish.call_args
    assert call_args[0][0] == "minion/tasks/task-1/claimed"
    assert call_args[1]["retain"] is True


async def test_release(claimer: TaskClaimer) -> None:
    mock_client = MagicMock()
    mock_client.publish = AsyncMock()
    claimer.set_client(mock_client)

    await claimer.release("task-1")
    mock_client.publish.assert_called_once()

    call_args = mock_client.publish.call_args
    assert call_args[0][0] == "minion/tasks/task-1/claimed"
    assert call_args[0][1] == b""
    assert call_args[1]["retain"] is True


async def test_release_without_client(claimer: TaskClaimer) -> None:
    await claimer.release("task-1")  # should not raise
