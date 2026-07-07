# Code critic worker node - validates symbol usage, checks for hallucinations, and audits patches.
import logging
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from src.core.config import CODE_CRITIC_MODEL_PRIMARY, CODE_CRITIC_MODEL_FALLBACK
from src.core.model_provider import build_model_with_fallback, resolve_provider

logger = logging.getLogger("MultiAgent.CodeCriticWorker")

CRITIC_SYSTEM_PROMPT = """You are a Code Critic, Security Auditor, and Runtime Validator. Your job is to validate the coding worker's outputs using static review AND execution artifacts.

A. Static review:
   - Symbol references, patch correctness, logic flaws, hardcoded secrets, injection risks.

B. Execution verification:
   - If the worker ran validation commands, inspect their stdout/stderr/returncode.
   - A FAILED build/test is a CRITICAL finding.
   - If no validation command was executed, mark that as a CRITICAL finding for verifiable tasks.

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


def code_critic_worker_node(state: dict) -> dict:
    """
    Code critic worker that audits coding worker outputs against repository symbol tables.
    """
    logger.info("Executing Code Critic Worker node...")
    
    # 1. Access current blackboard findings
    scratchpad = state.get("scratchpad", "")
    current_task = state.get("current_task", "")
    worker_outputs = state.get("worker_outputs", {})
    
    retry_count = state.get("critic_retry_count", 0)
    if retry_count > 2:
        retry_count = 2
    
    # Get coding worker's output
    coding_output = worker_outputs.get("coding_worker", "")
    if not coding_output:
        logger.warning("No coding worker output detected to critique. Skipping validation.")
        return {
            "worker_complete": {"code_critic_worker": True},
            "worker_outputs": {"code_critic_worker": "No coding specialist output was found to validate."},
            "worker_type": "code_critic_worker",
            "next_agent": "supervisor"
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
    if verification_artifacts:
        verification_context = "\n\n=== VERIFICATION ARTIFACTS ===\n" + "\n---\n".join(verification_artifacts[-3:])
    else:
        verification_context = "\n\n=== VERIFICATION ARTIFACTS ===\nNo validation commands were found in the coding worker output. If the task involved creating or modifying files, this is a CRITICAL gap."

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
        HumanMessage(content=f"Coding Specialist Task: {current_task}\n\nCoding Specialist Output:\n{coding_output}")
    ]
    
    is_invalid = False
    try:
        report: CriticReport = model.invoke(critic_prompt)
        
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
    else:
        updated_scratchpad = scratchpad + f"\n- [Code Critic]: Code validation report:\n{final_text}"
    
    state_update = {
        "messages": [AIMessage(content=final_text, name="code_critic_worker")],
        "scratchpad": updated_scratchpad,
        "worker_complete": {"code_critic_worker": True},
        "worker_outputs": {"code_critic_worker": final_text},
        "worker_type": "code_critic_worker",
        "next_agent": "supervisor",
        "active_project": state.get("active_project"),
        "created_files": state.get("created_files", []),
    }
    
    if is_invalid and retry_count < 2:
        logger.info(f"[CODE CRITIC WORKER] Critical issue detected! Forcing coding worker retry (retry {retry_count + 1}/2).")
        current_plan = state.get("plan", [])

        # Issue #2: Include specific critic findings in the retry task so the
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

        state_update["plan"] = current_plan + [f"FIX: {findings_text[:500]}"]
        state_update["current_task"] = f"CRITIC RETRY ({retry_count + 1}/2): Address these specific issues found by the code critic: {findings_text[:800]}"
        state_update["critic_retry_count"] = retry_count + 1
        state_update["next_agent"] = "coding_worker"
    else:
        # Issue #2: Reset retry count to prevent stale state from blocking future critic cycles
        state_update["critic_retry_count"] = 0
        
    return state_update
