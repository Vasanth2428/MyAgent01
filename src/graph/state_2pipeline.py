# State schema for Tool-Calling Agent Architecture
from typing import List, Optional, Annotated, Dict
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage


def add_messages(left: List[BaseMessage], right: List[BaseMessage]) -> List[BaseMessage]:
    """Reducer that appends new messages to the existing list."""
    if left is None:
        left = []
    if right is None:
        right = []
    return left + right


# Lightweight state schema - minimal tracking, relies on message history
class AgentState(TypedDict):
    session_id: str
    messages: Annotated[List[BaseMessage], add_messages]
    next_agent: str
    current_task: str
    parallel_tasks: List[str]
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
    active_project: Optional[str]
    final_answer: str


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
        "active_project": None,
        "retry_counter": 0
    }
