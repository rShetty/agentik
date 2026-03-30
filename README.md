# agentik — Agentic OS POC

Where Agents go to work.

A minimal, working proof-of-concept for an **Agentic OS for enterprises** — a platform where AI agents manage and execute tasks and workflows on behalf of human teams.

## What it demonstrates

- **Multi-agent task execution** — specialized agents handle different task types (planning, engineering, review)
- **Workflow orchestration** — tasks chain together in DAG-based workflows
- **LLM-powered agents** — each agent uses Claude to reason and produce outputs
- **Enterprise-ready design** — role-based agents, audit trail, status tracking

## Architecture

```
poc/
  models.py       # Task, Agent, Workflow data models
  store.py        # In-memory task/workflow store
  agents.py       # Agent definitions + Claude-powered execution
  orchestrator.py # Workflow runner — dispatches tasks, tracks state
  demo.py         # CLI demo: runs an end-to-end enterprise workflow
```

## Quickstart

```bash
pip install anthropic
export ANTHROPIC_API_KEY=your-key
python demo.py
```

## Demo workflow

The demo runs a simplified "new feature request" enterprise workflow:

1. **Planner agent** — breaks down the feature request into engineering tasks
2. **Engineer agent** — implements the solution (code + explanation)
3. **Reviewer agent** — reviews the output and approves/flags issues

All agent outputs are displayed in real-time with status tracking.
