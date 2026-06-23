import os
import sys
import shutil
import time
from typing import Dict, List, Tuple
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from dotenv import load_dotenv

# Load active environment variables
load_dotenv("config/.env", override=True)

# Ensure workspace root is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Global logs for assertions
phases_recorded = []
blocked_tool_calls = []
syntax_corrections = []
synthesized_successfully = False

# Weaviate mock retriever output
mock_guidelines = [
    {
        "text": "MOCK_GUIDELINE_STRICT_CSS: Always use Outfit font, glassmorphic container layout, and HSL tailored themes for smart home dashboard visual hierarchy.",
        "source": "smart_home_guidelines.md"
    }
]

class PredefinedSupervisor:
    def __init__(self):
        self.call_count = 0
        
    def invoke(self, messages, *args, **kwargs):
        self.call_count += 1
        from src.graph.supervisor import SupervisorDecision
        print(f"[MOCK SUPERVISOR] invoke count: {self.call_count}")
        
        has_critic_retry = False
        for msg in messages:
            if "RETRY_REQUIRED" in getattr(msg, "content", ""):
                has_critic_retry = True
                break
                
        if has_critic_retry:
            # The critic failed and triggered rollback.
            # Assert that the modified files (like smart_home/backend/main.py) were rolled back / deleted!
            backend_main_file = os.path.realpath(os.path.join(os.path.dirname(__file__), "workspace", "smart_home", "backend", "main.py"))
            assert not os.path.exists(backend_main_file), "Assertion failed: Rollback did not delete modified file on validation failure!"
            print("[PASSED] Critique Rollback verified: modified file was successfully rolled back.")
            
            # Decrement call_count so that the future steps align!
            self.call_count -= 1
            return SupervisorDecision(
                plan=["Write backend", "Write frontend", "Review and Synthesize"],
                next_agent="coding_worker",
                current_task="Address specific issues found by the code critic: database table does not exist."
            )
            
        if self.call_count == 1:
            return SupervisorDecision(
                plan=["Research UI trends", "Scaffold smart_home app", "Write tests", "Write backend", "Write frontend", "Review and Synthesize"],
                next_agent="web_worker",
                current_task="Search for premium smart home dashboard UX/UI design trends and layout guidelines"
            )
        elif self.call_count == 2:
            return SupervisorDecision(
                plan=["Scaffold smart_home app", "Write tests", "Write backend", "Write frontend", "Review and Synthesize"],
                next_agent="scraper_worker",
                current_task="Scrape energy saving statistics from https://example.com/smarthome"
            )
        elif self.call_count == 3:
            return SupervisorDecision(
                plan=["Scaffold smart_home app", "Write tests", "Write backend", "Write frontend", "Review and Synthesize"],
                next_agent="coding_worker",
                current_task="Scaffold the React application named 'smart_home' in `./workspace`"
            )
        elif self.call_count == 4:
            return SupervisorDecision(
                plan=["Write tests", "Write backend", "Write frontend", "Review and Synthesize"],
                next_agent="coding_worker",
                current_task="Create unit test cases for backend device manager in `smart_home/backend/test_main.py` using pytest"
            )
        elif self.call_count == 5:
            return SupervisorDecision(
                plan=["Write backend", "Write frontend", "Review and Synthesize"],
                next_agent="coding_worker",
                current_task="Create backend device manager main.py under `smart_home/backend/` using SQLite and verify it using pytest on `smart_home/backend/test_main.py`"
            )
        elif self.call_count == 6:
            return SupervisorDecision(
                plan=["Write frontend", "Review and Synthesize"],
                next_agent="code_critic_worker",
                current_task="Review backend code syntax and design completeness for `smart_home/backend/main.py` and its test suite"
            )
        elif self.call_count == 7:
            return SupervisorDecision(
                plan=["Write frontend", "Review and Synthesize"],
                next_agent="coding_worker",
                current_task="Create premium frontend controls in `smart_home/src/App.jsx` and styling in `smart_home/src/App.css` using glassmorphism"
            )
        elif self.call_count == 8:
            return SupervisorDecision(
                plan=["Review and Synthesize"],
                next_agent="critic_worker",
                current_task="Audit final smart home codebase layout and design aesthetics integration"
            )
        else:
            return SupervisorDecision(
                plan=[],
                next_agent="synthesizer",
                current_task=""
            )


