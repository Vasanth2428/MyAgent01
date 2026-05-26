# Professional Improvements for RAGAgent

## Retrieval-First Architecture

The agent now uses a **retrieval-first architecture** where:

1. **Router determines pipeline BEFORE any LLM involvement** - The orchestrator (not the LLM) decides whether to use STRICT_RAG, WEB_AGENT, HYBRID, or CHAT pipeline
2. **Retrieval is infrastructure, not a tool choice** - In STRICT_RAG mode, retrieval happens automatically. The LLM cannot skip or bypass this.
3. **Confidence-based uncertainty messaging** - Low (<0.3) and medium (0.3-0.5) confidence results trigger explicit warnings in the prompt.

## Current Architecture

The `core/agent.py` contains the retrieval-first agent implementation with:

- Router-driven pipeline selection (`core/router.py`)
- Mandatory retrieval infrastructure for STRICT_RAG pipeline
- Confidence-based prompt modification
- Clean separation between RAG and web agent modes

## 🔴 High Priority (Production-Ready)

### 1. **Structured Exception Handling**
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

### 2. **Input Validation & Sanitization**
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
        "web_search": 200,
        "web_fetch": 2048,
        "calculate_math": 100
    }
    return len(arg) <= max_lengths.get(tool_name, 500)
```

### 3. **Timeout Management**
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

## 🟡 Medium Priority (Production Polish)

### 4. **Structured Logging**
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

### 5. **Tool Execution Metrics**
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

### 6. **Comprehensive Type Hints**
Add:
- Return types for all methods
- TypedDict for complex dicts
- Callable types for functions

## 🟢 Nice to Have (Best Practices)

### 7. **Performance Optimization**
- Cache `web_fetch` results (URL → content mapping)
- Parallel execution for read-only tools where applicable
- Early exit heuristics for casual conversation queries

### 8. **Documentation**
- Add docstrings with examples for each tool
- Document error scenarios ("What happens if web_fetch times out?")
- Add inline comments for complex regex/parsing logic