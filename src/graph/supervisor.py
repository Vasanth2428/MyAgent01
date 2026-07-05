# Supervisor node for routing queries to specialized workers.

import os

import logging

from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage



from src.core.config import SUPERVISOR_MODEL_PRIMARY, SUPERVISOR_MODEL_FALLBACK

from src.core.model_provider import build_model_with_fallback, resolve_provider

from src.graph.worker_output_cache import (

    get_worker_output_summary,

)

from src.core.blackboard_reference_store import compact_scratchpad



logger = logging.getLogger("MultiAgent.Supervisor")



MAX_PLAN_STEPS = 15



import threading



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

- rag_worker: Retrieve information from private documents only. Use for questions about uploaded files, documents, or custom knowledge base.

- web_worker: Search the web for real-time/current information, news, or general external web search.

- utility_worker: Perform calculations, math, date/time lookups, and basic formatting.

- scraper_worker: Fetch and extract text content from specific URLs or links. Use this when the query or step explicitly requires reading the content of a web page.

- critic_worker: Analyze accumulated findings, cross-reference sources, fact-check, and identify inconsistencies or gaps. Use this to critique findings before synthesis.

- report_worker: Generate comprehensive, long-form markdown reports from the accumulated findings. Use this when the user explicitly requests a report or summary document.

- coding_worker: Code generation, file creation/editing, security auditing, code review, and architecture evaluation. Use for creating files, writing code, modifying existing code, and code analysis tasks.

- code_critic_worker: Validate findings from coding_worker against repository symbols, audit patch correctness, and check for security risks.



Your duties:

1. Construct or update a step-by-step plan (max 8 steps per turn) to answer the user query.

2. Evaluate the 'scratchpad', 'worker_summaries', 'file_status_flags', and especially 'Completed Tasks' to pick the safest next move.

3. Determine the next step. If all research steps are resolved, check if the user explicitly requested a report/summary document. If yes, route to the report_worker ONCE. If no report is needed, route to the synthesizer.

4. Otherwise, select the next appropriate worker. For code analysis tasks, route to coding_worker for analysis then code_critic_worker for validation.

5. Write the updated plan (max 8 steps), next_agent, and current_task in the JSON response.



CRITICAL DEDUPLICATION RULES (you MUST follow these before every routing decision):

- Check the 'Completed Tasks' list in the blackboard carefully. If a task fingerprint matching your intended next_agent + task already appears there, DO NOT route to that worker again.

- If the scratchpad or worker summaries already contain results from a worker for this session, do not re-run that same worker for the same sub-task.

- If the coding_worker has already scaffolded a project (keyword 'scaffold' appears in completed tasks), route to coding_worker for CONTENT only — not scaffolding again.

- If all planned steps are complete or covered by completed tasks, route DIRECTLY to 'synthesizer'. Do not route to 'report_worker' unless the user explicitly asked for a report.

- Prefer 'synthesizer' over any looping back to workers when sufficient information is available.



CODING TASK SPECIFICATION RULES:

