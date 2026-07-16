from unittest.mock import Mock, patch

from langchain_core.messages import AIMessage

from src.graph.supervisor import (
    PlanTask,
    ProjectContextUpdate,
    apply_post_worker_state_updates,
    build_task_instruction,
    get_next_pending_task,
)


def test_task_contract_is_included_in_worker_instruction():
    task = PlanTask(
        id="task_001",
        title="Create login form",
        domain="frontend",
        acceptance_criteria=["Shows validation errors", "Works on mobile"],
        verification_commands=["npm run test"],
        expected_artifacts=["src/components/LoginForm.tsx"],
        owned_paths=["src/components/LoginForm.tsx"],
    )

    instruction = build_task_instruction(task, "original")

    assert "Acceptance Criteria:\n- Shows validation errors\n- Works on mobile" in instruction
    assert "Verification Commands:\n- npm run test" in instruction
    assert "Expected Artifacts:\n- src/components/LoginForm.tsx" in instruction


def test_project_context_update_omits_unset_values():
    context = ProjectContextUpdate(active_project="frontend")

    assert context.model_dump(exclude_defaults=True) == {
        "active_project": "frontend"
    }


def test_dependency_and_attempt_limit_gate_task_selection():
    prerequisite = PlanTask(id="task_001", title="Create API", status="in_progress")
    dependent = PlanTask(id="task_002", title="Wire UI")
    exhausted = PlanTask(id="task_003", title="Broken task", attempt_count=3, max_attempts=3)

    assert get_next_pending_task([prerequisite, dependent]) == prerequisite
    exhausted.status = "needs_replan"
    assert exhausted.status == "needs_replan"


def test_validated_feedback_records_evidence_and_task_history():
    task = PlanTask(id="task_001", title="Build endpoint", status="in_progress")
    state = {
        "current_task_id": "task_001",
        "worker_complete": {"code_critic_worker": True},
        "worker_type": "code_critic_worker",
        "critic_feedback": {
            "status": "validated",
            "evidence": [{"source": "pytest", "details": "passed"}],
        },
    }

    plan, validated_id, history, events = apply_post_worker_state_updates(state, [task], [])

    assert plan[0].status == "validated"
    assert validated_id == "task_001"
    assert plan[0].evidence[0]["type"] == "critic_validation"
    assert plan[0].evidence[0]["worker"] == "code_critic_worker"


def test_code_critic_reads_specialist_output_not_only_legacy_worker_key():
    from src.agents.code_critic_worker import code_critic_worker_node

    report = Mock(valid=True, criticism_summary="Looks good", findings=[])
    model = Mock()
    model.invoke.return_value = report
    state = {
        "current_task": "Create page",
        "worker_outputs": {"frontend_worker": "### VERIFICATION RESULTS\nnpm run test passed"},
        "scratchpad": "",
        "active_project": "missing-project",
        "critic_retry_count": 0,
        "current_task_id": "task_001",
        "plan": [{"id": "task_001", "title": "Create page", "status": "in_progress"}],
    }

    with patch("src.agents.code_critic_worker.get_critic_model", return_value=model), patch(
        "src.agents.coding_worker.get_retrieval_service", side_effect=RuntimeError("not needed")
    ):
        result = code_critic_worker_node(state)

    assert result["critic_feedback"]["status"] == "validated"
    assert result["critic_feedback"]["target_worker"] == "frontend_worker"
    assert result["plan"][0]["status"] == "in_progress"
