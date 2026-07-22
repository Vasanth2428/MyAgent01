# State schema for Tool-Calling Agent Architecture
from typing import List, Optional, Annotated, Dict, Any
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage


def add_messages(left: List[BaseMessage], right: List[BaseMessage]) -> List[BaseMessage]:
    """Reducer that appends new messages to the existing list, trimming older ones to prevent token exhaustion."""
    if left is None:
        left = []
    if right is None:
        right = []
    
    combined = left + right
    MAX_MESSAGES = 40
    
    if len(combined) > MAX_MESSAGES:
        start_idx = len(combined) - MAX_MESSAGES
        # Ensure we don't sever a ToolMessage from its initiating AIMessage
        from langchain_core.messages import ToolMessage, SystemMessage
        while start_idx > 0 and isinstance(combined[start_idx], ToolMessage):
            start_idx -= 1
            
        truncated_count = start_idx
        retained_messages = combined[start_idx:]
        
        # Inject a context marker for the LLM
        if truncated_count > 0:
            marker = SystemMessage(content=f"[SYSTEM] {truncated_count} older messages were archived to preserve context window.")
            return [marker] + retained_messages
            
        return retained_messages
        
    return combined

def update_next_agent(left: str, right: str) -> str:
    """Reducer for next_agent."""
    return right if right else left

def merge_dicts(left: dict, right: dict) -> dict:
    """Reducer that merges dictionaries, or clears if __CLEAR__ flag is present."""
    if right is None:
        return left if left else {}
    if right.get("__CLEAR__"):
        return {}
    if left is None:
        return right.copy()
    merged = left.copy()
    merged.update(right)
    return merged

def extend_list(left: list, right: list) -> list:
    """Reducer that safely concatenates two lists."""
    return (left or []) + (right or [])

# Lightweight state schema - minimal tracking, relies on message history
class AgentState(TypedDict):
    session_id: str
    messages: Annotated[List[BaseMessage], add_messages]
    next_agent: Annotated[str, update_next_agent]
    current_task: str
    parallel_tasks: Annotated[List[Dict[str, str]], extend_list]
    steps_remaining: int
    plan: List[str]
    retry_counter: int
    critic_retry_count: int
    
    # Context Awareness (IDE metadata)
    active_documents: List[str]
    cursor_position: Dict[str, int]
    
    # HITL security - programmatic interrupts
    waiting_for_approval: bool
    approval_requested: Optional[str]
    approval_filepath: str
    approval_decision: Optional[str]
    approval_tool: Optional[str]
    
    # Coding worker state
    coding_worker_messages: Optional[List[BaseMessage]]
    coding_worker_step: Optional[int]
    coding_worker_tool_calls_count: Optional[int]
    coding_worker_resume_tool_result: Optional[str]
    coding_worker_resume_tool_call_id: Optional[str]
    
    bypass_hitl: Optional[bool]
    patch_is_verified: bool
    final_answer: str
    
    # Missing fields for worker coordination
    worker_outputs: Annotated[dict, merge_dicts]
    worker_complete: dict
    worker_type: str
    scratchpad: str
    scratchpad_references: List[str]
    worker_output_ids: dict
    worker_output_summaries: dict
    task_hashes: List[str]
    file_status_flags: dict
    pending_file_approvals: dict
    created_files: List[str]
    code_modified: bool

    # Durable workflow records. These are checkpointed with the graph state and
    # deliberately kept separate from the ephemeral scratchpad.
    project_context: Dict[str, Any]
    task_history: Annotated[List[Dict[str, Any]], extend_list]
    task_events: Annotated[List[Dict[str, Any]], extend_list]
    critic_feedback: Dict[str, Any]
    current_task_id: Optional[str]
    current_task_domain: str
    last_validated_task_id: Optional[str]


def create_initial_state(messages: List[BaseMessage], bypass_hitl: bool = False) -> dict:
    """Helper factory to construct the default AgentState dict consistently."""
    return {
        "session_id": "",
        "messages": messages,
        "next_agent": "supervisor",
        "steps_remaining": 10,
        "final_answer": "",
        "plan": [],
        "current_task": "",
        "parallel_tasks": [],
        "active_documents": [],
        "cursor_position": {},
        "critic_retry_count": 0,
        "waiting_for_approval": False,
        "approval_requested": None,
        "approval_filepath": "",
        "approval_tool": "",
        "approval_decision": "",
        "bypass_hitl": bypass_hitl,
        "coding_worker_messages": [],
        "coding_worker_step": 0,
        "coding_worker_tool_calls_count": 0,
        "coding_worker_resume_tool_result": None,
        "coding_worker_resume_tool_call_id": None,
        "patch_is_verified": False,
        "retry_counter": 0,
        "worker_outputs": {},
        "worker_complete": {},
        "worker_type": "",
        "scratchpad": "",
        "scratchpad_references": [],
        "worker_output_ids": {},
        "worker_output_summaries": {},
        "task_hashes": [],
        "file_status_flags": {},
        "pending_file_approvals": {},
        "created_files": [],
        "code_modified": False,
        "project_context": {},
        "task_history": [],
        "task_events": [],
        "critic_feedback": {},
        "current_task_id": None,
        "current_task_domain": "unknown",
        "last_validated_task_id": None,
    }