- When routing to coding_worker for implementation or editing:

  1. Break down broad requests (e.g. "Create a fullstack crypto portfolio website") into specific, component-level tasks (e.g., "Scaffold Vite app", "Implement SQLite schema and FastAPI backend", "Develop premium dashboard interface in App.jsx"). Never dispatch a single task covering both frontend and backend.

  2. For frontend tasks, explicitly instruct coding_worker to produce Lovable-quality designs using the full modern stack: Tailwind CSS with HSL theme tokens (bg-primary, text-muted-foreground), shadcn/ui components (Button, Card, Input, Dialog, Table, Select, Tabs, Sheet), Lucide React icons, dark/light mode via CSS custom properties, glassmorphism (backdrop-blur-md), smooth gradients, responsive breakpoints (sm/md/lg/xl), micro-animations (transition-all, hover:scale-105, animate-fade-in), and Inter font from Google Fonts. Use the cn() utility for class composition and CVA for component variants. Never accept basic grey/white styling, native browser defaults, inline styles, or placeholder designs.

  3. For backend tasks, instruct the worker to use local SQLite databases, FastAPI routes, and write validation checks.

  4. Ensure task instructions are concrete, specifying file paths and expected behaviors. Do not use vague or generic summaries.

  6. For complex UIs (dashboards, admin panels, multi-page apps), decompose into sequential tasks: (a) Scaffold with design system via scaffold_react_app, (b) Create layout shell and navigation (Sidebar, Header, routing), (c) Build individual page components one at a time, (d) Add data integration and state management. Always instruct coding_worker to use shadcn/ui primitives (Button, Card, Dialog, Table, Input, Select, Tabs, Sheet) instead of building raw HTML equivalents.

  5. **TEST-DRIVEN DEVELOPMENT (TDD) RULES**:

     - Before writing unit tests or backend logic, the supervisor **MUST** first dispatch a task to scaffold/create the basic backend directory structure (e.g. creating the folder and requirements.txt).

     - The supervisor **MUST** then dispatch a separate task to write a corresponding unit test file (e.g., `test_main.py` or `tests/test_devices.py`) outlining the expected behaviors, status codes, and input/output contracts.

     - Only then should the supervisor dispatch tasks to implement the actual backend logic and run the tests to verify correctness (verifying they exit with status 0 using `run_safe_commands`).

     - **AUTO-DEPENDENCY RESOLUTION & INSTALLATION RULES**: When instructing coding_worker to create, modify, or verify frontend (React) or backend (Python) projects, explicitly command it to check imported packages against the local subdirectory `package.json` / `requirements.txt` and install them before executing tests, building, compiling, or starting servers. For nested frontend apps, require `npm --prefix <subdir> install`, `npm --prefix <subdir> install <package>`, and `npm --prefix <subdir> run build`; do not use bare root-level npm commands for subdirectory apps. For Python services, use `python -m pip install -r <subdir>/requirements.txt` or `python -m pip install <package>`.

      - **TERMINAL COMMAND LIMITATIONS**: Never use command chaining with `&&` or `;` in task instructions. Never use `cd` commands. Never use absolute paths (always use relative paths inside the workspace, e.g., `classroom-management-app/frontend`). To target nested directories, instruct `coding_worker` to use the `--prefix` flag (for npm) or pass relative paths. Note that persistent background servers (like `npm run dev` or `nodemon`) are unsupported because the execution sandbox terminates any process after 15 seconds. Do not attempt to run persistent background services.

- **PLAN COMPLETION RULES**:
  - Do not route to `synthesizer` or `FINISH` unless every step in the current plan is completely implemented and verified.
  - If a coding step was scaffolded but not yet filled with full content, continue dispatching to `coding_worker` rather than concluding.
  - Only mark the task as complete when all files listed in the plan have been created/finalized and the code critic has validated them.

- **ACTIVE PROJECT RULES**:
  - When starting any application code generation task (Scaffold, backend API, React app), set the `active_project` field in the response to the sanitized project directory name (e.g. `beezlebub`, `dashboard`). Leave `active_project` empty for analysis-only or research tasks.

