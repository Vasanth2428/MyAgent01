"""
================================================================================
UNIT TESTS: core/agent_exceptions.py
================================================================================
Tests for exception hierarchy and error handling utilities.
"""

import pytest
from core.agent_exceptions import (
    RAGAgentException, ToolExecutionError, ToolTimeoutError,
    ToolValidationError, ToolNotFoundError, ActionParseError,
    LLMCallError, LLMTimeoutError, ContextOverflowError,
    InvalidQueryError, RetryExhaustedError, RETRYABLE_ERRORS,
    NON_RETRYABLE_ERRORS
)


class TestExceptionHierarchy:
    """Tests for exception inheritance"""

    def test_all_exceptions_inherit_from_base(self):
        """All custom exceptions should inherit from RAGAgentException"""
        exceptions = [
            ToolExecutionError, ToolTimeoutError, ToolValidationError,
            ToolNotFoundError, ActionParseError, LLMCallError,
            LLMTimeoutError, ContextOverflowError, InvalidQueryError,
            RetryExhaustedError
        ]
        
        for exc_class in exceptions:
            assert issubclass(exc_class, RAGAgentException)

    def test_tool_exceptions_inherit_from_tool_execution_error(self):
        """Tool-specific exceptions should inherit from ToolExecutionError"""
        exceptions = [
            ToolTimeoutError, ToolValidationError, ToolNotFoundError,
            RetryExhaustedError
        ]
        
        for exc_class in exceptions:
            assert issubclass(exc_class, ToolExecutionError)

    def test_llm_timeout_inherits_from_llm_call_error(self):
        """LLMTimeoutError should inherit from LLMCallError"""
        assert issubclass(LLMTimeoutError, LLMCallError)


class TestToolExecutionError:
    """Tests for ToolExecutionError"""

    def test_creation_with_message(self):
        """Should create with tool name and message"""
        error = ToolExecutionError("web_search", "Connection timeout")
        
        assert error.tool_name == "web_search"
        assert error.message == "Connection timeout"
        assert "web_search" in str(error)
        assert "Connection timeout" in str(error)

    def test_creation_with_original_error(self):
        """Should store original exception"""
        original = ValueError("Invalid value")
        error = ToolExecutionError("tool", "Failed", original_error=original)
        
        assert error.original_error is original
        assert isinstance(error.original_error, ValueError)

    def test_string_representation(self):
        """Should have readable string representation"""
        error = ToolExecutionError("kb_search", "No results")
        
        assert "kb_search" in str(error)
        assert "No results" in str(error)


class TestToolTimeoutError:
    """Tests for ToolTimeoutError"""

    def test_creation_with_timeout(self):
        """Should create with tool name and timeout value"""
        error = ToolTimeoutError("web_fetch", timeout_seconds=30)
        
        assert error.tool_name == "web_fetch"
        assert error.timeout_seconds == 30
        assert "timed out" in str(error).lower()
        assert "30" in str(error)

    def test_inherits_from_tool_execution_error(self):
        """Should be instance of ToolExecutionError"""
        error = ToolTimeoutError("tool", timeout_seconds=10)
        
        assert isinstance(error, ToolExecutionError)


class TestToolValidationError:
    """Tests for ToolValidationError"""

    def test_creation_with_validation_message(self):
        """Should create with tool name and validation message"""
        error = ToolValidationError("web_fetch", "URL must start with http://")
        
        assert error.tool_name == "web_fetch"
        assert "URL must start with http://" in str(error)

    def test_string_representation(self):
        """Should mention validation failure"""
        error = ToolValidationError("tool", "Invalid format")
        
        assert "Validation failed" in str(error)


class TestToolNotFoundError:
    """Tests for ToolNotFoundError"""

    def test_creation_with_tool_name(self):
        """Should create with missing tool name"""
        error = ToolNotFoundError("unknown_tool")
        
        assert error.tool_name == "unknown_tool"
        assert "unknown_tool" in str(error)
        assert "not found" in str(error).lower()


class TestActionParseError:
    """Tests for ActionParseError"""

    def test_creation_with_text(self):
        """Should create with malformed action text"""
        text = "This is not a valid action: foo bar baz"
        error = ActionParseError(text, "Could not find Action: keyword")
        
        assert error.text == text
        assert "Could not find Action:" in str(error)

    def test_truncates_long_text(self):
        """Should truncate very long text in representation"""
        long_text = "x" * 200
        error = ActionParseError(long_text)
        
        error_str = str(error)
        # Should be truncated
        assert len(error_str) < len(long_text) + 50


