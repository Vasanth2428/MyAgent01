
# Supervisor node for routing queries using Native Tool Calling

import os
import re
import json
import uuid
import hashlib
import logging
import threading
from typing import Dict, List, Optional, Literal, Any

from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage

from src.core.config import SUPERVISOR_MODEL_PRIMARY, SUPERVISOR_MODEL_FALLBACK
from src.core.model_provider import build_model_with_fallback, resolve_provider

logger = logging.getLogger("MultiAgent.Supervisor")
MAX_PLAN_STEPS = 15
MAX_GLOBAL_MESSAGES = 30

APPROVAL_REGISTRY: Dict[str, set] = {}
_approval_lock = threading.Lock()

TaskStatus = Literal["pending", "in_progress", "validated", "done", "blocked", "failed"]


def approve_file(session_id: str, filepath: str) -> None:
    with _approval_lock:
        APPROVAL_REGISTRY.setdefault(session_id, set()).add(os.path.realpath(filepath))


def is_file_approved(session_id: str, filepath: str) -> bool:
    with _approval_lock:
        return os.path.realpath(filepath) in APPROVAL_REGISTRY.get(session_id, set())


def clear_session_approvals(session_id: str) -> None:
    with _approval_lock:
        APPROVAL_REGISTRY.pop(session_id, None)


SUPERVISOR_PROMPT = """You are a central planner and supervisor for a multi-agent cooperative system.
Your job is to coordinate a team of specialized workers to solve a user's query.

Available Workers:
- rag_worker: Retrieve information from private documents only.
- web_worker: Search the web for real-time/current information.
- utility_worker: Perform calculations, math, date/time lookups.
- scraper_worker: Fetch and extract text content from specific URLs.
- critic_worker: Analyze accumulated findings, cross-reference sources.
- report_worker: Generate comprehensive markdown reports.
- frontend_worker: Code generation, file editing, and frontend design tasks. Flexible and highly opinionated about UI aesthetics (Tailwind, animations). Use for all frontend programming work.
- backend_worker: Code generation, file editing, and backend architecture tasks. Flexible and highly opinionated about architecture (Python, FastAPI, scaling). Use for all backend programming work.
- code_critic_worker: Validate findings, technical correctness, and design quality from frontend_worker and backend_worker.

Your duties:
1. Review the structured task state. Do NOT recreate already completed tasks.
2. Select the safest next move based on current task statuses.
3. Prefer continuing an existing in-progress task over inventing a duplicate.
4. Only choose tasks that are still pending or in_progress.
5. If all tasks are complete, route to 'synthesizer'.

Rules:
- Never select a task whose status is done or validated.
- If code_critic_worker validated a task, move on to the next pending task.
- Only add new tasks if the existing plan is insufficient.
- Keep plans concise and actionable.
"""


class PlanTask(BaseModel):
    id: str
    title: str
    description: str = ""
    status: TaskStatus = "pending"
    assigned_agent: Optional[str] = None
    attempt_count: int = 0
    validation_required: bool = False
    fingerprint: str = ""
    last_result_summary: str = ""


class PlanTaskInput(BaseModel):
    title: str
    description: str = ""
    validation_required: bool = False


class SupervisorDecision(BaseModel):
    next_agent: str = Field(description="The next agent to route to")
    selected_task_id: Optional[str] = Field(
        default=None,
        description="ID of an existing task to continue or execute next"
    )
    current_task: str = Field(
        description="Specific instruction for the next worker. Prefer the selected task title/description.",
        default=""
    )
    new_tasks: List[PlanTaskInput] = Field(
        default_factory=list,
        description="Only append genuinely new tasks that do not already exist in the plan"
    )
    parallel_tasks: List[str] = Field(
        default_factory=list,
        description="If routing to frontend_worker or backend_worker, you may provide multiple independent tasks here to be executed concurrently by separate workers."
    )
    active_project: Optional[str] = Field(
        description="Sanitized folder name for the project if this task involves creating an application.",
        default=""
    )