"""




class SupervisorDecision(BaseModel):

    plan: List[str] = Field(description="Step-by-step plan to answer the query (maximum 8 steps)")

    next_agent: str = Field(description="The next agent to route to")

    current_task: str = Field(description="Specific instruction for the next worker", default="")

    active_project: Optional[str] = Field(
        description="Sanitized folder name for the project (e.g. 'beezlebub') if this task involves creating or modifying a specific application. Otherwise, leave empty.",
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





def _approval_decision_from_message(message: str) -> str:

    text = (message or "").strip().lower()

    if not text:

        return ""



    approval_phrases = ["approve", "yes", "ok", "go ahead", "apply", "proceed", "yep", "sure"]

    rejection_phrases = ["reject", "no", "deny", "stop", "cancel", "dont", "don't"]



    if any(phrase in text for phrase in approval_phrases):

        return "approved"

    if any(phrase in text for phrase in rejection_phrases):

        return "rejected"

    return ""





def _approval_decision_from_state(state: dict) -> str:

    decision = str(state.get("approval_decision") or state.get("approval_requested") or "").strip().lower()

    if decision in {"approved", "approve", "yes", "true", "1"}:

        return "approved"

    if decision in {"rejected", "reject", "no", "false", "0"}:

        return "rejected"



    for approval in (state.get("pending_file_approvals") or {}).values():

        if not isinstance(approval, dict):

            continue

        item_decision = str(approval.get("decision") or approval.get("approved") or "").strip().lower()

        if item_decision in {"approved", "approve", "yes", "true", "1"}:

            return "approved"

        if item_decision in {"rejected", "reject", "no", "false", "0"}:

            return "rejected"



    return ""





def _display_scratchpad(scratchpad: str) -> str:

    if len(scratchpad) > 6000:

        return "[...earlier findings truncated...]\n" + scratchpad[-6000:]

    return scratchpad





def _summarize_worker_outputs(

    state: dict,

) -> Tuple[str, Dict[str, str]]:

    worker_output_ids = state.get("worker_output_ids") or {}

    worker_output_summaries = state.get("worker_output_summaries") or {}

    summaries = dict(worker_output_summaries)

    for worker_name, cache_id in worker_output_ids.items():

        summaries.setdefault(worker_name, get_worker_output_summary(cache_id))

    return "\n".join(f"- [{name}]: {summary}" for name, summary in summaries.items()) or "(No worker summaries yet)", summaries





def supervisor_node(state: dict) -> dict:



    messages = state.get("messages", [])

    context_notes = state.get("context_notes") or []

    steps = state.get("steps_remaining", 30)

    plan = state.get("plan") or []

    # Retain the compacted scratchpad for error messages, but primary context is in scratchpad_references

    scratchpad = state.get("scratchpad") or ""

    scratchpad_references = state.get("scratchpad_references") or []

    worker_output_ids = state.get("worker_output_ids") or {}

    worker_output_summaries = state.get("worker_output_summaries") or {}

    file_status_flags = state.get("file_status_flags") or {}

    task_hashes = state.get("task_hashes") or []

    active_document_ids = state.get("active_document_ids") or []

    retry_counter = int(state.get("retry_counter") or 0)

    completed_tasks = list(state.get("completed_tasks") or [])

    created_files = list(state.get("created_files") or [])

    # Structured HITL handling - avoid parsing scratchpad text

    is_waiting = state.get("waiting_for_approval", False)
    pending_approvals = state.get("pending_file_approvals") or {}

    blocked_files = []

    if is_waiting:

        if state.get("approval_filepath"):

            blocked_files.append(state.get("approval_filepath"))

        elif pending_approvals:

            blocked_files.extend(pending_approvals.keys())

    

    latest_user_message = ""

    for msg in reversed(messages):

        if isinstance(msg, dict) and msg.get("role") == "user":

            latest_user_message = msg.get("content", "")

            break

        elif hasattr(msg, "content") and (msg.__class__.__name__ == "HumanMessage" or getattr(msg, "type", "") == "human"):

            latest_user_message = msg.content

            break



    approval_decision = _approval_decision_from_state(state) or _approval_decision_from_message(latest_user_message)



    state_update_overrides = {}



    if blocked_files:

        session_id = _get_session_id(state)

        from src.agents.coding_worker import execute_pending_approval, clear_pending_approval, get_pending_approval

        from src.tools.coding_tools import _get_absolute_path



        pending = get_pending_approval(session_id)

        pending_tool_call_id = pending.get("tool_call_id") if pending else None



        if approval_decision == "approved":

            for filepath in blocked_files:

                try:

                    abs_path = os.path.realpath(_get_absolute_path(filepath.strip()))

                    approve_file(session_id, abs_path)

                except Exception as e:

                    logger.warning(f"Failed to register approval for {filepath}: {e}")

                    

            execution_result = execute_pending_approval(session_id)

            # Extract successfully created files from HITL approval execution
            import re as _re
            _success_files_match = _re.search(r"Successfully processed:\s*(.+)", execution_result)
            if _success_files_match:
                _new_created = [_f.strip() for _f in _success_files_match.group(1).split(",") if _f.strip()]
                created_files = list(dict.fromkeys(created_files + _new_created))

            state_update_overrides["scratchpad_references"] = scratchpad_references + [

                f"- [SYSTEM HITL]: User approved modifications. Action result: {execution_result}"]

            logger.info(f"Human-in-the-Loop Approved and Executed: {execution_result}")

            

            state_update_overrides["waiting_for_approval"] = False

            state_update_overrides["pending_file_approvals"] = {}

            state_update_overrides["approval_decision"] = "approved"

            state_update_overrides["coding_worker_resume_tool_result"] = execution_result

            state_update_overrides["coding_worker_resume_tool_call_id"] = pending_tool_call_id



        elif approval_decision == "rejected":

            clear_pending_approval(session_id)

            

            # Extract steering feedback from latest user message

            user_feedback = latest_user_message.strip()

            # Remove leading rejection words (no, reject, deny, cancel, stop, dont, don't)

            import re

            cleaned_feedback = re.sub(r'^(?:no|reject|deny|stop|cancel|dont|don\'t)(?:\s*,\s*|\s+)?', '', user_feedback, flags=re.IGNORECASE)

            

            feedback_reason = f"User feedback: \"{cleaned_feedback}\"" if cleaned_feedback else "No feedback provided."

            rejection_message = f"Error: User rejected the proposed file modifications. {feedback_reason}"

            

            state_update_overrides["scratchpad_references"] = scratchpad_references + [

                f"- [SYSTEM HITL]: User rejected the proposed file modifications. {feedback_reason}"]

            logger.info(f"Human-in-the-Loop: User rejected changes. {feedback_reason}")

            

            state_update_overrides["waiting_for_approval"] = False

            state_update_overrides["pending_file_approvals"] = {}

            state_update_overrides["approval_decision"] = "rejected"

            state_update_overrides["coding_worker_resume_tool_result"] = rejection_message

            state_update_overrides["coding_worker_resume_tool_call_id"] = pending_tool_call_id



        else:

            hitl_note = (

                f"- [SYSTEM HITL]: Awaiting user approval for "

                f"{state.get('approval_tool') or 'file operation'} on "

                f"{state.get('approval_filepath') or ', '.join(blocked_files)}."

            )

            if hitl_note not in scratchpad_references:

                scratchpad_references = scratchpad_references + [hitl_note]

                state_update_overrides["scratchpad_references"] = scratchpad_references

            logger.info("Human-in-the-Loop: Awaiting explicit approval; pausing workflow.")



        pause_update = {

            "plan": plan,

            "next_agent": "supervisor",

            "current_task": "",

            "steps_remaining": steps,

            "scratchpad": compact_scratchpad(scratchpad),

            "retry_counter": retry_counter,

            "worker_output_summaries": worker_output_summaries,

            "worker_output_ids": worker_output_ids,

            "scratchpad_references": scratchpad_references,

            "waiting_for_approval": True,

            "pending_file_approvals": pending_approvals,

            "approval_filepath": state.get("approval_filepath", ""),

            "approval_tool": state.get("approval_tool", ""),

        }

        pause_update.update(state_update_overrides)

        return pause_update



    summaries_text, summaries = _summarize_worker_outputs(state)



    # Reconstruct a readable scratchpad from references for display

    reconstructed_scratchpad = "\n".join(scratchpad_references)

    display_scratchpad = _display_scratchpad(reconstructed_scratchpad)



    blackboard_context = "\n".join(

        [

            "--- COOPERATIVE BLACKBOARD ---",

            f"Current Plan: {plan}",

            f"Active Document IDs: {', '.join(active_document_ids[:5]) or 'None'}",

            f"Task Hashes: {', '.join(task_hashes[:5]) or 'None'}",

            f"Retry Attempts: {retry_counter}",

            f"File Status Flags: {file_status_flags or 'None'}",

            f"Completed Tasks (DO NOT re-assign these): {completed_tasks if completed_tasks else 'None'}",

            f"Created Files Manifest: {created_files if created_files else 'None'}",

            "Accumulated Findings (Scratchpad):",

            display_scratchpad if display_scratchpad else "(No findings yet)",

            "Worker Summaries:",

            summaries_text,

            "-------------------------------",

        ]

    )



    routing_prompt = [

        SystemMessage(content=SUPERVISOR_PROMPT),

        SystemMessage(content=blackboard_context),

    ]



    worker_names = {

        "rag_worker",

        "web_worker",

        "utility_worker",

        "scraper_worker",

        "critic_worker",

        "report_worker",

        "coding_worker",

        "code_critic_worker",

    }

    last_human_index = -1

    for i, msg in enumerate(messages):

        role = None

        content = None

        if isinstance(msg, dict):

            role = msg.get("role")

            content = msg.get("content")

        else:

            if msg.__class__.__name__ == "HumanMessage" or getattr(msg, "type", "") == "human":

                role = "user"

                content = msg.content

            elif hasattr(msg, "content"):

                role = getattr(msg, "type", "assistant")

                content = msg.content

        if role == "user":

            last_human_index = i



    for i, msg in enumerate(messages):

        role = None

        content = None

        name = None

        if isinstance(msg, dict):

            role = msg.get("role")

            content = msg.get("content")

            name = msg.get("name")

        else:

            name = getattr(msg, "name", None)

            if msg.__class__.__name__ == "HumanMessage" or getattr(msg, "type", "") == "human":

                role = "user"

                content = msg.content

            elif hasattr(msg, "content"):

                role = getattr(msg, "type", "assistant")

                content = msg.content



        if i < last_human_index and name in worker_names:

            continue

        if role == "user":

            routing_prompt.append(HumanMessage(content=content or "", name=name))

        elif role in ("assistant", "ai"):

            routing_prompt.append(AIMessage(content=content or "", name=name))

        elif content:

            routing_prompt.append(msg)



    if context_notes:

        routing_prompt.append(SystemMessage(content=f"Additional context notes: {' '.join(context_notes)}"))



    new_steps = max(0, steps - 1)

    new_retry_counter = retry_counter



    injected_traceback = ""

    if retry_counter >= 1:

        new_retry_counter = retry_counter + 1

        if retry_counter == 1:

            try:

                model = get_routing_model().with_config(temperature=0.2)

            except Exception:

                pass

            injected_traceback = "\n[RETRY NOTE] Previous attempt failed. Prioritize the most recent worker summary and file_status_flags. Do not repeat prior path."

        else:

            injected_traceback = "\n[RETRY NOTE] Multiple retries occurred. Consider a different worker or strategy."

    if state.get("worker_output_ids"):

        injected_traceback += "\n[RETRY NOTE] Existing worker outputs exist in memory; use cached summaries instead of re-running the same worker."



    plan_out = plan if plan else []

    next_agent = "synthesizer"

    current_task = ""

    active_project_override = None



    try:

        model = get_routing_model()

        if injected_traceback:

            routing_prompt.append(SystemMessage(content=injected_traceback))

        response = model.invoke(routing_prompt)

        plan_out = (response.plan or [])[:MAX_PLAN_STEPS]

        next_agent = response.next_agent

        current_task = response.current_task

        active_project_override = getattr(response, "active_project", None) or None

        if active_project_override == "":

            active_project_override = None



    except Exception as e:

        error_str = str(e)

        logger.error(f"Supervisor routing/planning error: {error_str}")

        if "401" in error_str or "invalid_api_key" in error_str.lower():

            err_msg = "\n- [SYSTEM ERROR]: LLM API authentication failed. The API key may be expired or invalid. Please restart the server after updating your .env file."

        elif "429" in error_str or "rate_limit" in error_str.lower():

            err_msg = "\n- [SYSTEM ERROR]: LLM API rate limit exceeded. Please wait and try again."

        else:

            err_msg = f"\n- [SYSTEM ERROR]: Supervisor LLM call failed: {error_str[:200]}"

        scratchpad += err_msg

        # Also record in persistent references for future context

        state_update_overrides["scratchpad_references"] = (state_update_overrides.get("scratchpad_references", []) + [err_msg.strip()])



    valid_agents = [

        "rag_worker",

        "web_worker",

        "utility_worker",

        "scraper_worker",

        "critic_worker",

        "report_worker",

        "coding_worker",

        "code_critic_worker",

        "synthesizer",

        "FINISH",

    ]

    if next_agent not in valid_agents or next_agent == "FINISH":

        next_agent = "synthesizer"



    # Hard plan-completion guard: prevent premature synthesis when planned files are missing

    if next_agent == "synthesizer" and plan_out:

        missing_planned_files = [

            step for step in plan_out

            if any(keyword in step.lower() for keyword in ["create", "scaffold", "build", "implement", "write", "generate"])

            and not any(created_file for created_file in created_files if step.lower().split(":")[0].strip() in created_file.lower())

        ]

        if missing_planned_files:

            logger.warning(f"[SUPERVISOR] Hard guard blocked synthesis: {len(missing_planned_files)} planned steps have no created_files evidence.")

            next_agent = "coding_worker"

            current_task = f"Complete remaining plan steps and verify file creation: {'; '.join(missing_planned_files[:3])}"

            plan_out = [step for step in plan_out if step not in missing_planned_files] + missing_planned_files

            active_project_override = active_project_override or state.get("active_project") or None



    # Compact scratchpad to prevent bloat (GRAPH-01)

    compact_scratchpad_text = compact_scratchpad(scratchpad)

    

    # Dynamic plan expansion support (GRAPH-03)

    # Check for "EXPAND PLAN" directives in scratchpad

    import re

    plan_expansion_match = re.search(r"EXPAND PLAN: (.+?)(?:\n|$)", scratchpad, re.IGNORECASE)

    if plan_expansion_match and plan:

        expansion_text = plan_expansion_match.group(1).strip()

        plan_out.extend([f"EXPANDED: {expansion_text}"])

    

    # Build task fingerprint: worker:task_summary to detect duplicates next turn

    import hashlib

    task_fingerprint = None

    if next_agent not in ("synthesizer", "FINISH") and current_task:

        raw_fp = f"{next_agent}:{current_task[:120]}"

        task_fingerprint = f"{next_agent}:{hashlib.md5(raw_fp.encode()).hexdigest()[:8]}"

        # Duplicate guard: if we are about to route to the same worker+task, override to synthesizer

        if task_fingerprint in completed_tasks:

            logger.warning(f"[SUPERVISOR] Duplicate task fingerprint detected: {task_fingerprint}. Overriding next_agent to 'synthesizer'.")

            print(f"[SUPERVISOR] Duplicate task blocked ({task_fingerprint}). Forcing synthesizer.")

            next_agent = "synthesizer"

            task_fingerprint = None  # Don't record synthesizer as a completed task fingerprint



    # Track dispatched task in completed_tasks list

    new_completed_tasks = list(completed_tasks)

    if task_fingerprint and task_fingerprint not in new_completed_tasks:

        new_completed_tasks.append(task_fingerprint)



    state_update = {

        "plan": plan_out,

        "next_agent": next_agent,

        "current_task": current_task,
        
        "active_project": active_project_override if active_project_override is not None else (state.get("active_project") or None),

        "steps_remaining": new_steps,

        "scratchpad": compact_scratchpad_text,

        "retry_counter": new_retry_counter,

        "worker_output_summaries": summaries,

        "worker_output_ids": worker_output_ids,

        "scratchpad_references": scratchpad_references,

        "completed_tasks": new_completed_tasks,
        
        "created_files": created_files,

    }

    

    state_update.update(state_update_overrides)



    print(f"\n[SUPERVISOR] Next Node: '{next_agent}' | Task: '{current_task}' | Steps Left: {new_steps} | Retries: {new_retry_counter}")

    return state_update

