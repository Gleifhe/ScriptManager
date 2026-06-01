"""DAG workflow executor.

Runs nodes in topological waves, respecting parallel fan-out and join semantics.
Each node executes synchronously inside a thread-pool so the workflow run itself
can be handed off to a Celery worker without blocking the API server.
"""
from __future__ import annotations

import logging
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from scriptmgr.core.db import session_scope
from scriptmgr.core.models import Run, RunStatus, Workflow
from scriptmgr.workflows.dag import Dag

logger = logging.getLogger(__name__)


def execute_workflow(parent_run_id: int) -> None:
    """Orchestrate all nodes of a workflow run synchronously."""
    with session_scope() as db:
        parent = db.get(Run, parent_run_id)
        if not parent:
            raise ValueError(f"Run {parent_run_id} not found")
        workflow = db.get(Workflow, parent.workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {parent.workflow_id} not found")

        dag = Dag.from_dict(workflow.dag)
        parent.status = RunStatus.RUNNING
        parent.started_at = datetime.now(timezone.utc)
        parent.host = socket.gethostname()
        db.add(parent)

    had_failure = _run_dag(dag, parent_run_id)

    with session_scope() as db:
        parent = db.get(Run, parent_run_id)
        if parent:
            parent.status = RunStatus.FAILED if had_failure else RunStatus.SUCCESS
            parent.finished_at = datetime.now(timezone.utc)
            db.add(parent)


def _run_dag(dag: Dag, parent_run_id: int) -> bool:
    """
    Execute nodes wave by wave (BFS over satisfied predecessors).
    Returns True if any node failed.
    """
    from scriptmgr.executor.runner import execute_script

    node_map = {n.id: n for n in dag.nodes}
    completed: dict[str, str] = {}  # node_id -> "success" | "failure"
    had_failure = False

    ready: set[str] = {n.id for n in dag.roots()}

    while ready:
        with ThreadPoolExecutor(max_workers=min(len(ready), 8)) as pool:
            futures = {pool.submit(_run_node, node_map[nid], parent_run_id): nid for nid in ready}
            next_ready: set[str] = set()

            for fut in as_completed(futures):
                node_id, outcome = fut.result()
                completed[node_id] = outcome
                if outcome == "failure":
                    had_failure = True

                for successor in dag.successors(node_id, outcome):
                    if successor.id not in completed:
                        preds = dag.predecessors(successor.id)
                        if all(p in completed for p in preds):
                            next_ready.add(successor.id)

        ready = next_ready

    return had_failure


def _run_node(node, parent_run_id: int) -> tuple[str, str]:
    from scriptmgr.executor.runner import execute_script

    with session_scope() as db:
        run = Run(
            script_id=node.script_id,
            parent_run_id=parent_run_id,
            trigger_source="workflow",
            status=RunStatus.QUEUED,
        )
        db.add(run)
        db.flush()
        run_id = run.id

    try:
        exit_code = execute_script(run_id)
    except Exception as exc:
        logger.exception("Node %s (run %s) raised: %s", node.id, run_id, exc)
        exit_code = -1

    # Retry logic
    for attempt in range(node.retry):
        if exit_code == 0:
            break
        logger.info("Retrying node %s (attempt %d/%d)", node.id, attempt + 1, node.retry)
        with session_scope() as db:
            retry_run = Run(
                script_id=node.script_id,
                parent_run_id=parent_run_id,
                trigger_source="workflow-retry",
                status=RunStatus.QUEUED,
            )
            db.add(retry_run)
            db.flush()
            run_id = retry_run.id
        exit_code = execute_script(run_id)

    outcome = "success" if exit_code == 0 else "failure"
    return node.id, outcome
