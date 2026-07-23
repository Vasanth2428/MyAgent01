
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
    domain: str = "unknown"
    status: TaskStatus = "pending"
    assigned_agent: Optional[str] = None
    attempt_count: int = 0
    validation_required: bool = False
    fingerprint: str = ""
    last_result_summary: str = ""
    acceptance_criteria: List[str] = Field(default_factory=list)
    verification_commands: List[str] = Field(default_factory=list)
    expected_artifacts: List[str] = Field(default_factory=list)
    owned_paths: List[str] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)
    max_attempts: int = 3
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    review_feedback: List[Dict[str, Any]] = Field(default_factory=list)


class PlanTaskInput(BaseModel):
    title: str
    description: str = ""
    validation_required: bool = False
    domain: str = "unknown"
    acceptance_criteria: List[str] = Field(default_factory=list)
    verification_commands: List[str] = Field(default_factory=list)

class ProjectContextUpdate(BaseModel):
    active_project: Optional[str] = Field(None, description="The name of the current active project, or None if global.")
class ParallelRoute(BaseModel):
    agent: str = Field(description="The worker to execute this task (e.g. 'frontend_worker' or 'backend_worker').")
    task_id: str = Field(description="The ID of the task to execute.")

class SupervisorRouting(BaseModel):
    next_agent: str = Field(description="The worker to execute the next action (or 'parallel' if dispatching multiple tasks).")
    current_task: Optional[Any] = Field(description="The instruction to pass if routing to a single agent.")
    current_task_id: Optional[str] = Field(None, description="The ID of the task being executed if routing to a single agent.")
    parallel_tasks: List[ParallelRoute] = Field(default_factory=list, description="List of tasks to execute concurrently if next_agent is 'parallel'.")


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
        structured_output=SupervisorRouting,
    )


def _get_session_id(state: dict) -> str:
    config = state.get("configurable") or {}
    return config.get("thread_id", "default")


def normalize_task_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def task_fingerprint(title: str, description: str = "", *args) -> str:
    payload = normalize_task_text(f"{title} {description} {' '.join(str(a) for a in args if a)}".strip())
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


def build_task_instruction(task: PlanTask, original_instruction: str) -> str:
    """Combines LLM instruction with hard verification contracts for the worker."""
    instruction = f"{original_instruction}\n\n[TASK CONTRACT: {task.id}]\n"
    if task.acceptance_criteria:
        instruction += "Acceptance Criteria:\n- " + "\n- ".join(task.acceptance_criteria) + "\n"
    if task.verification_commands:
        instruction += "Verification Commands:\n- " + "\n- ".join(task.verification_commands) + "\n"
    if task.expected_artifacts:
        instruction += "Expected Artifacts:\n- " + "\n- ".join(task.expected_artifacts) + "\n"
    return instruction


from datetime import datetime, timezone

def apply_post_worker_state_updates(state: dict, plan: List[PlanTask], messages: list) -> tuple[List[PlanTask], str, list, list]:
    """Deterministic state transitions based on worker completion flags."""
    worker_outputs = state.get("worker_outputs", {})
    worker_complete = state.get("worker_complete", {})
    current_task_id = state.get("current_task_id")
    last_validated_task_id = state.get("last_validated_task_id", "")
    task_history = state.get("task_history") or []
    task_events = state.get("task_events") or []

    if not current_task_id:
        return plan, last_validated_task_id, task_history, task_events

    selected_task = get_task_by_id(plan, current_task_id)
    if not selected_task:
        return plan, last_validated_task_id, task_history, task_events

    if selected_task.status == "needs_replan":
        return plan, last_validated_task_id, task_history, task_events

    worker_type = state.get("worker_type", "")
    is_complete = worker_complete.get(worker_type, False)
    
    if is_complete and worker_type in {"frontend_worker", "backend_worker", "code_critic_worker", "rag_worker", "web_worker", "utility_worker", "scraper_worker"}:
        if worker_type == "code_critic_worker":
            # Critic decides if it's validated
            critic_feedback = state.get("critic_feedback", {})
            if critic_feedback.get("status") == "validated":
                selected_task.status = "validated"
                last_validated_task_id = current_task_id
                selected_task.evidence.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "type": "critic_validation",
                    "worker": "code_critic_worker",
                    "summary": critic_feedback.get("feedback", "")
                })
            elif critic_feedback.get("status") == "needs_changes":
                pass
        else:
            # Coding/utility workers finish their part
            if selected_task.validation_required and worker_type in {"frontend_worker", "backend_worker"}:
                selected_task.status = "in_progress" # Waiting for critic
            else:
                selected_task.status = "done"
            
            output_summary = str(worker_outputs.get(worker_type, ""))[:500]
            selected_task.last_result_summary = output_summary
            
            selected_task.evidence.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "worker_completion",
                "worker": worker_type,
                "summary": output_summary
            })
            
            task_history.append({
                "task_id": selected_task.id,
                "worker": worker_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": selected_task.status,
                "summary": output_summary
            })

    return plan, last_validated_task_id, task_history, task_events