def get_routing_model():
    provider = resolve_provider("supervisor", "primary")
    if provider == "cerebras":
        keys = ("CEREBRAS_API_KEY",)
    elif provider == "mistral":
        keys = ("MISTRAL_API_KEY",)
    else:
        keys = ("AGENT_API_KEY",)
    return build_model_with_fallback(
        "supervisor",
        SUPERVISOR_MODEL_PRIMARY,
        SUPERVISOR_MODEL_FALLBACK,
        temperature=0,
        api_key_envs=keys,
        structured_output=SupervisorDecision,
    )


def _get_session_id(state: dict) -> str:
    config = state.get("configurable") or {}
    return config.get("thread_id", "default")


def normalize_task_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def task_fingerprint(title: str, description: str = "") -> str:
    payload = normalize_task_text(f"{title} {description}".strip())
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _coerce_task(item: Any) -> PlanTask:
    if isinstance(item, PlanTask):
        task = item
    elif isinstance(item, dict):
        task = PlanTask(**item)
    elif isinstance(item, str):
        task = PlanTask(
            id=f"task_{uuid.uuid4().hex[:8]}",
            title=item,
            fingerprint=task_fingerprint(item, "")
        )
    else:
        raise TypeError(f"Unsupported plan task type: {type(item)}")

    if not task.fingerprint:
        task.fingerprint = task_fingerprint(task.title, task.description)
    return task


def normalize_plan(plan: List[Any]) -> List[PlanTask]:
    normalized: List[PlanTask] = []
    seen_ids = set()
    seen_fingerprints = set()

    for item in plan or []:
        try:
            task = _coerce_task(item)
        except Exception as e:
            logger.warning(f"Skipping invalid plan task {item!r}: {e}")
            continue

        if task.id in seen_ids:
            continue

        if task.fingerprint in seen_fingerprints:
            continue

        seen_ids.add(task.id)
        seen_fingerprints.add(task.fingerprint)
        normalized.append(task)

    return normalized[:MAX_PLAN_STEPS]


def serialize_plan(plan: List[PlanTask]) -> List[dict]:
    return [task.model_dump() for task in plan]


def get_task_by_id(plan: List[PlanTask], task_id: Optional[str]) -> Optional[PlanTask]:
    if not task_id:
        return None
    for task in plan:
        if task.id == task_id:
            return task
    return None


def find_task_by_fingerprint(plan: List[PlanTask], fingerprint: str) -> Optional[PlanTask]:
    for task in plan:
        if task.fingerprint == fingerprint:
            return task
    return None


def get_next_pending_task(plan: List[PlanTask]) -> Optional[PlanTask]:
    for task in plan:
        if task.status in {"pending", "in_progress"}:
            return task
    return None


def all_tasks_complete(plan: List[PlanTask]) -> bool:
    if not plan:
        return False
    return all(task.status in {"done", "validated"} for task in plan)


def summarize_plan(plan: List[PlanTask]) -> str:
    if not plan:
        return "No plan exists yet."
    lines = []
    for task in plan:
        lines.append(
            f"- {task.id} | {task.status} | {task.title}"
            + (f" | assigned={task.assigned_agent}" if task.assigned_agent else "")
            + (f" | attempts={task.attempt_count}" if task.attempt_count else "")
        )
    return "\n".join(lines)


def extract_validation_status(messages: List[Any]) -> Optional[str]:
    if not messages:
        return None

    last = messages[-1]
    if not isinstance(last, AIMessage) or last.name != "code_critic_worker":
        return None

    content = (last.content or "").lower()
    if "verification failed repeatedly" in content:
        return "failed_repeatedly"
    if "validated" in content or "✓ validated" in content or "status: validated" in content:
        return "validated"
    if "needs changes" in content or "not validated" in content or "failed" in content:
        return "needs_changes"
    return None


