# Supervisor node for routing queries using Native Tool Calling

import os
import logging
import threading
from typing import Dict, List, Optional

from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from src.core.config import SUPERVISOR_MODEL_PRIMARY, SUPERVISOR_MODEL_FALLBACK
from src.core.model_provider import build_model_with_fallback, resolve_provider

logger = logging.getLogger("MultiAgent.Supervisor")
MAX_PLAN_STEPS = 15

APPROVAL_REGISTRY: Dict[str, set] = {}
_approval_lock = threading.Lock()

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
- coding_worker: Code generation, file editing, and code analysis tasks. Use for all programming work.
- code_critic_worker: Validate findings from coding_worker.

Your duties:
1. Construct or update a step-by-step plan to answer the user query.
2. Evaluate the message history to determine the safest next move.
3. Determine the next step. If all steps are complete, route to 'synthesizer'.
4. Select the next appropriate worker. 
5. Write the updated plan, next_agent, and current_task.
"""

class SupervisorDecision(BaseModel):
    plan: List[str] = Field(description="Step-by-step plan to answer the query (maximum 8 steps)")
    next_agent: str = Field(description="The next agent to route to")
    current_task: str = Field(description="Specific instruction for the next worker", default="")
    parallel_tasks: List[str] = Field(description="If routing to coding_worker, you may provide multiple independent tasks here to be executed concurrently by separate workers.", default_factory=list)
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

def supervisor_node(state: dict) -> dict:
    messages = state.get("messages", [])
    steps = state.get("steps_remaining", 30)
    plan = state.get("plan") or []
    retry_counter = int(state.get("retry_counter") or 0)
    active_documents = state.get("active_documents") or []
    cursor_position = state.get("cursor_position") or {}
    
    ide_context = f"\n[IDE CONTEXT]\nActive Documents: {active_documents}\nCursor: {cursor_position}\n" if (active_documents or cursor_position) else ""
    
    routing_prompt = [
        SystemMessage(content=SUPERVISOR_PROMPT + ide_context),
        SystemMessage(content=f"Current Plan: {plan}\nSteps Remaining: {steps}\nRetry Counter: {retry_counter}"),
    ]

    for msg in messages:
        routing_prompt.append(msg)

    if messages and not isinstance(messages[-1], HumanMessage):
        routing_prompt.append(HumanMessage(content="Please review the recent outputs and determine the next step."))

    new_steps = max(0, steps - 1)
    plan_out = plan
    next_agent = "synthesizer"
    current_task = ""
    parallel_tasks = []
    active_project_override = None

    try:
        model = get_routing_model()
        response = model.invoke(routing_prompt)
        plan_out = (response.plan or [])[:MAX_PLAN_STEPS]
        next_agent = response.next_agent
        current_task = response.current_task
        parallel_tasks = response.parallel_tasks or []
        active_project_override = getattr(response, "active_project", None) or None
        if active_project_override == "":
            active_project_override = None

    except Exception as e:
        logger.error(f"Supervisor routing error: {e}")
        next_agent = "synthesizer"

    valid_agents = [
        "rag_worker", "web_worker", "utility_worker", "scraper_worker",
        "critic_worker", "report_worker", "coding_worker", "code_critic_worker",
        "synthesizer", "FINISH",
    ]
    if next_agent not in valid_agents or next_agent == "FINISH":
        next_agent = "synthesizer"

    state_update = {
        "plan": plan_out,
        "next_agent": next_agent,
        "current_task": current_task,
        "parallel_tasks": parallel_tasks if next_agent == "coding_worker" else [],
        "active_project": active_project_override if active_project_override is not None else (state.get("active_project") or None),
        "steps_remaining": new_steps,
        "retry_counter": retry_counter,
    }
    
    print(f"\n[SUPERVISOR] Next Node: '{next_agent}' | Task: '{current_task}' | Swarm Tasks: {len(parallel_tasks)} | Steps Left: {new_steps}")
    return state_update
