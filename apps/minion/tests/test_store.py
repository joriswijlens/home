import tempfile
from pathlib import Path

import pytest

from minion.store import TaskStore


@pytest.fixture
def store(tmp_path: Path) -> TaskStore:
    s = TaskStore(str(tmp_path / "test.db"))
    yield s
    s.close()


def test_create_task(store: TaskStore) -> None:
    result = store.create_task("t1", "github", "42", "venus", "Fix bug")
    assert result is True
    task = store.get_task("t1")
    assert task is not None
    assert task["source"] == "github"
    assert task["external_ref"] == "42"
    assert task["agent"] == "venus"
    assert task["status"] == "claimed"
    assert task["title"] == "Fix bug"


def test_is_known(store: TaskStore) -> None:
    assert store.is_known("t1") is False
    store.create_task("t1", "github", "1", "venus", "Task")
    assert store.is_known("t1") is True


def test_update_status(store: TaskStore) -> None:
    store.create_task("t1", "github", "1", "venus", "Task")
    store.update_status("t1", "done")
    task = store.get_task("t1")
    assert task is not None
    assert task["status"] == "done"


def test_duplicate_insert_ignored(store: TaskStore) -> None:
    first = store.create_task("t1", "github", "1", "venus", "First")
    assert first is True
    second = store.create_task("t1", "github", "1", "mars", "Second")
    assert second is False
    task = store.get_task("t1")
    assert task is not None
    assert task["agent"] == "venus"


def test_conversation_messages(store: TaskStore) -> None:
    store.create_task("t1", "github", "1", "venus", "Task")
    store.add_message("t1", "user", "Hello")
    store.add_message("t1", "assistant", "Hi there")

    messages = store.get_conversation("t1")
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Hi there"


def test_list_tasks(store: TaskStore) -> None:
    store.create_task("t1", "github", "1", "venus", "Task 1")
    store.create_task("t2", "github", "2", "venus", "Task 2")
    store.update_status("t1", "done")

    all_tasks = store.list_tasks()
    assert len(all_tasks) == 2

    done_tasks = store.list_tasks(status="done")
    assert len(done_tasks) == 1
    assert done_tasks[0]["id"] == "t1"

    claimed_tasks = store.list_tasks(status="claimed")
    assert len(claimed_tasks) == 1
    assert claimed_tasks[0]["id"] == "t2"