def apply_post_worker_state_updates(state: dict, plan: List[PlanTask], messages: List[Any]) -> tuple[List[PlanTask], Optional[str]]:
    """
    Deterministic task state updates based on the most recent worker output.
    Returns (updated_plan, last_validated_task_id).
    """
    current_task_id = state.get("current_task_id")
    last_validated_task_id = state.get("last_validated_task_id")
    validation_status = extract_validation_status(messages)

    if not current_task_id:
        return plan, last_validated_task_id

    current_task = get_task_by_id(plan, current_task_id)
    if not current_task:
        return plan, last_validated_task_id

    if validation_status == "validated":
        current_task.status = "done"
        current_task.last_result_summary = "Validated by code_critic_worker"
        last_validated_task_id = current_task.id
        state["current_task_id"] = None
    elif validation_status == "failed_repeatedly":
        current_task.status = "blocked"
        current_task.last_result_summary = "Verification failed repeatedly"
        state["current_task_id"] = None
    elif validation_status == "needs_changes":
        current_task.status = "in_progress"
        current_task.last_result_summary = "Critic requested changes"

    return plan, last_validated_task_id


def build_task_instruction(task: Optional[PlanTask], fallback: str = "") -> str:
    if task:
        parts = [task.title.strip()]
        if task.description.strip():
            parts.append(task.description.strip())
        return " - ".join(parts)
    return fallback or ""


