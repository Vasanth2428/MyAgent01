import os

filepath = r"c:\Users\vasan\Documents\Apphelix Intern\RAG\run_offline_pipeline.py"

with open(filepath, "r") as f:
    lines = f.readlines()

start_index = -1
end_index = -1

for i, line in enumerate(lines):
    if 'elif "frontend" in task or "Scaffold" in task:' in line:
        start_index = i
    if 'supervisor_mock_instance = PredefinedSupervisor()' in line:
        end_index = i - 1
        break

if start_index != -1 and end_index != -1:
    new_block = """        elif "frontend" in task or "Scaffold" in task:
            modify_count = tool_calls_history.count("modify_files")
            compile_count = tool_calls_history.count("run_safe_commands")
            
            if "Scaffold" in task:
                if "scaffold_react_app" in tool_calls_history:
                    return AIMessage(content="Smart Home React application scaffolded successfully.", tool_calls=[{
                        "name": "run_safe_commands",
                        "args": {"command": "echo scaffolded"},
                        "id": "dummy_scaffold_fix"
                    }])
                return AIMessage(
                    content="I will scaffold the Smart Home React application.",
                    tool_calls=[{
                        "name": "scaffold_react_app",
                        "args": {"project_name": "smart_home"},
                        "id": "scaffold_smart_home"
                    }]
                )

            if modify_count == 0:
                app_jsx = (
                    "import React from 'react';\\n"
                    "import './App.css';\\n\\n"
                    "export default function App() {\\n"
                    "  return (\\n"
                    "    <div className='glass-dashboard'>\\n"
                    "      <h1 className='title'>Smart Home Panel</h1>\\n"
                    "    </div>\\n"
                    "  );\\n"
                    "}\\n"
                )
                app_css = (
                    "body {\\n"
                    "  font-family: 'Outfit', sans-serif;\\n"
                    "  background: #0d1117;\\n"
                    "}\\n"
                    ".glass-dashboard {\\n"
                    "  background: rgba(255, 255, 255, 0.05);\\n"
                    "  backdrop-filter: blur(10px);\\n"
                    "  border-radius: 12px;\\n"
                    "}\\n"
                )
                return AIMessage(
                    content="Creating frontend code.",
                    tool_calls=[
                        {
                            "name": "modify_files",
                            "args": {
                                "filepath": "smart_home/src/App.jsx",
                                "target_code": "",
                                "replacement_code": app_jsx
                            },
                            "id": "write_app_jsx"
                        },
                        {
                            "name": "modify_files",
                            "args": {
                                "filepath": "smart_home/src/App.css",
                                "target_code": "",
                                "replacement_code": app_css
                            },
                            "id": "write_app_css"
                        }
                    ]
                )
            else:
                return AIMessage(content="Frontend layout complete.")
        else:
            return AIMessage(content="Task completed successfully.")

"""
    
    new_lines = lines[:start_index] + [new_block] + lines[end_index:]
    
    with open(filepath, "w") as f:
        f.writelines(new_lines)
    print("Patched successfully")
else:
    print(f"Could not find blocks. start={start_index}, end={end_index}")
