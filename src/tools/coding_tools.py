import os
import subprocess
import logging
import shlex
import time
import psutil
import re
import tempfile
from typing import List, Optional, Tuple

logger = logging.getLogger("MultiAgent.CodingTools")

PROJECT_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
WORKSPACE_ROOT = os.path.realpath(os.path.join(PROJECT_ROOT, "workspace"))

if not os.path.exists(WORKSPACE_ROOT):
    try:
        os.makedirs(WORKSPACE_ROOT, exist_ok=True)
        logger.info(f"Created workspace root directory at '{WORKSPACE_ROOT}'")
    except Exception as e:
        logger.error(f"Failed to create workspace root directory: {e}")

ALLOWED_EXTENSIONS = {".html", ".css", ".js", ".ts", ".jsx", ".tsx", ".json", ".md", ".txt", ".py"}

FORBIDDEN_PATH_FRAGMENTS = {"/", "/etc", "/root", "/usr", "/var", "../"}

ALLOWED_COMMANDS = [
    "python -m py_compile",
    "python -m http.server",
    "pytest",
    "npm run lint",
    "npm run test",
    "npm run build",
    "git diff"
]


_active_project: str = ""

def set_active_project(project_name: str) -> None:
    """Sets the active project subdirectory name to programmatically restrict file writes."""
    global _active_project
    _active_project = project_name


def sanitize_file_content_for_llm(content: str) -> str:
    """Sanitize read file content to prevent prompt injections."""
    dangerous_phrases = [
        "system note", "system message", "system prompt", "ignore previous instructions",
        "ignore the instructions", "new instructions", "override rules", "jailbreak",
        "developer mode", "do not follow", "you must print", "reveal prompt",
        "secret key", "api key", "password", "token"
    ]
    sanitized = content
    for phrase in dangerous_phrases:
        sanitized = re.sub(re.escape(phrase), "[REDACTED_SECURE]", sanitized, flags=re.IGNORECASE)
    return sanitized


def _is_safe_path(filepath: str) -> bool:
    """Check if filepath is safe (within workspace root and doesn't contain forbidden paths)."""
    if not filepath or not filepath.strip():
        return False
        
    norm_path = filepath.replace("\\", "/")
    forbidden_prefixes = ("/", "/etc", "/root", "/usr", "/var", "..")
    if any(norm_path.startswith(p) for p in forbidden_prefixes) or "../" in norm_path:
        return False
        
    # Programmatic active project boundary enforcement
    global _active_project
    if _active_project:
        clean_path = norm_path
        while clean_path.startswith("./"):
            clean_path = clean_path[2:]
        if clean_path.startswith("workspace/"):
            clean_path = clean_path[len("workspace/"):]
        while clean_path.startswith("./"):
            clean_path = clean_path[2:]
            
        allowed_root_configs = {"vite.config.js", "package.json"}
        if clean_path not in allowed_root_configs:
            if not (clean_path == _active_project or clean_path.startswith(_active_project + "/") or clean_path.startswith(_active_project + "_")):
                return False
        
    real_workspace = os.path.realpath(WORKSPACE_ROOT)
    abs_path = os.path.realpath(os.path.join(WORKSPACE_ROOT, filepath))
    
    if not abs_path.lower().startswith(real_workspace.lower()):
        return False
            
    rel_path = os.path.relpath(abs_path, WORKSPACE_ROOT)
    normalized_rel = rel_path.replace("\\", "/").lower()
    
    if normalized_rel == "package.json":
        return False
        
    if normalized_rel == ".." or normalized_rel.startswith("../") or ".." in normalized_rel:
        return False
        
    abs_path_norm = abs_path.replace("\\", "/").lower()
    system_forbidden = ["/etc", "/root", "/usr", "/var"]
    for sys_p in system_forbidden:
        if abs_path_norm == sys_p or abs_path_norm.startswith(sys_p + "/"):
            return False
            
    if re.match(r"^[a-zA-Z]:/(etc|root|usr|var)(/|$)", abs_path_norm):
        return False
        
    return True


def _has_allowed_extension(filepath: str) -> bool:
    """Check if the file has an approved extension."""
    _, ext = os.path.splitext(filepath)
    return ext.lower() in ALLOWED_EXTENSIONS


def _get_absolute_path(filepath: str) -> str:
    """Get absolute path to a file in the `./workspace` folder."""
    p = filepath.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if p.startswith("workspace/"):
        p = p[len("workspace/"):]
    while p.startswith("./"):
        p = p[2:]
    return os.path.realpath(os.path.join(WORKSPACE_ROOT, p))


