import os
import re

filepath = r"c:\Users\vasan\Documents\Apphelix Intern\RAG\run_offline_pipeline.py"

with open(filepath, "r") as f:
    content = f.read()

new_classes = """class PredefinedSupervisor:
    def __init__(self):
        self.call_count = 0

    def invoke(self, messages, *args, **kwargs):
        from src.graph.supervisor import SupervisorRouting
        self.call_count += 1
        print(f"[MOCK SUPERVISOR] invoke count: {self.call_count}")
        
        if self.call_count == 1:
            return SupervisorRouting(
                next_agent="web_worker",
                current_task="Search for premium smart home dashboard UX/UI design trends and layout guidelines"
            )
        elif self.call_count == 2:
            return SupervisorRouting(
                next_agent="scraper_worker",
                current_task="Scrape energy saving statistics from https://example.com/smarthome"
            )
        elif self.call_count == 3:
            return SupervisorRouting(
                next_agent="frontend_worker",
                current_task="Scaffold the React application named 'smart_home' in `./workspace`"
            )
        elif self.call_count == 4:
            return SupervisorRouting(
                next_agent="backend_worker",
                current_task="Create unit test cases for backend device manager in `smart_home/backend/test_main.py` using pytest"
            )
        elif self.call_count == 5:
            return SupervisorRouting(
                next_agent="backend_worker",
                current_task="Create backend device manager main.py under `smart_home/backend/` using SQLite and verify it using pytest"
            )
        elif self.call_count == 6:
            return SupervisorRouting(
                next_agent="code_critic_worker",
                current_task="Review backend code syntax and design completeness for `smart_home/backend/main.py` and its test suite"
            )
        elif self.call_count == 7:
            return SupervisorRouting(
                next_agent="frontend_worker",
                current_task="Create premium frontend controls in `smart_home/src/App.jsx` and styling in `smart_home/src/App.css` using glassmorphism"
            )
        elif self.call_count == 8:
            return SupervisorRouting(
                next_agent="critic_worker",
                current_task="Audit final smart home codebase layout and design aesthetics integration"
            )
        else:
            return SupervisorRouting(
                next_agent="synthesizer",
                current_task=""
            )


class PredefinedCodingWorker:
    def invoke(self, messages, *args, **kwargs):
        task = ""
        # Get the very first HumanMessage as the main task
        for m in messages:
            if hasattr(m, 'content') and isinstance(m.content, str) and "SystemMessage" not in str(type(m)) and "AIMessage" not in str(type(m)) and "ToolMessage" not in str(type(m)):
                if "Scaffold" in m.content or "backend" in m.content or "main.py" in m.content or "unit test" in m.content or "test cases" in m.content or "frontend" in m.content or "Review backend code syntax" in m.content:
                    task = m.content.split("\\n\\nBlackboard Findings:")[0]
                    break
        
        system_prompts = [m.content for m in messages if hasattr(m, 'content') and "SystemMessage" in str(type(m))]
        
        phases_recorded.append("PLANNING")
        phases_recorded.append("EXECUTION")
        phases_recorded.append("VERIFICATION")
        phases_recorded.append("RAG_RULES_INJECTED")
        
        tool_calls_history = []
        for m in messages:
            if hasattr(m, 'tool_calls') and getattr(m, 'tool_calls'):
                tool_calls_history.extend([tc["name"] for tc in m.tool_calls])

        if "Scaffold" in task:
            if "scaffold_react_app" in tool_calls_history:
                return AIMessage(content="Smart Home React application scaffolded successfully.", tool_calls=[{
                    "name": "run_safe_commands",
                    "args": {"command": "echo scaffolded"},
                    "id": "dummy_scaffold_fix"
                }])
            return AIMessage(
                content="I will scaffold the Smart Home React application.",
                tool_calls=[
                    {
                        "name": "scaffold_react_app",
                        "args": {"project_name": "smart_home"},
                        "id": "scaffold_smart_home"
                    },
                    {
                        "name": "run_safe_commands",
                        "args": {"command": "echo scaffolding"},
                        "id": "dummy_scaffold_fix_1"
                    }
                ]
            )
            
        elif "Review backend code syntax" in task:
            return AIMessage(content="Backend logic is complete and fully reviewed.", tool_calls=[{
                "name": "run_safe_commands",
                "args": {"command": "echo reviewing"},
                "id": "dummy_review_fix"
            }])

        elif "unit test" in task or "test cases" in task:
            create_count = tool_calls_history.count("create_files")
            compile_count = tool_calls_history.count("run_safe_commands")
            
            if create_count < 1:
                return AIMessage(
                    content="Writing test_main.py backend test cases.",
                    tool_calls=[{
                        "name": "create_files",
                        "args": {
                            "filepath": "smart_home/backend/test_main.py",
                            "content": (
                                "from fastapi.testclient import TestClient\\n"
                                "from smart_home.backend.main import app\\n\\n"
                                "client = TestClient(app)\\n\\n"
                                "def test_read_devices():\\n"
                                "    response = client.get('/api/devices')\\n"
                                "    assert response.status_code == 200\\n"
                                "    assert len(response.json()) > 0\\n"
                            )
                        },
                        "id": "write_test_main"
                    }]
                )
            elif compile_count == 0:
                return AIMessage(
                    content="Running pytest on the test suite to verify initial status.",
                    tool_calls=[{
                        "name": "run_safe_commands",
                        "args": {"command": "pytest smart_home/backend/test_main.py"},
                        "id": "run_pytest_test_suite"
                    }]
                )
            else:
                return AIMessage(content="Backend unit tests have been written and verified.", tool_calls=[{
                    "name": "run_safe_commands",
                    "args": {"command": "echo done"},
                    "id": "dummy_done_fix"
                }])

        elif "backend" in task or "main.py" in task:
            create_count = tool_calls_history.count("create_files")
            compile_count = tool_calls_history.count("run_safe_commands")
            
            if create_count < 1:
                bad_code = (
                    "from fastapi import FastAPI\\n"
                    "app = FastAPI()\\n\\n"
                    "@app.get('/api/devices')\\n"
                    "def get_devices(\\n"  # Syntax error (unclosed parenthesis)
                    "    return [{'id': 1, 'name': 'Thermostat', 'status': 'on'}]\\n"
                )
                return AIMessage(
                    content="Writing smart home backend logic.",
                    tool_calls=[{
                        "name": "create_files",
                        "args": {
                            "filepath": "smart_home/backend/main.py",
                            "content": bad_code
                        },
                        "id": "write_bad_backend"
                    }]
                )
            elif create_count < 2:
                good_code = (
                    "from fastapi import FastAPI\\n"
                    "app = FastAPI()\\n\\n"
                    "@app.get('/api/devices')\\n"
                    "def get_devices():\\n"
                    "    return [{'id': 1, 'name': 'Thermostat', 'status': 'on'}]\\n"
                )
                return AIMessage(
                    content="I see the syntax validation error. Let me write it with corrected syntax.",
                    tool_calls=[{
                        "name": "create_files",
                        "args": {
                            "filepath": "smart_home/backend/main.py",
                            "content": good_code
                        },
                        "id": "write_good_backend"
                    }]
                )
            elif compile_count == 0:
                return AIMessage(
                    content="Verifying syntax of main.py using compiler.",
                    tool_calls=[{
                        "name": "run_safe_commands",
                        "args": {"command": "python -m py_compile smart_home/backend/main.py"},
                        "id": "run_compile_good"
                    }]
                )
            elif compile_count == 1:
                return AIMessage(
                    content="Running pytest to verify code against test cases.",
                    tool_calls=[{
                        "name": "run_safe_commands",
                        "args": {"command": "pytest smart_home/backend/test_main.py"},
                        "id": "run_pytest_verify"
                    }]
                )
            else:
                return AIMessage(content="Backend logic is complete and successfully verified.", tool_calls=[{
                    "name": "run_safe_commands",
                    "args": {"command": "echo backend done"},
                    "id": "dummy_backend_done"
                }])

        elif "frontend" in task:
            modify_count = tool_calls_history.count("modify_files")
            
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
                return AIMessage(content="Frontend layout complete.", tool_calls=[{
                    "name": "run_safe_commands",
                    "args": {"command": "echo frontend done"},
                    "id": "dummy_frontend_done"
                }])
        else:
            return AIMessage(content="Task completed successfully.", tool_calls=[{
                "name": "run_safe_commands",
                "args": {"command": "echo fallback"},
                "id": "dummy_fallback"
            }])
"""

# Now find the first "    def invoke(self, messages, *args, **kwargs):" in the file
# and replace everything up to "supervisor_mock_instance = PredefinedSupervisor()"

lines = content.split('\\n')
start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    # Find the START of where we messed up.
    # It might just be '    def invoke(self, messages, *args, **kwargs):'
    if '    def invoke(self, messages, *args, **kwargs):' in line and start_idx == -1:
        start_idx = i
    if 'supervisor_mock_instance = PredefinedSupervisor()' in line:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    # the replacement string is new_classes
    new_content = "\\n".join(lines[:start_idx]) + "\\n" + new_classes + "\\n" + "\\n".join(lines[end_idx:])
    with open(filepath, "w") as f:
        f.write(new_content)
    print("Replaced both classes correctly this time.")
else:
    print(f"Could not find indices. start={start_idx}, end={end_idx}")
