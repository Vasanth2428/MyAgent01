import os
import pytest
from src.graph.state_2pipeline import merge_created_files, create_initial_state
from src.graph.workflow import route_after_coding_worker
from langchain_core.messages import HumanMessage


def test_merge_created_files_deduplicates_and_preserves_order():
    assert merge_created_files(["a", "b"], ["b", "c", "d"]) == ["a", "b", "c", "d"]
    assert merge_created_files([], ["x"]) == ["x"]
    assert merge_created_files(["a"], []) == ["a"]
    assert merge_created_files(None, ["x"]) == ["x"]
    assert merge_created_files(["a"], None) == ["a"]


def test_create_initial_state_has_created_files_and_active_project_none():
    from langchain_core.messages import HumanMessage
    state = create_initial_state([HumanMessage(content="hi")])
    assert state["created_files"] == []
    assert state["active_project"] is None


def test_route_after_coding_worker_sends_to_code_critic_when_not_approval():
    result = route_after_coding_worker({"waiting_for_approval": False})
    assert result == "code_critic_worker_node"


def test_route_after_coding_worker_sends_to_supervisor_when_approval():
    result = route_after_coding_worker({"waiting_for_approval": True})
    assert result == "supervisor_node"
