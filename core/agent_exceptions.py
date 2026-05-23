"""
================================================================================
RAG AGENT - CUSTOM EXCEPTIONS
================================================================================
Specific exception types for better error handling and debugging.
Replaces broad "except Exception" pattern.
"""


class RAGAgentException(Exception):
    """Base exception for RAG Agent"""
    pass


class ToolExecutionError(RAGAgentException):
    """Raised when a tool execution fails"""
    def __init__(self, tool_name: str, message: str, original_error: Exception = None):
        self.tool_name = tool_name
        self.message = message
        self.original_error = original_error
        super().__init__(f"Tool '{tool_name}' failed: {message}")


class ToolTimeoutError(ToolExecutionError):
    """Raised when a tool exceeds its timeout"""
    def __init__(self, tool_name: str, timeout_seconds: int):
        super().__init__(
            tool_name, 
            f"Execution timed out after {timeout_seconds} seconds"
        )
        self.timeout_seconds = timeout_seconds


class ToolValidationError(ToolExecutionError):
    """Raised when tool argument validation fails"""
    def __init__(self, tool_name: str, message: str):
        super().__init__(tool_name, f"Validation failed: {message}")


class ToolNotFoundError(ToolExecutionError):
    """Raised when a tool is not registered"""
    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(tool_name, f"Tool not found: {tool_name}")


class ActionParseError(RAGAgentException):
    """Raised when ReAct action parsing fails"""
    def __init__(self, text: str, message: str = "Could not parse action"):
        self.text = text
        super().__init__(f"{message}. Text: {text[:100]}")


class LLMCallError(RAGAgentException):
    """Raised when LLM API call fails"""
    def __init__(self, model: str, message: str, original_error: Exception = None):
        self.model = model
        self.message = message
        self.original_error = original_error
        super().__init__(f"LLM '{model}' error: {message}")


class LLMTimeoutError(LLMCallError):
    """Raised when LLM call exceeds timeout"""
    def __init__(self, model: str, timeout_seconds: int):
        super().__init__(model, f"Request timed out after {timeout_seconds} seconds")
        self.timeout_seconds = timeout_seconds


class ContextOverflowError(RAGAgentException):
    """Raised when context exceeds token limits"""
    def __init__(self, tokens_used: int, limit: int):
        self.tokens_used = tokens_used
        self.limit = limit
        super().__init__(
            f"Context overflow: {tokens_used} tokens exceeds limit of {limit}"
        )


class InvalidQueryError(RAGAgentException):
    """Raised when user query is invalid"""
    def __init__(self, query: str, reason: str):
        self.query = query
        self.reason = reason
        super().__init__(f"Invalid query: {reason}")


class RetryExhaustedError(ToolExecutionError):
    """Raised when tool retries are exhausted"""
    def __init__(self, tool_name: str, retry_count: int, last_error: str):
        self.retry_count = retry_count
        self.last_error = last_error
        super().__init__(
            tool_name,
            f"Failed after {retry_count} retries. Last error: {last_error}"
        )


# Mapping of exception types to retry strategies
RETRYABLE_ERRORS = {
    ToolTimeoutError,
    LLMTimeoutError,
}

NON_RETRYABLE_ERRORS = {
    ToolValidationError,
    ActionParseError,
    ToolNotFoundError,
    InvalidQueryError,
}
