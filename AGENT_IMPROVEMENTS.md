# Professional Improvements for RAGAgent

## Current Codebase Refactor Priorities

The project already has both the legacy `core/agent.py` and the newer `core/agent_refactored.py`, and `core/engine.py` currently instantiates the refactored version. The next cleanup should focus on integration quality rather than adding another parallel agent.

1. Consolidate the agent entry point.
   Keep one public `RAGAgent` implementation and move the legacy file behind a compatibility import or archive it after tests pass. Right now tests import both paths, which makes it easy for fixes to land in only one implementation.

2. Restore streaming telemetry parity in the refactored agent.
   The legacy agent emits richer `planning`, `memory_retrieval`, `context_assembly`, retrieval, overflow, traversal, and final telemetry events. The refactored agent has better architecture but a thinner stream contract. Pull the richer event contract into small helper methods so the UI does not depend on legacy-only fields.

3. Split ReAct orchestration from transport details.
   `run_stream` currently mixes prompt construction, LLM calls, parsing, tool execution, memory writes, telemetry, and UI-facing event naming. Extract `AgentRunState`, `build_messages`, `apply_observation`, and `build_done_stats` helpers to make each loop testable without running the full stream.

4. Make tool implementations callable objects.
   `ToolRegistry` stores metadata, but `_execute_tool` still branches by tool name. Register `handler` callables or a `ToolExecutor` map so adding `web_fetch`, stats, or future database tools does not require editing the agent loop.

5. Standardize telemetry schemas.
   Use `TypedDict` or Pydantic models for stream events and persisted telemetry. This will catch field mismatches like `output` versus `text` before the frontend sees them.

6. Normalize web traversal result fields.
   `search_web` call sites use both `url` and `link`. Add one adapter layer in `core/web_traversal.py` so every UI and agent path receives `{title, url, snippet}`.

---

## 🔴 High Priority (Production-Ready)

### 1. **Tool Registry Pattern** (Replaces hardcoded tools)
- Define tools declaratively instead of embedding in SYSTEM_PROMPT
- Add tool validation before execution
- Enables runtime tool registration/removal

**Impact**: Easier to add tools, better testability, reduced duplication

```python
# Create core/agent_tools.py
@dataclass
class ToolDefinition:
    name: str
    description: str
    required_args: List[str]
    timeout_seconds: int = 30
    retry_count: int = 2
```

---

### 2. **Structured Exception Handling**
Current: `except Exception as e` (catches everything)
Issue: Masks real errors, makes debugging hard

**Implement**:
- Specific exception types (ToolExecutionError, TimeoutError, ValidationError)
- Retry logic with exponential backoff for transient failures
- Circuit breaker for flaky tools (e.g., web_fetch)

```python
class ToolExecutionError(Exception):
    """Raised when a tool fails execution"""
    pass

class ToolTimeoutError(ToolExecutionError):
    """Raised when tool exceeds timeout"""
    pass
```

---

### 3. **Input Validation & Sanitization**
Current: No validation on tool arguments
Risk: Injection attacks, malformed queries crashing tools

**Implement**:
- Validate query length (max 5000 chars)
- Sanitize URLs before fetch (check domain whitelist if needed)
- Validate tool args against schema
- Strip/escape dangerous patterns

```python
def validate_tool_argument(tool_name: str, arg: str) -> bool:
    """Validates tool argument before execution"""
    max_lengths = {
        "search_knowledge_base": 500,
        "web_search": 200,
        "web_fetch": 2048
    }
    return len(arg) <= max_lengths.get(tool_name, 1000)
```

---

### 4. **Timeout Management**
Current: No timeouts on LLM/tool calls
Risk: Agent hangs indefinitely, blocking requests

**Implement**:
- Add `timeout_seconds` to tool definitions (default 30s)
- Use `asyncio.wait_for()` for timeouts
- Graceful fallback when tool times out

```python
@timeout(seconds=30)
def execute_tool(self, tool_name: str, arg: str) -> str:
    """Execute tool with timeout protection"""
    pass
```

