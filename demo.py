#!/usr/bin/env python3
"""
AgentOS POC — Demo

Runs a simulated enterprise workflow through three AI agents:
  1. Planner    — breaks the feature request into tasks
  2. Engineer   — implements the solution
  3. Reviewer   — reviews and approves/flags the work

Usage:
    export ANTHROPIC_API_KEY=your-key
    python demo.py
    python demo.py --request "Add user authentication with JWT tokens"
"""
import argparse
import sys
from models import Task, Workflow, AgentRole
from store import Store
from agents import AgentRuntime
from orchestrator import Orchestrator

DEFAULT_REQUEST = (
    "Build a REST API endpoint that accepts a list of product IDs and returns "
    "their names, prices, and inventory status from our database. "
    "It should be fast, handle missing products gracefully, and be easy to test."
)


def build_feature_workflow(request: str) -> Workflow:
    """Constructs the 3-agent feature development workflow."""

    plan_task = Task(
        title="Plan the implementation",
        description="Break down the feature request into engineering tasks",
        role=AgentRole.PLANNER,
        input=f"Feature request:\n{request}",
        depends_on=[],
    )

    eng_task = Task(
        title="Implement the solution",
        description="Write the code for the planned tasks",
        role=AgentRole.ENGINEER,
        input=(
            f"Implement the following feature request:\n{request}\n\n"
            "Follow the plan provided in the context and write clean, working code."
        ),
        depends_on=[plan_task.id],
    )

    review_task = Task(
        title="Review the implementation",
        description="Review the engineering output",
        role=AgentRole.REVIEWER,
        input=(
            f"Review the implementation for this feature request:\n{request}\n\n"
            "Evaluate the engineering work from the context and provide your verdict."
        ),
        depends_on=[eng_task.id],
    )

    return Workflow(
        title="Feature Development Workflow",
        description=f'Request: "{request[:80]}{"..." if len(request) > 80 else ""}"',
        tasks=[plan_task, eng_task, review_task],
    )


def main():
    parser = argparse.ArgumentParser(description="AgentOS POC Demo")
    parser.add_argument(
        "--request",
        default=DEFAULT_REQUEST,
        help="Feature request to process through the agent pipeline",
    )
    parser.add_argument(
        "--model",
        default="claude-haiku-4-5-20251001",
        help="Claude model to use (default: claude-haiku-4-5-20251001 for speed)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress streaming output, only show final summary",
    )
    parser.add_argument(
        "--react",
        action="store_true",
        default=True,
        help="Use ReAct loop with reviewer->engineer feedback cycles (default: True)",
    )
    args = parser.parse_args()

    store = Store()
    runtime = AgentRuntime(model=args.model)
    orchestrator = Orchestrator(store, runtime, verbose=not args.quiet)

    workflow = build_feature_workflow(args.request)
    if args.react:
        result = orchestrator.run_workflow_react(workflow)
    else:
        result = orchestrator.run_workflow(workflow)

    if args.quiet:
        print(f"\nWorkflow: {result.title}")
        print(f"Status:   {result.status.value}")
        for task in result.tasks:
            print(f"\n[{task.title}] — {task.status.value}")
            if task.output:
                print(task.output[:500] + ("..." if len(task.output) > 500 else ""))

    return 0 if result.status.value == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
