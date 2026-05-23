"""
================================================================================
UNIT TESTS: core/agent_tools.py
================================================================================
Tests for tool registry, definitions, and metrics collection.
"""

import pytest
from core.agent_tools import (
    ToolRegistry, ToolDefinition, ToolType, ToolMetrics
)


class TestToolDefinition:
    """Tests for ToolDefinition dataclass"""

    def test_tool_definition_creation_valid(self):
        """Valid tool definition should initialize"""
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            tool_type=ToolType.KNOWLEDGE_BASE,
            required_args=["query"],
            timeout_seconds=10
        )
        assert tool.name == "test_tool"
        assert tool.timeout_seconds == 10
        assert tool.retry_count == 2  # default

    def test_tool_definition_missing_name(self):
        """Tool without name should raise error"""
        with pytest.raises(ValueError):
            ToolDefinition(
                name="",
                description="A test tool",
                tool_type=ToolType.KNOWLEDGE_BASE,
                required_args=["query"]
            )

    def test_tool_definition_invalid_timeout(self):
        """Timeout < 5 seconds should raise error"""
        with pytest.raises(ValueError, match="Timeout must be >= 5"):
            ToolDefinition(
                name="test_tool",
                description="A test tool",
                tool_type=ToolType.KNOWLEDGE_BASE,
                required_args=["query"],
                timeout_seconds=2
            )

    def test_tool_definition_with_optional_args(self):
        """Tool with optional args should work"""
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            tool_type=ToolType.WEB,
            required_args=["url"],
            optional_args=["headers", "timeout"],
            timeout_seconds=15
        )
        assert len(tool.optional_args) == 2


class TestToolRegistry:
    """Tests for ToolRegistry"""

    def test_registry_initialization(self):
        """Registry should initialize with default tools"""
        registry = ToolRegistry()
        tools = registry.list_tools()
        
        assert len(tools) == 7
        assert any(t.name == "search_knowledge_base" for t in tools)
        assert any(t.name == "web_search" for t in tools)
        assert any(t.name == "web_fetch" for t in tools)
        assert any(t.name == "get_system_stats" for t in tools)
        assert any(t.name == "direct_response" for t in tools)
        assert any(t.name == "calculate_math" for t in tools)
        assert any(t.name == "get_current_time" for t in tools)

    def test_get_tool(self):
        """Should retrieve registered tool"""
        registry = ToolRegistry()
        tool = registry.get_tool("web_search")
        
        assert tool is not None
        assert tool.name == "web_search"
        assert tool.tool_type == ToolType.WEB

    def test_get_tool_not_found(self):
        """Should return None for non-existent tool"""
        registry = ToolRegistry()
        tool = registry.get_tool("nonexistent_tool")
        
        assert tool is None

    def test_register_tool(self):
        """Should register new tool"""
        registry = ToolRegistry()
        initial_count = len(registry.list_tools())
        
        new_tool = ToolDefinition(
            name="custom_tool",
            description="A custom tool",
            tool_type=ToolType.CHAT,
            required_args=["message"],
            timeout_seconds=10
        )
        registry.register(new_tool)
        
        assert len(registry.list_tools()) == initial_count + 1
        assert registry.get_tool("custom_tool") is not None

    def test_overwrite_existing_tool(self):
        """Should allow overwriting existing tool"""
        registry = ToolRegistry()
        initial_count = len(registry.list_tools())
        
        new_tool = ToolDefinition(
            name="web_search",
            description="Updated web search",
            tool_type=ToolType.WEB,
            required_args=["query"],
            timeout_seconds=25
        )
        registry.register(new_tool)
        
        # Count should stay same (overwrite)
        assert len(registry.list_tools()) == initial_count
        # But tool should be updated
        assert registry.get_tool("web_search").timeout_seconds == 25

    def test_validate_tool_argument_valid(self):
        """Should validate correct tool argument"""
        registry = ToolRegistry()
        is_valid, error = registry.validate_tool_argument("web_search", "python programming")
        
        assert is_valid is True
        assert error is None

    def test_validate_tool_argument_empty(self):
        """Should reject empty argument for tools that require it"""
        registry = ToolRegistry()
        is_valid, error = registry.validate_tool_argument("web_search", "")
        
        assert is_valid is False
        assert error is not None

    def test_validate_tool_argument_too_long(self):
        """Should reject argument exceeding max length"""
        registry = ToolRegistry()
        long_arg = "x" * 300  # web_search max is 200
        is_valid, error = registry.validate_tool_argument("web_search", long_arg)
        
        assert is_valid is False
        assert "exceeds max length" in error

    def test_validate_url_format(self):
        """Should reject invalid URLs for web_fetch"""
        registry = ToolRegistry()
        
        # Invalid URL
        is_valid, error = registry.validate_tool_argument("web_fetch", "not_a_url")
        assert is_valid is False
        assert "http" in error.lower()
        
        # Valid URL
        is_valid, error = registry.validate_tool_argument("web_fetch", "https://example.com")
        assert is_valid is True

    def test_validate_unknown_tool(self):
        """Should reject unknown tool"""
        registry = ToolRegistry()
        is_valid, error = registry.validate_tool_argument("unknown_tool", "arg")
        
        assert is_valid is False
        assert "Unknown tool" in error

    def test_get_timeout(self):
        """Should return correct timeout for tool"""
        registry = ToolRegistry()
        
        kb_timeout = registry.get_timeout("search_knowledge_base")
        web_timeout = registry.get_timeout("web_search")
        
        assert kb_timeout == 15
        assert web_timeout == 10
        assert registry.get_timeout("unknown") == 30  # default

    def test_get_retry_count(self):
        """Should return correct retry count for tool"""
        registry = ToolRegistry()
        
        kb_retries = registry.get_retry_count("search_knowledge_base")
        assert kb_retries == 2
        
        stats_retries = registry.get_retry_count("get_system_stats")
        assert stats_retries == 0

    def test_generate_system_prompt(self):
        """Should generate system prompt from registry"""
        registry = ToolRegistry()
        prompt = registry.generate_system_prompt()
        
        # Should include tool info
        assert "search_knowledge_base" in prompt
        assert "web_search" in prompt
        assert "ReAct" in prompt
        assert "Action: tool_name[arguments]" in prompt

    def test_record_execution_success(self):
        """Should record successful execution"""
        registry = ToolRegistry()
        
        registry.record_execution("web_search", duration_ms=150.5, success=True)
        metrics = registry.metrics["web_search"]
        
        assert metrics.execution_count == 1
        assert metrics.success_count == 1
        assert metrics.error_count == 0
        assert metrics.total_duration_ms == 150.5

    def test_record_execution_failure(self):
        """Should record failed execution"""
        registry = ToolRegistry()
        
        registry.record_execution("web_search", duration_ms=200, success=False, error="Network error")
        metrics = registry.metrics["web_search"]
        
        assert metrics.execution_count == 1
        assert metrics.success_count == 0
        assert metrics.error_count == 1
        assert "Network error" in metrics.errors

    def test_record_multiple_executions(self):
        """Should track multiple executions"""
        registry = ToolRegistry()
        
        registry.record_execution("web_search", duration_ms=100, success=True)
        registry.record_execution("web_search", duration_ms=200, success=True)
        registry.record_execution("web_search", duration_ms=150, success=False, error="Timeout")
        
        metrics = registry.metrics["web_search"]
        
        assert metrics.execution_count == 3
        assert metrics.success_count == 2
        assert metrics.error_count == 1
        assert metrics.success_rate == pytest.approx(66.67, rel=0.1)
        assert metrics.avg_duration_ms == pytest.approx(150, rel=0.1)


