import os

filepath = r"c:\Users\vasan\Documents\Apphelix Intern\RAG\run_offline_pipeline.py"
with open(filepath, "r") as f:
    content = f.read()

# Fix literal \n created by my patch
content = content.replace("\\n", "\n")

with open(filepath, "w") as f:
    f.write(content)
print("Fixed literal newlines.")
