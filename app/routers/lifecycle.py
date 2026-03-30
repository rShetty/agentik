"""Agent lifecycle and runtime API router.

Endpoints
---------
POST /agents/:id/start   — trigger a heartbeat run
POST /agents/:id/stop    — gracefully terminate active run
POST /agents/:id/pause   — suspend scheduling (no new runs started)
POST /agents/:id/resume  — re-enable scheduling
PATCH /agents/:id/instructions-path — set the agent's instructions file path

GET  /agents/:id/runs/:run_id        — get a single run's status
GET  /agents/:id/budget              — query current budget utilisation
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adapters.registry import get_adapter
from app.database import get_db
from app.deps import get_company_id
from app.models.agent import Agent, AgentRun
from app.runtime.budget import assert_within_budget, check_budget
from app.runtime.exceptions import BudgetExceededError, InvalidTransitionError
from app.runtime.lifecycle import next_state
from app.runtime.prompts import compose_system_prompt

router = APIRouter(prefix="/agents", tags=["lifecycle"])

CompanyId = Annotated[str, Depends(get_company_id)]
DB = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class RunOut(BaseModel):
    id: str
    agent_id: str
    status: str
    trigger: str | None
    input_context: dict[str, Any] | None
    output: str | None
    error: str | None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class BudgetOut(BaseModel):
    tokens_used: int
    tokens_limit: int | None
    tokens_pct: float | None
    usd_used_cents: int
    usd_limit_cents: int | None
    usd_pct: float | None
    should_pause: bool
    is_exhausted: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_agent_or_404(agent_id: str, company_id: str, db: Session) -> Agent:
    agent = (
        db.query(Agent)
        .filter(
            Agent.id == agent_id,
            Agent.company_id == company_id,
            Agent.deleted_at.is_(None),
        )
        .first()
    )
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )
    return agent


def _apply_transition(agent: Agent, action: str, db: Session) -> None:
    """Apply a lifecycle transition, persisting the new state."""
    try:
        new_state = next_state(agent.status, action)
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    agent.status = new_state
    db.commit()
    db.refresh(agent)


# ---------------------------------------------------------------------------
# POST /agents/:id/start
# ---------------------------------------------------------------------------

class StartRunRequest(BaseModel):
    trigger: str = "manual"
    input_context: dict[str, Any] | None = None
    skill_instructions: list[str] | None = None
    company_context: str | None = None


@router.post("/{agent_id}/start", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
async def start_agent(
    agent_id: str,
    body: StartRunRequest,
    company_id: CompanyId,
    db: DB,
) -> RunOut:
    """Trigger a new heartbeat run for an agent."""
    agent = _get_agent_or_404(agent_id, company_id, db)

    # Budget guard
    try:
        assert_within_budget(
            agent.budget,
            tokens_used=0,  # cumulative tokens not tracked per-agent yet; guarded by run history
            usd_used_cents=0,
        )
    except BudgetExceededError as exc:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc))

    # Lifecycle guard — only idle agents can start
    try:
        new_state = next_state(agent.status, "start")
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    # Build system prompt
    task = body.input_context or {}
    system_prompt = compose_system_prompt(
        role=agent.role,
        agent_override=agent.system_prompt,
        company_context=body.company_context,
        skill_instructions=body.skill_instructions,
        task_context=task,
    )
    task["system_prompt"] = system_prompt

    # Create run record (pending → running via adapter)
    run = AgentRun(
        agent_id=agent.id,
        status="running",
        trigger=body.trigger,
        input_context=task,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)

    # Transition agent to running
    agent.status = new_state
    db.commit()
    db.refresh(run)

    # Fire adapter asynchronously (best-effort; errors recorded on run)
    adapter = get_adapter(agent.adapter_type, agent.adapter_config)
    try:
        handle = await adapter.start(agent_id=agent.id, task=task)
        run.input_context = {**(run.input_context or {}), "run_handle_id": handle.run_id}
        db.commit()
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        agent.status = "idle"
        db.commit()

    db.refresh(run)
    return run  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# POST /agents/:id/stop
# ---------------------------------------------------------------------------

@router.post("/{agent_id}/stop", response_model=dict)
async def stop_agent(
    agent_id: str,
    company_id: CompanyId,
    db: DB,
) -> dict:
    """Gracefully stop the active run and transition agent to stopped."""
    agent = _get_agent_or_404(agent_id, company_id, db)
    _apply_transition(agent, "stop", db)

    # Cancel any in-progress runs
    active_runs = (
        db.query(AgentRun)
        .filter(AgentRun.agent_id == agent_id, AgentRun.status == "running")
        .all()
    )
    adapter = get_adapter(agent.adapter_type, agent.adapter_config)
    for run in active_runs:
        try:
            handle_id = (run.input_context or {}).get("run_handle_id", run.id)
            await adapter.stop(handle_id)
        except Exception:
            pass
        run.status = "cancelled"
        run.completed_at = datetime.now(timezone.utc)
    db.commit()

    return {"agent_id": agent_id, "status": agent.status}


# ---------------------------------------------------------------------------
# POST /agents/:id/pause
# ---------------------------------------------------------------------------

@router.post("/{agent_id}/pause", response_model=dict)
def pause_agent(agent_id: str, company_id: CompanyId, db: DB) -> dict:
    """Suspend scheduling — no new runs will be started."""
    agent = _get_agent_or_404(agent_id, company_id, db)
    _apply_transition(agent, "pause", db)
    return {"agent_id": agent_id, "status": agent.status}


# ---------------------------------------------------------------------------
# POST /agents/:id/resume
# ---------------------------------------------------------------------------

@router.post("/{agent_id}/resume", response_model=dict)
def resume_agent(agent_id: str, company_id: CompanyId, db: DB) -> dict:
    """Re-enable scheduling after a pause."""
    agent = _get_agent_or_404(agent_id, company_id, db)
    _apply_transition(agent, "resume", db)
    return {"agent_id": agent_id, "status": agent.status}


# ---------------------------------------------------------------------------
# PATCH /agents/:id/instructions-path
# ---------------------------------------------------------------------------

class InstructionsPathRequest(BaseModel):
    path: str | None


@router.patch("/{agent_id}/instructions-path", response_model=dict)
def set_instructions_path(
    agent_id: str,
    body: InstructionsPathRequest,
    company_id: CompanyId,
    db: DB,
) -> dict:
    """Set or clear the agent's instructions file path."""
    agent = _get_agent_or_404(agent_id, company_id, db)
    # Store in adapter_config under the conventional key
    config = dict(agent.adapter_config or {})
    if body.path is None:
        config.pop("instructionsFilePath", None)
    else:
        config["instructionsFilePath"] = body.path
    agent.adapter_config = config
    db.commit()
    return {"agent_id": agent_id, "instructions_path": body.path}


