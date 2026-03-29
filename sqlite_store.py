"""
SQLite-backed persistent store for AgentOS POC.
Drop-in replacement for the in-memory Store class.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from typing import Optional

from models import AgentRole, Task, TaskStatus, Workflow

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    role        TEXT NOT NULL DEFAULT 'planner',
    status      TEXT NOT NULL DEFAULT 'pending',
    input       TEXT NOT NULL DEFAULT '',
    output      TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL DEFAULT 0,
    completed_at REAL,
    depends_on  TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS workflows (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  REAL NOT NULL DEFAULT 0,
    task_ids    TEXT NOT NULL DEFAULT '[]'
);
"""


def _task_from_row(row: dict) -> Task:
    return Task(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        role=AgentRole(row["role"]),
        status=TaskStatus(row["status"]),
        input=row["input"],
        output=row["output"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        depends_on=json.loads(row["depends_on"]),
    )


class SqliteStore:
    """Persistent store backed by SQLite with the same interface as Store."""

    def __init__(self, db_path: str = "./agentos.db"):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def add_task(self, task: Task) -> Task:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO tasks
                  (id, title, description, role, status, input, output,
                   created_at, completed_at, depends_on)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.title,
                    task.description,
                    task.role.value,
                    task.status.value,
                    task.input,
                    task.output,
                    task.created_at,
                    task.completed_at,
                    json.dumps(task.depends_on),
                ),
            )
            self._conn.commit()
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return _task_from_row(dict(row)) if row else None

    def update_task(self, task_id: str, **kwargs) -> Optional[Task]:
        task = self.get_task(task_id)
        if not task:
            return None
        for key, value in kwargs.items():
            setattr(task, key, value)
        self.add_task(task)
        return task

    def list_tasks(self, status: Optional[TaskStatus] = None) -> list[Task]:
        with self._lock:
            if status:
                rows = self._conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY created_at",
                    (status.value,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM tasks ORDER BY created_at"
                ).fetchall()
        return [_task_from_row(dict(r)) for r in rows]

    # ------------------------------------------------------------------
    # Workflows
    # ------------------------------------------------------------------

    def add_workflow(self, workflow: Workflow) -> Workflow:
        for task in workflow.tasks:
            self.add_task(task)
        task_ids = json.dumps([t.id for t in workflow.tasks])
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO workflows
                  (id, title, description, status, created_at, task_ids)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow.id,
                    workflow.title,
                    workflow.description,
                    workflow.status.value,
                    workflow.created_at,
                    task_ids,
                ),
            )
            self._conn.commit()
        return workflow

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM workflows WHERE id = ?", (workflow_id,)
            ).fetchone()
        if not row:
            return None
        row = dict(row)
        task_ids: list[str] = json.loads(row["task_ids"])
        tasks = [self.get_task(tid) for tid in task_ids]
        tasks = [t for t in tasks if t is not None]
        return Workflow(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            status=TaskStatus(row["status"]),
            created_at=row["created_at"],
            tasks=tasks,
        )

    def list_workflows(self) -> list[Workflow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM workflows ORDER BY created_at"
            ).fetchall()
        return [wf for row in rows if (wf := self.get_workflow(row["id"])) is not None]