def view_code_file(filepath: str, start_line: int = 1, end_line: int = 100) -> str:
    """Safely view a range of lines inside a file in `./workspace`."""
    if not _is_safe_path(filepath):
        return f"Error: Access denied. Filepath '{filepath}' violates safety or path policies."
        
    if not _has_allowed_extension(filepath):
        return f"Error: Access denied. File extension not allowed. Approved extensions: {', '.join(ALLOWED_EXTENSIONS)}"
    
    abs_path = _get_absolute_path(filepath)
    if not os.path.isfile(abs_path):
        return f"Error: File '{filepath}' does not exist."
    
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        start_idx = max(0, start_line - 1)
        end_idx = min(total_lines, end_line)
        
        output = []
        for i in range(start_idx, end_idx):
            output.append(f"{i + 1}: {lines[i]}")
            
        header = f"--- Viewing {filepath} (Lines {start_line}-{end_line} of {total_lines}) ---\n"
        return sanitize_file_content_for_llm(header + "".join(output))
    except Exception as e:
        return f"Error reading file '{filepath}': {e}"


def read_files(filepath: str, start_line: int = 1, end_line: int = 100) -> str:
    """Safely view a range of lines inside a file in `./workspace`."""
    return view_code_file(filepath, start_line, end_line)


def search_code(query: str, directory: str = ".") -> str:
    """Find occurrences of a text query inside source code files in `./workspace`."""
    if not _is_safe_path(directory):
        return "Error: Access denied. Target directory violates safety policies."
    
    abs_dir = _get_absolute_path(directory)
    if not os.path.isdir(abs_dir):
        return f"Error: Directory '{directory}' does not exist."
    
    results = []
    max_matches = 50
    matches_count = 0
    
    try:
        for root, dirs, files in os.walk(abs_dir):
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".venv", "node_modules", "checkpoints"}]
            
            for file in files:
                if not _has_allowed_extension(file):
                    continue
                
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, WORKSPACE_ROOT)
                
                if not _is_safe_path(rel_path):
                    continue
                    
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    for line_num, line in enumerate(f, 1):
                        if query in line:
                            results.append(f"{rel_path}:{line_num}: {line.strip()}")
                            matches_count += 1
                            if matches_count >= max_matches:
                                break
                    if matches_count >= max_matches:
                        break
        
        if not results:
            return f"No matches found for '{query}'."
            
        header = f"--- Search results for '{query}' (Max {max_matches} matches) ---\n"
        return sanitize_file_content_for_llm(header + "\n".join(results))
    except Exception as e:
        return f"Error searching code: {e}"


def create_files(filepath: str, content: str) -> str:
    """Create a new file with the specified content inside `./workspace`. Fails if the file already exists."""
    from src.core.code.validation import validate_syntax
    
    if not _is_safe_path(filepath):
        return f"Error: Access denied. Filepath '{filepath}' violates safety or path policies."
        
    if not _has_allowed_extension(filepath):
        return f"Error: Access denied. File extension not allowed. Approved extensions: {', '.join(ALLOWED_EXTENSIONS)}"
        
    abs_path = _get_absolute_path(filepath)
    if os.path.exists(abs_path):
        return f"Error: File '{filepath}' already exists. Use modify_files to make changes."
        
    dir_name = os.path.dirname(abs_path)
    if not os.path.isdir(dir_name):
        try:
            os.makedirs(dir_name, exist_ok=True)
        except Exception as e:
            return f"Error creating parent directory: {e}"
            
    filename = os.path.basename(filepath)
    if filename.endswith(".py"):
        ok, msg = validate_syntax(content, filepath)
        if not ok:
            return f"Error: {msg}"
            
    try:
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Success: Created new file '{filepath}'."
    except Exception as e:
        return f"Error creating file '{filepath}': {e}"


