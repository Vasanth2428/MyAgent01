import os
import pytest
from src.graph.state_2pipeline import merge_created_files, create_initial_state
from src.graph.workflow import route_after_coding_worker
from src.core.blackboard_reference_store import compact_scratchpad
from src.agents.coding_worker import _enforce_final_response_format
from langchain_core.messages import HumanMessage


def test_merge_created_files_deduplicates_and_preserves_order():
    assert merge_created_files(["a", "b"], ["b", "c", "d"]) == ["a", "b", "c", "d"]
    assert merge_created_files([], ["x"]) == ["x"]
    assert merge_created_files(["a"], []) == ["a"]
    assert merge_created_files(None, ["x"]) == ["x"]
    assert merge_created_files(["a"], None) == ["a"]


def test_create_initial_state_has_created_files_and_active_project_none():
    state = create_initial_state([HumanMessage(content="hi")])
    assert state["created_files"] == []
    assert state["active_project"] is None


def test_route_after_coding_worker_sends_to_code_critic_when_not_approval():
    result = route_after_coding_worker({"waiting_for_approval": False})
    assert result == "code_critic_worker_node"


def test_route_after_coding_worker_sends_to_supervisor_when_approval():
    result = route_after_coding_worker({"waiting_for_approval": True})
    assert result == "supervisor_node"


def test_compact_scratchpad_preserves_code_context_and_compacts_old():
    lines = [
        "- [Worker]: Old irrelevant line 1",
        "- [Worker]: Old irrelevant line 2",
        "Error: Failed to compile src/App.jsx",
        "Success: Created file ./workspace/dashboard/src/App.tsx",
        "npm --prefix dashboard run build exited with status 0",
        "- [Coding Worker]: Verification passed",
    ]
    text = "\n".join(lines)
    # Use max_refs=4: should keep the 4 code-relevant lines and drop 2 irrelevant ones
    result = compact_scratchpad(text, max_refs=4)
    assert "Error: Failed to compile" in result
    assert "Success: Created file" in result
    assert "npm --prefix" in result
    assert "Old irrelevant line 1" not in result
    assert "Old irrelevant line 2" not in result


def test_enforce_final_response_format_adds_missing_headers():
    raw = "I created the React app and verified it builds successfully."
    result = _enforce_final_response_format(raw)
    assert "### SUMMARY" in result
    assert "### FILES CREATED" in result
    assert "### FILES MODIFIED" in result
    assert "### VERIFICATION RESULTS" in result
    assert "### NEXT STEPS" in result


def test_enforce_final_response_format_preserves_well_formed():
    raw = "### SUMMARY\nDone.\n### FILES CREATED\nx\n### FILES MODIFIED\nNone\n### VERIFICATION RESULTS\nPassed.\n### NEXT STEPS\nNone"
    result = _enforce_final_response_format(raw)
    assert result == raw

