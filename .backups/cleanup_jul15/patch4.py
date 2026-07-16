import os

filepath = r"c:\Users\vasan\Documents\Apphelix Intern\RAG\run_offline_pipeline.py"

with open(filepath, "r") as f:
    lines = f.readlines()

start_index = -1
end_index = -1

for i, line in enumerate(lines):
    if 'elif "backend" in task or "main.py" in task:' in line:
        start_index = i
    if 'elif "frontend" in task or "Scaffold" in task:' in line:
        end_index = i - 1
        break

if start_index != -1 and end_index != -1:
    new_block = """        elif "backend" in task or "main.py" in task:
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
                    content="I see the syntax validation error. Let me write it with corrected syntax using create_files again since it was never created.",
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

"""
    
    new_lines = lines[:start_index] + [new_block] + lines[end_index:]
    
    with open(filepath, "w") as f:
        f.writelines(new_lines)
    print("Patched successfully")
else:
    print(f"Could not find blocks. start={start_index}, end={end_index}")
