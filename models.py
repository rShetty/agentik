"""
Core data models for AgentOS POC.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid
import time


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    NEEDS_REVISION = "needs_revision"  # reviewer flagged issues


class AgentRole(str, Enum):
    PLANNER = "planner"
    ENGINEER = "engineer"
    REVIEWER = "reviewer"


@dataclass
class Task:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = ""
    description: str = ""
    role: AgentRole = AgentRole.PLANNER
    status: TaskStatus = TaskStatus.PENDING
    input: str = ""
    output: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    depends_on: list[str] = field(default_factory=list)  # task ids
    revision_count: int = 0  # how many times this task has been revised


@dataclass
class Workflow:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = ""
    description: str = ""
    tasks: list[Task] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    max_revisions: int = 3  # max engineer→reviewer cycles


@dataclass
class AgentDef:
    role: AgentRole
    name: str
    system_prompt: str
