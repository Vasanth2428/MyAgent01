from unittest.mock import Mock, patch

from langchain_core.messages import HumanMessage


def test_architect_preserves_completed_tasks_and_creates_contracts():
    from src.agents.architect_worker import architect_worker_node
    from src.graph.supervisor import PlanTaskInput, ProjectContextUpdate

    response = Mock(
        project_context=ProjectContextUpdate(goal="Build a dashboard"),
        tasks=[
            PlanTaskInput(
                title="Create dashboard API",
                domain="backend",
                acceptance_criteria=["Returns dashboard data"],
                verification_commands=["pytest"],
                expected_artifacts=["src/api/dashboard.py"],
            )
        ],
        summary="Blueprint complete",
    )
    model = Mock()
    model.invoke.return_value = response
    state = {
        "messages": [HumanMessage(content="Build a dashboard")],
        "project_context": {"name": "Existing project"},
        "plan": [{"id": "done", "title": "Scaffold", "status": "done", "fingerprint": "existing"}],
    }

    with patch("src.agents.architect_worker.get_architect_model", return_value=model):
        result = architect_worker_node(state)

    assert result["project_context"]["name"] == "Existing project"
    assert result["project_context"]["goal"] == "Build a dashboard"
    assert result["plan"][0]["id"] == "done"
    assert result["plan"][1]["acceptance_criteria"] == ["Returns dashboard data"]
    assert result["next_agent"] == "supervisor"