def supervisor_node(state: dict) -> dict:
    messages = state.get("messages", [])
    steps = state.get("steps_remaining", 30)
    retry_counter = int(state.get("retry_counter") or 0)
    active_documents = state.get("active_documents") or []
    cursor_position = state.get("cursor_position") or {}

    ide_context = (
        f"\n[IDE CONTEXT]\nActive Documents: {active_documents}\nCursor: {cursor_position}\n"
        if (active_documents or cursor_position)
        else ""
    )

    # Normalize legacy plans and apply deterministic post-worker updates first.
    plan = normalize_plan(state.get("plan") or [])
    plan, last_validated_task_id = apply_post_worker_state_updates(state, plan, messages)

    routing_prompt = [
        SystemMessage(content=SUPERVISOR_PROMPT + ide_context),
        SystemMessage(
            content=(
                f"Task Status Snapshot:\n{summarize_plan(plan)}\n\n"
                f"Steps Remaining: {steps}\n"
                f"Retry Counter: {retry_counter}\n"
                f"Current Task ID: {state.get('current_task_id')}\n"
                f"Last Validated Task ID: {last_validated_task_id}"
            )
        ),
    ]

    messages_to_route = messages
    if len(messages) > MAX_GLOBAL_MESSAGES:
        start_idx = len(messages) - MAX_GLOBAL_MESSAGES
        while start_idx > 0 and isinstance(messages[start_idx], ToolMessage):
            start_idx -= 1
        messages_to_route = messages[start_idx:]
        routing_prompt.append(
            SystemMessage(
                content=(
                    "[SYSTEM NOTE] Older global execution history has been truncated to preserve token limits. "
                    "Rely on the structured Task Status Snapshot above instead of reconstructing completed work from old messages."
                )
            )
        )

    for msg in messages_to_route:
        if isinstance(msg, AIMessage) and msg.name and msg.name != "supervisor":
            routing_prompt.append(HumanMessage(content=f"[{msg.name.upper()}]:\n{msg.content}"))
        else:
            routing_prompt.append(msg)

    if messages_to_route and not isinstance(routing_prompt[-1], HumanMessage):
        routing_prompt.append(HumanMessage(content="Please review the recent outputs and determine the next step."))

    new_steps = max(0, steps - 1)
    next_agent = "synthesizer"
    current_task = ""
    parallel_tasks: List[str] = []
    active_project_override = None
    current_task_id = state.get("current_task_id")

    try:
        # Fast path: if all tasks are complete after deterministic updates, stop routing workers.
        if all_tasks_complete(plan):
            next_agent = "synthesizer"
        else:
            model = get_routing_model()
            response = model.invoke(routing_prompt)

            next_agent = response.next_agent
            parallel_tasks = response.parallel_tasks or []
            active_project_override = getattr(response, "active_project", None) or None
            if active_project_override == "":
                active_project_override = None

            # Merge newly proposed tasks without duplicating existing ones.
            for new_task in response.new_tasks or []:
                fp = task_fingerprint(new_task.title, new_task.description)
                existing = find_task_by_fingerprint(plan, fp)
                if existing:
                    continue
                plan.append(
                    PlanTask(
                        id=f"task_{uuid.uuid4().hex[:8]}",
                        title=new_task.title.strip(),
                        description=new_task.description.strip(),
                        validation_required=new_task.validation_required,
                        fingerprint=fp,
                    )
                )

            selected_task = get_task_by_id(plan, response.selected_task_id)

            # Fallback if the model did not pick a task but there is work left.
            if selected_task is None and next_agent != "synthesizer":
                selected_task = get_next_pending_task(plan)

            # Hard guard: never allow routing back into a validated/done task.
            if selected_task and selected_task.status in {"done", "validated"}:
                logger.warning(
                    "Supervisor selected a completed task (%s). Overriding to next pending task.",
                    selected_task.id
                )
                selected_task = get_next_pending_task([t for t in plan if t.id != selected_task.id])

            # Hard guard: prevent validated coding loops.
            if (
                next_agent in {"frontend_worker", "backend_worker"}
                and selected_task
                and selected_task.id == last_validated_task_id
            ):
                logger.warning(
                    "Supervisor attempted to reroute a validated task (%s) back to frontend/backend worker. Overriding.",
                    selected_task.id
                )
                selected_task = get_next_pending_task([t for t in plan if t.id != selected_task.id])
                if not selected_task:
                    next_agent = "synthesizer"

            # Generic same-agent loop guard for non-coding workers.
            if messages and isinstance(messages[-1], AIMessage):
                last_agent = messages[-1].name
                if last_agent == next_agent and next_agent not in ["frontend_worker", "backend_worker", "synthesizer"]:
                    logger.warning(f"Supervisor loop detected: {next_agent} called twice. Forcing synthesizer.")
                    next_agent = "synthesizer"
                    selected_task = None

            # If we still have no selected task but pending work exists, grab the next pending task.
            if next_agent != "synthesizer" and selected_task is None:
                selected_task = get_next_pending_task(plan)
                if selected_task is None:
                    next_agent = "synthesizer"

            if selected_task and next_agent != "synthesizer":
                current_task_id = selected_task.id
                selected_task.status = "in_progress"
                selected_task.assigned_agent = next_agent
                selected_task.attempt_count += 1
                current_task = build_task_instruction(selected_task, response.current_task)
            else:
                current_task_id = None
                current_task = response.current_task or ""

    except Exception as e:
        logger.error(f"Supervisor routing error: {e}")
        next_agent = "synthesizer"

    valid_agents = [
        "rag_worker", "web_worker", "utility_worker", "scraper_worker",
        "critic_worker", "report_worker", "frontend_worker", "backend_worker", "code_critic_worker",
        "synthesizer", "FINISH",
    ]
    if next_agent not in valid_agents or next_agent == "FINISH":
        next_agent = "synthesizer"

    state_update = {
        "plan": serialize_plan(plan),
        "next_agent": next_agent,
        "current_task": current_task,
        "current_task_id": current_task_id if next_agent != "synthesizer" else None,
        "last_validated_task_id": last_validated_task_id,
        "parallel_tasks": parallel_tasks if next_agent in {"frontend_worker", "backend_worker"} else [],
        "active_project": active_project_override if active_project_override is not None else (state.get("active_project") or None),
        "steps_remaining": new_steps,
        "retry_counter": retry_counter,
    }

    print(
        f"\n[SUPERVISOR] Next Node: '{next_agent}' | Task ID: '{state_update['current_task_id']}' "
        f"| Task: '{current_task}' | Swarm Tasks: {len(state_update['parallel_tasks'])} | Steps Left: {new_steps}"
    )
    return state_update
