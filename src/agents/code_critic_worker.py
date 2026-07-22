# Code critic worker node - validates symbol usage, checks for hallucinations, and audits patches.
import logging
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from src.core.config import CODE_CRITIC_MODEL_PRIMARY, CODE_CRITIC_MODEL_FALLBACK
from src.core.model_provider import build_model_with_fallback, resolve_provider

logger = logging.getLogger("MultiAgent.CodeCriticWorker")

CRITIC_SYSTEM_PROMPT = """You are a Code Critic and Reviewer. Your job is to validate the frontend_worker and backend_worker outputs.
You enforce both TECHNICAL QUALITY (syntax, architecture, logic) and DESIGN QUALITY (premium UI, aesthetic design, responsive styling).

ENVIRONMENT WARNING: This system runs on a Windows machine with PowerShell. When reviewing verification command errors, if the error is due to a missing Linux command (like `cat` or `grep`), this is an environment command failure, NOT a failure of the code itself.

CRITICAL INSTRUCTION: The user is often building new projects from scratch. DO NOT be overly strict about missing features, failed builds, or incomplete code during the initial scaffolding phase.
- A FAILED build/test or missing validation command should be marked as a WARNING, not critical.
- Let the agent make the project first; we will strive to make it perfect later.
- Only mark an issue as CRITICAL if it is a severe syntax error that corrupts the file, a severe security vulnerability, or a catastrophic design failure.

Output structured findings (info/warning/critical). If any critical issue remains, end with RETRY_REQUIRED."""

class CriticFinding(BaseModel):
    issue_type: str = Field(description="The category of issue (e.g. 'hallucinated_symbol', 'syntax_error', 'unsupported_claim', 'patch_mismatch', 'security_risk')")
    symbol_name: Optional[str] = Field(description="The symbol associated with the issue, if applicable", default=None)
    file_location: Optional[str] = Field(description="The file location where the issue was found", default=None)
    details: str = Field(description="Detailed explanation of the issue or validation finding")
    severity: str = Field(description="Severity rating ('info', 'warning', 'critical')")
    evidence: Optional[str] = Field(description="Evidence supporting the finding", default=None)

class CriticReport(BaseModel):
    valid: bool = Field(description="True if the coding worker's findings and patches are fully validated with no critical issues.")
    findings: List[CriticFinding] = Field(description="Detailed checklist of individual validation findings")
    criticism_summary: str = Field(description="Overall review summary and critique of the work")


def get_critic_model():
    """Return the configured model with structured CriticReport output."""
    provider = resolve_provider("code_critic", "primary")
    if provider == "cerebras":
        keys = ("CEREBRAS_API_KEY",)
    elif provider == "mistral":
        keys = ("MISTRAL_API_KEY",)
    else:
        keys = ("AGENT_API_KEY",)
    return build_model_with_fallback(
        "code_critic",
        CODE_CRITIC_MODEL_PRIMARY,
        CODE_CRITIC_MODEL_FALLBACK,
        temperature=0,
        api_key_envs=keys,
        structured_output=CriticReport,
    )

class CIDecision(BaseModel):
    action: Literal["WAIT", "SEND_INPUT", "ABORT"] = Field(description="Action to take: WAIT (normal progress), SEND_INPUT (stuck on prompt), ABORT (error loop).")
    input_text: str = Field(description="Text to send if action is SEND_INPUT. Must include newline (\\n) if simulating Enter.", default="")
    reasoning: str = Field(description="Why this action was chosen.")

def _get_ci_monitor_model():
    provider = resolve_provider("code_critic", "primary")
    if provider == "cerebras":
        keys = ("CEREBRAS_API_KEY",)
    elif provider == "mistral":
        keys = ("MISTRAL_API_KEY",)
    else:
        keys = ("AGENT_API_KEY",)
    return build_model_with_fallback(
        "code_critic",
        CODE_CRITIC_MODEL_PRIMARY,
        CODE_CRITIC_MODEL_FALLBACK,
        temperature=0,
        api_key_envs=keys,
        structured_output=CIDecision,
    )