def try_fuzzy_replace(content: str, target: str, replacement: str) -> Optional[str]:
    """Attempts to replace the target block of code in the content using normalized matches."""
    target_norm = target.replace("\r\n", "\n").rstrip()
    content_norm = content.replace("\r\n", "\n")
    
    if target_norm in content_norm:
        if content_norm.count(target_norm) == 1:
            parts = content_norm.split(target_norm, 1)
            return parts[0] + replacement + parts[1]

    target_lines = [line.strip() for line in target.replace("\r\n", "\n").split("\n")]
    if not target_lines or (len(target_lines) == 1 and not target_lines[0]):
        return None
        
    content_lines = [line.replace("\r\n", "\n") for line in content.split("\n")]
    content_lines_stripped = [line.strip() for line in content_lines]
    
    target_len = len(target_lines)
    match_index = -1
    match_count = 0
    
    for i in range(len(content_lines_stripped) - target_len + 1):
        sub_window = content_lines_stripped[i : i + target_len]
        if sub_window == target_lines:
            match_count += 1
            match_index = i
            
    if match_count == 1:
        before = content_lines[:match_index]
        after = content_lines[match_index + target_len :]
        return "\n".join(before + [replacement] + after)
        
    return None


def edit_code_file(filepath: str, target: str, replacement: str) -> str:
    """Search and replace a specific block of text in a file inside `./workspace`. Creates file if missing."""
    from src.tools.rollback import backup_file
    
    if not _is_safe_path(filepath):
        return f"Error: Access denied. Filepath '{filepath}' violates safety or path policies."
        
    if not _has_allowed_extension(filepath):
        return f"Error: Access denied. File extension not allowed. Approved extensions: {', '.join(ALLOWED_EXTENSIONS)}"
        
    abs_path = _get_absolute_path(filepath)
    
    if not os.path.isfile(abs_path):
        dir_name = os.path.dirname(abs_path)
        if not os.path.isdir(dir_name):
            try:
                os.makedirs(dir_name, exist_ok=True)
            except Exception as e:
                return f"Error creating parent directory: {e}"
        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(replacement)
            return f"Success: Created new file '{filepath}'."
        except Exception as e:
            return f"Error creating file '{filepath}': {e}"
    
    if not target:
        backup_file(filepath)
        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(replacement)
            return f"Success: Overwrote '{filepath}' completely."
        except Exception as e:
            return f"Error overwriting file '{filepath}': {e}"

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        occurrences = content.count(target)
        if occurrences == 0:
            fuzzy_content = try_fuzzy_replace(content, target, replacement)
            if fuzzy_content is not None:
                backup_file(filepath)
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(fuzzy_content)
                return f"Success: Modified '{filepath}' successfully using relaxed matching."
                
            return (
                f"Error: Target text not found in '{filepath}'. "
                "Make sure spacing, newlines, and indentation match exactly.\n"
                "Fuzzy matching also failed.\n"
                "Fallback: If you cannot match the exact surgical block, you can overwrite the entire file "
                "by passing an empty target string (target='') and providing the complete new file content in replacement."
            )
        if occurrences > 1:
            return (
                f"Error: Target text matches {occurrences} times in '{filepath}'. "
                "Provide a larger context block to make the target query unique."
            )
            
        backup_file(filepath)
        new_content = content.replace(target, replacement, 1)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        return f"Success: Modified '{filepath}' successfully."
    except Exception as e:
        return f"Error editing file '{filepath}': {e}"


def modify_files(filepath: str, target_code: str, replacement_code: str) -> str:
    """Search and replace a specific block of text in a file inside `./workspace`. Fails if file does not exist."""
    from src.tools.rollback import backup_file
    
    if not _is_safe_path(filepath):
        return f"Error: Access denied. Filepath '{filepath}' violates safety or path policies."
        
    if not _has_allowed_extension(filepath):
        return f"Error: Access denied. File extension not allowed. Approved extensions: {', '.join(ALLOWED_EXTENSIONS)}"
        
    abs_path = _get_absolute_path(filepath)
    if not os.path.isfile(abs_path):
        return f"Error: File '{filepath}' does not exist. Use create_files to create it first."
        
    if not target_code:
        backup_file(filepath)
        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(replacement_code)
            return f"Success: Overwrote '{filepath}' completely."
        except Exception as e:
            return f"Error overwriting file '{filepath}': {e}"

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        occurrences = content.count(target_code)
        if occurrences == 0:
            fuzzy_content = try_fuzzy_replace(content, target_code, replacement_code)
            if fuzzy_content is not None:
                backup_file(filepath)
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(fuzzy_content)
                return f"Success: Modified '{filepath}' successfully using relaxed matching."
                
            return (
                f"Error: Target text not found in '{filepath}'. "
                "Make sure spacing, newlines, and indentation match exactly.\n"
                "Fuzzy matching also failed.\n"
                "Fallback: If you cannot match the exact surgical block, you can overwrite the entire file "
                "by passing an empty target string (target_code='') and providing the complete new file content in replacement_code."
            )
        if occurrences > 1:
            return (
                f"Error: Target text matches {occurrences} times in '{filepath}'. "
                "Provide a larger context block to make the target query unique."
            )
            
        backup_file(filepath)
        new_content = content.replace(target_code, replacement_code, 1)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        return f"Success: Modified '{filepath}' successfully."
    except Exception as e:
        return f"Error editing file '{filepath}': {e}"


