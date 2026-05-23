# Migration Guide: Agent Refactoring

## 📋 Summary

A production-ready refactored agent has been created with:
- ✅ Tool Registry pattern (eliminates hardcoded tools)
- ✅ Specific exception types (better error handling)
- ✅ Input validation (security)
- ✅ Retry logic with exponential backoff
- ✅ Timeout management
- ✅ Structured logging
- ✅ Comprehensive type hints
- ✅ Configuration externalization

## 📂 New Files Created

| File | Purpose |
|------|---------|
| `core/agent_tools.py` | Tool registry, definitions, and metrics collection |
| `core/agent_exceptions.py` | Custom exception types for better error handling |
| `core/agent_refactored.py` | Improved agent implementation with best practices |
| `AGENT_IMPROVEMENTS.md` | Comprehensive list of improvements (this file provided) |

## 🔄 Integration Steps

### Option 1: Gradual Migration (Recommended)

**Step 1:** Update `core/engine.py` to use the refactored agent

```python
# In core/engine.py, around line 124 (in __init__)

# OLD:
from core.agent import RAGAgent
self.agent = RAGAgent(self)

# NEW:
from core.agent_refactored import RAGAgent
from core.agent_tools import ToolRegistry
tool_registry = ToolRegistry()
self.agent = RAGAgent(self, tool_registry=tool_registry)
```

**Step 2:** Test endpoints with new agent

```bash
# In terminal
python main.py
# Test with browser: http://localhost:8000
```

**Step 3:** If satisfied, backup and replace old agent
```bash
# Backup
mv core/agent.py core/agent_backup.py

# Replace
mv core/agent_refactored.py core/agent.py
```

### Option 2: Full Replacement (Faster)

1. Rename `core/agent_refactored.py` to `core/agent.py` (overwrites)
2. Update imports in `core/engine.py` as shown above
3. Run tests

## 🧪 Testing the New Agent

### Unit Tests
```python
# tests/unit/test_agent_refactored.py

from core.agent_tools import ToolRegistry
from core.agent_refactored import RAGAgent
from unittest.mock import Mock

def test_query_validation():
    mock_engine = Mock()
    agent = RAGAgent(mock_engine)
    
    # Valid query
    is_valid, error = agent.validate_query("What is AI?")
    assert is_valid == True
    
    # Empty query
    is_valid, error = agent.validate_query("")
    assert is_valid == False
    
    # SQL injection attempt
    is_valid, error = agent.validate_query("'; DROP TABLE users; --")
    assert is_valid == False

def test_tool_registry():
    registry = ToolRegistry()
    
    # Check tools are registered
    assert len(registry.list_tools()) == 5
    assert registry.get_tool("search_knowledge_base") is not None
    
    # Test argument validation
    is_valid, error = registry.validate_tool_argument("web_fetch", "invalid_url")
    assert is_valid == False
    assert "http" in error.lower()
```

### Integration Test
```python
# Test full ReAct loop with greeting
def test_greeting_early_exit():
    mock_engine = Mock()
    agent = RAGAgent(mock_engine)
    
    events = list(agent.run_stream("hello", session_id="test"))
    
    # Should have early exit event
    assert any(e.get("event") == "answer_chunk" for e in events)
    assert any("done" in str(e) for e in events)
```

## 📊 Configuration Changes

New configuration in `core/config.py`:

```python
AGENT_CONFIG = {
    "max_iterations": 5,
    "default_llm_timeout_seconds": 30,
    "tool_timeouts": {
        "knowledge_base": 15,
        "web": 10,
        ...
    },
    "default_retry_count": 2,
    "retry_backoff_factor": 2.0,
    ...
}
```

**To customize:**
```python
# In core/config.py
AGENT_CONFIG["max_iterations"] = 10
AGENT_CONFIG["tool_timeouts"]["web"] = 20
```

## 🔧 Adding New Tools

### Old Way (Hardcoded)
```python
# Modify SYSTEM_PROMPT string
# Modify run_stream method
# Risk: Easy to break existing code
```

### New Way (Registry)
```python
from core.agent_tools import ToolRegistry, ToolDefinition, ToolType

registry = ToolRegistry()

# Add custom tool
registry.register(ToolDefinition(
    name="my_custom_tool",
    description="Does something cool",
    tool_type=ToolType.KNOWLEDGE_BASE,
    required_args=["input"],
    timeout_seconds=20,
    max_arg_length=500
))

# Tool is now automatically in system prompt
```

## 🚨 Breaking Changes

None! The refactored agent is **backward compatible**:
- Same `run_stream()` interface
- Same event format (e.g., `{"event": "done", "response": "..."}`)
- Same memory integration

## 📈 Performance Improvements

| Metric | Before | After |
|--------|--------|-------|
| Tool timeout | None (hangs possible) | Configurable (prevents hangs) |
| Retry logic | Manual (not implemented) | Automatic exponential backoff |
| Input validation | None | Full validation + injection detection |
| Error visibility | Generic exceptions | Specific, actionable errors |
| Tool addition | Code change required | Registry-based (runtime) |

## ✅ Validation Checklist

Before deploying to production:

- [ ] Run existing unit tests pass
- [ ] Test greeting early-exit flow
- [ ] Test tool execution (KB search, web search)
- [ ] Verify timeout protection (disable tool, verify graceful failure)
- [ ] Check logging output (should be structured)
- [ ] Monitor memory usage (no leaks)
- [ ] Test with load (concurrent sessions)
- [ ] Verify metrics collection (`/metrics` endpoint if exposed)

## 🐛 Troubleshooting

### Issue: Tools not executing
**Solution**: Check tool registry is initialized
```python
registry = ToolRegistry()
print(registry.list_tools())  # Should show 5 tools
```

### Issue: Timeouts still happening
**Solution**: Verify timeout configuration
```python
# Check config
print(AGENT_CONFIG["tool_timeouts"])
```

### Issue: Validation rejecting valid queries
**Solution**: Adjust validation rules in `AGENT_CONFIG`
```python
AGENT_CONFIG["max_query_length"] = 10000  # Increase limit
```

## 📚 Documentation

Detailed docstrings available in:
- `core/agent_refactored.py` - Main agent class
- `core/agent_tools.py` - Tool registry and definitions
- `core/agent_exceptions.py` - Exception hierarchy

## 🎯 Next Steps (Post-Deployment)

1. **Add observability**: Integrate Prometheus metrics
2. **Add tracing**: Add OpenTelemetry spans
3. **Performance tuning**: Profile and optimize hot paths
4. **Tool audit**: Review tool success rates in production
5. **A/B testing**: Test new tools with subset of users

## 📞 Support

Questions? Check:
1. Tool registry docstrings
2. Exception hierarchy in `agent_exceptions.py`
3. Configuration examples in `config.py`
4. Unit tests (when added)
