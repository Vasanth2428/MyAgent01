import os

filepath = r"c:\Users\vasan\Documents\Apphelix Intern\RAG\run_offline_pipeline.py"

with open(filepath, "r") as f:
    lines = f.readlines()

start_index = -1
end_index = -1

for i, line in enumerate(lines):
    if 'elif "unit test" in task or "test cases" in task:' in line:
        start_index = i
    if 'elif "frontend" in task or "Scaffold" in task:' in line:
        end_index = i
        break

if start_index != -1 and end_index != -1:
    new_block = """        elif "Review backend code syntax" in task:
            return AIMessage(content="Backend logic is complete and fully reviewed.")

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
                return AIMessage(content="Backend unit tests have been written and verified.")

        elif "backend" in task or "main.py" in task:
            create_count = tool_calls_history.count("create_files")
            compile_count = tool_calls_history.count("run_safe_commands")
            modify_count = tool_calls_history.count("modify_files")
            
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
            elif modify_count < 1:
                good_code = (
                    "def get_devices():\\n"
                )
                return AIMessage(
                    content="I see the syntax validation error. Let me write it with corrected syntax using modify_files.",
                    tool_calls=[{
                        "name": "modify_files",
                        "args": {
                            "filepath": "smart_home/backend/main.py",
                            "target_code": "def get_devices(\\n",
                            "replacement_code": good_code
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

"""
    
    new_lines = lines[:start_index] + [new_block] + lines[end_index:]
    
    with open(filepath, "w") as f:
        f.writelines(new_lines)
    print("Patched successfully")
else:
    print("Could not find blocks")