def delete_file(filepath: str) -> str:
    """Delete a file in the workspace."""
    from src.tools.rollback import backup_file
    
    if not _is_safe_path(filepath):
        return f"Error: Access denied. Filepath '{filepath}' violates safety or path policies."
        
    abs_path = _get_absolute_path(filepath)
    if not os.path.isfile(abs_path):
        return f"Error: File '{filepath}' does not exist."
        
    backup_file(filepath)
    
    try:
        os.remove(abs_path)
        return f"Success: Deleted file '{filepath}'."
    except Exception as e:
        return f"Error deleting file '{filepath}': {e}"


def list_files(directory: str = ".") -> str:
    """List files and subdirectories inside the `./workspace` folder."""
    if not _is_safe_path(directory):
        return "Error: Access denied. Target directory violates safety policies."
        
    abs_dir = _get_absolute_path(directory)
    if not os.path.isdir(abs_dir):
        return f"Error: Directory '{directory}' does not exist."
        
    try:
        items = os.listdir(abs_dir)
        output = []
        for item in items:
            full_path = os.path.join(abs_dir, item)
            rel_path = os.path.relpath(full_path, WORKSPACE_ROOT)
            
            if not _is_safe_path(rel_path):
                continue
                
            if os.path.isdir(full_path):
                output.append(f"[DIR]  {item}")
            else:
                sz = os.path.getsize(full_path)
                output.append(f"[FILE] {item} ({sz} bytes)")
                
        if not output:
            return f"Directory '{directory}' is empty."
            
        header = f"--- Listing contents of {directory if directory != '.' else 'workspace root'} ---\n"
        return header + "\n".join(output)
    except Exception as e:
        return f"Error listing directory '{directory}': {e}"


