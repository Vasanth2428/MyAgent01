"""Project architect node for initial blueprints and bounded replanning."""

import logging
import uuid
import asyncio
from datetime import datetime, timezone
from typing import List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.core.config import SUPERVISOR_MODEL_FALLBACK, SUPERVISOR_MODEL_PRIMARY
from src.core.model_provider import build_model_with_fallback, resolve_provider
from src.graph.supervisor import PlanTask, PlanTaskInput, ProjectContextUpdate, task_fingerprint

logger = logging.getLogger("MultiAgent.ArchitectWorker")


class ArchitectureBlueprint(BaseModel):
    project_context: ProjectContextUpdate
    tasks: List[PlanTaskInput] = Field(default_factory=list)
    summary: str = ""
    is_goal_completed: bool = Field(default=False)


ARCHITECT_SYSTEM_PROMPT = (
    "You are the project Architect for a stateful coding harness.\n"
    "Create a durable blueprint; do not implement code. Define product context and a small, ordered task plan.\n\n"
    "CRITICAL ITERATIVE PLANNING INSTRUCTION:\n"
    "The user wants an iterative, step-by-step approach. DO NOT generate a massive up-front plan.\n"
    "Instead, generate ONLY 1 or 2 small tasks for the immediate next step (e.g. 'plan one file, write it, save it').\n"
    "Once those are completed, you will be called again to generate the next steps.\n"
    "If the user's overarching goal has been fully achieved by the completed tasks in the history, set `is_goal_completed` to true, return an empty task list, and output a summary stating that the goal is complete.\n\n"
    "ENVIRONMENT:\n"
    "The system runs on Windows PowerShell. Any verification_commands MUST be valid PowerShell commands (e.g. `Get-Content`, `Select-String`, `Test-Path`). Do NOT use linux commands like `cat`, `grep`, `ls`.\n\n"
    "Every coding task must include a domain, measurable acceptance criteria, expected artifacts, and applicable verification commands. Add explicit integration tasks for API contracts or end-to-end behavior.\n\n"
    "CRITICAL REPLANNING INSTRUCTION:\n"
    "If this is a replan (i.e. there are tasks with status 'needs_replan'), you MUST analyze the 'Task history' and 'Task events' provided in the prompt.\n"
    "1. Identify WHY the previous task failed (e.g. repeated test failures, missing dependencies, flawed design).\n"
    "2. Do NOT simply reissue the exact same task.\n"
    "3. Replace the failed task with 1-3 new, smaller, or differently-approached tasks that address the root cause of the failure.\n"
    "4. Do not recreate tasks that are already 'done' or 'validated'.\n"
)


def get_architect_model():
    provider = resolve_provider("supervisor", "primary")
    keys = ("CEREBRAS_API_KEY",) if provider == "cerebras" else (("MISTRAL_API_KEY",) if provider == "mistral" else ("AGENT_API_KEY",))
    return build_model_with_fallback(
        "architect_worker",
        SUPERVISOR_MODEL_PRIMARY,
        SUPERVISOR_MODEL_FALLBACK,
        temperature=0,
        api_key_envs=keys,
        structured_output=ArchitectureBlueprint,
    )


def _latest_user_request(messages: list) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
        if isinstance(message, dict) and message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


async def architect_worker_node(state: dict) -> dict:
    """Build or revise a plan while preserving completed tasks as immutable history."""
    existing_plan = list(state.get("plan") or [])
    completed = [task for task in existing_plan if isinstance(task, dict) and task.get("status") in {"done", "validated"}]
    preserved = [task for task in existing_plan if isinstance(task, dict) and task.get("status") != "needs_replan"]
    needs_replan = [task for task in existing_plan if isinstance(task, dict) and task.get("status") == "needs_replan"]

    prompt = (
        f"User request: {_latest_user_request(state.get('messages') or [])}\n\n"
        f"Existing project context: {state.get('project_context') or {}}\n\n"
        f"Completed tasks (do not recreate): {completed}\n\n"
        f"Tasks needing replan: {needs_replan}\n\n"
        f"Task events: {state.get('task_events') or []}\n\n"
        f"Task history: {state.get('task_history') or []}"
    )
    try:
        messages_prompt = [
            SystemMessage(content=ARCHITECT_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        for attempt in range(3):
            try:
                blueprint: ArchitectureBlueprint = await asyncio.wait_for(get_architect_model().ainvoke(messages_prompt), timeout=120)
                break
            except Exception as e:
                if attempt == 2:
                    raise e
                logger.warning(f"Architect LLM parsing failed (attempt {attempt+1}): {e}")
                messages_prompt.append(HumanMessage(content=f"Failed to parse structured output. Error: {e}\nPlease correct your JSON and try again."))
        planned_tasks = []
        known_fingerprints = {task.get("fingerprint") for task in completed if task.get("fingerprint")}
        for task_input in blueprint.tasks:
            fingerprint = task_fingerprint(
                task_input.title, task_input.description, task_input.domain, task_input.acceptance_criteria
            )
            if fingerprint in known_fingerprints:
                continue
            known_fingerprints.add(fingerprint)
            planned_tasks.append(
                PlanTask(
                    id=f"task_{uuid.uuid4().hex[:8]}",
                    title=task_input.title.strip(),
                    description=task_input.description.strip(),
                    domain=task_input.domain,
                    validation_required=True,
                    acceptance_criteria=task_input.acceptance_criteria,
                    verification_commands=task_input.verification_commands,
                    fingerprint=fingerprint,
                ).model_dump()
            )

        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "project_replanned" if needs_replan else "project_planned",
            "task_id": None,
            "details": {"summary": blueprint.summary, "task_count": len(planned_tasks)},
        }
        from src.core.task_logger import log_task_event
        log_task_event(event)
        
        project_context = dict(state.get("project_context") or {})
        project_context.update(blueprint.project_context.model_dump(exclude_defaults=True))
        if blueprint.is_goal_completed:
            project_context["is_goal_completed"] = True
            
        return {
            "messages": [AIMessage(content=blueprint.summary or "Architecture blueprint created.", name="architect_worker")],
            "project_context": project_context,
            "plan": preserved + planned_tasks,
            "task_events": [*(state.get("task_events") or []), event][-200:],
            "worker_complete": {"architect_worker": True},
            "worker_outputs": {"architect_worker": blueprint.summary},
            "worker_type": "architect_worker",
            "next_agent": "supervisor",
            "current_task_id": None,
        }
    except Exception as exc:
        logger.exception("Architect worker failed")
        return {
            "messages": [AIMessage(content=f"Architecture planning failed: {exc}", name="architect_worker")],
            "worker_complete": {"architect_worker": True},
            "worker_outputs": {"architect_worker": f"Architecture planning failed: {exc}"},
            "worker_type": "architect_worker",
            "next_agent": "synthesizer",
        }
