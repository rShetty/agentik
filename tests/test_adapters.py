"""Tests for the adapter layer: registry, base interface, and budget/prompt utilities."""
from __future__ import annotations

import pytest

from app.adapters.registry import get_adapter
from app.adapters.claude_local import ClaudeLocalAdapter
from app.adapters.codex_local import CodexLocalAdapter
from app.adapters.http_webhook import HttpWebhookAdapter
from app.runtime.budget import BudgetExceededError, apply_run_usage, assert_within_budget, check_budget
from app.runtime.exceptions import InvalidTransitionError
from app.runtime.prompts import compose_system_prompt, get_role_template


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

class TestAdapterRegistry:
    def test_get_claude_local(self):
        adapter = get_adapter("claude_local", {"cwd": "/tmp"})
        assert isinstance(adapter, ClaudeLocalAdapter)

    def test_get_codex_local(self):
        adapter = get_adapter("codex_local", {"cwd": "/tmp"})
        assert isinstance(adapter, CodexLocalAdapter)

    def test_get_http_webhook(self):
        adapter = get_adapter("http_webhook", {"url": "http://localhost:9999"})
        assert isinstance(adapter, HttpWebhookAdapter)

    def test_unknown_adapter_raises(self):
        with pytest.raises(ValueError, match="Unknown adapter_type"):
            get_adapter("magic_adapter", {})


# ---------------------------------------------------------------------------
# Adapter config
# ---------------------------------------------------------------------------

class TestClaudeLocalAdapter:
    def test_defaults(self):
        a = ClaudeLocalAdapter({})
        assert a.binary == "claude"
        assert a.max_turns == 10
        assert a.cwd is None

    def test_custom_config(self):
        a = ClaudeLocalAdapter({"claude_binary": "/usr/local/bin/claude", "max_turns": 5, "cwd": "/repo"})
        assert a.binary == "/usr/local/bin/claude"
        assert a.max_turns == 5
        assert a.cwd == "/repo"


class TestCodexLocalAdapter:
    def test_defaults(self):
        a = CodexLocalAdapter({})
        assert a.binary == "codex"
        assert a.approval_mode == "auto-edit"

    def test_custom_binary(self):
        a = CodexLocalAdapter({"codex_binary": "/opt/codex"})
        assert a.binary == "/opt/codex"


class TestHttpWebhookAdapter:
    def test_required_url(self):
        a = HttpWebhookAdapter({"url": "https://example.com/run"})
        assert a.url == "https://example.com/run"
        assert a.poll_interval == 5
        assert a.timeout == 300

    def test_custom_config(self):
        a = HttpWebhookAdapter({
            "url": "https://example.com/run",
            "poll_interval": 10,
            "timeout": 60,
            "auth_header": "Bearer secret",
        })
        assert a.poll_interval == 10
        assert a.timeout == 60
        assert a.auth_header == "Bearer secret"


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------

class TestBudget:
    def test_no_limits_never_pauses(self):
        status = check_budget({}, tokens_used=999_999, usd_used_cents=999_999)
        assert status.should_pause is False
        assert status.is_exhausted is False

    def test_token_limit_not_reached(self):
        status = check_budget({"max_tokens": 1000, "pause_at_pct": 80}, 700, 0)
        assert status.tokens_pct == pytest.approx(70.0)
        assert status.should_pause is False

    def test_token_pause_threshold(self):
        status = check_budget({"max_tokens": 1000, "pause_at_pct": 80}, 800, 0)
        assert status.should_pause is True
        assert status.is_exhausted is False

    def test_token_exhausted(self):
        status = check_budget({"max_tokens": 1000, "pause_at_pct": 80}, 1000, 0)
        assert status.is_exhausted is True

    def test_usd_pause_threshold(self):
        status = check_budget({"max_usd": 10.0, "pause_at_pct": 80}, 0, 800)
        assert status.should_pause is True

    def test_assert_within_budget_ok(self):
        # Should not raise
        assert_within_budget({"max_tokens": 1000}, 500, 0)

    def test_assert_within_budget_raises(self):
        with pytest.raises(BudgetExceededError):
            assert_within_budget({"max_tokens": 1000}, 1001, 0)

    def test_apply_run_usage(self):
        new_tokens, new_cents, should_pause = apply_run_usage(
            {"max_tokens": 1000, "pause_at_pct": 80},
            current_tokens=700,
            current_usd_cents=0,
            run_tokens=200,
            run_usd_cents=0,
        )
        assert new_tokens == 900
        assert should_pause is True


# ---------------------------------------------------------------------------
# System prompt composition
# ---------------------------------------------------------------------------

class TestPrompts:
    def test_role_template_engineer(self):
        t = get_role_template("engineer")
        assert "software engineer" in t.lower()

    def test_role_template_unknown(self):
        assert get_role_template("alien") == ""

    def test_compose_minimal(self):
        prompt = compose_system_prompt(role="engineer")
        assert "software engineer" in prompt.lower()

    def test_compose_with_override(self):
        prompt = compose_system_prompt(role="engineer", agent_override="You are a wizard.")
        assert "wizard" in prompt
        assert "software engineer" not in prompt.lower()

    def test_compose_with_all_parts(self):
        prompt = compose_system_prompt(
            role="researcher",
            company_context="We build AI tools.",
            skill_instructions=["Use markdown.", "Be concise."],
            task_context={"title": "Investigate X", "priority": "high"},
        )
        assert "Company Context" in prompt
        assert "We build AI tools." in prompt
        assert "Skill Instructions" in prompt
        assert "Use markdown." in prompt
        assert "Current Task" in prompt
        assert "Investigate X" in prompt

    def test_compose_skips_empty_parts(self):
        prompt = compose_system_prompt(
            role="custom",
            company_context="   ",
            skill_instructions=[],
        )
        # custom role has empty template; empty context and skills should not add sections
        assert "Company Context" not in prompt
        assert "Skill Instructions" not in prompt