async def _monitor_ci_task(task_id: str, script_name: str) -> str:
    import json, time
    from src.tools.coding_tools import check_task_status, kill_task, send_task_input
    
    model = _get_ci_monitor_model()
    
    for iteration in range(12): # 12 iterations * 15s = 3 minutes max
        time.sleep(15)
        status_res = check_task_status(task_id)
        try:
            status_json = json.loads(status_res)
            
            if "exited" in status_json.get("message", ""):
                return status_res
                
            stdout_so_far = status_json.get("data", {}).get("output", "")
            
            prompt = [
                SystemMessage(content="You are a CI Task Monitor. Your job is to read the terminal output of a running command and decide the next action.\n- WAIT: If it is downloading, compiling, or progressing normally.\n- SEND_INPUT: If it is explicitly waiting for user input (e.g. 'Press y').\n- ABORT: If it is stuck in an infinite error loop or has completely crashed without exiting."),
                HumanMessage(content=f"Command: {script_name}\n\nRecent Output:\n{stdout_so_far[-2000:]}")
            ]
            
            decision: CIDecision = await model.ainvoke(prompt)
            logger.info(f"[CI MONITOR] Action: {decision.action} | Reason: {decision.reasoning}")
            
            if decision.action == "ABORT":
                kill_task(task_id)
                return f"{status_res}\n\n[SYSTEM NOTE: The CI process was forcefully ABORTED by the Intelligent Monitor. Reason: {decision.reasoning}]"
            elif decision.action == "SEND_INPUT":
                send_task_input(task_id, decision.input_text)
                # continue waiting
                
        except Exception as e:
            logger.warning(f"CI Monitor error: {e}")
            
    kill_task(task_id)
    return f"{status_res}\n\n[SYSTEM NOTE: The CI process exceeded the maximum 3-minute limit and was forcefully terminated to prevent a system hang. Treat this as a CRITICAL validation failure.]"



