import os
import pytest
from src.tools.coding_tools import (
    read_files,
    search_code,
    create_files,
    modify_files,
    list_files,
    run_safe_commands,
    _is_safe_path,
    WORKSPACE_ROOT
)

TEST_FILE = "temp_test_file.txt"
TEST_ABS_PATH = os.path.join(WORKSPACE_ROOT, TEST_FILE)
TEST_CONTENT = """# Mock test file
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
"""

@pytest.fixture(autouse=True)
def setup_and_teardown():
    # Setup: Create a temporary test file in the workspace folder
    os.makedirs(WORKSPACE_ROOT, exist_ok=True)
    with open(TEST_ABS_PATH, "w", encoding="utf-8") as f:
        f.write(TEST_CONTENT)
    yield
    # Teardown: Remove the file if it exists
    if os.path.exists(TEST_ABS_PATH):
        os.remove(TEST_ABS_PATH)


def test_is_safe_path():
    assert _is_safe_path("temp_test_file.txt") is True
    assert _is_safe_path("../src/tools/coding_tools.py") is False  # outside workspace
    # Test path traversal containment
    assert _is_safe_path("../outside_workspace.txt") is False
    assert _is_safe_path("dir/../../passwd") is False
    assert _is_safe_path("etc/passwd") is True  # relative path is fine since it resolves to ./workspace/etc/passwd
    assert _is_safe_path("/etc/passwd") is False  # absolute path traversal /etc/ is blocked
    assert _is_safe_path("/") is False  # root blocked
    assert _is_safe_path("/usr") is False
    assert _is_safe_path("/root") is False
    assert _is_safe_path("/var") is False


def test_read_files():
    res = read_files(TEST_FILE, start_line=2, end_line=3)
    assert "def add(a, b):" in res
    assert "return a + b" in res
    assert "subtract" not in res
    
    pass


def test_search_code():
    res = search_code("def subtract")
    assert TEST_FILE in res
    assert "subtract" in res


def test_create_and_modify_files():
    # Test create_files
    new_file = "new_created_file.txt"
    new_abs_path = os.path.join(WORKSPACE_ROOT, new_file)
    try:
        res_create = create_files(new_file, "Line 1\nLine 2")
        assert "Success" in res_create
        assert os.path.exists(new_abs_path)
        
        # Test creating existing file fails
        res_fail = create_files(new_file, "Different content")
        assert "Error" in res_fail
        
        # Test modify_files
        res_modify = modify_files(new_file, "Line 2", "Line 2 modified")
        assert "Success" in res_modify
        with open(new_abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "Line 2 modified" in content
        
        # Test modifying non-existent file fails
        res_mod_fail = modify_files("non_existent_file.txt", "target", "replacement")
        assert "Error" in res_mod_fail
    finally:
        if os.path.exists(new_abs_path):
            os.remove(new_abs_path)


def test_list_files():
    res = list_files(".")
    assert TEST_FILE in res
    assert "[FILE]" in res


def test_scaffold_react_app_allows_nested_project_name():
    from src.tools.coding_tools import scaffold_react_app

    project_name = "beezlebub/frontend"
    result = scaffold_react_app(project_name)

    assert "Scaffolded React application" in result
    project_dir = os.path.join(WORKSPACE_ROOT, project_name)
    assert os.path.isdir(os.path.join(project_dir, "src"))
    local_pkg = os.path.join(project_dir, "package.json")
    assert os.path.isfile(local_pkg)

    with open(local_pkg, "r", encoding="utf-8") as f:
        import json
        pkg = json.load(f)

    assert pkg["name"] == "frontend"

    # Cleanup
    import shutil
    shutil.rmtree(project_dir, ignore_errors=True)

