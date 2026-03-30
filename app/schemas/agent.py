"""Pydantic schemas for request validation and API responses."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AgentRole = Literal["ceo", "cto", "engineer", "researcher", "reviewer", "custom"]
AdapterType = Literal["claude_local", "codex_local", "openai_assistants", "http_webhook"]
AgentStatus = Literal["idle", "running", "paused", "stopped", "deactivated"]
RunStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


# ---------------------------------------------------------------------------
# Shared nested schemas
# ---------------------------------------------------------------------------

class SkillRef(BaseModel):
    skill_id: str = Field(..., min_length=1, max_length=255)
    skill_version: str | None = None


class BudgetConfig(BaseModel):
    max_usd: float | None = None
    max_tokens: int | None = None
    pause_at_pct: int = Field(default=80, ge=0, le=100)


# ---------------------------------------------------------------------------
# Agent request schemas
# ---------------------------------------------------------------------------

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    role: AgentRole
    adapter_type: AdapterType
    adapter_config: dict[str, Any] = Field(default_factory=dict)
    system_prompt: str | None = None
    skills: list[SkillRef] = Field(default_factory=list)
    chain_of_command: list[str] = Field(default_factory=list)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    adapter_config: dict[str, Any] | None = None
    system_prompt: str | None = None
    skills: list[SkillRef] | None = None
    chain_of_command: list[str] | None = None
    budget: BudgetConfig | None = None
    status: AgentStatus | None = None


# ---------------------------------------------------------------------------
# Agent response schemas
# ---------------------------------------------------------------------------

class SkillRefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill_id: str
    skill_version: str | None
    position: int


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    name: str
    role: str
    adapter_type: str
    adapter_config: dict[str, Any]
    system_prompt: str | None
    status: str
    chain_of_command: list[str]
    budget: dict[str, Any]
    skills: list[SkillRefOut]
    created_at: datetime
    updated_at: datetime


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    status: str
    trigger: str | None
    input_context: dict[str, Any] | None
    output: str | None
    error: str | None
    started_at: datetime
    completed_at: datetime | None
