"""Abstract base class for all agent runtime adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterable


@dataclass
class RunHandle:
    """Opaque handle returned when an adapter starts a run."""
    run_id: str
    pid: int | None = None          # subprocess PID, if applicable
    external_id: str | None = None  # webhook job ID, if applicable


@dataclass
class RunStatus:
    """Point-in-time status of a run."""
    run_id: str
    status: str  # pending | running | completed | failed | cancelled
    output: str | None = None
    error: str | None = None
    tokens_used: int = 0
    cost_usd_cents: int = 0  # stored as integer cents to avoid float issues


@dataclass
class OutputChunk:
    """A single streamed output fragment."""
    run_id: str
    data: str
    chunk_type: str = "stdout"  # stdout | stderr | log
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentAdapter(ABC):
    """
    Pluggable runtime adapter interface.

    Each adapter knows how to launch, stop, query, and stream output from
    a specific kind of agent runtime (local subprocess, HTTP webhook, etc.).
    """

    @abstractmethod
    async def start(self, agent_id: str, task: dict[str, Any]) -> RunHandle:
        """Launch the agent for the given task and return a RunHandle."""

    @abstractmethod
    async def stop(self, run_id: str) -> None:
        """Gracefully terminate an active run."""

    @abstractmethod
    async def get_status(self, run_id: str) -> RunStatus:
        """Return the current status of a run."""

    @abstractmethod
    async def stream_output(self, run_id: str) -> AsyncIterable[OutputChunk]:
        """
        Yield output chunks as they become available.

        Implementations should yield an empty async iterable when the run
        has already completed.
        """
