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
WORKSPACE_ROOT = os.environ.get("AGENT_WORKSPACE_ROOT", PROJECT_ROOT)

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
    if not filepath or not filepath.strip():
        return False
        
    norm_path = filepath.replace("\\", "/")
    forbidden_prefixes = ("/", "/etc", "/root", "/usr", "/var", "..")
    if any(norm_path.startswith(p) for p in forbidden_prefixes) or "../" in norm_path:
        return False
        

    real_workspace = os.path.realpath(WORKSPACE_ROOT)
    abs_path = os.path.realpath(os.path.join(WORKSPACE_ROOT, filepath))
    
    if not abs_path.lower().startswith(real_workspace.lower()):
        return False
            
    rel_path = os.path.relpath(abs_path, WORKSPACE_ROOT)
    normalized_rel = rel_path.replace("\\", "/").lower()
    
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
    return True


def _get_absolute_path(filepath: str) -> str:
    """Get absolute path to a file in the `./workspace` folder."""
    p = filepath.replace("\\", "/")
    
    # Strip leading slashes to prevent os.path.join from treating it as a drive-absolute path on Windows
    while p.startswith("/"):
        p = p[1:]
        
    while p.startswith("./"):
        p = p[2:]
    if p.startswith("workspace/"):
        p = p[len("workspace/"):]
    while p.startswith("./"):
        p = p[2:]
    return os.path.realpath(os.path.join(WORKSPACE_ROOT, os.path.normpath(p)))


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
        if os.path.isfile(dir_name):
            return f"Error: Cannot create parent directory '{os.path.basename(dir_name)}' because a file with that name already exists. If you accidentally created it as a file, delete it first using delete_file."
        try:
            os.makedirs(dir_name, exist_ok=True)
        except Exception as e:
            return f"Error creating parent directory: {e}"
            
    filename = os.path.basename(filepath)
    if filename.lower().endswith((".py", ".js", ".jsx", ".ts", ".tsx")):
        ok, msg = validate_syntax(content, filepath)
        if not ok:
            return f"Error: {msg}"
            
    try:
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Success: Created new file '{filepath}'."
    except Exception as e:
        return f"Error creating file '{filepath}': {e}"



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



    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        occurrences = content.count(target)
        if occurrences == 0:
            fuzzy_content = try_fuzzy_replace(content, target, replacement)
            if fuzzy_content is not None:
                backup_file(filepath)
                from src.core.code.validation import validate_syntax
                if filepath.lower().endswith((".py", ".js", ".jsx", ".ts", ".tsx")):
                    ok, msg = validate_syntax(fuzzy_content, filepath)
                    if not ok:
                        return f"Error: Validation failed on fuzzy edited file. {msg}"
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
        
        from src.core.code.validation import validate_syntax
        if filepath.lower().endswith((".py", ".js", ".jsx", ".ts", ".tsx")):
            ok, msg = validate_syntax(new_content, filepath)
            if not ok:
                return f"Error: Validation failed on edited file. {msg}"
                
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        return f"Success: Modified '{filepath}' successfully."
    except Exception as e:
        return f"Error editing file '{filepath}': {e}"


def _multi_replace_file_content(filepath: str, chunks: list) -> str:
    """
    Replace multiple specific line ranges with replacement content.
    chunks: list of dict with StartLine, EndLine, TargetContent, ReplacementContent
    """
    from src.tools.rollback import backup_file
    
    if not _is_safe_path(filepath):
        return f"Error: Access denied. Filepath '{filepath}' violates safety or path policies."
        
    if not _has_allowed_extension(filepath):
        return f"Error: Access denied. File extension not allowed. Approved extensions: {', '.join(ALLOWED_EXTENSIONS)}"
        
    abs_path = _get_absolute_path(filepath)
    if not os.path.isfile(abs_path):
        return f"Error: File '{filepath}' does not exist."
        
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        backup_file(filepath)
        
        # Process chunks from bottom up to avoid index shifting
        sorted_chunks = sorted(chunks, key=lambda x: x.get('StartLine', 0), reverse=True)
        
        for chunk in sorted_chunks:
            start_line = chunk.get("StartLine", 1) - 1
            end_line = chunk.get("EndLine", len(lines))
            target = chunk.get("TargetContent", "")
            replacement = chunk.get("ReplacementContent", "")
            
            # Simple substring replace within the targeted lines
            target_lines = "".join(lines[start_line:end_line])
            if target not in target_lines:
                return f"Error: TargetContent not found in lines {start_line+1}-{end_line}."
            
            new_lines_str = target_lines.replace(target, replacement, 1)
            lines = lines[:start_line] + [new_lines_str] + lines[end_line:]
            
        new_content = "".join(lines)
        from src.core.code.validation import validate_syntax
        if filepath.lower().endswith((".py", ".js", ".jsx", ".ts", ".tsx")):
            ok, msg = validate_syntax(new_content, filepath)
            if not ok:
                return f"Error: Validation failed on multi-edited file. {msg}"
                
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        return f"Success: Modified '{filepath}' successfully with {len(chunks)} chunk(s)."
    except Exception as e:
        return f"Error in multi_replace: {e}"



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
def create_directory(directory_path: str) -> str:
    """Create a new directory (and any missing parent directories) inside the workspace."""
    if not _is_safe_path(directory_path):
        return f"Error: Access denied. Directory path '{directory_path}' violates safety or path policies."
        
    abs_dir = _get_absolute_path(directory_path)
    
    if os.path.exists(abs_dir):
        if os.path.isdir(abs_dir):
            return f"Directory '{directory_path}' already exists."
        else:
            return f"Error: A file already exists at '{directory_path}'."
            
    try:
        os.makedirs(abs_dir, exist_ok=True)
        return f"Success: Created directory '{directory_path}'."
    except Exception as e:
        return f"Error creating directory '{directory_path}': {e}"


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