class TestToolMetrics:
    """Tests for ToolMetrics dataclass"""

    def test_metrics_initialization(self):
        """Metrics should initialize with defaults"""
        metrics = ToolMetrics("test_tool")
        
        assert metrics.tool_name == "test_tool"
        assert metrics.execution_count == 0
        assert metrics.success_count == 0
        assert metrics.success_rate == 0.0
        assert metrics.avg_duration_ms == 0.0

    def test_metrics_record_success(self):
        """Should record successful execution"""
        metrics = ToolMetrics("test_tool")
        metrics.record(duration_ms=100, success=True)
        
        assert metrics.execution_count == 1
        assert metrics.success_count == 1
        assert metrics.success_rate == 100.0

    def test_metrics_success_rate_calculation(self):
        """Should calculate success rate correctly"""
        metrics = ToolMetrics("test_tool")
        
        metrics.record(100, success=True)
        metrics.record(150, success=True)
        metrics.record(200, success=False, error="Error 1")
        metrics.record(175, success=False, error="Error 2")
        
        assert metrics.success_rate == pytest.approx(50.0)
        assert metrics.execution_count == 4

    def test_metrics_avg_duration_calculation(self):
        """Should calculate average duration correctly"""
        metrics = ToolMetrics("test_tool")
        
        metrics.record(100, success=True)
        metrics.record(200, success=True)
        metrics.record(300, success=True)
        
        assert metrics.avg_duration_ms == pytest.approx(200.0)

    def test_metrics_error_capping(self):
        """Should cap error log at 10 entries"""
        metrics = ToolMetrics("test_tool")
        
        for i in range(15):
            metrics.record(100, success=False, error=f"Error {i}")
        
        assert len(metrics.errors) == 10
        # First 10 errors (0-9) are kept
        assert metrics.errors[0] == "Error 0"
        assert metrics.errors[-1] == "Error 9"

    def test_metrics_to_dict(self):
        """Should export metrics as dictionary"""
        metrics = ToolMetrics("test_tool")
        metrics.record(100, success=True)
        metrics.record(200, success=False, error="Test error")
        
        result = metrics.to_dict()
        
        assert result["tool_name"] == "test_tool"
        assert result["execution_count"] == 2
        assert result["success_count"] == 1
        assert result["error_count"] == 1
        assert "success_rate_percent" in result
        assert "avg_duration_ms" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
