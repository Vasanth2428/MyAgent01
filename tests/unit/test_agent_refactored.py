"""
================================================================================
UNIT TESTS: core/agent_refactored.py
================================================================================
Tests for the refactored RAGAgent with improved error handling and best practices.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from core.agent_refactored import RAGAgent, ToolResult
from core.agent_tools import ToolRegistry, ToolDefinition, ToolType
from core.agent_exceptions import (
    ActionParseError, ToolExecutionError, ToolTimeoutError
)


class TestRAGAgentInitialization:
    """Tests for RAGAgent initialization"""

    def test_initialization_with_defaults(self):
        """Should initialize with default tool registry"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        assert agent.engine is mock_engine
        assert agent.tool_registry is not None
        assert agent.max_iterations == 5
        assert "search_knowledge_base" in agent.system_prompt

    def test_initialization_with_custom_registry(self):
        """Should accept custom tool registry"""
        mock_engine = Mock()
        custom_registry = ToolRegistry()
        
        agent = RAGAgent(mock_engine, tool_registry=custom_registry)
        
        assert agent.tool_registry is custom_registry

    def test_system_prompt_generated(self):
        """System prompt should be generated from registry"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        assert agent.system_prompt is not None
        assert len(agent.system_prompt) > 0
        assert "ReAct" in agent.system_prompt


class TestQueryValidation:
    """Tests for query validation"""

    def test_valid_query(self):
        """Valid queries should pass validation"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        is_valid, error = agent.validate_query("What is Python?")
        
        assert is_valid is True
        assert error is None

    def test_empty_query_rejected(self):
        """Empty query should fail validation"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        is_valid, error = agent.validate_query("")
        
        assert is_valid is False
        assert error is not None
        assert "empty" in error.lower()

    def test_whitespace_only_query_rejected(self):
        """Whitespace-only query should fail validation"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        is_valid, error = agent.validate_query("   ")
        
        assert is_valid is False

    def test_query_too_long_rejected(self):
        """Query exceeding max length should fail validation"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        long_query = "x" * 6000
        is_valid, error = agent.validate_query(long_query)
        
        assert is_valid is False
        assert "too long" in error.lower()

    def test_query_with_sql_injection_rejected(self):
        """Query with SQL injection pattern should fail validation"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        is_valid, error = agent.validate_query("'; DROP TABLE users; --")
        
        assert is_valid is False
        assert "dangerous" in error.lower()

    def test_query_with_script_tag_rejected(self):
        """Query with script tag should fail validation"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        is_valid, error = agent.validate_query("<script>alert('xss')</script>")
        
        assert is_valid is False

    def test_query_at_min_length(self):
        """Query at minimum length should pass"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        is_valid, error = agent.validate_query("a")
        
        assert is_valid is True

    def test_query_at_max_length(self):
        """Query at maximum length should pass"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        max_query = "x" * 5000
        is_valid, error = agent.validate_query(max_query)
        
        assert is_valid is True


class TestActionParsing:
    """Tests for ReAct action parsing"""

    def test_parse_valid_action_with_arg(self):
        """Should parse valid action with argument"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        text = "Thought: I need to search\nAction: search_knowledge_base[machine learning]"
        result = agent.parse_action(text)
        
        assert result is not None
        tool_name, tool_arg = result
        assert tool_name == "search_knowledge_base"
        assert tool_arg == "machine learning"

    def test_parse_action_with_quoted_arg(self):
        """Should strip quotes from arguments"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        text = 'Action: web_search["artificial intelligence"]'
        result = agent.parse_action(text)
        
        assert result is not None
        tool_name, tool_arg = result
        assert tool_arg == "artificial intelligence"

    def test_parse_action_with_single_quotes(self):
        """Should strip single quotes"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        text = "Action: web_fetch['https://example.com']"
        result = agent.parse_action(text)
        
        assert result is not None
        tool_name, tool_arg = result
        assert tool_arg == "https://example.com"

    def test_parse_action_with_backticks(self):
        """Should strip backticks"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        text = "Action: direct_response[`Hello there`]"
        result = agent.parse_action(text)
        
        assert result is not None
        tool_name, tool_arg = result
        assert tool_arg == "Hello there"

    def test_parse_action_no_argument(self):
        """Should handle action without argument"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        text = "Action: get_system_stats"
        result = agent.parse_action(text)
        
        assert result is not None
        tool_name, tool_arg = result
        assert tool_name == "get_system_stats"
        assert tool_arg == ""

    def test_parse_action_case_insensitive(self):
        """Should parse action case-insensitively"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        text = "action: SEARCH_KNOWLEDGE_BASE[query]"
        result = agent.parse_action(text)
        
        assert result is not None
        tool_name, tool_arg = result
        assert tool_name == "search_knowledge_base"

    def test_parse_invalid_action_returns_none(self):
        """Should return None for invalid actions"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        text = "This is not a valid action line"
        result = agent.parse_action(text)
        
        assert result is None

    def test_parse_action_with_spaces(self):
        """Should handle action with extra spaces"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        text = "Action:   web_search   [  python  ]"
        result = agent.parse_action(text)
        
        assert result is not None
        tool_name, tool_arg = result
        assert tool_name == "web_search"
        assert tool_arg == "python"


class TestToolExecution:
    """Tests for tool execution"""

    def test_execute_search_knowledge_base(self):
        """Should execute knowledge base search"""
        mock_engine = Mock()
        mock_engine.context_engine_subsystem.retrieve_and_compress.return_value = "Found results"
        
        agent = RAGAgent(mock_engine)
        result = agent._execute_tool("search_knowledge_base", "test query")
        
        assert result == "Found results"
        mock_engine.context_engine_subsystem.retrieve_and_compress.assert_called_once()

    def test_execute_get_system_stats(self):
        """Should execute system stats"""
        mock_engine = Mock()
        mock_engine.retriever.get_count.return_value = 42
        
        agent = RAGAgent(mock_engine)
        result = agent._execute_tool("get_system_stats", "")
        
        assert "CPU:" in result
        assert "RAM:" in result
        assert "42" in result

    def test_execute_direct_response(self):
        """Should execute direct response (echo)"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        response_text = "Hello, user!"
        result = agent._execute_tool("direct_response", response_text)
        
        assert result == response_text

    def test_execute_unknown_tool_raises_error(self):
        """Should raise error for unknown tool"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        with pytest.raises(ToolExecutionError):
            agent._execute_tool("unknown_tool", "arg")


class TestToolExecutionWithRetry:
    """Tests for tool execution with retry logic"""

    def test_execute_tool_with_retry_success(self):
        """Should succeed on first attempt"""
        mock_engine = Mock()
        mock_engine.context_engine_subsystem.retrieve_and_compress.return_value = "Result"
        
        agent = RAGAgent(mock_engine)
        result = agent.execute_tool_with_retry("search_knowledge_base", "query")
        
        assert result.success is True
        assert result.content == "Result"
        assert result.retries_used == 0

    def test_execute_tool_with_invalid_argument(self):
        """Should fail validation before execution"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        # web_fetch requires valid URL
        result = agent.execute_tool_with_retry("web_fetch", "not_a_url")
        
        assert result.success is False
        assert "validation" in result.error.lower() or "http" in result.error.lower()

    def test_execute_tool_unknown_tool(self):
        """Should handle unknown tool gracefully"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        result = agent.execute_tool_with_retry("unknown_tool", "arg")
        
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_tool_result_structure(self):
        """ToolResult should have all required fields"""
        result = ToolResult(
            tool_name="test",
            success=True,
            content="test content",
            duration_ms=100.5,
            retries_used=1
        )
        
        assert result.tool_name == "test"
        assert result.success is True
        assert result.content == "test content"
        assert result.duration_ms == 100.5
        assert result.retries_used == 1


class TestGreetingEarlyExit:
    """Tests for greeting early exit"""

    def test_greeting_simple_hello(self):
        """Should handle simple 'hello' greeting"""
        mock_engine = Mock()
        mock_engine.get_memory.return_value = Mock(get_active_context=Mock(return_value=""))
        mock_engine.save_memory = Mock()
        
        agent = RAGAgent(mock_engine)
        events = list(agent.run_stream("hello"))
        
        # Should have early exit
        assert any(e.get("event") == "answer_chunk" for e in events)
        assert any(e.get("event") == "done" for e in events)

    def test_greeting_good_morning(self):
        """Should handle 'good morning' greeting"""
        mock_engine = Mock()
        mock_engine.get_memory.return_value = Mock(get_active_context=Mock(return_value=""))
        mock_engine.save_memory = Mock()
        
        agent = RAGAgent(mock_engine)
        events = list(agent.run_stream("good morning"))
        
        assert any(e.get("event") == "done" for e in events)

    def test_greeting_with_question_mark(self):
        """Should process 'how are you?' as normal query"""
        mock_engine = Mock()
        mock_engine.get_memory.return_value = Mock(get_active_context=Mock(return_value=""))
        mock_engine.client = Mock()
        mock_engine.client.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content="I'm doing well!"))]
        )
        mock_engine.llm_service = Mock()
        mock_engine.llm_service.model = "test-model"
        mock_engine.save_memory = Mock()
        
        agent = RAGAgent(mock_engine)
        events = list(agent.run_stream("how are you?"))
        
        # Should have processed the query
        assert len(events) > 0


class TestStreamingEvents:
    """Tests for streaming event generation"""

    def test_stream_yields_events(self):
        """Should yield events during processing"""
        mock_engine = Mock()
        mock_engine.get_memory.return_value = Mock(get_active_context=Mock(return_value=""))
        mock_engine.save_memory = Mock()
        
        agent = RAGAgent(mock_engine)
        events = list(agent.run_stream("hello"))
        
        assert len(events) > 0
        assert all(isinstance(e, dict) for e in events)

    def test_stream_includes_answer_chunk(self):
        """Stream should include answer_chunk event"""
        mock_engine = Mock()
        mock_engine.get_memory.return_value = Mock(get_active_context=Mock(return_value=""))
        mock_engine.save_memory = Mock()
        
        agent = RAGAgent(mock_engine)
        events = list(agent.run_stream("hello"))
        
        answer_events = [e for e in events if e.get("event") == "answer_chunk"]
        assert len(answer_events) > 0
        assert "text" in answer_events[0]

    def test_stream_includes_done_event(self):
        """Stream should include done event"""
        mock_engine = Mock()
        mock_engine.get_memory.return_value = Mock(get_active_context=Mock(return_value=""))
        mock_engine.save_memory = Mock()
        
        agent = RAGAgent(mock_engine)
        events = list(agent.run_stream("hello"))
        
        done_events = [e for e in events if e.get("event") == "done"]
        assert len(done_events) > 0


class TestInvalidQueryHandling:
    """Tests for invalid query handling"""

    def test_invalid_query_returns_error_event(self):
        """Stream should yield error for invalid query"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        events = list(agent.run_stream(""))
        
        assert any(e.get("event") == "error" for e in events)

    def test_sql_injection_returns_error(self):
        """SQL injection should trigger error event"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        events = list(agent.run_stream("'; DROP TABLE users; --"))
        
        assert any(e.get("event") == "error" for e in events)


class TestToolMetricsRecording:
    """Tests for tool metrics recording"""

    def test_successful_execution_records_metrics(self):
        """Should record metrics for successful tool execution"""
        mock_engine = Mock()
        mock_engine.context_engine_subsystem.retrieve_and_compress.return_value = "Result"
        
        agent = RAGAgent(mock_engine)
        agent.execute_tool_with_retry("search_knowledge_base", "query")
        
        metrics = agent.tool_registry.metrics["search_knowledge_base"]
        assert metrics.execution_count == 1
        assert metrics.success_count == 1

    def test_failed_execution_records_metrics(self):
        """Should record metrics for failed tool execution"""
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        agent.execute_tool_with_retry("web_fetch", "invalid_url")
        
        metrics = agent.tool_registry.metrics["web_fetch"]
        assert metrics.execution_count == 1
        assert metrics.error_count == 1

class TestMathAndTimeControl:
    """Tests for the safe math evaluator and format_current_time helper"""

    def test_safe_math_eval_basic(self):
        from core.agent_refactored import safe_math_eval
        assert safe_math_eval("2 + 3 * 4") == 14
        assert safe_math_eval("(10 - 2) / 2") == 4.0
        assert safe_math_eval("-5 + 10") == 5
        assert safe_math_eval("2 ** 3") == 8

    def test_safe_math_eval_exponent_limits(self):
        from core.agent_refactored import safe_math_eval
        with pytest.raises(ValueError, match="Exponent or base too large"):
            safe_math_eval("2 ** 101")
        with pytest.raises(ValueError, match="Exponent or base too large"):
            safe_math_eval("10000000001 ** 2")

    def test_safe_math_eval_invalid(self):
        from core.agent_refactored import safe_math_eval
        with pytest.raises(ValueError):
            safe_math_eval("1 / 0")
        with pytest.raises(ValueError, match="Invalid math expression"):
            safe_math_eval("import os")
        with pytest.raises(ValueError, match="Invalid math expression"):
            safe_math_eval("2 + foo")

    def test_format_current_time(self):
        from core.agent_refactored import format_current_time
        time_str = format_current_time()
        assert isinstance(time_str, str)
        assert len(time_str) > 0
        # Time format contains day name and local time description
        assert "local time" in time_str

    def test_math_tool_execution(self):
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        res = agent._execute_tool("calculate_math", "12 + 18")
        assert "Calculation Result: 30" in res

        res_err = agent._execute_tool("calculate_math", "invalid expression")
        assert "Error evaluating expression" in res_err

    def test_time_tool_execution(self):
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        res = agent._execute_tool("get_current_time", "")
        assert "Current Time:" in res


class TestWebTraversalIntegration:
    """Tests for web search and fetch traversal execution inside agent_refactored"""

    @patch("core.agent_refactored.search_web")
    def test_web_search_execution(self, mock_search):
        mock_search.return_value = [
            {"title": "Result 1", "url": "https://r1.com", "snippet": "Snippet 1"},
            {"title": "Result 2", "url": "https://r2.com", "snippet": "Snippet 2"}
        ]
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        res = agent._execute_tool("web_search", "query")
        
        assert "Result 1" in res
        assert "https://r1.com" in res
        assert "Snippet 2" in res
        mock_search.assert_called_once_with("query")

    @patch("core.agent_refactored.search_web")
    def test_web_search_empty_execution(self, mock_search):
        mock_search.return_value = []
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        res = agent._execute_tool("web_search", "query")
        assert "No search results found" in res

    @patch("core.agent_refactored.fetch_web_page")
    def test_web_fetch_short_execution(self, mock_fetch):
        mock_fetch.return_value = ("short page content", [{"url": "https://link.com", "text": "link text"}])
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        res = agent._execute_tool("web_fetch", "https://test.com")
        
        assert "Raw web page text content" in res
        assert "short page content" in res
        mock_fetch.assert_called_once_with("https://test.com")

    @patch("core.agent_refactored.fetch_web_page")
    @patch("core.agent_refactored.RAGAgent._summarize_web_content")
    def test_web_fetch_long_execution_summarizes(self, mock_summarize, mock_fetch):
        long_content = "x" * 2000
        mock_fetch.return_value = (long_content, [])
        mock_summarize.return_value = "This is a summary of the long content."
        mock_engine = Mock()
        agent = RAGAgent(mock_engine)
        
        res = agent._execute_tool("web_fetch", "https://longtest.com")
        assert "LLM Summary of https://longtest.com" in res
        assert "This is a summary" in res
        mock_summarize.assert_called_once_with("https://longtest.com", long_content, "")


class TestAgentRouting:
    """Tests for retriever awareness and dynamic query routing"""

    def test_routing_awareness_retrieves_sources_and_chunks(self):
        """Should query retriever for unique sources and chunk count to develop awareness"""
        mock_engine = MagicMock()
        mock_engine.retriever.get_sources.return_value = ["file1.pdf", "file2.txt"]
        mock_engine.retriever.get_count.return_value = 150
        mock_engine.get_memory.return_value = Mock(get_active_context=Mock(return_value=""))
        
        # Mock LLM call to return DIRECT route to make it exit early
        mock_response = MagicMock()
        mock_response.choices = [Mock(message=Mock(content='{"route": "DIRECT", "reasoning": "testing awareness"}'))]
        mock_engine.client.chat.completions.create.return_value = mock_response

        agent = RAGAgent(mock_engine)
        events = list(agent.run_stream("test query"))

        # Verify retriever awareness calls were made
        mock_engine.retriever.get_sources.assert_called_once()
        mock_engine.retriever.get_count.assert_called_once()

        # Verify routing decision event was emitted with correct sources metadata
        routing_event = next(e for e in events if e.get("event") == "routing_decision")
        assert routing_event["route"] == "DIRECT"
        assert routing_event["reasoning"] == "testing awareness"
        assert routing_event["sources_count"] == 2
        assert routing_event["chunks_count"] == 150

    def test_routing_decision_direct_route_conversational(self):
        """Simple greetings bypass LLM call and are routed DIRECT"""
        mock_engine = MagicMock()
        mock_engine.get_memory.return_value = Mock(get_active_context=Mock(return_value=""))
        
        agent = RAGAgent(mock_engine)
        events = list(agent.run_stream("hello"))
        
        # Verify LLM chat completions was NOT called for routing analysis
        mock_engine.client.chat.completions.create.assert_not_called()
        
        routing_event = next(e for e in events if e.get("event") == "routing_decision")
        assert routing_event["route"] == "DIRECT"
        assert "greeting" in routing_event["reasoning"].lower()

    def test_routing_decision_kb_route(self):
        """If routed strictly to KNOWLEDGE_BASE, web tools are excluded from system prompt and execution"""
        mock_engine = MagicMock()
        mock_engine.get_memory.return_value = Mock(get_active_context=Mock(return_value=""))
        
        # Mock LLM routing call
        mock_response = MagicMock()
        mock_response.choices = [Mock(message=Mock(content='{"route": "KNOWLEDGE_BASE", "reasoning": "strictly local concepts"}'))]
        mock_engine.client.chat.completions.create.return_value = mock_response
        
        agent = RAGAgent(mock_engine)
        
        # We manually run routing by starting run_stream
        generator = agent.run_stream("What is Java Collection framework?")
        
        # Consume up to the routing decision event
        events = []
        for e in generator:
            events.append(e)
            if e.get("event") == "routing_decision":
                break
        
        # Advance generator to execute the tool exclusion logic
        try:
            next(generator)
        except StopIteration:
            pass
        
        # Verify WEB tools are excluded from agent allowed tools list
        assert "search_knowledge_base" in agent._allowed_tools
        assert "web_search" not in agent._allowed_tools
        assert "web_fetch" not in agent._allowed_tools
        
        # Check system prompt includes the KNOWLEDGE_BASE rule
        assert "ONLY use the local knowledge base tools" in agent.system_prompt
        tools_section = agent.system_prompt.split("Available tools:")[1].split("Strict rules:")[0]
        assert "web_search" not in tools_section

        # Verify trying to execute web_search raises allowed tools error
        result = agent.execute_tool_with_retry("web_search", "some query")
        assert result.success is False
        assert "not allowed for the selected route" in result.error

    def test_routing_decision_web_route(self):
        """If routed strictly to WEB, knowledge base tools are excluded from system prompt and execution"""
        mock_engine = MagicMock()
        mock_engine.get_memory.return_value = Mock(get_active_context=Mock(return_value=""))
        
        # Mock LLM routing call
        mock_response = MagicMock()
        mock_response.choices = [Mock(message=Mock(content='{"route": "WEB", "reasoning": "latest news"}'))]
        mock_engine.client.chat.completions.create.return_value = mock_response
        
        agent = RAGAgent(mock_engine)
        generator = agent.run_stream("latest news today")
        
        # Consume up to the routing decision event
        for e in generator:
            if e.get("event") == "routing_decision":
                break
                
        # Advance generator to execute the tool exclusion logic
        try:
            next(generator)
        except StopIteration:
            pass

        # Verify KNOWLEDGE_BASE tool is excluded
        assert "web_search" in agent._allowed_tools
        assert "search_knowledge_base" not in agent._allowed_tools
        
        # Check system prompt includes the WEB rule
        assert "ONLY use live web search tools" in agent.system_prompt
        
        # Verify trying to execute search_knowledge_base returns validation error
        result = agent.execute_tool_with_retry("search_knowledge_base", "some query")
        assert result.success is False
        assert "not allowed for the selected route" in result.error

    def test_routing_fallback_to_hybrid(self):
        """If LLM routing call fails or returns invalid JSON, fallback to HYBRID with all tools allowed"""
        mock_engine = MagicMock()
        mock_engine.get_memory.return_value = Mock(get_active_context=Mock(return_value=""))
        
        # Mock LLM routing call with invalid JSON
        mock_response = MagicMock()
        mock_response.choices = [Mock(message=Mock(content='invalid-json-content'))]
        mock_engine.client.chat.completions.create.return_value = mock_response
        
        agent = RAGAgent(mock_engine)
        generator = agent.run_stream("some complex query")
        
        events = []
        for e in generator:
            events.append(e)
            if e.get("event") == "routing_decision":
                break
                
        # Advance generator to execute the tool exclusion logic
        try:
            next(generator)
        except StopIteration:
            pass

        routing_event = next(e for e in events if e.get("event") == "routing_decision")
        assert routing_event["route"] == "HYBRID"
        
        # Verify both tools are allowed
        assert "search_knowledge_base" in agent._allowed_tools
        assert "web_search" in agent._allowed_tools
        assert "cross-reference findings from the local knowledge base" in agent.system_prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