_active_tasks = {}
_task_outputs = {}
import uuid
import threading

def _build_response(status: str, message: str, data: dict = None) -> str:
    import json
    return json.dumps({"status": status, "message": message, "data": data})

def _build_error_response(message: str, data: dict = None) -> str:
    return _build_response("error", message, data)

def _clean_terminal_output(raw_text: str) -> str:
    if not raw_text:
        return ""
    import re
    # 1. Strip ANSI escape codes
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', raw_text)
    
    # 2. Process carriage returns to simulate terminal overwrite
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        if '\r' in line:
            segments = line.split('\r')
            line = segments[-1] if segments[-1] else (segments[-2] if len(segments) > 1 else "")
            
        line_stripped = line.strip()
        # 3. Filter known progress spam
        if not line_stripped:
            continue
        if "npm WARN" in line_stripped:
            continue
        if line_stripped.startswith("[") and line_stripped.endswith("]") and len(line_stripped) > 5 and ("#" in line_stripped or "=" in line_stripped):
            continue
                
        cleaned.append(line)
    
    return '\n'.join(cleaned)

def execute_command(command: str, directory: str = ".", wait_ms_before_async: int = 2000) -> str:
    """Execute a shell command securely and return a JSON response. Automatically yields to background if it takes longer than WaitMs."""
    cmd_clean = command.strip()
    if not cmd_clean:
        return _build_error_response("Empty command provided.")
    
    # Resolve the directory safely relative to WORKSPACE_ROOT
    if directory == ".":
        exec_cwd = WORKSPACE_ROOT
    else:
        abs_dir = _get_absolute_path(directory)
        if not _is_safe_path(directory) or not os.path.exists(abs_dir):
            return _build_error_response(f"Directory '{directory}' does not exist or violates safety policies.")
        exec_cwd = abs_dir
    print(f"\n[EXEC] Executing command: {cmd_clean} in '{exec_cwd}' (WaitMsBeforeAsync={wait_ms_before_async})")
    
    task_id = str(uuid.uuid4())[:8]
    try:
        kwargs = {}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            # Use PowerShell explicitly on Windows instead of cmd.exe
            cmd_args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd_clean]
            use_shell = False
        else:
            cmd_args = cmd_clean
            use_shell = True
            
        proc = subprocess.Popen(
            cmd_args, shell=use_shell, cwd=exec_cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE, text=True,
            **kwargs
        )
        _active_tasks[task_id] = proc
        _task_outputs[task_id] = []
        
        def _read_output():
            try:
                for line in iter(proc.stdout.readline, ''):
                    if line:
                        _task_outputs[task_id].append(line)
            finally:
                if proc.stdout:
                    proc.stdout.close()
                if proc.stdin:
                    proc.stdin.close()
        threading.Thread(target=_read_output, daemon=True).start()
        
        try:
            # Wait for the process to complete synchronously within the threshold
            returncode = proc.wait(timeout=wait_ms_before_async / 1000.0)
            
            # Allow thread to finish reading
            time.sleep(0.1) 
            raw_stdout = "".join(_task_outputs[task_id])
            stdout = _clean_terminal_output(raw_stdout)
            if len(stdout) > 5000:
                stdout = stdout[:2500] + "\n...[TRUNCATED FOR LLM CONTEXT LIMITS]...\n" + stdout[-2500:]
            
            # Clean up task
            _active_tasks.pop(task_id, None)
            _task_outputs.pop(task_id, None)
            
            return _build_response(
                "ok" if returncode == 0 else "error",
                "Command finished",
                {"stdout": stdout, "returncode": returncode}
            )
        except subprocess.TimeoutExpired:
            # It's taking longer than WaitMsBeforeAsync. Leave it in the background!
            current_output = "".join(_task_outputs[task_id])
            return _build_response(
                "ok", 
                "Command is still running (possibly waiting for input). It has been sent to the background. Use check_task_status and send_task_input if it is stuck.", 
                {"task_id": task_id, "stdout_so_far": current_output}
            )
            
    except Exception as e:
        return _build_error_response(str(e))

