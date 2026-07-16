import os
import re

filepath = r"c:\Users\vasan\Documents\Apphelix Intern\RAG\run_offline_pipeline.py"
with open(filepath, "r") as f:
    content = f.read()

old_mock = """    else:
        mock_model.invoke.return_value = AIMessage(content="Mocked worker response.")
        
    return mock_model"""

new_mock = """    elif role == "code_critic":
        from src.agents.code_critic_worker import CriticReport
        mock_model.invoke.return_value = CriticReport(
            valid=True,
            findings=[],
            criticism_summary="Mock code critic review passed."
        )
        mock_model.with_structured_output.return_value = mock_model
    elif role == "critic_worker":
        from src.agents.critic_worker import QualityReport
        mock_model.invoke.return_value = QualityReport(
            valid=True,
            quality_score=100,
            feedback_summary="Mock critic review passed.",
            blocking_issues=[]
        )
        mock_model.with_structured_output.return_value = mock_model
    else:
        mock_model.invoke.return_value = AIMessage(content="Mocked worker response.")
        
    return mock_model"""

if old_mock in content:
    content = content.replace(old_mock, new_mock)
    with open(filepath, "w") as f:
        f.write(content)
    print("Patch 18 applied successfully!")
else:
    print("Could not find the target string in run_offline_pipeline.py")
