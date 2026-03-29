"""
AI agent definitions and execution runtime for AgentOS POC.
Each agent is powered by Claude and has a specific role.
"""
from __future__ import annotations
import anthropic
from models import AgentDef, AgentRole, Task, TaskStatus
import time
from typing import Optional

# Agent definitions — each has a specialized system prompt
AGENTS: dict[AgentRole, AgentDef] = {
    AgentRole.PLANNER: AgentDef(
        role=AgentRole.PLANNER,
        name="Planner",
        system_prompt=(
            "You are a planning agent in an enterprise agentic OS. "
            "Your job is to receive a feature request or business goal and break it down "
            "into clear, actionable engineering tasks. "
            "Output a numbered list of concrete tasks with brief descriptions. "
            "Be concise and practical. Focus on what an engineer needs to actually do."
        ),
    ),
    AgentRole.ENGINEER: AgentDef(
        role=AgentRole.ENGINEER,
        name="Engineer",
        system_prompt=(
            "You are a software engineering agent in an enterprise agentic OS. "
            "You receive a task description and produce a clean implementation. "
            "Write actual code with brief explanations. "
            "Be concise, idiomatic, and production-quality. "
            "Include only what's needed — no boilerplate or over-engineering."
        ),
    ),
    AgentRole.REVIEWER: AgentDef(
        role=AgentRole.REVIEWER,
        name="Reviewer",
        system_prompt=(
            "You are a senior code reviewer agent in an enterprise agentic OS. "
            "You receive engineering work output and provide a structured review. "
            "Format: APPROVED or NEEDS_CHANGES, then 2-4 bullet points of feedback. "
            "Be direct and specific. Focus on correctness, clarity, and maintainability."
        ),
    ),
}


class AgentRuntime:
    """Executes tasks using Claude-powered agents."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001", memory=None):
        self.client = anthropic.Anthropic()
        self.model = model
        self.memory = memory  # Optional[VectorMemory]

    def _build_user_message(self, task: Task, context: str) -> str:
        parts = []
        # Semantic memory: retrieve relevant past context from vector store
        if self.memory:
            semantic = self.memory.retrieve(task.input, role=task.role.value)
            if semantic:
                parts.append(f"Relevant past context (from memory):\n{semantic}")
        # Direct dependency context from this workflow run
        if context:
            parts.append(f"Context from previous steps:\n{context}")
        parts.append(f"Your task:\n{task.input}")
        return "\n\n---\n\n".join(parts)

    def run_task(self, task: Task, context: str = "") -> str:
        """Run a task using the appropriate agent. Returns the agent's output."""
        agent = AGENTS[task.role]
        user_message = self._build_user_message(task, context)
        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=agent.system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        output = message.content[0].text
        # Store completed task in vector memory for future retrieval
        if self.memory:
            self.memory.store(task.id, task.role.value, task.title, task.input, output)
        return output

    def run_task_react(self, task: Task, context: str = "", max_turns: int = 3) -> str:
        """Run a task with a ReAct multi-turn self-evaluation loop.

        Steps per turn:
          1. Run the task (or apply the previous incomplete result).
          2. Ask the agent to self-evaluate: COMPLETE or INCOMPLETE: <reason>.
          3. If INCOMPLETE and turns remain, ask the agent to complete the missing parts.
        Returns the final output and stores it in vector memory if available.
        """
        agent = AGENTS[task.role]
        user_message = self._build_user_message(task, context)

        messages: list[dict] = [{"role": "user", "content": user_message}]

        output = ""
        for turn in range(max_turns):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=agent.system_prompt,
                messages=messages,
            )
            output = response.content[0].text
            messages.append({"role": "assistant", "content": output})

            # Self-evaluation step
            eval_prompt = (
                "Is the above output complete and correct for the task? "
                "Reply with exactly COMPLETE or INCOMPLETE: <reason>."
            )
            messages.append({"role": "user", "content": eval_prompt})

            eval_response = self.client.messages.create(
                model=self.model,
                max_tokens=256,
                system=agent.system_prompt,
                messages=messages,
            )
            eval_text = eval_response.content[0].text.strip()
            messages.append({"role": "assistant", "content": eval_text})

            if eval_text.upper().startswith("COMPLETE"):
                # Done — no more turns needed
                break

            # INCOMPLETE — ask to finish, but only if turns remain
            if turn < max_turns - 1:
                fix_prompt = "Please complete the missing parts and provide the full, corrected output."
                messages.append({"role": "user", "content": fix_prompt})
            # On final turn we just use what we have

        # Store completed task in vector memory for future retrieval
        if self.memory:
            self.memory.store(task.id, task.role.value, task.title, task.input, output)
        return output

    def run_task_streaming(self, task: Task, context: str = "", on_chunk=None) -> str:
        """Run a task with streaming output. Calls on_chunk(text) for each chunk."""
        agent = AGENTS[task.role]
        user_message = self._build_user_message(task, context)

        full_output = []
        with self.client.messages.stream(
            model=self.model,
            max_tokens=1024,
            system=agent.system_prompt,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for text in stream.text_stream:
                full_output.append(text)
                if on_chunk:
                    on_chunk(text)

        output = "".join(full_output)
        # Store completed task in vector memory for future retrieval
        if self.memory:
            self.memory.store(task.id, task.role.value, task.title, task.input, output)
        return output
