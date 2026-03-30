"""System prompt management.

Composition order (each part is appended only if non-empty):
  1. role_template   — default behaviour for the agent's role
  2. company_context — shared context injected from company config
  3. skill_instructions — concatenated instructions from assigned skills
  4. task_context    — the specific task payload
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Role-based default templates
# ---------------------------------------------------------------------------

_ROLE_TEMPLATES: dict[str, str] = {
    "ceo": (
        "You are the CEO agent. Your responsibility is to set company strategy, "
        "allocate work to your team of agents, and ensure business goals are met. "
        "Coordinate across departments, prioritize critical issues, and escalate "
        "appropriately. Think long-term and make decisions that serve the company mission."
    ),
    "cto": (
        "You are the CTO agent. Your responsibility is to lead technical strategy, "
        "review architectural decisions, and guide the engineering team. "
        "You coordinate engineering agents, review their work, and ensure the "
        "technical roadmap aligns with company goals."
    ),
    "engineer": (
        "You are a software engineer agent. Your responsibility is to implement "
        "features, fix bugs, write tests, and maintain code quality. "
        "Follow existing conventions, write clear commit messages, and "
        "communicate blockers promptly."
    ),
    "researcher": (
        "You are a research agent. Your responsibility is to investigate topics, "
        "gather information, synthesise findings, and produce clear reports. "
        "Cite sources, highlight uncertainties, and present conclusions concisely."
    ),
    "reviewer": (
        "You are a code review agent. Your responsibility is to review pull requests "
        "and code changes for correctness, security, and maintainability. "
        "Provide constructive feedback with specific suggestions."
    ),
    "custom": "",
}


def get_role_template(role: str) -> str:
    """Return the default system prompt template for *role*.

    Falls back to an empty string for unknown roles.
    """
    return _ROLE_TEMPLATES.get(role, "")


# ---------------------------------------------------------------------------
# Prompt composer
# ---------------------------------------------------------------------------

def compose_system_prompt(
    role: str,
    agent_override: str | None = None,
    company_context: str | None = None,
    skill_instructions: list[str] | None = None,
    task_context: dict[str, Any] | None = None,
) -> str:
    """Build the full system prompt for an agent run.

    Parts are included in order and separated by blank lines.
    ``agent_override`` replaces the role template entirely when provided.

    Args:
        role: Agent role (e.g. ``"engineer"``).
        agent_override: Per-agent custom system prompt; if set, replaces the
            role template.
        company_context: Company-level context paragraph injected for all agents.
        skill_instructions: List of instruction strings from each installed skill.
        task_context: The task payload dict; rendered as a JSON-like summary.

    Returns:
        A fully composed system prompt string.
    """
    parts: list[str] = []

    # 1. Role template or per-agent override
    base = agent_override if agent_override else get_role_template(role)
    if base:
        parts.append(base.strip())

    # 2. Company context
    if company_context and company_context.strip():
        parts.append(f"## Company Context\n{company_context.strip()}")

    # 3. Skill instructions
    if skill_instructions:
        active = [s.strip() for s in skill_instructions if s and s.strip()]
        if active:
            parts.append("## Skill Instructions\n" + "\n\n".join(active))

    # 4. Task context
    if task_context:
        lines = [f"- **{k}**: {v}" for k, v in task_context.items() if v is not None]
        if lines:
            parts.append("## Current Task\n" + "\n".join(lines))

    return "\n\n".join(parts)