---

## 🟡 Medium Priority (Production Polish)

### 5. **Structured Logging**
Current: Plain text logs
Better: JSON structured logs for observability

**Implement**:
```python
logger.info("tool_execution", extra={
    "tool_name": "web_search",
    "arg": query,
    "duration_ms": elapsed_ms,
    "success": True,
    "session_id": session_id
})
```

---

### 6. **Tool Execution Metrics**
Current: No visibility into tool performance
Implement:
- Track tool latency, success rate, errors
- Collect metrics per tool and per session
- Expose metrics endpoint for monitoring

```python
@dataclass
class ToolMetrics:
    tool_name: str
    execution_count: int
    success_count: int
    avg_latency_ms: float
    error_log: List[str]
```

---

### 7. **Dependency Injection**
Current: `self.engine` passed via constructor (tightly coupled)
Better: Inject dependencies explicitly

```python
def __init__(
    self, 
    engine: "AgenticSystem",
    tool_registry: ToolRegistry = None,
    logger: logging.Logger = None,
    metrics_collector: MetricsCollector = None
):
    self.engine = engine
    self.tools = tool_registry or DefaultToolRegistry()
    self.logger = logger or logging.getLogger(__name__)
    self.metrics = metrics_collector
```

---

### 8. **Comprehensive Type Hints**
Current: Partial type hints
Add:
- Return types for all methods
- TypedDict for complex dicts
- Callable types for functions

```python
def run_stream(
    self, 
    query: str, 
    session_id: str = "default",
    source_filter: Optional[str] = None,
    context_limit: Optional[int] = None
) -> Generator[Dict[str, Any], None, None]:
    """Executes ReAct loop streaming events."""
    pass
```

---

### 9. **Configuration Externalization**
Current: Magic numbers in code (max_iterations=5, etc.)
Move to config:

```python
# In core/config.py
AGENT_CONFIG = {
    "max_iterations": 5,
    "default_timeout_seconds": 30,
    "memory_token_limit": 1500,
    "web_search_timeout": 10,
    "web_fetch_timeout": 15,
}
```

---

### 10. **Testability Refactoring**
Current: Tight coupling, hard to test
Implement:
- Extract tool execution logic to separate method
- Use Protocol/ABC for dependencies
- Mock-friendly design

```python
# Before (hard to test)
response = self.engine.client.chat.completions.create(...)

# After (testable)
response = self._call_llm(messages, **kwargs)
# Can mock _call_llm
```

---

## 🟢 Nice to Have (Best Practices)

### 11. **Audit Logging for Sensitive Operations**
Track:
- Web fetch URLs (potential data exfiltration detection)
- Queries that fail/retry frequently
- Tool execution chains per session

---

### 12. **Performance Optimization**
- Cache `web_fetch` results (URL → content mapping)
- Parallel execution for read-only tools (search_knowledge_base + web_search)
- Early exit heuristics (don't search web if KB has high-confidence answer)

---

### 13. **Documentation**
- Add docstrings with examples for each tool
- Document error scenarios ("What happens if web_fetch times out?")
- Add inline comments for complex regex/parsing logic

---

### 14. **Agent State Machine**
Model agent as explicit state machine:
```
INIT → PLANNING → THOUGHT → ACTION → OBSERVATION → [LOOP/SYNTHESIS] → DONE
```
Makes it easier to add hooks, debug, and test.

---

## 📋 Implementation Order (Recommended)

1. **Tool Registry** (enables easier future work)
2. **Specific Exceptions** (improves debugging immediately)
3. **Input Validation** (security)
4. **Timeouts** (reliability)
5. **Type Hints** (code quality)
6. **Config Externalization** (maintainability)
7. **Structured Logging** (observability)
8. **Tests** (confidence)

---

## Quick Wins (5-10 min each)
- ✅ Move `SYSTEM_PROMPT` to config
- ✅ Add `@timeout` decorators
- ✅ Replace bare `except Exception` with specific types
- ✅ Add return type hints to all methods
