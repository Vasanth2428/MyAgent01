import os

filepath = r"c:\Users\vasan\Documents\Apphelix Intern\RAG\run_offline_pipeline.py"

with open(filepath, "r") as f:
    content = f.read()

# Find the tasks list in architect_worker mock and replace it with an empty list
import re
new_content = re.sub(
    r'tasks=\[\s*PlanTaskInput[^\]]+\]',
    'tasks=[]',
    content
)

with open(filepath, "w") as f:
    f.write(new_content)

print("Patched architect_worker tasks to empty list.")