def _is_safe_command(cmd_args: List[str]) -> bool:
    """Check if the command and arguments are safely within strict allowlist limits."""
    if not cmd_args:
        return False
        
    # Block shell command injection metacharacters in any argument
    for arg in cmd_args:
        if any(c in arg for c in [";", "&", "|", "$", "`"]):
            return False
            
    executable = cmd_args[0]
    
    if executable not in ["python", "pytest", "npm", "git", "npx"]:
        return False
        
    if executable == "python":
        if len(cmd_args) >= 3 and cmd_args[1] == "-m":
            module = cmd_args[2]
            if module == "py_compile":
                if len(cmd_args) == 4:
                    return _is_safe_path(cmd_args[3])
                return False
            elif module == "http.server":
                if len(cmd_args) == 3:
                    return True
                elif len(cmd_args) == 4:
                    return cmd_args[3].isdigit()
                return False
            elif module == "pip":
                if len(cmd_args) >= 5 and cmd_args[3] == "install":
                    import re
                    pip_flags = {"--upgrade", "--force-reinstall", "--no-cache-dir", "--user"}
                    filtered_pip_args = []
                    for arg in cmd_args[4:]:
                        if arg not in pip_flags:
                            filtered_pip_args.append(arg)
                            
                    if not filtered_pip_args:
                        return False
                        
                    # python -m pip install -r requirements.txt
                    if filtered_pip_args[0] == "-r" and len(filtered_pip_args) == 2:
                        req_path = filtered_pip_args[1]
                        return "requirements.txt" in req_path and ".." not in req_path
                        
                    for pkg in filtered_pip_args:
                        if not re.match(r"^[a-zA-Z0-9\-@_/<>=!.^]+$", pkg):
                            return False
                    return True
        # Allow running scripts directly in the workspace
        if len(cmd_args) == 2:
            return _is_safe_path(cmd_args[1])
        return False
        
    if executable == "pytest":
        pytest_flags = {"-v", "-s", "-q", "--version", "--tb=short", "--tb=line", "--no-header", "--disable-warnings", "-x", "--exitfirst", "--lf", "--last-failed", "--ff", "--failed-first", "--cache-show", "--co", "--collect-only"}
        for arg in cmd_args[1:]:
            if arg.startswith("-"):
                if arg not in pytest_flags:
                    return False
            else:
                if not _is_safe_path(arg):
                    return False
        return True
        
    if executable == "npm":
        # Handle --prefix <path> in arguments
        cleaned_npm_args = []
        prefix_dir = None
        i = 1
        while i < len(cmd_args):
            if cmd_args[i] == "--prefix":
                if i + 1 < len(cmd_args):
                    prefix_dir = cmd_args[i+1]
                    i += 2
                    continue
                else:
                    return False
            cleaned_npm_args.append(cmd_args[i])
            i += 1
            
        if prefix_dir is not None:
            if not _is_safe_path(prefix_dir):
                return False
                
        npm_flags = {"-D", "--save-dev", "--save", "--no-save", "--save-optional", "--no-optional", "--legacy-peer-deps", "--force", "--package-lock-only", "--no-audit", "--no-fund", "--ignore-scripts", "--silent", "--verbose", "--progress", "--yes", "--json"}
        filtered_npm_args = []
        for arg in cleaned_npm_args:
            if arg not in npm_flags:
                filtered_npm_args.append(arg)
                
        if not filtered_npm_args:
            return False
            
        if filtered_npm_args[0] in ["install", "ci"]:
            return True
        if filtered_npm_args[0] == "uninstall":
            return len(filtered_npm_args) >= 2
        if filtered_npm_args[0] == "update":
            return True
        if filtered_npm_args[0] == "run":
            if len(filtered_npm_args) >= 2:
                import re
                script_name = filtered_npm_args[1]
                return bool(re.match(r"^[a-zA-Z0-9_-]+$", script_name))
            return False
        if filtered_npm_args[0] == "exec":
            return True
        if filtered_npm_args[0] == "config":
            return True
        if filtered_npm_args[0] in ["cache", "audit", "outdated", "ls", "search", "view", "publish", "pack", "version", "whoami", "login", "logout"]:
            return True
        return False
        
    if executable == "npx":
        if len(cmd_args) < 2:
            return False
        npx_cmd = cmd_args[1]
        if npx_cmd == "tailwindcss":
            return True
        if npx_cmd in ("shadcn@latest", "shadcn-ui@latest"):
            return True
        if npx_cmd.startswith("shadcn@"):
            return True
        return False
        
    if executable == "git":
        git_commands = {"status", "diff", "log", "checkout", "branch", "add", "commit", "push", "pull", "fetch", "reset", "restore", "stash", "rebase", "merge", "remote", "tag", "show", "blame", "grep", "ls-files", "ls-tree", "rev-parse"}
        if len(cmd_args) >= 2 and cmd_args[1] in git_commands:
            return True
        return False
        
    return False


def _prepare_command_execution(cmd_args: List[str]) -> Tuple[List[str], str]:
    """Return subprocess args and cwd after applying safe workspace-scoped command options."""
    exec_args = list(cmd_args)
    cwd = WORKSPACE_ROOT

    if exec_args and exec_args[0] == "npm":
        i = 1
        while i < len(exec_args):
            if exec_args[i] == "--prefix":
                if i + 1 >= len(exec_args):
                    break
                prefix_dir = exec_args[i + 1]
                if not _is_safe_path(prefix_dir):
                    break
                cwd = _get_absolute_path(prefix_dir)
                del exec_args[i:i + 2]
                break
            i += 1
            
    if os.name == 'nt' and exec_args and exec_args[0] == "npx":
        exec_args[0] = "npx.cmd"

    return exec_args, cwd


