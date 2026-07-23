# Project Log

This file records and tracks every major decision we take and implement.

## 2026-07-21
- Created this `log.md` file to track major decisions and implementations moving forward.
- Conducted initial system audit to identify missing architectural components and gaps against project guidelines.
- Fixed `langchain` missing module errors in `src/core/model_provider.py` by updating imports to use `langchain_core` and `langchain_community` directly.
- Added a global 1 RPS rate limiter for Mistral API calls in `src/core/model_provider.py` and updated `.env` to use the `codestral-latest` model to bypass API rate limits on new keys.
- Discovered a critical context bloat bug in the multi-agent framework during the live pipeline run, where terminal output and error loops can cause the prompt to exceed 21 million tokens, crashing the LLMs (Error 400).

## 2026-07-22
- Deferred Supabase migration architectural change to focus on first running the live pipeline successfully with an API key.
- Switched Weaviate connection in `.env` from the cloud instance to the local instance (`http://localhost:8080`) to resolve 429 limit errors and properly use the local environment.
- Fixed a path hallucination issue where the agent wrote a truncated `package.json` to the root `workspace/` directory instead of `workspace/ai_dashboard/`, which crashed Vite's config resolution.
- Refactored `run_live_pipeline.py` and `coding_worker.py` system prompts to enforce mature agent practices (mandating CLI scaffolding over manual file writing, and enforcing strict directory rules).
- Cleared the corrupted `workspace/ai_dashboard` directory and restarted the live pipeline to ensure the new architectural rules are applied cleanly from scratch.
- Investigated recurring "Access Denied" errors and discovered a critical architectural flaw: an artificial `active_project` sandbox state that blocked the agent from natively scaffolding projects.
- Executed a structural refactor to completely rip out the `active_project` sandbox from `supervisor.py`, `state_2pipeline.py`, `coding_worker.py`, `code_critic_worker.py`, and `coding_tools.py`, untethering the agent and allowing it free native access within the `workspace/` root.
- Removed deprecated/obsolete tools (`modify_files`, `scaffold_react_app`, `try_fuzzy_replace`) from `coding_tools.py` and `coding_worker.py` to prevent LLM hallucinations, strictly enforcing `multi_replace_file_content` and CLI scaffolding via terminal commands.
- Fixed residual `ImportError` in `token_saving.py` caused by removing the obsolete `edit_code_file` utility.
- **Fixed Episodic Memory Loop:** The CodingWorker agent was getting stuck in an infinite loop because Weaviate (Episodic Memory) cached a past "Access Denied" failure for the scaffolding tools. Temporarily removed the Episodic Memory Retrieval guardrail in `coding_worker.py` to allow the agent to proceed.
- **Fixed Windows PowerShell Shell execution:** `run_safe_commands` defaulted to `cmd.exe` on Windows (`shell=True`), causing PowerShell verification commands like `Test-Path` to fail. Modified `execute_command` in `coding_tools.py` to explicitly route commands through `powershell`.
- **Fixed Hardcoded Execution Directory Bug:** `run_safe_commands` completely ignored the agent's desired working directory, executing all commands in the root workspace folder (`exec_cwd = WORKSPACE_ROOT`). Added a `directory` parameter to both `coding_tools.py` and `coding_worker.py`, allowing the agent to target subdirectories correctly (e.g., scaffolding inside `ai_platform/backend`).

### Pipeline Debugging & Fixes (Session 3)
- **Fixed Context Bloat Error (951,000 tokens):** The supervisor crashed due to a 1-million token context blowup caused by long-running terminal output (like `npm install` progress bars) being fully ingested into the LangGraph state. Added aggressive 5000-character log truncation inside `coding_tools.py` (`execute_command`) and `supervisor.py` (`messages_to_route`) to protect the LLM context limits.
- **Fixed Directory Hallucination / WinError 183:** Discovered that the LLM was calling `create_files` to create directories, which instead created 0-byte blank files named `backend` without extensions. When subsequent tasks tried to create actual files inside `backend/`, Windows threw WinError 183. Added a hard guardrail in `create_files` that intercepts this mistake and returns a descriptive error forcing the LLM to use `delete_file` before continuing.