class TestLLMCallError:
    """Tests for LLMCallError"""

    def test_creation_with_model_and_message(self):
        """Should create with model name and error message"""
        error = LLMCallError("gpt-4", "API rate limit exceeded")
        
        assert error.model == "gpt-4"
        assert error.message == "API rate limit exceeded"
        assert "gpt-4" in str(error)

    def test_creation_with_original_error(self):
        """Should store original exception"""
        original = ConnectionError("Network unreachable")
        error = LLMCallError("llama-7b", "Connection failed", original_error=original)
        
        assert error.original_error is original


class TestLLMTimeoutError:
    """Tests for LLMTimeoutError"""

    def test_creation_with_timeout(self):
        """Should create with model and timeout"""
        error = LLMTimeoutError("gpt-4", timeout_seconds=60)
        
        assert error.model == "gpt-4"
        assert error.timeout_seconds == 60
        assert "timed out" in str(error).lower()
        assert "60" in str(error)

    def test_inherits_from_llm_call_error(self):
        """Should be instance of LLMCallError"""
        error = LLMTimeoutError("model", timeout_seconds=30)
        
        assert isinstance(error, LLMCallError)


class TestContextOverflowError:
    """Tests for ContextOverflowError"""

    def test_creation_with_token_counts(self):
        """Should create with token usage and limit"""
        error = ContextOverflowError(tokens_used=2500, limit=2048)
        
        assert error.tokens_used == 2500
        assert error.limit == 2048
        assert "2500" in str(error)
        assert "2048" in str(error)
        assert "overflow" in str(error).lower()


class TestInvalidQueryError:
    """Tests for InvalidQueryError"""

    def test_creation_with_query_and_reason(self):
        """Should create with query and reason"""
        query = "SELECT * FROM users"
        error = InvalidQueryError(query, "SQL injection detected")
        
        assert error.query == query
        assert error.reason == "SQL injection detected"
        assert "SQL injection" in str(error)


class TestRetryExhaustedError:
    """Tests for RetryExhaustedError"""

    def test_creation_with_retry_info(self):
        """Should create with retry count and last error"""
        error = RetryExhaustedError("web_search", retry_count=3, last_error="Timeout")
        
        assert error.tool_name == "web_search"
        assert error.retry_count == 3
        assert error.last_error == "Timeout"
        assert "3" in str(error)
        assert "Timeout" in str(error)


class TestRetryableErrorClassification:
    """Tests for error classification (retryable vs non-retryable)"""

    def test_retryable_errors(self):
        """Should classify transient errors as retryable"""
        assert ToolTimeoutError in RETRYABLE_ERRORS
        assert LLMTimeoutError in RETRYABLE_ERRORS

    def test_non_retryable_errors(self):
        """Should classify permanent errors as non-retryable"""
        assert ToolValidationError in NON_RETRYABLE_ERRORS
        assert ActionParseError in NON_RETRYABLE_ERRORS
        assert ToolNotFoundError in NON_RETRYABLE_ERRORS
        assert InvalidQueryError in NON_RETRYABLE_ERRORS

    def test_retryable_vs_non_retryable_exclusive(self):
        """Retryable and non-retryable should be separate"""
        assert len(RETRYABLE_ERRORS & NON_RETRYABLE_ERRORS) == 0


class TestExceptionUsagePatterns:
    """Tests for realistic exception usage patterns"""

    def test_exception_chaining(self):
        """Should support exception chaining"""
        try:
            try:
                raise ValueError("Original error")
            except ValueError as e:
                raise ToolExecutionError("my_tool", "Failed to execute", original_error=e)
        except ToolExecutionError as outer:
            assert outer.original_error is not None
            assert isinstance(outer.original_error, ValueError)

    def test_catching_by_parent_class(self):
        """Should be catchable by parent class"""
        error = ToolTimeoutError("tool", timeout_seconds=10)
        
        # Should be catchable as ToolExecutionError
        try:
            raise error
        except ToolExecutionError as e:
            assert e.tool_name == "tool"

    def test_retry_decision_logic(self):
        """Should enable retry decision logic"""
        errors_to_test = [
            (ToolTimeoutError("tool", 10), True),
            (LLMTimeoutError("model", 30), True),
            (ToolValidationError("tool", "Invalid"), False),
            (ActionParseError("text"), False),
        ]
        
        for error, should_retry in errors_to_test:
            error_type = type(error)
            can_retry = error_type in RETRYABLE_ERRORS
            assert can_retry == should_retry, f"Failed for {error_type}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
