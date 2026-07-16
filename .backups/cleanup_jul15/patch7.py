import os

filepath = r"c:\Users\vasan\Documents\Apphelix Intern\RAG\run_offline_pipeline.py"

with open(filepath, "r") as f:
    lines = f.readlines()

start_index = -1
end_index = -1

for i, line in enumerate(lines):
    if 'elif role == "architect_worker":' in line:
        start_index = i
    if 'elif role == "code_critic":' in line:
        end_index = i - 1
        break

if start_index != -1 and end_index != -1:
    new_block = """    elif role == "architect_worker":
        from src.agents.architect_worker import ArchitectureBlueprint
        from src.graph.supervisor import ProjectContextUpdate, PlanTaskInput
        
        if not hasattr(coding_worker_mock_instance, 'architect_calls'):
            coding_worker_mock_instance.architect_calls = 0
        coding_worker_mock_instance.architect_calls += 1
        
        if coding_worker_mock_instance.architect_calls == 1:
            mock_model.invoke.return_value = ArchitectureBlueprint(
                summary="Mock Plan",
                project_context=ProjectContextUpdate(active_project="smart_home"),
                tasks=[
                    PlanTaskInput(title="Research UI", domain="design"),
                    PlanTaskInput(title="Scaffold", domain="frontend"),
                    PlanTaskInput(title="Backend Logic", domain="backend")
                ],
                is_goal_completed=False
            )
        else:
            mock_model.invoke.return_value = ArchitectureBlueprint(
                summary="Goal Completed",
                project_context=ProjectContextUpdate(active_project="smart_home"),
                tasks=[],
                is_goal_completed=True
            )
            
        mock_model.with_structured_output.return_value = mock_model
"""
    
    new_lines = lines[:start_index] + [new_block] + lines[end_index+1:]
    
    with open(filepath, "w") as f:
        f.writelines(new_lines)
    print("Patched architect_worker mock successfully.")
else:
    print(f"Could not find blocks. start={start_index}, end={end_index}")