class PredefinedCodingWorker:
    def invoke(self, messages, *args, **kwargs):
        task = ""
        for m in reversed(messages):
            if isinstance(m, HumanMessage):
                task = m.content.split("\n\nBlackboard Findings:")[0]
                break
        
        system_prompts = [m.content for m in messages if isinstance(m, SystemMessage)]
        
        current_phase = "PLANNING"
        for p in system_prompts:
            if "=== PHASE 2: EXECUTION ===" in p:
                current_phase = "EXECUTION"
            elif "=== PHASE 3: VERIFICATION ===" in p or "=== MANDATORY VERIFICATION REQUIRED ===" in p:
                current_phase = "VERIFICATION"
        
        phases_recorded.append(current_phase)
        
        has_rag_rules = any("MOCK_GUIDELINE_STRICT_CSS" in p for p in system_prompts)
        if has_rag_rules:
            phases_recorded.append("RAG_RULES_INJECTED")

        tool_calls_history = []
        tool_results_history = []
        for m in messages:
            if isinstance(m, AIMessage) and m.tool_calls:
                tool_calls_history.extend([tc["name"] for tc in m.tool_calls])
            elif isinstance(m, ToolMessage):
                tool_results_history.append(m.content)

        print(f"[MOCK CODOCK WORKER] Task: '{task[:40]}...' | Phase: {current_phase} | Tool History: {tool_calls_history}")

        if "Scaffold" in task:
            if "scaffold_react_app" in tool_calls_history:
                return AIMessage(content="Smart Home React application scaffolded successfully.")
                
            return AIMessage(
                content="I will scaffold the Smart Home React application.",
                tool_calls=[{
                    "name": "scaffold_react_app",
                    "args": {"project_name": "smart_home"},
                    "id": "scaffold_smart_home"
                }]
            )
            
        elif "unit test" in task or "test cases" in task:
            create_count = tool_calls_history.count("create_files")
            compile_count = tool_calls_history.count("run_safe_commands")
            
            if current_phase == "PLANNING":
                blocked_tool_calls.append("PLANNING_WRITE_BLOCKED")
                return AIMessage(
                    content="I will try to create backend/test_main.py in PLANNING phase.",
                    tool_calls=[{
                        "name": "create_files",
                        "args": {
                            "filepath": "smart_home/backend/test_main.py",
                            "content": (
                                "from fastapi.testclient import TestClient\n"
                                "from smart_home.backend.main import app\n\n"
                                "client = TestClient(app)\n\n"
                                "def test_read_devices():\n"
                                "    response = client.get('/api/devices')\n"
                                "    assert response.status_code == 200\n"
                                "    assert len(response.json()) > 0\n"
                            )
                        },
                        "id": f"blocked_create_test_{len(tool_calls_history)}"
                    }]
                )
            elif current_phase in ("EXECUTION", "VERIFICATION"):
                if create_count < 3:  # 2 blocked in planning
                    return AIMessage(
                        content="Phase is EXECUTION. Writing test_main.py backend test cases.",
                        tool_calls=[{
                            "name": "create_files",
                            "args": {
                                "filepath": "smart_home/backend/test_main.py",
                                "content": (
                                    "from fastapi.testclient import TestClient\n"
                                    "from smart_home.backend.main import app\n\n"
                                    "client = TestClient(app)\n\n"
                                    "def test_read_devices():\n"
                                    "    response = client.get('/api/devices')\n"
                                    "    assert response.status_code == 200\n"
                                    "    assert len(response.json()) > 0\n"
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
                    return AIMessage(content="Backend unit tests have been written and verified.")

        elif "Address specific issues" in task or "CRITIC RETRY" in task:
            create_count = tool_calls_history.count("create_files")
            compile_count = tool_calls_history.count("run_safe_commands")
            
            if current_phase == "PLANNING":
                blocked_tool_calls.append("PLANNING_WRITE_BLOCKED")
                return AIMessage(
                    content="I will try to create backend/main.py in PLANNING phase.",
                    tool_calls=[{
                        "name": "create_files",
                        "args": {
                            "filepath": "smart_home/backend/main.py",
                            "content": "from fastapi import FastAPI\napp = FastAPI()"
                        },
                        "id": f"blocked_create_{len(tool_calls_history)}"
                    }]
                )
            elif current_phase in ("EXECUTION", "VERIFICATION"):
                if create_count < 3:
                    good_code = (
                        "from fastapi import FastAPI\n"
                        "app = FastAPI()\n\n"
                        "@app.get('/api/devices')\n"
                        "def get_devices():\n"
                        "    return [{'id': 1, 'name': 'Thermostat', 'status': 'on'}]\n"
                    )
                    return AIMessage(
                        content="Phase is EXECUTION. Writing good backend logic.",
                        tool_calls=[{
                            "name": "create_files",
                            "args": {
                                "filepath": "smart_home/backend/main.py",
                                "content": good_code
                            },
                            "id": "write_good_backend_retry"
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
                    return AIMessage(content="Backend logic is complete and successfully verified against unit tests.")

        elif "backend" in task or "main.py" in task:
            create_count = tool_calls_history.count("create_files")
            compile_count = tool_calls_history.count("run_safe_commands")
            
            if current_phase == "PLANNING":
                blocked_tool_calls.append("PLANNING_WRITE_BLOCKED")
                return AIMessage(
                    content="I will try to create backend/main.py in PLANNING phase.",
                    tool_calls=[{
                        "name": "create_files",
                        "args": {
                            "filepath": "smart_home/backend/main.py",
                            "content": "from fastapi import FastAPI\napp = FastAPI()"
                        },
                        "id": f"blocked_create_{len(tool_calls_history)}"
                    }]
                )
            elif current_phase in ("EXECUTION", "VERIFICATION"):
                if create_count < 3:  # 2 blocked in planning of this task
                    bad_code = (
                        "from fastapi import FastAPI\n"
                        "app = FastAPI()\n\n"
                        "@app.get('/api/devices')\n"
                        "def get_devices(\n"  # Syntax error (unclosed parenthesis)
                        "    return [{'id': 1, 'name': 'Thermostat', 'status': 'on'}]\n"
                    )
                    return AIMessage(
                        content="Phase is EXECUTION. Writing smart home backend logic.",
                        tool_calls=[{
                            "name": "create_files",
                            "args": {
                                "filepath": "smart_home/backend/main.py",
                                "content": bad_code
                            },
                            "id": "write_bad_backend"
                        }]
                    )
                elif create_count == 3 and not any("Success:" in res for res in tool_results_history if "write_bad_backend" in res or "write_good_backend" in res):
                    # Syntax error correction loop
                    syntax_corrections.append("PARSED_AND_CORRECTING_SYNTAX")
                    good_code = (
                        "from fastapi import FastAPI\n"
                        "app = FastAPI()\n\n"
                        "@app.get('/api/devices')\n"
                        "def get_devices():\n"  # Fixed
                        "    return [{'id': 1, 'name': 'Thermostat', 'status': 'on'}]\n"
                    )
                    return AIMessage(
                        content="I see the syntax validation error from create_files. Let me write it with corrected syntax.",
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
                    return AIMessage(content="Backend logic is complete and successfully verified against unit tests.")
                
        elif "frontend" in task:
            modify_count = tool_calls_history.count("modify_files")
            compile_count = tool_calls_history.count("run_safe_commands")
            
            if current_phase == "PLANNING":
                return AIMessage(content="I am planning the frontend component layout first.")
            elif current_phase == "EXECUTION":
                if modify_count == 0:
                    app_jsx = (
                        "import React from 'react';\n"
                        "import './App.css';\n\n"
                        "export default function App() {\n"
                        "  return (\n"
                        "    <div className='glass-dashboard'>\n"
                        "      <h1 className='title'>Smart Home Panel</h1>\n"
                        "    </div>\n"
                        "  );\n"
                        "}\n"
                    )
                    app_css = (
                        "body {\n"
                        "  font-family: 'Outfit', sans-serif;\n"
                        "  background: #0d1117;\n"
                        "}\n"
                        ".glass-dashboard {\n"
                        "  background: rgba(255, 255, 255, 0.05);\n"
                        "  backdrop-filter: blur(10px);\n"
                        "  border-radius: 12px;\n"
                        "}\n"
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
                elif compile_count == 3:  # 1 from test step, 2 from backend step
                    return AIMessage(
                        content="Verifying frontend build.",
                        tool_calls=[{
                            "name": "run_safe_commands",
                            "args": {"command": "npm run build --prefix smart_home"},
                            "id": "npm_build_check"
                        }]
                    )
                else:
                    return AIMessage(content="Frontend is verified.")
            elif current_phase == "VERIFICATION":
                return AIMessage(content="Frontend is verified and fully built.")
        else:
            return AIMessage(content="Task completed successfully.")

supervisor_mock_instance = PredefinedSupervisor()
coding_worker_mock_instance = PredefinedCodingWorker()
critic_call_count = 0

def mock_build_model_with_fallback(
    role: str,
    primary_model: str,
    fallback_model: str,
    *,
    temperature: float = 0,
    api_key_envs: tuple = (),
    tools: list = None,
    structured_output: type = None,
    **kwargs
):
    mock_model = MagicMock()
    print(f"[MOCK LLM] build_model_with_fallback invoked for role: {role}")
    
    if role == "supervisor":
        mock_model.invoke.side_effect = supervisor_mock_instance.invoke
    elif role == "coding_worker":
        mock_model.invoke.side_effect = coding_worker_mock_instance.invoke
    elif role in ("code_critic", "code_critic_worker"):
        from src.agents.code_critic_worker import CriticReport, CriticFinding
        
        global critic_call_count
        critic_call_count += 1
        
        if critic_call_count == 1:
            print("[MOCK LLM] Code critic returning validation failure (to test rollback/retry).")
            mock_model.invoke.return_value = CriticReport(
                valid=False,
                findings=[CriticFinding(
                    issue_type="hallucinated_symbol",
                    file_location="smart_home/backend/main.py",
                    details="The database file path should use sales.db.",
                    severity="critical"
                )],
                criticism_summary="Found critical symbol hallucination."
            )
        else:
            print("[MOCK LLM] Code critic returning validation success.")
            mock_model.invoke.return_value = CriticReport(
                valid=True,
                findings=[],
                criticism_summary="All code looks correct and fully validated."
            )
    elif role == "critic_worker":
        mock_model.invoke.return_value = AIMessage(
            content="Design audit: Typography and glassmorphic aesthetics are correctly integrated.",
            name="critic_worker"
        )
    elif role == "web_worker":
        mock_model.invoke.return_value = AIMessage(
            content="Search results show: Glassmorphism layout and Outfit/Inter fonts are premium smart home UI trends.",
            name="web_worker"
        )
    elif role == "scraper_worker":
        mock_model.invoke.return_value = AIMessage(
            content="Scraped info: Smart home energy trackers should use interactive toggles.",
            name="scraper_worker"
        )
    elif role == "synthesizer":
        global synthesized_successfully
        synthesized_successfully = True
        mock_model.invoke.return_value = AIMessage(
            content="Summary: Smart Home Automation Dashboard successfully created and validated. Backend uses FastAPI and SQLite. Frontend uses React and premium glassmorphic UI.",
            name="synthesizer"
        )
    else:
        mock_model.invoke.return_value = AIMessage(content="Mocked worker response.")
        
    return mock_model

# START PATCHER BEFORE IMPORTING THE WORKFLOW GRAPH
print("Starting global model patcher...")
patcher_model = patch("src.core.model_provider.build_model_with_fallback", side_effect=mock_build_model_with_fallback)
patcher_model.start()

# Now import workflow safely
from src.graph.workflow import build_multi_agent_graph, get_graph_config

def main():
    print("==============================================================")
    print("INITIALIZING RIGOROUS MULTI-AGENT OFFLINE INTEGRATION TEST")
    print("==============================================================")
    
    # 1. Clean up any existing smart_home directory under workspace
    workspace_smart_home = os.path.realpath(os.path.join(os.path.dirname(__file__), "workspace", "smart_home"))
    if os.path.exists(workspace_smart_home):
        print(f"Cleaning existing smart_home directory: {workspace_smart_home}")
        shutil.rmtree(workspace_smart_home)

    # 2. Setup checkpointer
    from src.graph.checkpointer import setup_checkpointer
    checkpointer = setup_checkpointer()
    graph = build_multi_agent_graph(checkpointer)
    
    config = get_graph_config(f"offline_smarthome_{int(time.time())}")
    
    query = "Create a premium Smart Home Automation Dashboard inside `./workspace` named 'smart_home'"
    initial_state = {
        "messages": [HumanMessage(content=query)],
        "next_agent": "supervisor",
        "steps_remaining": 20,
        "plan": [],
        "current_task": "",
        "worker_complete": {},
        "retry_counter": 0,
        "critic_retry_count": 0,
        "waiting_for_approval": False,
        "approval_filepath": "",
        "pending_file_approvals": {},
        "patch_is_verified": False,
        "active_project": "smart_home",
        "session_id": "offline_smarthome_session",
        "active_document_ids": [],
        "task_hashes": [],
        "file_status_flags": {},
        "worker_output_ids": {},
        "worker_output_summaries": {},
        "scratchpad_references": [],
        "scratchpad": "",
        "worker_outputs": {},
        "final_answer": "",
        "bypass_hitl": True # Bypass HITL for non-interactive runner
    }
    
    print("\nRunning Multi-Agent integration pipeline...")
    
    # Patch retriever to return custom guidelines for task query matching (Dynamic RAG rules injection)
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = (mock_guidelines, 0.0, 0.0)
    
    # Patch the run_safe_commands tool in coding_worker to mock Vite npm build execution offline
    from src.agents.coding_worker import tools_map
    original_run_safe = tools_map["run_safe_commands"]
    
    def mock_run_safe(args):
        command = args.get("command", "")
        if "npm run build" in command:
            return "[Command exited with status 0]\n✓ built in 150ms"
        if "pytest" in command:
            return "[Command exited with status 0]\n3 tests passed successfully."
        return original_run_safe.invoke(args)
        
    mock_run_safe_tool = MagicMock()
    mock_run_safe_tool.invoke.side_effect = mock_run_safe
    tools_map["run_safe_commands"] = mock_run_safe_tool
    
    # Mock take_webpage_screenshot to simulate visual verification offline
    original_screenshot = tools_map.get("take_webpage_screenshot")
    mock_screenshot_tool = MagicMock()
    mock_screenshot_tool.invoke.return_value = "Success: Screenshot captured and saved to 'screenshot.png'."
    tools_map["take_webpage_screenshot"] = mock_screenshot_tool
    
    with patch("src.agents.coding_worker.get_retrieval_service") as mock_get_service:
         
         # Mock retrieval service in coding worker
         mock_service = MagicMock()
         mock_service.retriever = mock_retriever
         mock_get_service.return_value = mock_service
         
         result = graph.invoke(initial_state, config=config)
         
    print("\n==============================================================")
    print("RUN COMPLETED. RUNNING DETAILED ASSERTIONS...")
    print("==============================================================")
    
    # 1. Assert file creation and content accuracy
    backend_test = os.path.join(workspace_smart_home, "backend", "test_main.py")
    assert os.path.exists(backend_test), "Assertion failed: smart_home/backend/test_main.py was not created!"
    print("[PASSED] backend/test_main.py file created successfully.")
    
    with open(backend_test, "r", encoding="utf-8") as f:
        test_content = f.read()
    assert "test_read_devices" in test_content, "Assertion failed: test_main.py does not contain test_read_devices case!"
    print("[PASSED] backend/test_main.py has correct unit test code (TDD verified).")

    backend_main = os.path.join(workspace_smart_home, "backend", "main.py")
    assert os.path.exists(backend_main), "Assertion failed: smart_home/backend/main.py was not created!"
    print("[PASSED] backend/main.py file created successfully.")
    
    with open(backend_main, "r", encoding="utf-8") as f:
        backend_content = f.read()
    
    assert "def get_devices():" in backend_content, "Assertion failed: main.py does not contain corrected parenthesis!"
    assert "def get_devices(\n" not in backend_content, "Assertion failed: main.py still contains syntax errors!"
    print("[PASSED] backend/main.py has correct syntax content (compiler self-correction verified).")
    
    frontend_jsx = os.path.join(workspace_smart_home, "src", "App.jsx")
    assert os.path.exists(frontend_jsx), "Assertion failed: smart_home/src/App.jsx was not created!"
    print("[PASSED] src/App.jsx file created successfully.")
    
    # 2. Assert Dynamic RAG rule injection occurred
    assert "RAG_RULES_INJECTED" in phases_recorded, "Assertion failed: Custom RAG rules were not injected into CODING_SYSTEM_PROMPT!"
    print("[PASSED] Weaviate RAG rule matching successfully retrieved and injected guidelines.")

    # 3. Assert Plan-Execute-Verify Phase State Machine
    assert "PLANNING" in phases_recorded, "Assertion failed: Coding worker did not start in PLANNING phase!"
    assert "EXECUTION" in phases_recorded, "Assertion failed: Coding worker did not transition to EXECUTION phase!"
    assert "VERIFICATION" in phases_recorded, "Assertion failed: Coding worker did not transition to VERIFICATION phase!"
    assert len(blocked_tool_calls) >= 2, "Assertion failed: Write tools were not blocked during the PLANNING phase!"
    print("[PASSED] Plan-Execute-Verify Phase transitions and write tool blocking validated.")

    # 4. Assert Pipeline routing completeness
    assert synthesized_successfully, "Assertion failed: Synthesizer was not executed to finalize output!"
    print("[PASSED] Multi-agent routing loop traversed all required workers and synthesized successfully.")
    
    # 5. Assert Whitespace-Tolerant Patch Matching
    print("\nVerifying whitespace-tolerant patch application...")
    from src.tools.patch_tools import apply_patch
    original_text = "def hello():\n    print(  'Hello World'  )\n    return True\n"
    patch_text = """--- a/hello.py
+++ b/hello.py
@@ -1,3 +1,3 @@
 def hello():
-    print( 'Hello World' )
+    print('Hello, Space!')
     return True
"""
    patched = apply_patch(original_text, patch_text)
    assert "print('Hello, Space!')" in patched, "Assertion failed: Whitespace-tolerant patch application failed!"
    print("[PASSED] Whitespace-tolerant patch application verified.")
    
    # Output final answer
    print("\nFinal Synthesized Answer:")
    print("-" * 50)
    print(result.get("final_answer", ""))
    print("-" * 50)
    print("\nALL OFFLINE RIGOROUS INTEGRATION ASSERTIONS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
