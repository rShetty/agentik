"""codex_local adapter — spawn an OpenAI Codex CLI subprocess per run."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterable

from app.adapters.base import AgentAdapter, OutputChunk, RunHandle, RunStatus

_REGISTRY: dict[str, dict] = {}


class CodexLocalAdapter(AgentAdapter):
    """
    Launches ``codex`` (OpenAI Codex CLI) as a subprocess.

    Expected adapter_config keys:
      - ``cwd``            (str, optional): working directory for the process
      - ``codex_binary``   (str, optional): path to the codex CLI (default: "codex")
      - ``env``            (dict, optional): extra environment variables
      - ``approval_mode``  (str, optional): --approval-mode flag (default: "auto-edit")
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.cwd = config.get("cwd")
        self.binary = config.get("codex_binary", "codex")
        self.extra_env = config.get("env", {})
        self.approval_mode = config.get("approval_mode", "auto-edit")

    async def start(self, agent_id: str, task: dict[str, Any]) -> RunHandle:
        run_id = str(uuid.uuid4())

        env = {**os.environ, **self.extra_env}
        env["PAPERCLIP_AGENT_ID"] = agent_id
        env["PAPERCLIP_RUN_ID"] = run_id
        env["AGENTIK_TASK_PAYLOAD"] = json.dumps(task)

        prompt = task.get("prompt") or json.dumps(task)

        cmd = [
            self.binary,
            "--approval-mode", self.approval_mode,
            prompt,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=env,
        )

        _REGISTRY[run_id] = {
            "process": process,
            "stdout_buf": [],
            "stderr_buf": [],
            "status": "running",
            "started_at": datetime.now(timezone.utc),
            "finished_at": None,
        }

        asyncio.create_task(self._drain(run_id))

        return RunHandle(run_id=run_id, pid=process.pid)

    async def stop(self, run_id: str) -> None:
        entry = _REGISTRY.get(run_id)
        if entry is None:
            return
        proc: asyncio.subprocess.Process = entry["process"]
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except asyncio.TimeoutError:
                proc.kill()
        entry["status"] = "cancelled"
        entry["finished_at"] = datetime.now(timezone.utc)

    async def get_status(self, run_id: str) -> RunStatus:
        entry = _REGISTRY.get(run_id)
        if entry is None:
            return RunStatus(run_id=run_id, status="not_found")

        proc: asyncio.subprocess.Process = entry["process"]
        if proc.returncode is not None and entry["status"] == "running":
            entry["status"] = "completed" if proc.returncode == 0 else "failed"
            entry["finished_at"] = datetime.now(timezone.utc)

        output = "".join(entry["stdout_buf"])
        error = "".join(entry["stderr_buf"]) or None
        return RunStatus(
            run_id=run_id,
            status=entry["status"],
            output=output if output else None,
            error=error,
        )

    async def stream_output(self, run_id: str) -> AsyncIterable[OutputChunk]:
        entry = _REGISTRY.get(run_id)
        if entry is None:
            return

        proc: asyncio.subprocess.Process = entry["process"]
        if proc.stdout is None:
            return

        async for line in proc.stdout:
            text = line.decode(errors="replace")
            entry["stdout_buf"].append(text)
            yield OutputChunk(run_id=run_id, data=text, chunk_type="stdout")

    async def _drain(self, run_id: str) -> None:
        entry = _REGISTRY[run_id]
        proc: asyncio.subprocess.Process = entry["process"]

        stdout, stderr = await proc.communicate()
        entry["stdout_buf"] = [stdout.decode(errors="replace")]
        entry["stderr_buf"] = [stderr.decode(errors="replace")]
        entry["status"] = "completed" if proc.returncode == 0 else "failed"
        entry["finished_at"] = datetime.now(timezone.utc)