async def code_critic_worker_node(state: dict) -> dict:
    """
    Code critic worker that audits coding worker outputs against repository symbol tables.
    """
    logger.info("Executing Code Critic Worker node...")
    
    # 1. Access current blackboard findings
    scratchpad = state.get("scratchpad", "")
    current_task = state.get("current_task", "")
    worker_outputs = state.get("worker_outputs", {})
    current_task_id = state.get("current_task_id")
    plan = list(state.get("plan") or [])

    retry_count = 0
    for t in plan:
        if isinstance(t, dict) and t.get("id") == current_task_id:
            retry_count = t.get("attempt_count", 0)
            break
        elif hasattr(t, "id") and t.id == current_task_id:
            retry_count = t.attempt_count
            break

    # Review is a first-class transition. The task is not complete merely
    # because a worker returned text; the critic owns the move to a terminal
    # state after recording verification evidence.
    task_contract = {}
    for task in plan:
        if isinstance(task, dict) and task.get("id") == current_task_id:
            task["status"] = "in_progress"
            task_contract = task
            break

    
    # Get coding worker's output
    worker_name = next(
        (name for name in ("frontend_worker", "backend_worker", "coding_worker") if worker_outputs.get(name)),
        "coding_worker",
    )
    coding_output = worker_outputs.get(worker_name, "")
    if not coding_output:
        logger.warning("No coding worker output detected to critique. Skipping validation.")
        final_text = "No coding specialist output was found to validate."
        return {
            "messages": [AIMessage(content=final_text, name="code_critic_worker")],
            "worker_complete": {"code_critic_worker": True},
            "worker_outputs": {"code_critic_worker": final_text},
            "worker_type": "code_critic_worker",
            "next_agent": "supervisor",
            "plan": plan,
            "critic_feedback": {
                "status": "needs_changes",
                "target_worker": None,
                "summary": final_text,
                "evidence": [],
            },
        }
        
    # 2b. Collect execution/verification artifacts from scratchpad and worker outputs
    verification_artifacts = []
    
    for source in [scratchpad, coding_output]:
        if not source:
            continue
        for marker in ["[SECURE RUN]", "Command exited with status", "stdout", "stderr", "parsed_errors", "VERIFICATION RESULTS"]:
            if marker in source:
                verification_artifacts.append(source)
                break
    
    verification_context = ""
    # Phase 3: Automated Verification Loops (Headless Critic CI/CD)
    import os
    import json
    from src.tools.coding_tools import execute_command
    
    auto_ci_artifacts = []
    workspace_dir = os.path.abspath("./workspace")
    
    explicit_commands = task_contract.get("verification_commands", [])
    if explicit_commands:
        for cmd in explicit_commands:
            logger.info(f"[HEADLESS CRITIC] Executing explicit task contract verification: {cmd}")
            ci_result = execute_command(cmd, wait_ms_before_async=30000)
            try:
                res_json = json.loads(ci_result)
                if isinstance(res_json, dict) and res_json.get("status") == "ok" and "data" in res_json and "task_id" in res_json["data"]:
                    task_id = res_json["data"]["task_id"]
                    ci_result = await _monitor_ci_task(task_id, cmd)
            except Exception as e:
                logger.warning(f"Failed to check task_id in CI result: {e}")
            auto_ci_artifacts.append(f"--- AUTO CI RUN: {cmd} ---\n{ci_result}")
            
    elif task_contract.get("domain") in ["frontend", "fullstack"]:
        logger.info("[HEADLESS CRITIC] No explicit commands. Running frontend heuristics...")
        pkg_json_path = os.path.join(workspace_dir, "package.json")
        if os.path.exists(pkg_json_path):
            try:
                with open(pkg_json_path, 'r', encoding='utf-8') as f:
                    pkg_data = json.load(f)
                scripts = pkg_data.get("scripts", {}) if isinstance(pkg_data, dict) else {}
                for target_script in ["build", "lint", "test"]:
                    if target_script in scripts:
                        cmd = f"npm run {target_script}"
                        ci_result = execute_command(cmd, wait_ms_before_async=30000)
                        try:
                            res_json = json.loads(ci_result)
                            if isinstance(res_json, dict) and res_json.get("status") == "ok" and "data" in res_json and "task_id" in res_json["data"]:
                                task_id = res_json["data"]["task_id"]
                                ci_result = await _monitor_ci_task(task_id, cmd)
                        except Exception:
                            pass
                        auto_ci_artifacts.append(f"--- AUTO CI RUN (Fallback): {cmd} ---\n{ci_result}")
                        break
            except Exception as e:
                logger.warning(f"Failed to parse package.json: {e}")
                
    elif os.path.exists(os.path.join(workspace_dir, "pytest.ini")) or os.path.exists(os.path.join(workspace_dir, "requirements.txt")):
        logger.info("[HEADLESS CRITIC] Auto-discovered Python project. Executing pytest CI gate...")
        ci_result = execute_command("pytest", wait_ms_before_async=30000)
        try:
            res_json = json.loads(ci_result)
            if isinstance(res_json, dict) and res_json.get("status") == "ok" and "data" in res_json and "task_id" in res_json["data"]:
                task_id = res_json["data"]["task_id"]
                ci_result = await _monitor_ci_task(task_id, "pytest")
        except Exception:
            pass
        auto_ci_artifacts.append(f"--- AUTO CI RUN (Fallback): pytest ---\n{ci_result}")
            
    if auto_ci_artifacts:
        verification_artifacts.extend(auto_ci_artifacts)

    if verification_artifacts:
        verification_context = "\n\n=== VERIFICATION ARTIFACTS ===\n" + "\n---\n".join(verification_artifacts[-5:])
    else:
        verification_context = "\n\n=== VERIFICATION ARTIFACTS ===\nNo validation commands were found in the coding worker output, and no auto-CI scripts were detected in the workspace. If the task involved creating or modifying files, this is a CRITICAL gap."

    # 2c. Extract repository index symbols for validation context
    from src.agents.coding_worker import get_retrieval_service
    try:
        service = get_retrieval_service()
        all_symbols = service.indexer.symbol_table.get_all_symbols()
        symbol_details = [
            f"[{s['type'].upper()}] {s['name']} in {s['filepath']}:{s['start_line']}-{s['end_line']}"
            for s in all_symbols
        ]
        repo_context = "Repository Available Symbols:\n" + "\n".join(symbol_details)
    except Exception as e:
        logger.error(f"Failed to load repository symbols for critic: {e}")
        repo_context = "Repository Available Symbols: (Failed to load symbols)"

    # 3. Invoke structured LLM review
    model = get_critic_model()
    
    critic_prompt = [
        SystemMessage(content=CRITIC_SYSTEM_PROMPT),
        SystemMessage(content=repo_context + verification_context),
        HumanMessage(content=(
            f"Coding Specialist Task: {current_task}\n\n"
            f"Task Contract: {json.dumps(task_contract, default=str)}\n\n"
            f"Coding Specialist Output:\n{coding_output}"
        ))
    ]
    
    is_invalid = False
    try:
        report: CriticReport = await model.ainvoke(critic_prompt)
        
        # Format findings for presentation
        output_lines = []
        output_lines.append("### CODE CRITIC VALIDATION REPORT")
        output_lines.append(f"**Status**: {'✓ VALIDATED' if report.valid else '✗ ISSUES FOUND'}")
        output_lines.append(f"**Critique Summary**: {report.criticism_summary}\n")
        
        if report.findings:
            output_lines.append("### FINDINGS DETAIL")
            output_lines.append("")
            for f in report.findings:
                loc = f" ({f.file_location})" if f.file_location else ""
                output_lines.append(f"- **[{f.severity.upper()}]** ({f.issue_type}){loc}")
                output_lines.append(f"  - {f.details}")
                if f.evidence:
                    output_lines.append(f"  - Evidence: {f.evidence}")
                if f.symbol_name:
                    output_lines.append(f"  - Symbol: {f.symbol_name}")
                output_lines.append("")
        else:
            output_lines.append("No issues detected.")
        
        is_invalid = not report.valid or any(f.severity.lower() == "critical" for f in report.findings)
        
        if is_invalid:
            if retry_count < 2:
                output_lines.append("\nRETRY_REQUIRED")
            else:
                output_lines.append("\n[Max validation retry limit reached. Verification failed after multiple attempts. Proceeding without further retries.]")
             
        final_text = "\n".join(output_lines)
    except Exception as e:
        logger.error(f"Error executing critic model call: {e}")
        final_text = f"Error during Code Critic model execution: {e}"
        is_invalid = False

    logger.info("Code Critic Worker execution completed.")
    
    if is_invalid and retry_count >= 2:
        updated_scratchpad = scratchpad + f"\n- [Code Critic]: Verification failed repeatedly. Aborting corrections to prevent infinite loop.\nFindings:\n{final_text}"
        messages_out = [
            AIMessage(content=final_text, name="code_critic_worker"),
            SystemMessage(content="CRITICAL INSTRUCTION: The coding worker has failed the maximum number of times on this task. You MUST NOT route back to the coding_worker for this specific issue. Proceed to the next step or route to synthesizer.")
        ]
    else:
        updated_scratchpad = scratchpad + f"\n- [Code Critic]: Code validation report:\n{final_text}"
        messages_out = [AIMessage(content=final_text, name="code_critic_worker")]
    
    state_update = {
        "messages": messages_out,
        "scratchpad": updated_scratchpad,
        "worker_complete": {"code_critic_worker": True},
        "worker_outputs": {"code_critic_worker": final_text},
        "worker_type": "code_critic_worker",
        "next_agent": "supervisor",
        "created_files": state.get("created_files", []),
        "plan": plan,
        "critic_feedback": {
            "status": "needs_changes" if is_invalid else "validated",
            "target_worker": worker_name if worker_name in {"frontend_worker", "backend_worker"} else None,
            "summary": report.criticism_summary if 'report' in locals() else final_text,
            "findings": [finding.model_dump() for finding in report.findings] if 'report' in locals() else [],
            "evidence": [
                {"source": "verification", "details": artifact[:2000]}
                for artifact in verification_artifacts[-5:]
            ],
        },
    }
    
    if is_invalid and retry_count < 2:
        logger.info(f"[CODE CRITIC WORKER] Critical issue detected! Forcing coding worker retry (retry {retry_count + 1}/2).")
        # Include specific critic findings in the retry instruction, while
        # preserving the original task ID and contract.
        # coding worker gets concrete corrective instructions, not a vague "FIX ERROR".
        critic_feedback_summary = report.criticism_summary if report else "Unknown issues detected."
        finding_details = []
        if report and report.findings:
            for f in report.findings:
                if f.severity.lower() == "critical":
                    detail = f"[{f.issue_type}] {f.details}"
                    if f.file_location:
                        detail += f" (in {f.file_location})"
                    finding_details.append(detail)
        findings_text = "; ".join(finding_details) if finding_details else critic_feedback_summary

        state_update["current_task"] = f"CRITIC RETRY ({retry_count + 1}/2): Address these specific issues found by the code critic: {findings_text[:800]}"
        state_update["critic_retry_count"] = retry_count + 1
        state_update["next_agent"] = "supervisor"
    else:
        # Issue #2: Reset retry count to prevent stale state from blocking future critic cycles
        state_update["critic_retry_count"] = 0
        
    return state_update
