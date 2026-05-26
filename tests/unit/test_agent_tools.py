"""
Tests for tool registry and definitions.

Updated for retrieval-first architecture:
- Knowledge base retrieval is NOT a tool (it's infrastructure)
- Only web_search, web_fetch, get_system_stats, calculate_math, get_current_time
"""

import pytest
from core.agent_tools import (
    ToolRegistry, ToolDefinition, ToolType
)


class TestToolDefinition:
    """Tests for ToolDefinition dataclass."""

    def test_tool_definition_creation_valid(self):
        """Valid tool definition should initialize."""
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            tool_type=ToolType.WEB,
            required_args=["query"],
            timeout_seconds=10
        )
        assert tool.name == "test_tool"
        assert tool.timeout_seconds == 10
        assert tool.retry_count == 2  # default

    def test_tool_definition_missing_name(self):
        """Tool without name should raise error."""
        with pytest.raises(ValueError):
            ToolDefinition(
                name="",
                description="A test tool",
                tool_type=ToolType.WEB,
                required_args=["query"]
            )

    def test_tool_definition_invalid_timeout(self):
        """Timeout < 5 seconds should raise error."""
        with pytest.raises(ValueError, match="Timeout must be >= 5"):
            ToolDefinition(
                name="test_tool",
                description="A test tool",
                tool_type=ToolType.WEB,
                required_args=["query"],
                timeout_seconds=2
            )

    def test_tool_definition_with_optional_args(self):
        """Tool with optional args should work."""
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            tool_type=ToolType.SYSTEM,
            required_args=["arg1"],
            optional_args=["arg2"],
            timeout_seconds=15
        )
        assert len(tool.optional_args) == 1


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_registry_initialization(self):
        """Registry should initialize with 5 tools (no search_knowledge_base)."""
        registry = ToolRegistry()
        tools = registry.list_tools()
        
        assert len(tools) == 5
        tool_names = [t.name for t in tools]
        assert "web_search" in tool_names
        assert "web_fetch" in tool_names
        assert "get_system_stats" in tool_names
        assert "calculate_math" in tool_names
        assert "get_current_time" in tool_names
        assert "search_knowledge_base" not in tool_names  # Not a tool!

    def test_get_tool(self):
        """Should retrieve registered tool."""
        registry = ToolRegistry()
        tool = registry.get_tool("web_search")
        
        assert tool is not None
        assert tool.name == "web_search"
        assert tool.tool_type == ToolType.WEB

    def test_get_tool_not_found(self):
        """Should return None for non-existent tool."""
        registry = ToolRegistry()
        tool = registry.get_tool("nonexistent_tool")
        
        assert tool is None

    def test_register_tool(self):
        """Should register new tool."""
        registry = ToolRegistry()
        initial_count = len(registry.list_tools())
        
        new_tool = ToolDefinition(
            name="custom_tool",
            description="A custom tool",
            tool_type=ToolType.SYSTEM,
            required_args=["message"],
            timeout_seconds=10
        )
        registry.register(new_tool)
        
        assert len(registry.list_tools()) == initial_count + 1
        assert registry.get_tool("custom_tool") is not None

    def test_validate_tool_argument_valid(self):
        """Should validate correct tool argument."""
        registry = ToolRegistry()
        is_valid, error = registry.validate_tool_argument("web_search", "python programming")
        
        assert is_valid is True
        assert error is None

    def test_validate_tool_argument_empty(self):
        """Should reject empty argument for tools that require it."""
        registry = ToolRegistry()
        is_valid, error = registry.validate_tool_argument("web_search", "")
        
        assert is_valid is False
        assert error is not None

    def test_validate_url_format(self):
        """Should reject invalid URLs for web_fetch."""
        registry = ToolRegistry()
        
        # Invalid URL
        is_valid, error = registry.validate_tool_argument("web_fetch", "not_a_url")
        assert is_valid is False
        assert "http" in error.lower()
        
        # Valid URL
        is_valid, error = registry.validate_tool_argument("web_fetch", "https://example.com")
        assert is_valid is True

    def test_get_timeout(self):
        """Should return correct timeout for tool."""
        registry = ToolRegistry()
        
        web_timeout = registry.get_timeout("web_search")
        assert web_timeout == 10
        assert registry.get_timeout("unknown") == 30  # default

    def test_get_retry_count(self):
        """Should return correct retry count for tool."""
        registry = ToolRegistry()
        
        web_retries = registry.get_retry_count("web_search")
        assert web_retries == 2
        
        stats_retries = registry.get_retry_count("get_system_stats")
        assert stats_retries == 0

    def test_generate_system_prompt(self):
        """Should generate system prompt from registry."""
        registry = ToolRegistry()
        prompt = registry.generate_system_prompt()
        
        assert "web_search" in prompt
        assert "ReAct" in prompt
        assert "Action: tool_name[arguments]" in prompt

    def test_generate_system_prompt_for_strict_rag(self):
        """Should customize prompt for STRICT_RAG route."""
        registry = ToolRegistry()
        prompt = registry.generate_system_prompt(route="STRICT_RAG")
        
        assert "retrieval phase has already completed" in prompt
        assert "infrastructure, not a tool choice" in prompt


class TestToolMetrics:
    """Tests for ToolMetrics dataclass."""

    def test_metrics_initialization(self):
        """Metrics should initialize with defaults."""
        from core.agent_tools import ToolMetrics
        metrics = ToolMetrics("test_tool")
        
        assert metrics.tool_name == "test_tool"
        assert metrics.execution_count == 0
        assert metrics.success_count == 0
        assert metrics.success_rate == 0.0
        assert metrics.avg_duration_ms == 0.0

    def test_metrics_record_success(self):
        """Should record successful execution."""
        from core.agent_tools import ToolMetrics
        metrics = ToolMetrics("test_tool")
        metrics.record(duration_ms=100, success=True)
        
        assert metrics.execution_count == 1
        assert metrics.success_count == 1
        assert metrics.success_rate == 100.0

    def test_metrics_success_rate_calculation(self):
        """Should calculate success rate correctly."""
        from core.agent_tools import ToolMetrics
        metrics = ToolMetrics("test_tool")
        
        metrics.record(100, success=True)
        metrics.record(200, success=True)
        metrics.record(300, success=False, error="Error 1")
        
        assert metrics.success_rate == pytest.approx(66.67, rel=0.1)

    def test_metrics_to_dict(self):
        """Should export metrics as dictionary."""
        from core.agent_tools import ToolMetrics
        metrics = ToolMetrics("test_tool")
        metrics.record(100, success=True)
        metrics.record(200, success=False, error="Test error")
        
        result = metrics.to_dict()
        
        assert result["tool_name"] == "test_tool"
        assert result["execution_count"] == 2
        assert "success_rate_percent" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])