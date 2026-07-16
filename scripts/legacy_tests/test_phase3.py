import json
import os
import shutil

# Mocking the execute_command function to bypass real subprocess execution for the test
def mock_execute_command(cmd, wait_ms_before_async=15000):
    return f"MOCK RESULT FOR {cmd}"

def test_phase3_logic(workspace_dir):
    auto_ci_artifacts = []
    if os.path.exists(workspace_dir):
        pkg_json_path = os.path.join(workspace_dir, "package.json")
        if os.path.exists(pkg_json_path):
            try:
                with open(pkg_json_path, 'r', encoding='utf-8') as f:
                    pkg_data = json.load(f)
                
                # EDGE CASE FIX: Ensure scripts is a dictionary
                scripts = pkg_data.get("scripts", {}) if isinstance(pkg_data, dict) else {}
                if not isinstance(scripts, dict):
                    scripts = {}
                    
                # Look for common CI validation gates
                for target_script in ["lint", "test", "build"]:
                    if target_script in scripts:
                        print(f"[HEADLESS CRITIC] Auto-discovered '{target_script}' script. Executing CI gate...")
                        ci_result = mock_execute_command(f"npm run {target_script}", wait_ms_before_async=15000)
                        auto_ci_artifacts.append(f"--- AUTO CI RUN: npm run {target_script} ---\n{ci_result}")
                        
            except Exception as e:
                print(f"Failed to parse package.json for auto-CI: {e}")
        elif os.path.exists(os.path.join(workspace_dir, "pytest.ini")) or os.path.exists(os.path.join(workspace_dir, "requirements.txt")):
            print("[HEADLESS CRITIC] Auto-discovered Python project. Executing pytest CI gate...")
            ci_result = mock_execute_command("pytest", wait_ms_before_async=15000)
            auto_ci_artifacts.append(f"--- AUTO CI RUN: pytest ---\n{ci_result}")
            
    return auto_ci_artifacts

def setup_workspace(content=None, filename="package.json"):
    ws_dir = "./mock_workspace"
    os.makedirs(ws_dir, exist_ok=True)
    if content is not None:
        with open(os.path.join(ws_dir, filename), "w") as f:
            f.write(content)
    return ws_dir

def teardown_workspace():
    if os.path.exists("./mock_workspace"):
        shutil.rmtree("./mock_workspace")

print("--- Testing Phase 3 Edge Cases ---")

# Edge Case 1: Null scripts object
print("\nTest 1: null scripts object")
ws = setup_workspace('{"scripts": null}')
res = test_phase3_logic(ws)
print(f"Result length: {len(res)}")
teardown_workspace()

# Edge Case 2: package.json is an array instead of dict
print("\nTest 2: package.json is an array")
ws = setup_workspace('[{"scripts": {"test": "echo test"}}]')
res = test_phase3_logic(ws)
print(f"Result length: {len(res)}")
teardown_workspace()

# Edge Case 3: Invalid JSON syntax
print("\nTest 3: Invalid JSON syntax")
ws = setup_workspace('{scripts: {"test": "echo test"}"')
res = test_phase3_logic(ws)
print(f"Result length: {len(res)}")
teardown_workspace()

# Edge Case 4: No scripts, fallback to pytest
print("\nTest 4: Python project fallback")
ws = setup_workspace("pytest_args=-v", "pytest.ini")
res = test_phase3_logic(ws)
print(res)
teardown_workspace()

print("\nTests Complete!")
