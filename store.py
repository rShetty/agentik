"""
In-memory task and workflow store for AgentOS POC.
"""
from __future__ import annotations
from typing import Optional
from models import Task, Workflow, TaskStatus


class Store:
    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._workflows: dict[str, Workflow] = {}

    # --- Tasks ---

    def add_task(self, task: Task) -> Task:
        self._tasks[task.id] = task
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def update_task(self, task_id: str, **kwargs) -> Optional[Task]:
        task = self._tasks.get(task_id)
        if not task:
            return None
        for key, value in kwargs.items():
            setattr(task, key, value)
        return task

    def list_tasks(self, status: Optional[TaskStatus] = None) -> list[Task]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    # --- Workflows ---

    def add_workflow(self, workflow: Workflow) -> Workflow:
        self._workflows[workflow.id] = workflow
        for task in workflow.tasks:
            self.add_task(task)
        return workflow

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> list[Workflow]:
        return list(self._workflows.values())
