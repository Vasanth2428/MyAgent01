import os

filepath = r"c:\Users\vasan\Documents\Apphelix Intern\RAG\run_offline_pipeline.py"
with open(filepath, "r") as f:
    content = f.read()

content = content.replace("SupervisorDecision", "SupervisorRouting")
content = content.replace("plan=", "# plan=")

with open(filepath, "w") as f:
    f.write(content)
print("Replaced SupervisorDecision with SupervisorRouting.")