def _parse_command_errors(stdout: str, stderr: str) -> str:
    """Parses command stdout/stderr to identify specific compilation/execution errors and yield actionable suggestions."""
    combined = (stdout or "") + "\n" + (stderr or "")
    suggestions = []
    import re
    
    # 1. Match standard Python traceback patterns (File "...", line X)
    py_simple_trace = re.findall(r'File\s+["\'](.*?)["\'],\s+line\s+(\d+)', combined)
    py_err_lines = re.findall(r'(\w+Error:\s+[^\n]*)', combined)
    
    if py_simple_trace:
        seen = set()
        for filepath, line_num in py_simple_trace:
            clean_file = filepath.replace("\\", "/")
            if (clean_file, line_num) in seen:
                continue
            seen.add((clean_file, line_num))
            err_msg = py_err_lines[0] if py_err_lines else "Syntax or runtime error"
            suggestions.append(
                f"💡 DETECTED PYTHON ERROR:\n"
                f"  - File: {clean_file}\n"
                f"  - Line: {line_num}\n"
                f"  - Error: {err_msg}\n"
                f"  - Action required: Open '{clean_file}' around line {line_num} and fix the syntax/execution issue."
            )
            
    # 2. Match missing Python dependencies
    module_missing = re.findall(r'(?:ModuleNotFoundError|ImportError):\s*No\s+module\s+named\s+["\'](.*?)["\']', combined)
    for mod in module_missing[:2]:
        suggestions.append(
            f"💡 DETECTED MISSING DEPENDENCY:\n"
            f"  - Missing Python Module: '{mod}'\n"
            f"  - Action required: Add '{mod}' to your requirements.txt dependency file or install it."
        )
        
    # 3. Match frontend build errors (e.g. src/App.jsx:5:10)
    frontend_errors = re.findall(
        r'(\S+\.(?:jsx?|tsx?|css|js|ts))(?::|\s+line\s+)(\d+)(?::(\d+))?[\s:]*(.*error.*|.*failed.*|.*resolved.*)',
        combined,
        re.IGNORECASE
    )
    if frontend_errors:
        seen = set()
        for filepath, line_num, col_num, err_desc in frontend_errors:
            clean_file = filepath.replace("\\", "/")
            if (clean_file, line_num) in seen:
                continue
            seen.add((clean_file, line_num))
            col_str = f", Col: {col_num}" if col_num else ""
            suggestions.append(
                f"💡 DETECTED FRONTEND BUILD ERROR:\n"
                f"  - File: {clean_file}\n"
                f"  - Line: {line_num}{col_str}\n"
                f"  - Detail: {err_desc.strip()[:180]}\n"
                f"  - Action required: Open '{clean_file}' around line {line_num} and resolve the build/compilation error."
            )
            
    if suggestions:
        return "\n\n=== 🛠️ AUTO-PARSED ERRORS & ACTIONABLE SUGGESTIONS ===\n" + "\n\n".join(suggestions) + "\n=======================================================\n"
    return ""


def _build_response(status: str, message: str, data: dict = None) -> str:
    import json
    return json.dumps({"status": status, "message": message, "data": data})

def _build_error_response(message: str, data: dict = None) -> str:
    return _build_response("error", message, data)

def _get_command_resource_limits(command: str) -> dict:
    cmd = command.strip().lower()
    if any(cmd.startswith(pfx) for pfx in ["npm install", "npm ci", "npm uninstall"]):
        return {"timeout": 180.0, "memory_mb": 768, "cpu_seconds": 60.0}
    if cmd.startswith("npm ") or cmd.startswith("npx "):
        return {"timeout": 120.0, "memory_mb": 512, "cpu_seconds": 40.0}
    if cmd.startswith("pytest"):
        return {"timeout": 120.0, "memory_mb": 256, "cpu_seconds": 30.0}
    if cmd.startswith("python"):
        return {"timeout": 120.0, "memory_mb": 256, "cpu_seconds": 30.0}
    if cmd.startswith("git"):
        return {"timeout": 60.0, "memory_mb": 128, "cpu_seconds": 15.0}
    return {"timeout": 60.0, "memory_mb": 256, "cpu_seconds": 15.0}

def _terminate_process_tree(proc, p):
    try:
        if p:
            for child in p.children(recursive=True):
                try:
                    child.kill()
                except Exception:
                    pass
        proc.kill()
    except Exception:
        pass

def _measure_memory_mb(p) -> float:
    total_mb = 0.0
    try:
        mem_info = p.memory_info()
        total_mb += mem_info.rss / (1024 * 1024)
        for child in p.children(recursive=True):
            try:
                total_mb += child.memory_info().rss / (1024 * 1024)
            except Exception:
                pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return total_mb

def _measure_cpu_time(p) -> float:
    total_cpu = 0.0
    try:
        cpu_times = p.cpu_times()
        total_cpu += cpu_times.user + cpu_times.system
        for child in p.children(recursive=True):
            try:
                c_times = child.cpu_times()
                total_cpu += c_times.user + c_times.system
            except Exception:
                pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return total_cpu

def _safe_read_stream(stream, max_bytes=1024*1024) -> str:
    if hasattr(stream, 'seek'):
        try:
            stream.seek(0)
        except Exception:
            pass
    return stream.read(max_bytes)

