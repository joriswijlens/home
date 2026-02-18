import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class TaskStore:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                external_ref TEXT NOT NULL,
                agent TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'claimed',
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL REFERENCES tasks(id),
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
        """)

    def create_task(
        self,
        task_id: str,
        source: str,
        external_ref: str,
        agent: str,
        title: str,
        status: str = "claimed",
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        try:
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO tasks "
                "(id, source, external_ref, agent, status, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (task_id, source, external_ref, agent, status, title, now, now),
            )
            self._conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error:
            logger.exception("Failed to create task %s", task_id)
            return False

    def update_status(self, task_id: str, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, task_id),
        )
        self._conn.commit()

    def get_task(self, task_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return dict(row) if row else None

    def is_known(self, task_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return row is not None

    def add_message(self, task_id: str, role: str, content: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO messages (task_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (task_id, role, content, now),
        )
        self._conn.commit()

    def get_conversation(self, task_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT role, content, timestamp FROM messages WHERE task_id = ? ORDER BY id",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_tasks(self, status: str | None = None) -> list[dict]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at", (status,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM tasks ORDER BY created_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
