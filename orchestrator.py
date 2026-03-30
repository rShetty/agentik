"""
Workflow orchestrator for AgentOS POC.
Runs workflow tasks in dependency order, passing context between agents.
"""
from __future__ import annotations
import time
from models import Task, Workflow, TaskStatus
from agents import AgentRuntime


class Orchestrator:
    def __init__(self, store, runtime: AgentRuntime, verbose: bool = True):
        self.store = store
        self.runtime = runtime
        self.verbose = verbose

    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    def _get_ready_tasks(self, workflow: Workflow) -> list[Task]:
        """Return tasks whose dependencies are all done."""
        done_ids = {t.id for t in workflow.tasks if t.status == TaskStatus.DONE}
        ready = []
        for task in workflow.tasks:
            if task.status != TaskStatus.PENDING:
                continue
            if all(dep in done_ids for dep in task.depends_on):
                ready.append(task)
        return ready

    def _build_context(self, task: Task, workflow: Workflow) -> str:
        """Build context string from completed dependency outputs."""
        if not task.depends_on:
            return ""
        parts = []
        for dep_id in task.depends_on:
            dep = self.store.get_task(dep_id)
            if dep and dep.output:
                parts.append(f"[{dep.title}]\n{dep.output}")
        return "\n\n".join(parts)

    def run_workflow(self, workflow: Workflow) -> Workflow:
        """Execute a workflow to completion, respecting task dependencies."""
        self.store.add_workflow(workflow)
        workflow.status = TaskStatus.IN_PROGRESS

        self._log(f"\n{'='*60}")
        self._log(f"  WORKFLOW: {workflow.title}")
        self._log(f"{'='*60}")
        self._log(f"  {workflow.description}\n")

        max_rounds = len(workflow.tasks) + 1
        for _ in range(max_rounds):
            ready = self._get_ready_tasks(workflow)
            if not ready:
                break

            for task in ready:
                self._run_single_task(task, workflow)

        all_done = all(t.status == TaskStatus.DONE for t in workflow.tasks)
        workflow.status = TaskStatus.DONE if all_done else TaskStatus.FAILED

        self._log(f"\n{'='*60}")
        status_label = "COMPLETED" if all_done else "FAILED"
        self._log(f"  WORKFLOW {status_label}: {workflow.title}")
        self._log(f"{'='*60}\n")

        return workflow

    def _run_single_task(self, task: Task, workflow: Workflow, reviewer_feedback: str = ""):
        """Execute one task, streaming output if verbose.

        Args:
            reviewer_feedback: Optional feedback from a prior reviewer pass to
                               append to the task context (used in ReAct loop).
        """
        from agents import AGENTS
        agent_def = AGENTS[task.role]

        self._log(f"\n[{agent_def.name.upper()}] {task.title}")
        self._log("-" * 50)

        task.status = TaskStatus.IN_PROGRESS
        self.store.update_task(task.id, status=TaskStatus.IN_PROGRESS)

        context = self._build_context(task, workflow)
        if reviewer_feedback:
            context = (context + "\n\n" if context else "") + (
                f"Reviewer feedback requiring changes:\n{reviewer_feedback}"
            )

        try:
            if self.verbose:
                output = self.runtime.run_task_streaming(
                    task, context=context, on_chunk=lambda c: print(c, end="", flush=True)
                )
                print()  # newline after streaming
            else:
                output = self.runtime.run_task(task, context=context)

            task.output = output
            task.status = TaskStatus.DONE
            task.completed_at = time.time()
            self.store.update_task(
                task.id, output=output, status=TaskStatus.DONE, completed_at=task.completed_at
            )
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.output = f"ERROR: {e}"
            self.store.update_task(task.id, status=TaskStatus.FAILED, output=task.output)
            self._log(f"\n[ERROR] {e}")

    def run_workflow_react(self, workflow: Workflow) -> Workflow:
        """Execute a workflow with the generic ReAct feedback loop.

        Role-agnostic: runs tasks in dependency order. Any task whose output
        starts with NEEDS_CHANGES triggers a re-run of its direct dependencies,
        up to workflow.max_revisions times. Works for any workflow shape, not
        just the built-in Planner/Engineer/Reviewer roles.
        """
        self.store.add_workflow(workflow)
        workflow.status = TaskStatus.IN_PROGRESS

        self._log(f"\n{'='*60}")
        self._log(f"  WORKFLOW (ReAct): {workflow.title}")
        self._log(f"{'='*60}")
        self._log(f"  {workflow.description}\n")

        task_by_id = {t.id: t for t in workflow.tasks}
        # Cap total iterations to prevent runaway loops
        max_rounds = len(workflow.tasks) * (workflow.max_revisions + 1) + 1

        for _ in range(max_rounds):
            ready = self._get_ready_tasks_react(workflow)
            if not ready:
                break
            for task in ready:
                self._run_single_task_react(task, workflow, task_by_id)
                # After each task, check if it's requesting changes from its deps
                if task.output and task.output.strip().startswith("NEEDS_CHANGES"):
                    self._handle_needs_changes(task, workflow, task_by_id)

        all_done = all(
            t.status in (TaskStatus.DONE, TaskStatus.NEEDS_REVISION)
            for t in workflow.tasks
        )
        workflow.status = TaskStatus.DONE if all_done else TaskStatus.FAILED

        self._log(f"\n{'='*60}")
        status_label = "COMPLETED" if workflow.status == TaskStatus.DONE else "FAILED"
        self._log(f"  WORKFLOW {status_label}: {workflow.title}")
        self._log(f"{'='*60}\n")

        return workflow

    def _get_ready_tasks_react(self, workflow: Workflow) -> list[Task]:
        """Return PENDING or NEEDS_REVISION tasks whose dependencies are all DONE."""
        done_ids = {t.id for t in workflow.tasks if t.status == TaskStatus.DONE}
        return [
            t for t in workflow.tasks
            if t.status in (TaskStatus.PENDING, TaskStatus.NEEDS_REVISION)
            and all(dep in done_ids for dep in t.depends_on)
        ]

    def _handle_needs_changes(
        self, task: Task, workflow: Workflow, task_by_id: dict
    ) -> None:
        """Reset direct dependencies of a NEEDS_CHANGES task for revision.

        Increments the revision counter on the requesting task. If max revisions
        are reached, annotates the output instead of resetting.
        """
        if task.revision_count >= workflow.max_revisions:
            self._log(
                f"\n[REACT] Max revisions ({workflow.max_revisions}) reached for "
                f"'{task.title}'. Keeping output as-is."
            )
            task.output += (
                f"\n\n[NOTE: Max revisions ({workflow.max_revisions}) reached. "
                "Workflow completed as-is.]"
            )
            self.store.update_task(task.id, output=task.output)
            return

        task.revision_count += 1
        dep_titles = [
            task_by_id[d].title for d in task.depends_on if d in task_by_id
        ]
        self._log(
            f"\n[REACT] '{task.title}' requested changes "
            f"(revision {task.revision_count}/{workflow.max_revisions}). "
            f"Re-running: {dep_titles}"
        )

        # Reset direct dependencies so they re-run before this task
        for dep_id in task.depends_on:
            dep = task_by_id.get(dep_id)
            if dep:
                dep.status = TaskStatus.NEEDS_REVISION
                self.store.update_task(dep_id, status=TaskStatus.NEEDS_REVISION)

        # Reset this task to PENDING so it re-runs after deps complete
        task.status = TaskStatus.PENDING
        self.store.update_task(task.id, status=TaskStatus.PENDING)

    def _run_single_task_react(
        self, task: Task, workflow: Workflow, task_by_id: dict | None = None
    ) -> None:
        """Execute one task using the ReAct multi-turn loop.

        Automatically injects any NEEDS_CHANGES feedback from tasks that
        depend on this one (found by scanning task_by_id).
        """
        from agents import AGENTS
        agent_def = AGENTS[task.role]

        self._log(f"\n[{agent_def.name.upper()} / ReAct] {task.title}")
        self._log("-" * 50)

        task.status = TaskStatus.IN_PROGRESS
        self.store.update_task(task.id, status=TaskStatus.IN_PROGRESS)

        context = self._build_context(task, workflow)

        # Inject reviewer feedback: any downstream task that depends on this
        # one and currently holds a NEEDS_CHANGES output
        if task_by_id:
            feedback_parts = [
                other.output
                for other in task_by_id.values()
                if task.id in other.depends_on
                and other.output
                and other.output.strip().startswith("NEEDS_CHANGES")
            ]
            if feedback_parts:
                feedback_str = "\n\n".join(feedback_parts)
                context = (context + "\n\n" if context else "") + (
                    f"Feedback requesting changes:\n{feedback_str}"
                )

        try:
            from models import AgentRole
            # The reviewer must produce output starting with APPROVED or NEEDS_CHANGES.
            # run_task_react's self-evaluation loop can reformat the output and corrupt
            # that required prefix, causing NEEDS_CHANGES detection to silently fail.
            # Use a single-turn run_task for the reviewer to preserve the format.
            if task.role == AgentRole.REVIEWER:
                output = self.runtime.run_task(task, context=context)
            else:
                output = self.runtime.run_task_react(task, context=context)

            task.output = output
            task.status = TaskStatus.DONE
            task.completed_at = time.time()
            self.store.update_task(
                task.id, output=output, status=TaskStatus.DONE, completed_at=task.completed_at
            )
            if self.verbose:
                print(output)
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.output = f"ERROR: {e}"
            self.store.update_task(task.id, status=TaskStatus.FAILED, output=task.output)
            self._log(f"\n[ERROR] {e}")