def execute_command(command: str) -> str:
    """Execute a command in the `./workspace` folder securely and return a JSON response.
    The JSON contains keys: status (ok/error), message, data (stdout, stderr, returncode).
    """
    cmd_clean = command.strip()
    if not cmd_clean:
        return _build_error_response("Empty command provided.")
        
    try:
        cmd_args = shlex.split(cmd_clean, posix=True)
    except Exception as e:
        return _build_error_response(f"Error parsing command line: {e}")
        
    if not cmd_args:
        return _build_error_response("Empty command provided.")
        
    if not _is_safe_command(cmd_args):
        return _build_error_response(f"Command '{command}' blocked by safety policy. Command is not in allowlist.")

    exec_args, exec_cwd = _prepare_command_execution(cmd_args)
    print(f"\n[SECURE RUN] Executing command: {exec_args} in '{exec_cwd}'")
    
    try:
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stdout_file, \
             tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr_file:
            
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            
            proc = subprocess.Popen(
                exec_args,
                cwd=exec_cwd,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                **kwargs
            )
            
            try:
                p = psutil.Process(proc.pid)
            except psutil.NoSuchProcess:
                p = None
                
            limits = _get_command_resource_limits(cmd_clean)
            timeout = limits["timeout"]
            mem_limit_mb = limits["memory_mb"]
            cpu_limit_s = limits["cpu_seconds"]
            start_time = time.time()
            
            while proc.poll() is None:
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    _terminate_process_tree(proc, p)
                    return _build_error_response(f"Command execution timed out after {timeout} seconds.")
                    
                if p:
                    mem_mb = _measure_memory_mb(p)
                    if mem_mb > mem_limit_mb:
                        _terminate_process_tree(proc, p)
                        return _build_error_response(f"Command execution exceeded memory limit of {mem_limit_mb}MB (used {mem_mb:.2f}MB).")
                    
                    cpu_time_used = _measure_cpu_time(p)
                    if cpu_time_used > cpu_limit_s:
                        _terminate_process_tree(proc, p)
                        return _build_error_response(f"Command execution exceeded CPU time limit of {cpu_limit_s}s (used {cpu_time_used:.2f}s CPU time).")
                        
                time.sleep(0.1)
                
            stdout_data = _safe_read_stream(stdout_file)
            stderr_data = _safe_read_stream(stderr_file)
            
            output = []
            if stdout_data:
                output.append("--- stdout ---")
                output.append(stdout_data)
            if stderr_data:
                output.append("--- stderr ---")
                output.append(stderr_data)
                
            status = f"\n[Command exited with status {proc.returncode}]"
            
            parsed_errors = ""
            if proc.returncode != 0:
                parsed_errors = _parse_command_errors(stdout_data, stderr_data)
                
            response_data = {
                "stdout": stdout_data,
                "stderr": stderr_data,
                "returncode": proc.returncode,
                "cwd": exec_cwd,
                "parsed_errors": parsed_errors.strip()
            }
            return _build_response("ok" if proc.returncode == 0 else "error", "Command execution completed.", response_data)
            
    except Exception as e:
        return _build_error_response(f"Error executing command: {e}")


def run_safe_commands(command: str) -> str:
    """Execute a shell command in the `./workspace` folder using the secure executor.
    Returns the same JSON structure as :func:`execute_command`.
    """
    return execute_command(command)



def update_vite_config_root(project_name: str) -> None:
    """Programmatically updates the root option in workspace/vite.config.js."""
    config_path = os.path.join(WORKSPACE_ROOT, "vite.config.js")
    
    # Default config template if not exists
    default_config = (
        "import { defineConfig } from 'vite'\n"
        "import react from '@vitejs/plugin-react'\n\n"
        "// https://vitejs.dev/config/\n"
        "export default defineConfig({\n"
        "  plugins: [react()],\n"
        f"  root: './{project_name}'\n"
        "})\n"
    )
    
    if not os.path.exists(config_path):
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(default_config)
        return
        
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Check if root is already defined
    if "root:" in content:
        # Replace the root line
        new_content = re.sub(
            r"root:\s*['\"].*?['\"]",
            f"root: './{project_name}'",
            content
        )
    else:
        # Insert root after defineConfig({
        match = re.search(r"defineConfig\s*\(\s*\{", content)
        if match:
            idx = match.end()
            new_content = content[:idx] + f"\n  root: './{project_name}'," + content[idx:]
        else:
            new_content = default_config
            
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(new_content)


