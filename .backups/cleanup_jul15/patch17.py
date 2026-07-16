import os
import re

filepath = r"c:\Users\vasan\Documents\Apphelix Intern\RAG\run_offline_pipeline.py"
with open(filepath, "r") as f:
    content = f.read()

# Replace coding_worker in PredefinedSupervisor
content = content.replace(
    'next_agent="coding_worker",\n                current_task="Scaffold',
    'next_agent="frontend_worker",\n                current_task="Scaffold'
)
content = content.replace(
    'next_agent="coding_worker",\n                current_task="Create unit test cases',
    'next_agent="backend_worker",\n                current_task="Create unit test cases'
)
content = content.replace(
    'next_agent="coding_worker",\n                current_task="Create backend',
    'next_agent="backend_worker",\n                current_task="Create backend'
)
content = content.replace(
    'next_agent="coding_worker",\n                current_task="Create premium frontend controls',
    'next_agent="frontend_worker",\n                current_task="Create premium frontend controls'
)

with open(filepath, "w") as f:
    f.write(content)
print("Replaced coding_worker with frontend/backend_worker.")
