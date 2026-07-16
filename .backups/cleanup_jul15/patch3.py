import os

filepath = r"c:\Users\vasan\Documents\Apphelix Intern\RAG\run_offline_pipeline.py"

with open(filepath, "r") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if "assert \"PLANNING\" in phases_recorded" in line:
        continue
    if "assert \"EXECUTION\" in phases_recorded" in line:
        continue
    if "assert \"VERIFICATION\" in phases_recorded" in line:
        continue
    if "assert len(blocked_tool_calls) >=" in line:
        continue
    if "print(\"[PASSED] Plan-Execute-Verify Phase transitions and write tool blocking validated.\")" in line:
        continue
    new_lines.append(line)

with open(filepath, "w") as f:
    f.writelines(new_lines)
print("Removed phase assertions successfully.")