# ---------------------------------------------------------------------------
# GET /agents/:id/runs/:run_id — single run status
# ---------------------------------------------------------------------------

@router.get("/{agent_id}/runs/{run_id}", response_model=RunOut)
async def get_run(
    agent_id: str,
    run_id: str,
    company_id: CompanyId,
    db: DB,
) -> RunOut:
    """Return the current status of a specific run."""
    agent = _get_agent_or_404(agent_id, company_id, db)
    run = (
        db.query(AgentRun)
        .filter(AgentRun.id == run_id, AgentRun.agent_id == agent.id)
        .first()
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    # Sync status from adapter if still running
    if run.status == "running":
        adapter = get_adapter(agent.adapter_type, agent.adapter_config)
        handle_id = (run.input_context or {}).get("run_handle_id", run.id)
        try:
            run_status = await adapter.get_status(handle_id)
            if run_status.status in ("completed", "failed", "cancelled"):
                run.status = run_status.status
                run.output = run_status.output
                run.error = run_status.error
                run.completed_at = datetime.now(timezone.utc)
                if run_status.status == "completed":
                    agent.status = "idle"
                db.commit()
        except Exception:
            pass

    db.refresh(run)
    return run  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# GET /agents/:id/budget
# ---------------------------------------------------------------------------

@router.get("/{agent_id}/budget", response_model=BudgetOut)
def get_budget(agent_id: str, company_id: CompanyId, db: DB) -> BudgetOut:
    """Return budget utilisation for an agent."""
    agent = _get_agent_or_404(agent_id, company_id, db)
    bs = check_budget(agent.budget, tokens_used=0, usd_used_cents=0)
    return BudgetOut(
        tokens_used=bs.tokens_used,
        tokens_limit=bs.tokens_limit,
        tokens_pct=bs.tokens_pct,
        usd_used_cents=bs.usd_used_cents,
        usd_limit_cents=bs.usd_limit_cents,
        usd_pct=bs.usd_pct,
        should_pause=bs.should_pause,
        is_exhausted=bs.is_exhausted,
    )
