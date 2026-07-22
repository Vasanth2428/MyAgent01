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
