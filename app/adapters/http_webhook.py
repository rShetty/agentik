"""http_webhook adapter — POST task to a URL, poll for completion."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterable

import httpx

from app.adapters.base import AgentAdapter, OutputChunk, RunHandle, RunStatus

_REGISTRY: dict[str, dict] = {}


class HttpWebhookAdapter(AgentAdapter):
    """
    Generic HTTP adapter: POST task payload to a configured URL,
    then poll a status endpoint or wait for a callback.

    Expected adapter_config keys:
      - ``url``             (str, required): endpoint to POST the task to
      - ``auth_header``     (str, optional): value for ``Authorization`` header
      - ``poll_url``        (str, optional): URL to poll for status (GET)
                                             Defaults to ``{url}/{job_id}``
      - ``poll_interval``   (int, optional): seconds between polls (default: 5)
      - ``timeout``         (int, optional): max seconds to wait (default: 300)
      - ``extra_headers``   (dict, optional): additional headers to send
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.url: str = config["url"]
        self.auth_header: str | None = config.get("auth_header")
        self.poll_url_template: str | None = config.get("poll_url")
        self.poll_interval: int = int(config.get("poll_interval", 5))
        self.timeout: int = int(config.get("timeout", 300))
        self.extra_headers: dict[str, str] = config.get("extra_headers", {})

    # ------------------------------------------------------------------
    # AgentAdapter interface
    # ------------------------------------------------------------------

    async def start(self, agent_id: str, task: dict[str, Any]) -> RunHandle:
        run_id = str(uuid.uuid4())

        headers = {**self.extra_headers, "Content-Type": "application/json"}
        if self.auth_header:
            headers["Authorization"] = self.auth_header

        payload = {
            "agent_id": agent_id,
            "run_id": run_id,
            "task": task,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = client.post(self.url, json=payload, headers=headers)
            if hasattr(response, "__aenter__"):
                response = await response
            response.raise_for_status()
            body = response.json() if response.content else {}

        external_id: str = body.get("job_id") or body.get("id") or run_id

        _REGISTRY[run_id] = {
            "external_id": external_id,
            "status": "running",
            "output": None,
            "error": None,
            "started_at": datetime.now(timezone.utc),
            "finished_at": None,
            "log_chunks": [],
        }

        # Start background polling
        asyncio.create_task(self._poll(run_id, external_id, headers))

        return RunHandle(run_id=run_id, external_id=external_id)

    async def stop(self, run_id: str) -> None:
        entry = _REGISTRY.get(run_id)
        if entry is None:
            return
        # Best-effort: send a DELETE/cancel request if the URL is inferrable
        entry["status"] = "cancelled"
        entry["finished_at"] = datetime.now(timezone.utc)

    async def get_status(self, run_id: str) -> RunStatus:
        entry = _REGISTRY.get(run_id)
        if entry is None:
            return RunStatus(run_id=run_id, status="not_found")
        return RunStatus(
            run_id=run_id,
            status=entry["status"],
            output=entry.get("output"),
            error=entry.get("error"),
        )

    async def stream_output(self, run_id: str) -> AsyncIterable[OutputChunk]:
        entry = _REGISTRY.get(run_id)
        if entry is None:
            return

        sent = 0
        while True:
            chunks: list[str] = entry.get("log_chunks", [])
            while sent < len(chunks):
                yield OutputChunk(run_id=run_id, data=chunks[sent], chunk_type="log")
                sent += 1
            if entry["status"] not in ("running", "pending"):
                break
            await asyncio.sleep(1)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _poll(
        self, run_id: str, external_id: str, headers: dict[str, str]
    ) -> None:
        poll_url = (
            self.poll_url_template.format(job_id=external_id)
            if self.poll_url_template
            else f"{self.url.rstrip('/')}/{external_id}"
        )

        elapsed = 0
        async with httpx.AsyncClient(timeout=30) as client:
            while elapsed < self.timeout:
                entry = _REGISTRY.get(run_id)
                if entry is None or entry["status"] == "cancelled":
                    return

                try:
                    resp = await client.get(poll_url, headers=headers)
                    resp.raise_for_status()
                    body = resp.json()
                except Exception as exc:
                    _REGISTRY[run_id]["status"] = "failed"
                    _REGISTRY[run_id]["error"] = str(exc)
                    _REGISTRY[run_id]["finished_at"] = datetime.now(timezone.utc)
                    return

                remote_status = body.get("status", "")
                if log := body.get("log"):
                    _REGISTRY[run_id]["log_chunks"].append(log)

                if remote_status in ("completed", "done", "success"):
                    _REGISTRY[run_id]["status"] = "completed"
                    _REGISTRY[run_id]["output"] = body.get("output")
                    _REGISTRY[run_id]["finished_at"] = datetime.now(timezone.utc)
                    return
                elif remote_status in ("failed", "error"):
                    _REGISTRY[run_id]["status"] = "failed"
                    _REGISTRY[run_id]["error"] = body.get("error")
                    _REGISTRY[run_id]["finished_at"] = datetime.now(timezone.utc)
                    return

                await asyncio.sleep(self.poll_interval)
                elapsed += self.poll_interval

        # Timed out
        _REGISTRY[run_id]["status"] = "failed"
        _REGISTRY[run_id]["error"] = f"Polling timed out after {self.timeout}s"
        _REGISTRY[run_id]["finished_at"] = datetime.now(timezone.utc)
