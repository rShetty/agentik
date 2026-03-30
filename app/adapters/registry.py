"""Adapter factory: maps adapter_type strings to concrete implementations."""
from __future__ import annotations

from typing import Any

from app.adapters.base import AgentAdapter
from app.adapters.claude_local import ClaudeLocalAdapter
from app.adapters.codex_local import CodexLocalAdapter
from app.adapters.http_webhook import HttpWebhookAdapter

_ADAPTER_CLASSES: dict[str, type[AgentAdapter]] = {
    "claude_local": ClaudeLocalAdapter,
    "codex_local": CodexLocalAdapter,
    "http_webhook": HttpWebhookAdapter,
}


def get_adapter(adapter_type: str, config: dict[str, Any]) -> AgentAdapter:
    """Return an instantiated adapter for the given type and config.

    Raises ``ValueError`` if *adapter_type* is unknown.
    """
    cls = _ADAPTER_CLASSES.get(adapter_type)
    if cls is None:
        supported = ", ".join(_ADAPTER_CLASSES)
        raise ValueError(
            f"Unknown adapter_type '{adapter_type}'. Supported: {supported}"
        )
    return cls(config)