async def supervisor_node(state: dict) -> dict:
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

    plan = normalize_plan(state.get("plan") or [])
    plan, last_validated_task_id, task_history, task_events = apply_post_worker_state_updates(state, plan, messages)

    is_goal_completed = state.get("project_context", {}).get("is_goal_completed", False)
    all_completed = all(t.status in {"done", "validated"} for t in plan) if plan else False

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

    import copy
    for msg in messages_to_route:
        msg_copy = copy.copy(msg)
        content_str = str(msg_copy.content)
        if len(content_str) > 5000:
            msg_copy.content = content_str[:2500] + "\n...[TRUNCATED FOR SUPERVISOR CONTEXT LIMITS]...\n" + content_str[-2500:]
            
        if isinstance(msg_copy, AIMessage) and msg_copy.name and msg_copy.name != "supervisor":
            routing_prompt.append(HumanMessage(content=f"[{msg_copy.name.upper()}]:\n{msg_copy.content}"))
        else:
            routing_prompt.append(msg_copy)

    if messages_to_route and not isinstance(routing_prompt[-1], HumanMessage):
        routing_prompt.append(HumanMessage(content="Please review the recent outputs and determine the next step."))

    new_steps = max(0, steps - 1)
    next_agent = "synthesizer"
    current_task = ""
    parallel_tasks: List[str] = []
    legacy_plan_output: Optional[List[str]] = None
    current_task_id = state.get("current_task_id")
    
    try:
        review_status = (state.get("critic_feedback") or {}).get("status")
        review_target = (state.get("critic_feedback") or {}).get("target_worker")
        
        if state.get("coding_worker_resume_tool_result"):
            next_agent = state.get("worker_type") or "frontend_worker"
            return {
                "next_agent": next_agent,
                "current_task": state.get("current_task", ""),
                "current_task_id": current_task_id,
            }

        if is_goal_completed:
            next_agent = "synthesizer"
        elif not plan and next_agent != "architect_worker":
            next_agent = "architect_worker"
            current_task_id = None
            current_task = "Create the initial architecture blueprint and task plan."
        elif all_completed and not is_goal_completed:
            next_agent = "architect_worker"
            current_task_id = None
            current_task = "Iteratively plan the next tasks for the user's overarching goal."
        elif any(task.status == "needs_replan" for task in plan):
            next_agent = "architect_worker"
            current_task_id = None
            current_task = "Replan tasks that exhausted their retry budget."
        elif review_status == "needs_changes" and review_target in {"frontend_worker", "backend_worker"}:
            selected_task = get_task_by_id(plan, state.get("current_task_id"))
            next_agent = review_target
            if selected_task:
                if selected_task.attempt_count >= selected_task.max_attempts:
                    logger.warning(f"Task {selected_task.id} failed repeatedly (attempts: {selected_task.attempt_count}). Escalating.")
                    selected_task.status = "needs_replan"
                    next_agent = "architect_worker"
                    current_task_id = None
                    current_task = "Replan tasks that exhausted their retry budget."
                else:
                    current_task_id = selected_task.id
                    selected_task.status = "in_progress"
                    selected_task.assigned_agent = next_agent
                    selected_task.attempt_count += 1
                    task_events.append({"event": "task_retry_started", "task": selected_task.id})
                    current_task = build_task_instruction(selected_task, "")
            return {
                "next_agent": next_agent,
                "current_task": current_task,
                "current_task_id": current_task_id,
                "plan": serialize_plan(plan),
                "task_events": task_events,
            }
        elif all_tasks_complete(plan):
            next_agent = "synthesizer"
        else:
            model = get_routing_model()
            for attempt in range(3):
                try:
                    response = await model.ainvoke(routing_prompt)
                    break
                except Exception as e:
                    if attempt == 2:
                        raise e
                    logger.warning(f"Supervisor LLM parsing failed (attempt {attempt+1}): {e}")
                    routing_prompt.append(HumanMessage(content=f"Failed to parse structured output. Error: {e}\nPlease correct your JSON and try again."))

            next_agent = response.next_agent
            parallel_tasks = getattr(response, "parallel_tasks", []) or []
            
            # Handle parallel routing branch
            if next_agent == "parallel":
                processed_parallel_tasks = []
                for p_route in parallel_tasks:
                    task = get_task_by_id(plan, p_route.task_id)
                    if task and task.status in {"pending", "in_progress"}:
                        task.status = "in_progress"
                        task.assigned_agent = p_route.agent
                        task.attempt_count += 1
                        task_events.append({"event": "task_started", "task": task.id})
                        processed_parallel_tasks.append({"agent": p_route.agent, "task_id": task.id})
                
                if processed_parallel_tasks:
                    parallel_tasks = processed_parallel_tasks
                    selected_task = None
                    current_task_id = None
                    current_task = "Executing tasks in parallel."
                else:
                    next_agent = "synthesizer"
            
            if next_agent != "parallel":
                selected_task = get_task_by_id(plan, response.current_task_id)
    
                if selected_task is None and next_agent != "synthesizer":
                    selected_task = get_next_pending_task(plan)

            if selected_task and selected_task.domain == "integration" and next_agent in {"frontend_worker", "backend_worker"}:
                next_agent = "backend_worker"

            if selected_task and selected_task.status in {"done", "validated", "blocked", "cancelled"}:
                logger.warning(
                    "Supervisor selected a completed or blocked task (%s). Overriding to next pending task.",
                    selected_task.id
                )
                selected_task = get_next_pending_task([t for t in plan if t.id != selected_task.id])

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

            if messages and isinstance(messages[-1], AIMessage):
                last_agent = messages[-1].name
                if last_agent == next_agent and next_agent not in ["frontend_worker", "backend_worker", "synthesizer"]:
                    logger.warning(f"Supervisor loop detected: {next_agent} called twice.")
                    selected_task = get_next_pending_task(plan)
                    if selected_task:
                        next_agent = "frontend_worker" if selected_task.domain == "frontend" else "backend_worker"
                    else:
                        next_agent = "synthesizer"

            if next_agent == "synthesizer" and not all_tasks_complete(plan):
                logger.warning("Supervisor attempted to exit to synthesizer with pending tasks. Overriding.")
                selected_task = get_next_pending_task(plan)
                if selected_task:
                    next_agent = "frontend_worker" if selected_task.domain == "frontend" else "backend_worker"

            if next_agent != "synthesizer" and selected_task is None:
                selected_task = get_next_pending_task(plan)
                if selected_task is None:
                    next_agent = "synthesizer"
                elif next_agent not in ["frontend_worker", "backend_worker"]:
                    next_agent = "frontend_worker" if selected_task.domain == "frontend" else "backend_worker"

            if selected_task and next_agent != "synthesizer":
                current_task_id = selected_task.id
                selected_task.status = "in_progress"
                selected_task.assigned_agent = next_agent
                selected_task.attempt_count += 1
                task_events.append({"event": "task_started", "task": selected_task.id})
                current_task = (
                    response.current_task
                    if legacy_plan_output is not None and response.current_task
                    else build_task_instruction(selected_task, response.current_task or "")
                )
            else:
                current_task_id = None
                current_task = response.current_task or ""

    except Exception as e:
        logger.error(f"Supervisor routing error: {e}")
        next_agent = "synthesizer"

    valid_agents = [
        "rag_worker", "web_worker", "utility_worker", "scraper_worker",
        "critic_worker", "report_worker", "frontend_worker", "backend_worker", "code_critic_worker",
        "architect_worker", "synthesizer", "parallel", "FINISH",
    ]
    if next_agent not in valid_agents or next_agent == "FINISH":
        next_agent = "synthesizer"

    state_update = {
        "plan": serialize_plan(plan),
        "next_agent": next_agent,
        "current_task": current_task,
        "current_task_id": current_task_id if next_agent != "synthesizer" else None,
        "last_validated_task_id": last_validated_task_id,
        "parallel_tasks": parallel_tasks if next_agent == "parallel" else [],
        "steps_remaining": new_steps,
        "retry_counter": retry_counter,
        "task_history": task_history,
        "task_events": task_events,
    }

    print(
        f"\n[SUPERVISOR] Next Node: '{next_agent}' | Task ID: '{state_update['current_task_id']}' "
        f"| Task: '{current_task}' | Swarm Tasks: {len(state_update['parallel_tasks'])} | Steps Left: {new_steps}"
    )
    return state_update
