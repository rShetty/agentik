"""
FastAPI HTTP server layer for AgentOS POC.

Endpoints:
  POST /workflows      — create and run a workflow from a feature request
  GET  /workflows/{id} — get workflow status and task outputs
  GET  /workflows      — list all workflows
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

import os

from agents import AgentRuntime
from demo import build_feature_workflow
from models import TaskStatus, Workflow
from orchestrator import Orchestrator
from sqlite_store import SqliteStore
from vector_memory import VectorMemory

# ---------------------------------------------------------------------------
# Shared state — persistent across restarts
# ---------------------------------------------------------------------------

store = SqliteStore(os.getenv("AGENTOS_DB_PATH", "./agentos.db"))
memory = VectorMemory(os.getenv("AGENTOS_MEMORY_PATH", "./agentos_memory"))
runtime = AgentRuntime(memory=memory)
orchestrator = Orchestrator(store, runtime, verbose=False)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class CreateWorkflowRequest(BaseModel):
    request: str
    react: bool = True  # default to ReAct loop


class TaskOut(BaseModel):
    id: str
    title: str
    role: str
    status: str
    output: str


class WorkflowOut(BaseModel):
    id: str
    title: str
    description: str
    status: str
    tasks: list[TaskOut]


def _workflow_out(wf: Workflow) -> WorkflowOut:
    return WorkflowOut(
        id=wf.id,
        title=wf.title,
        description=wf.description,
        status=wf.status.value,
        tasks=[
            TaskOut(
                id=t.id,
                title=t.title,
                role=t.role.value,
                status=t.status.value,
                output=t.output,
            )
            for t in wf.tasks
        ],
    )


# ---------------------------------------------------------------------------
# Background execution helper
# ---------------------------------------------------------------------------


def _run_workflow_sync(workflow: Workflow, react: bool = False) -> None:
    """Execute the workflow synchronously in a thread-pool worker."""
    if react:
        orchestrator.run_workflow_react(workflow)
    else:
        orchestrator.run_workflow(workflow)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="AgentOS POC", version="0.1.0")


@app.post("/workflows", status_code=202, response_model=WorkflowOut)
async def create_workflow(
    body: CreateWorkflowRequest, background_tasks: BackgroundTasks
) -> WorkflowOut:
    """Create a new workflow and start processing it in the background."""
    workflow = build_feature_workflow(body.request)
    # Register with the store immediately so it's queryable right away
    store.add_workflow(workflow)

    loop = asyncio.get_event_loop()
    background_tasks.add_task(
        loop.run_in_executor, None, _run_workflow_sync, workflow, body.react
    )

    return _workflow_out(workflow)


@app.get("/workflows/{workflow_id}", response_model=WorkflowOut)
def get_workflow(workflow_id: str) -> WorkflowOut:
    """Return the current status and task outputs for a workflow."""
    wf = store.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    return _workflow_out(wf)


@app.get("/workflows", response_model=list[WorkflowOut])
def list_workflows() -> list[WorkflowOut]:
    """List all workflows and their current status."""
    return [_workflow_out(wf) for wf in store.list_workflows()]
