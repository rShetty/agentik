"""Agent CRUD REST API router."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_company_id
from app.models.agent import Agent, AgentRun, AgentSkill
from app.schemas.agent import AgentCreate, AgentOut, AgentRunOut, AgentUpdate

router = APIRouter(prefix="/agents", tags=["agents"])

CompanyId = Annotated[str, Depends(get_company_id)]
DB = Annotated[Session, Depends(get_db)]


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


def _sync_skills(agent: Agent, skills: list, db: Session) -> None:
    """Replace the agent's skill set with the provided ordered list."""
    db.query(AgentSkill).filter(AgentSkill.agent_id == agent.id).delete()
    for pos, skill_ref in enumerate(skills):
        db.add(
            AgentSkill(
                agent_id=agent.id,
                skill_id=skill_ref.skill_id,
                skill_version=skill_ref.skill_version,
                position=pos,
            )
        )


# ---------------------------------------------------------------------------
# POST /agents — create
# ---------------------------------------------------------------------------

@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(body: AgentCreate, company_id: CompanyId, db: DB) -> AgentOut:
    """Create a new agent scoped to the caller's company."""
    agent = Agent(
        company_id=company_id,
        name=body.name,
        role=body.role,
        adapter_type=body.adapter_type,
        adapter_config=body.adapter_config,
        system_prompt=body.system_prompt,
        chain_of_command=body.chain_of_command,
        budget=body.budget.model_dump(exclude_none=True),
        status="idle",
    )
    db.add(agent)
    db.flush()  # get the generated id before syncing skills
    _sync_skills(agent, body.skills, db)
    db.commit()
    db.refresh(agent)
    return agent  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# GET /agents — list
# ---------------------------------------------------------------------------

@router.get("", response_model=list[AgentOut])
def list_agents(
    company_id: CompanyId,
    db: DB,
    role: str | None = Query(default=None),
    agent_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[AgentOut]:
    """List agents for the company with optional filters."""
    q = db.query(Agent).filter(
        Agent.company_id == company_id,
        Agent.deleted_at.is_(None),
    )
    if role:
        q = q.filter(Agent.role == role)
    if agent_status:
        q = q.filter(Agent.status == agent_status)
    return q.offset(offset).limit(limit).all()  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# GET /agents/:id — get single
# ---------------------------------------------------------------------------

@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: str, company_id: CompanyId, db: DB) -> AgentOut:
    """Return a single agent with its current runtime status."""
    return _get_agent_or_404(agent_id, company_id, db)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# PATCH /agents/:id — update
# ---------------------------------------------------------------------------

@router.patch("/{agent_id}", response_model=AgentOut)
def update_agent(
    agent_id: str, body: AgentUpdate, company_id: CompanyId, db: DB
) -> AgentOut:
    """Update agent config, prompt, metadata, or status."""
    agent = _get_agent_or_404(agent_id, company_id, db)

    if body.name is not None:
        agent.name = body.name
    if body.adapter_config is not None:
        agent.adapter_config = body.adapter_config
    if body.system_prompt is not None:
        agent.system_prompt = body.system_prompt
    if body.chain_of_command is not None:
        agent.chain_of_command = body.chain_of_command
    if body.budget is not None:
        agent.budget = body.budget.model_dump(exclude_none=True)
    if body.status is not None:
        agent.status = body.status
    if body.skills is not None:
        _sync_skills(agent, body.skills, db)

    db.commit()
    db.refresh(agent)
    return agent  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# DELETE /agents/:id — soft-delete
# ---------------------------------------------------------------------------

@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: str, company_id: CompanyId, db: DB) -> None:
    """Soft-delete (deactivate) an agent."""
    agent = _get_agent_or_404(agent_id, company_id, db)
    agent.deleted_at = datetime.now(timezone.utc)
    agent.status = "deactivated"
    db.commit()


# ---------------------------------------------------------------------------
# GET /agents/:id/runs — list runs
# ---------------------------------------------------------------------------

@router.get("/{agent_id}/runs", response_model=list[AgentRunOut])
def list_agent_runs(
    agent_id: str,
    company_id: CompanyId,
    db: DB,
    run_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[AgentRunOut]:
    """Return historical runs for an agent, newest first."""
    _get_agent_or_404(agent_id, company_id, db)
    q = db.query(AgentRun).filter(AgentRun.agent_id == agent_id)
    if run_status:
        q = q.filter(AgentRun.status == run_status)
    return (
        q.order_by(AgentRun.started_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )  # type: ignore[return-value]