def scaffold_react_app(project_name: str) -> str:
    """
    Scaffolds a new React+Vite application inside `./workspace/[project_name]/`.
    Creates standard directories and files, and updates parent vite.config.js.
    """
    # Clean project_name
    project_name = "".join(c for c in project_name if c.isalnum() or c in "-_/")
    if not project_name:
        return "Error: Invalid project name."
    
    # Split nested paths like beezlebub/frontend into parent + leaf
    parts = [p for p in project_name.replace("\\", "/").split("/") if p]
    if not parts:
        return "Error: Invalid project name."
    leaf_name = parts[-1]
    parent_path = "/".join(parts[:-1])
    
    project_dir = os.path.join(WORKSPACE_ROOT, project_name)
    src_dir = os.path.join(project_dir, "src")
    
    try:
        # 1. Create directory structure
        os.makedirs(src_dir, exist_ok=True)
        if parent_path:
            os.makedirs(os.path.join(WORKSPACE_ROOT, parent_path), exist_ok=True)
        
        # 2. Write package.json if it doesn't exist in workspace
        pkg_path = os.path.join(WORKSPACE_ROOT, "package.json")
        if not os.path.exists(pkg_path):
            package_json_content = """{
  "name": "workspace-apps",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "lint": "eslint . --ext js,jsx --report-unused-disable-directives --max-warnings 0",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "vite": "^5.3.4"
  }
}"""
            with open(pkg_path, "w", encoding="utf-8") as f:
                f.write(package_json_content)
                
        # 2b. Write local package.json, package-lock.json, and vite.config.js inside project directory
        local_pkg_path = os.path.join(project_dir, "package.json")
        default_pkg_content = """{
  "name": "project_name_placeholder",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "lint": "eslint . --ext js,jsx --report-unused-disable-directives --max-warnings 0",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "vite": "^5.3.4"
  }
}""".replace("project_name_placeholder", leaf_name)

        parent_pkg_path = os.path.join(WORKSPACE_ROOT, "package.json")
        if os.path.exists(parent_pkg_path):
            try:
                import json
                with open(parent_pkg_path, "r", encoding="utf-8") as f:
                    p_data = json.load(f)
                p_data["name"] = leaf_name
                default_pkg_content = json.dumps(p_data, indent=2)
            except Exception as e:
                logger.warning(f"Failed to read parent package.json: {e}")

        with open(local_pkg_path, "w", encoding="utf-8") as f:
            f.write(default_pkg_content)

        local_lock_path = os.path.join(project_dir, "package-lock.json")
        parent_lock_path = os.path.join(WORKSPACE_ROOT, "package-lock.json")
        if os.path.exists(parent_lock_path):
            try:
                import shutil
                shutil.copy2(parent_lock_path, local_lock_path)
            except Exception as e:
                logger.warning(f"Failed to copy parent package-lock.json to local path: {e}")

        local_vite_path = os.path.join(project_dir, "vite.config.js")
        local_vite_content = """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()]
})
"""
        with open(local_vite_path, "w", encoding="utf-8") as f:
            f.write(local_vite_content)

        # 3. Write index.html
        html_path = os.path.join(project_dir, "index.html")
        html_content = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>React App</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="./src/index.jsx"></script>
  </body>
</html>"""
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        # 4. Write src/index.jsx
        index_jsx_path = os.path.join(src_dir, "index.jsx")
        index_jsx_content = """import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './App.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)"""
        with open(index_jsx_path, "w", encoding="utf-8") as f:
            f.write(index_jsx_content)
            
        # 5. Write src/App.jsx
        app_jsx_path = os.path.join(src_dir, "App.jsx")
        app_jsx_content = """import React from 'react'

function App() {
  return (
    <div style={{ padding: '20px', fontFamily: 'sans-serif' }}>
      <h1>React App Scaffolding Successful</h1>
      <p>Start editing src/App.jsx to customize your application.</p>
    </div>
  )
}

export default App"""
        with open(app_jsx_path, "w", encoding="utf-8") as f:
            f.write(app_jsx_content)
            
        # 6. Write src/App.css
        app_css_path = os.path.join(src_dir, "App.css")
        app_css_content = """/* App styles */
body {
  margin: 0;
  padding: 0;
  background-color: #f5f5f5;
}"""
        with open(app_css_path, "w", encoding="utf-8") as f:
            f.write(app_css_content)
            
        # 7. Update parent vite.config.js root option
        update_vite_config_root(project_name)
        
        return f"Success: Scaffolded React application '{project_name}' with default placeholders in src/App.jsx and src/App.css. IMPORTANT: You must now write the actual application logic and styles in these files using modify_files. Do not leave the placeholder code."
        
    except Exception as e:
        return f"Error scaffolding React application: {e}"
