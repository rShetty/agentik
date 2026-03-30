"""Budget tracking and auto-pause logic.

Budget is stored on the Agent record as a JSON dict::

    {
        "max_usd": 10.0,        # maximum spend in USD (optional)
        "max_tokens": 100000,   # maximum token count (optional)
        "pause_at_pct": 80      # auto-pause threshold (0–100, default 80)
    }

Usage is tracked cumulatively across all runs for the agent.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.runtime.exceptions import BudgetExceededError


@dataclass
class BudgetStatus:
    """Snapshot of an agent's budget utilisation."""
    tokens_used: int
    tokens_limit: int | None
    tokens_pct: float | None          # 0.0–100.0, None if no limit
    usd_used_cents: int               # stored as integer cents
    usd_limit_cents: int | None
    usd_pct: float | None             # 0.0–100.0, None if no limit
    should_pause: bool
    is_exhausted: bool


def _cents(usd: float) -> int:
    return round(usd * 100)


def check_budget(
    budget_config: dict[str, Any],
    tokens_used: int,
    usd_used_cents: int,
) -> BudgetStatus:
    """Evaluate current usage against budget config.

    Returns a :class:`BudgetStatus` describing whether the agent should
    pause or is fully exhausted.
    """
    max_tokens: int | None = budget_config.get("max_tokens")
    max_usd: float | None = budget_config.get("max_usd")
    pause_at_pct: int = int(budget_config.get("pause_at_pct", 80))
    max_usd_cents: int | None = _cents(max_usd) if max_usd is not None else None

    tokens_pct: float | None = None
    usd_pct: float | None = None

    if max_tokens:
        tokens_pct = min((tokens_used / max_tokens) * 100, 100.0)
    if max_usd_cents:
        usd_pct = min((usd_used_cents / max_usd_cents) * 100, 100.0)

    # Exhausted when any metric reaches 100 %
    is_exhausted = bool(
        (tokens_pct is not None and tokens_pct >= 100.0)
        or (usd_pct is not None and usd_pct >= 100.0)
    )

    # Should pause when any metric crosses the pause threshold
    should_pause = is_exhausted or bool(
        (tokens_pct is not None and tokens_pct >= pause_at_pct)
        or (usd_pct is not None and usd_pct >= pause_at_pct)
    )

    return BudgetStatus(
        tokens_used=tokens_used,
        tokens_limit=max_tokens,
        tokens_pct=tokens_pct,
        usd_used_cents=usd_used_cents,
        usd_limit_cents=max_usd_cents,
        usd_pct=usd_pct,
        should_pause=should_pause,
        is_exhausted=is_exhausted,
    )


def assert_within_budget(
    budget_config: dict[str, Any],
    tokens_used: int,
    usd_used_cents: int,
) -> None:
    """Raise :class:`BudgetExceededError` if the agent's budget is exhausted."""
    status = check_budget(budget_config, tokens_used, usd_used_cents)
    if status.is_exhausted:
        raise BudgetExceededError(
            f"Agent budget exhausted — "
            f"tokens: {tokens_used}/{status.tokens_limit}, "
            f"USD: ${usd_used_cents/100:.2f}/${(status.usd_limit_cents or 0)/100:.2f}"
        )


def apply_run_usage(
    budget_config: dict[str, Any],
    current_tokens: int,
    current_usd_cents: int,
    run_tokens: int,
    run_usd_cents: int,
) -> tuple[int, int, bool]:
    """Add run usage to cumulative totals.

    Returns ``(new_tokens, new_usd_cents, should_pause)`` where
    ``should_pause`` is True if the updated totals exceed ``pause_at_pct``.
    """
    new_tokens = current_tokens + run_tokens
    new_usd_cents = current_usd_cents + run_usd_cents
    status = check_budget(budget_config, new_tokens, new_usd_cents)
    return new_tokens, new_usd_cents, status.should_pause
