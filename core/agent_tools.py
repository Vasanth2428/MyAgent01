"""
================================================================================
RAG AGENT - TOOL DEFINITIONS & REGISTRY
================================================================================
Declarative tool definitions and tool registry for ReAct agent.
Enables runtime tool registration, validation, and metrics collection.

NOTE: Retrieval is NOT a tool here - it's infrastructure that happens 
before agent execution in the retrieval-first architecture.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, Any, Optional, List
from enum import Enum
import logging

logger = logging.getLogger("RAG.ToolRegistry")


class ToolType(Enum):
    """Categorizes tools for routing and timeout management"""
    WEB = "web"
    SYSTEM = "system"
    CHAT = "chat"


@dataclass
class ToolDefinition:
    """Declarative tool specification"""
    name: str
    description: str
    tool_type: ToolType
    required_args: List[str]
    optional_args: List[str] = field(default_factory=list)
    timeout_seconds: int = 30
    retry_count: int = 2
    max_arg_length: int = 1000
    allow_empty_arg: bool = False
    example: str = ""

    def __post_init__(self):
        """Validate tool definition"""
        if not self.name or not self.description:
            raise ValueError("Tool name and description are required")
        if self.timeout_seconds < 5:
            raise ValueError("Timeout must be >= 5 seconds")


class ToolRegistry:
    """Registry for tool definitions and metadata"""

    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}
        self.metrics: Dict[str, ToolMetrics] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        """Register built-in tools - NO KNOWLEDGE_BASE TOOL here!
        
        Retrieval is infrastructure, not a tool choice.
        """
        self.register(ToolDefinition(
            name="web_search",
            description="Searches the web for public facts, news, and details using DuckDuckGo. Use this to find live web data.",
            tool_type=ToolType.WEB,
            required_args=["query"],
            timeout_seconds=10,
            retry_count=2,
            max_arg_length=200,
            example="web_search[artificial intelligence trends 2024]"
        ))

        self.register(ToolDefinition(
            name="web_fetch",
            description="Fetches and extracts main text content from a web page URL. Use this to navigate and inspect details on web pages.",
            tool_type=ToolType.WEB,
            required_args=["url"],
            timeout_seconds=15,
            retry_count=1,
            max_arg_length=2048,
            example="web_fetch[https://example.com/article]"
        ))

        self.register(ToolDefinition(
            name="get_system_stats",
            description="Returns current CPU usage, RAM usage, and total indexed documents.",
            tool_type=ToolType.SYSTEM,
            required_args=[],
            optional_args=[],
            timeout_seconds=5,
            retry_count=0,
            allow_empty_arg=True,
            example="get_system_stats[]"
        ))

        self.register(ToolDefinition(
            name="calculate_math",
            description="Evaluates a mathematical expression safely. Supports basic operators like +, -, *, /, **, and parentheses. Use this for performing math calculations or evaluating expressions.",
            tool_type=ToolType.SYSTEM,
            required_args=["expression"],
            timeout_seconds=5,
            retry_count=0,
            max_arg_length=200,
            example="calculate_math[2 + 2 * (10 / 5)]"
        ))

        self.register(ToolDefinition(
            name="get_current_time",
            description="Returns the current local date, time, and timezone description. Use this when the user asks for the current date, time, year, or relative time-based queries.",
            tool_type=ToolType.SYSTEM,
            required_args=[],
            optional_args=[],
            timeout_seconds=5,
            retry_count=0,
            allow_empty_arg=True,
            example="get_current_time[]"
        ))

        # NOTE: direct_response is ONLY for casual chat mode
        # It should NOT be used to bypass grounding in STRICT_RAG pipeline

    def register(self, tool_def: ToolDefinition) -> None:
        """Register a new tool"""
        if tool_def.name in self.tools:
            logger.warning(f"Overwriting existing tool: {tool_def.name}")
        self.tools[tool_def.name] = tool_def
        self.metrics[tool_def.name] = ToolMetrics(tool_def.name)
        logger.info(f"Tool registered: {tool_def.name}")

    def get_tool(self, tool_name: str) -> Optional[ToolDefinition]:
        """Retrieve tool definition"""
        return self.tools.get(tool_name)

    def list_tools(self) -> List[ToolDefinition]:
        """Get all registered tools"""
        return list(self.tools.values())

    def generate_system_prompt(self, excluded_types: Optional[List[ToolType]] = None,
                                route: str = None) -> str:
        """Generate system prompt from tool registry, optionally filtering tool types."""
        excluded_types = excluded_types or []
        filtered_tools = [t for t in self.list_tools() if t.tool_type not in excluded_types]
        
        tools_desc = "\n".join([
            f"{i+1}. {tool.name}[{', '.join(tool.required_args)}]: {tool.description}"
            for i, tool in enumerate(filtered_tools)
        ])
        
        # Customize synthesis instruction based on route
        if route == "STRICT_RAG":
            synthesis_instruction = (
                "CRITICAL: The retrieval phase has already completed. "
                "You are given pre-retrieved context. Synthesize the answer "
                "using ONLY that context. Do not attempt additional retrieval - "
                "retrieval is infrastructure, not a tool choice."
            )
        elif route == "WEB_AGENT":
            synthesis_instruction = "You must ONLY use live web search tools."
        elif ToolType.WEB in excluded_types:
            synthesis_instruction = "Note: Web tools are excluded. Local knowledge base retrieval happens as infrastructure before agent execution."
        else:
            synthesis_instruction = "Use web tools to find live public information. Note: Local knowledge base retrieval is NOT a tool - it happens as infrastructure before agent execution."
        
        return f"""You are an advanced RAG Assistant with access to tools to help answer user questions.
