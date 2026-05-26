# Migration Guide: Retrieval-First Architecture

## 📋 Summary

The agent has been refactored to use a **retrieval-first architecture** with:

- ✅ **Router-driven pipeline selection** - Pipeline decided before LLM involvement
- ✅ **Retrieval as infrastructure** - Mandatory retrieval in STRICT_RAG, not a tool choice
- ✅ **Confidence-based uncertainty messaging** - Explicit warnings for low/medium confidence
- ✅ **Clear tool separation** - Web tools only available in WEB_AGENT/HYBRID pipelines

## 🔄 Architecture Changes

### Before: Tool-Choice RAG
```
Query → LLM decides to search_knowledge_base → Retrieve → Generate
```

### After: Retrieval-First
```
Query → Router decides pipeline → (Mandatory Retrieval in STRICT_RAG) → LLM synthesizes
```

### Pipeline Types

| Pipeline | When Used | Retrieval | Available Tools |
|----------|-----------|-----------|-----------------|
| STRICT_RAG | Private/enterprise queries | Mandatory (infrastructure) | None |
| WEB_AGENT | Live/web data queries | Optional | web_search, web_fetch, calculate_math, get_current_time, get_system_stats |
| HYBRID | Ambiguous queries | Yes | Same as WEB_AGENT |
| CHAT | Greetings/casual | No | None |

## 🧪 Testing the Router

### Unit Tests
```python
# tests/unit/test_router.py

from core.router import Router, PipelineType

def test_private_query_routes_to_strict_rag():
    router = Router()
    result = router.route("what is our company revenue", [], 50)
    assert result["pipeline"] == PipelineType.STRICT_RAG
    assert result["requires_retrieval"] is True

def test_casual_query_routes_to_chat():
    router = Router()
    result = router.route("hello", [], 0)
    assert result["pipeline"] == PipelineType.CHAT
    assert result["requires_retrieval"] is False
```

## 🔧 Key Implementation Details

- `core/router.py` - Orchestrator-driven pipeline selection
- `core/agent.py` - Retrieval-first agent using router output
- `search_knowledge_base` tool removed - retrieval is now infrastructure
- Confidence scoring: 0.0-1.0 from Cross-Encoder reranker

## 📊 Configuration

Confidence thresholds are defined in `core/router.py`:

```python
# Confidence thresholds
HIGH_CONFIDENCE = 0.5     # Clean grounded prompt
MEDIUM_CONFIDENCE = 0.3   # Uncertainty warning added
LOW_CONFIDENCE = 0.0      # Strong uncertainty warning
```

## 🧪 Testing the New Agent

### Unit Tests
```python
# tests/unit/test_agent.py

from core.agent import RAGAgent
from unittest.mock import Mock

def test_retrieval_first_for_private_query():
    """Private queries go through STRICT_RAG with mandatory retrieval."""
    mock_engine = Mock()
    mock_engine.retriever.get_sources.return_value = ["doc1.pdf"]
    mock_engine.retriever.get_count.return_value = 100
    
    agent = RAGAgent(mock_engine)
    events = list(agent.run_stream("what is our company revenue", session_id="test"))
    
    # Should have routing_decision event with STRICT_RAG_PIPELINE
    routing_events = [e for e in events if e.get("event") == "routing_decision"]
    assert len(routing_events) == 1
    assert "STRICT_RAG" in routing_events[0]["text"]

def test_grounded_generation_prompt():
    """Grounded generation uses only retrieved evidence."""
    from core.router import ground_generation
    
    prompt = ground_generation("question", "evidence content", 0.8)
    assert "ONLY the provided evidence" in prompt
    assert "evidence content" in prompt
```

### Integration Test
```python
# Test retrieval-first flow
def test_strict_rag_with_retrieval():
    """STRICT_RAG pipeline performs mandatory retrieval."""
    mock_engine = Mock()
    mock_engine.retriever.get_sources.return_value = ["test.pdf"]
    mock_engine.retriever.get_count.return_value = 50
    
    agent = RAGAgent(mock_engine)
    events = list(agent.run_stream("what is our sales data", session_id="test"))
    
    # Verify routing decision
    routing = [e for e in events if e.get("event") == "routing_decision"]
    assert "STRICT_RAG" in routing[0]["text"]
    
    # Verify retrieval phase
    retrieval = [e for e in events if e.get("event") == "retrieval_phase"]
    assert len(retrieval) == 1
```

## 📚 Documentation

See `docs/rag_explanation.md` for complete technical documentation.