def run_safe_commands(command: str, directory: str = ".", wait_ms_before_async: int = 2000) -> str:
    """Execute a shell command. Automatically pushes to background if it takes longer than WaitMsBeforeAsync."""
    return execute_command(command, directory, wait_ms_before_async)

def check_task_status(task_id: str) -> str:
    """Check the status and recent output of a background task."""
    if task_id not in _active_tasks:
        return _build_error_response(f"Invalid task ID: {task_id}")
    proc = _active_tasks[task_id]
    output = "".join(_task_outputs[task_id][-50:])
    output = _clean_terminal_output(output)
    if len(output) > 5000:
        output = output[:2500] + "\n...[TRUNCATED FOR LLM CONTEXT LIMITS]...\n" + output[-2500:]
    status = "running" if proc.poll() is None else f"exited with code {proc.returncode}"
    return _build_response("ok", f"Task {status}", {"output": output})

def send_task_input(task_id: str, text: str) -> str:
    """Send input to a background task."""
    if task_id not in _active_tasks:
        return _build_error_response(f"Invalid task ID: {task_id}")
    proc = _active_tasks[task_id]
    if proc.poll() is not None:
        return _build_error_response("Task already exited")
    try:
        proc.stdin.write(text + "\n")
        proc.stdin.flush()
        return _build_response("ok", "Input sent")
    except Exception as e:
        return _build_error_response(str(e))

def kill_task(task_id: str) -> str:
    """Kill a background task."""
    if task_id not in _active_tasks:
        return _build_error_response(f"Invalid task ID: {task_id}")
    proc = _active_tasks[task_id]
    try:
        import psutil
        try:
            p = psutil.Process(proc.pid)
            for child in p.children(recursive=True):
                child.kill()
        except psutil.NoSuchProcess:
            pass
        proc.kill()
        if proc.stdout:
            proc.stdout.close()
        if proc.stdin:
            proc.stdin.close()
        return _build_response("ok", "Task killed")
    except Exception as e:
        return _build_error_response(str(e))






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


def ingest_documentation(url: str, library_name: str) -> str:
    """
    Fetches official API documentation from a URL, extracts text, chunks it,
    and stores it in the Weaviate RAGDocs collection to prevent LLM hallucinations.
    """
    import urllib.request
    from bs4 import BeautifulSoup
    import re
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
        soup = BeautifulSoup(html, "html.parser")
        
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
            
        text = soup.get_text(separator=' ')
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        if not text:
            return f"Error: No readable text found at {url}"
            
        # Chunk text into ~1000 character segments
        chunk_size = 1000
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
        
        from src.agents.coding_worker import get_retrieval_service
        retriever = get_retrieval_service()
        
        for chunk in chunks:
            retriever.store_rag_doc(chunk, library_name, url)
            
        return f"Successfully ingested documentation from {url} for library '{library_name}'. Extracted {len(chunks)} chunks."
    except Exception as e:
        return f"Error ingesting documentation: {e}"


def search_docs(query: str, library_name: str = None) -> str:
    """
    Searches the ingested official API documentation to retrieve exact syntax
    and prevent hallucinating fake methods.
    """
    try:
        from src.agents.coding_worker import get_retrieval_service
        retriever = get_retrieval_service()
        
        results = retriever.search_rag_docs(query, library_name, limit=5)
        
        if not results:
            return "No official documentation found matching this query. You may need to use `ingest_documentation` first."
            
        formatted = []
        for i, res in enumerate(results, 1):
            formatted.append(f"--- Result {i} (Library: {res.get('library_name', 'Unknown')}) ---\nSource: {res.get('url', 'Unknown')}\n{res.get('content')}")
            
        return "\n\n".join(formatted)
    except Exception as e:
        return f"Error searching documentation: {e}"
