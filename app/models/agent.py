"""SQLAlchemy ORM models for agents, skills, and runs."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enumerations (stored as VARCHAR for portability)
# ---------------------------------------------------------------------------

AGENT_ROLES = ("ceo", "cto", "engineer", "researcher", "reviewer", "custom")
ADAPTER_TYPES = ("claude_local", "codex_local", "openai_assistants", "http_webhook")
AGENT_STATUSES = ("idle", "running", "paused", "stopped", "deactivated")
RUN_STATUSES = ("pending", "running", "completed", "failed", "cancelled")


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        Enum(*AGENT_ROLES, name="agent_role"), nullable=False
    )
    adapter_type: Mapped[str] = mapped_column(
        Enum(*ADAPTER_TYPES, name="adapter_type"), nullable=False
    )
    adapter_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(*AGENT_STATUSES, name="agent_status"),
        nullable=False,
        default="idle",
    )
    # Ordered list of parent agent IDs in chain of command
    chain_of_command: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Budget config: {"max_usd": float, "max_tokens": int, "pause_at_pct": int}
    budget: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    skills: Mapped[list[AgentSkill]] = relationship(
        "AgentSkill",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="AgentSkill.position",
    )
    runs: Mapped[list[AgentRun]] = relationship(
        "AgentRun",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="AgentRun.started_at.desc()",
    )


# ---------------------------------------------------------------------------
# AgentSkill  (join table with ordering)
# ---------------------------------------------------------------------------

class AgentSkill(Base):
    __tablename__ = "agent_skills"
    __table_args__ = (
        UniqueConstraint("agent_id", "skill_id", name="uq_agent_skill"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[str] = mapped_column(String(255), nullable=False)
    skill_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    agent: Mapped[Agent] = relationship("Agent", back_populates="skills")


# ---------------------------------------------------------------------------
# AgentRun
# ---------------------------------------------------------------------------

class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        Enum(*RUN_STATUSES, name="run_status"), nullable=False, default="pending"
    )
    trigger: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g. "heartbeat", "manual"
    input_context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    agent: Mapped[Agent] = relationship("Agent", back_populates="runs")