You must solve the user's request step-by-step using a ReAct loop.
You must use the following format:

Thought: Write what you need to do next to answer the user query.
Action: tool_name[arguments]
Observation: The output result from the tool.
... (this loop can repeat at most 5 times)
Thought: I have enough information to write the final response.
Final Answer: Write the response to the user.

Available tools:
{tools_desc}

Strict rules:
1. ONLY call one tool at a time.
2. You MUST use the exact format "Action: tool_name[arguments]".
3. Do NOT put quotes or backticks around tool arguments.
4. If the tools do not return enough relevant information, state that you do not know in the Final Answer.
5. {synthesis_instruction}"""

    def validate_tool_argument(self, tool_name: str, arg: str) -> tuple[bool, Optional[str]]:
        """
        Validates tool argument against tool definition.
        Returns: (is_valid, error_message)
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return False, f"Unknown tool: {tool_name}"

        # Check empty argument
        if not arg.strip() and not tool.allow_empty_arg:
            return False, f"Tool {tool_name} requires a non-empty argument"

        # Check length
        if len(arg) > tool.max_arg_length:
            return False, f"Argument for {tool_name} exceeds max length ({len(arg)} > {tool.max_arg_length})"

        # Tool-specific validation
        if tool_name == "web_fetch":
            if not (arg.startswith("http://") or arg.startswith("https://")):
                return False, "URL must start with http:// or https://"

        return True, None

    def get_timeout(self, tool_name: str) -> int:
        """Get timeout for a tool"""
        tool = self.get_tool(tool_name)
        return tool.timeout_seconds if tool else 30

    def get_retry_count(self, tool_name: str) -> int:
        """Get retry count for a tool"""
        tool = self.get_tool(tool_name)
        return tool.retry_count if tool else 1

    def record_execution(self, tool_name: str, duration_ms: float, success: bool, error: Optional[str] = None):
        """Record tool execution metrics"""
        if tool_name in self.metrics:
            self.metrics[tool_name].record(duration_ms, success, error)


@dataclass
class ToolMetrics:
    """Tracks metrics for a single tool"""
    tool_name: str
    execution_count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_duration_ms: float = 0.0
    errors: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Percentage of successful executions"""
        if self.execution_count == 0:
            return 0.0
        return (self.success_count / self.execution_count) * 100

    @property
    def avg_duration_ms(self) -> float:
        """Average execution duration"""
        if self.execution_count == 0:
            return 0.0
        return self.total_duration_ms / self.execution_count

    def record(self, duration_ms: float, success: bool, error: Optional[str] = None):
        """Record an execution"""
        self.execution_count += 1
        self.total_duration_ms += duration_ms
        if success:
            self.success_count += 1
        else:
            self.error_count += 1
            if error and len(self.errors) < 10:  # Keep last 10 errors
                self.errors.append(error)

    def to_dict(self) -> dict:
        """Export metrics as dict"""
        return {
            "tool_name": self.tool_name,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "success_rate_percent": round(self.success_rate, 2),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "recent_errors": self.errors
        }