"""
================================================================================
RAG AGENT - REFACTORED WITH BEST PRACTICES
================================================================================
Improved ReAct agent with:
- Tool registry pattern (no more hardcoded tools)
- Specific exception types (better error handling)
- Input validation (security)
- Structured logging (observability)
- Comprehensive type hints
- Timeout management
- Retry logic with exponential backoff
"""

import re
import logging
import psutil
import asyncio
import time
import ast
import operator
from datetime import datetime
from typing import Dict, Generator, Optional, List, Tuple, Any
from dataclasses import dataclass
import tiktoken

import requests

from core.config import (
    TOKENIZER_ENCODING, COST_PER_INPUT_TOKEN, COST_PER_OUTPUT_TOKEN, AGENT_CONFIG
)
from core.web_traversal import search_web, fetch_web_page
from core.agent_tools import ToolRegistry, ToolType
from core.agent_exceptions import (
    ToolExecutionError, ToolTimeoutError, ToolValidationError, 
    ActionParseError, LLMCallError, InvalidQueryError, RetryExhaustedError
)

logger = logging.getLogger("RAG.Agent")
tokenizer = tiktoken.get_encoding(TOKENIZER_ENCODING)


def count_tokens(text: str) -> int:
    """Counts exact BPE tokens for a given string."""
    if not text:
        return 0
    return len(tokenizer.encode(text))


def safe_math_eval(expr: str) -> float:
    """Evaluates mathematical expressions safely without raw eval."""
    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }
    
    def eval_node(node):
        if isinstance(node, ast.Num):  # python < 3.8 support
            return node.n
        elif isinstance(node, ast.Constant):  # python >= 3.8 support
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Unsupported constant type: {type(node.value)}")
        elif isinstance(node, ast.BinOp):
            left = eval_node(node.left)
            right = eval_node(node.right)
            op_type = type(node.op)
            if op_type not in operators:
                raise ValueError(f"Unsupported operator: {op_type}")
            # Prevent overflow / CPU hanging with very large exponents
            if op_type == ast.Pow:
                if right > 100 or left > 1e10:
                    raise ValueError("Exponent or base too large")
            return operators[op_type](left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = eval_node(node.operand)
            op_type = type(node.op)
            if op_type not in operators:
                raise ValueError(f"Unsupported unary operator: {op_type}")
            return operators[op_type](operand)
        else:
            raise ValueError(f"Unsupported syntax tree element: {type(node)}")

    # Clean expression and parse
    expr = expr.strip()
    try:
        tree = ast.parse(expr, mode='eval')
        return eval_node(tree.body)
    except Exception as e:
        raise ValueError(f"Invalid math expression: {e}")


def format_current_time() -> str:
    """Returns the current local date and time formatted string."""
    now = datetime.now()
    return now.strftime("%A, %B %d, %Y, %H:%M:%S (local time)")


@dataclass
class ToolResult:
    """Result of a tool execution"""
    tool_name: str
    success: bool
    content: str
    duration_ms: float
    error: Optional[str] = None
    retries_used: int = 0


class RAGAgent:
    """
    Autonomous ReAct agent with professional-grade error handling and observability.
    """

    def __init__(self, engine: "AgenticSystem", tool_registry: Optional[ToolRegistry] = None):
        """
        Initialize the RAG Agent.
        
        Args:
            engine: Reference to the AgenticSystem orchestrator
            tool_registry: Custom tool registry (defaults to built-in tools)
        """
        self.engine = engine
        self.tool_registry = tool_registry or ToolRegistry()
        self.max_iterations = AGENT_CONFIG["max_iterations"]
        self.llm_timeout = AGENT_CONFIG["default_llm_timeout_seconds"]
        
        # Initialize system prompt from registry
        self.system_prompt = self.tool_registry.generate_system_prompt()
        self._allowed_tools = set(self.tool_registry.tools.keys())
        
        logger.info(f"RAG Agent initialized with {len(self.tool_registry.list_tools())} tools")

    def validate_query(self, query: str) -> Tuple[bool, Optional[str]]:
        """
        Validates user query before processing.
        
        Args:
            query: User query to validate
            
        Returns:
            (is_valid, error_message)
        """
        if not query or not query.strip():
            return False, "Query cannot be empty"
        
        query_len = len(query)
        max_len = AGENT_CONFIG["max_query_length"]
        min_len = AGENT_CONFIG["min_query_length"]
        
        if query_len < min_len:
            return False, f"Query too short (min {min_len} characters)"
        
        if query_len > max_len:
            return False, f"Query too long (max {max_len} characters)"
        
        # Check for injection patterns (basic checks)
        dangerous_patterns = [
            r"<script",  # XSS
            r"DROP\s+TABLE",  # SQL injection
            r";\s*DELETE",  # SQL injection
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return False, "Query contains potentially dangerous content"
        
        return True, None

    def parse_action(self, text: str) -> Optional[Tuple[str, str]]:
        """
        Parses ReAct action from LLM response.
        
        Format: Action: tool_name[arguments]
        
        Args:
            text: LLM response text
            
        Returns:
            (tool_name, tool_arg) or None if no action found
            
        Raises:
            ActionParseError: If action is malformed
        """
        # Match "Action: tool_name[arguments]" or "Action: tool_name" with optional brackets
        match = re.search(r"Action:\s*([\w\-]+)\s*(?:\[(.*?)\])?", text, re.IGNORECASE)
        
        if not match:
            return None
        
        tool_name = match.group(1).strip().lower()
        tool_arg = match.group(2) or ""
        tool_arg = tool_arg.strip()
        
        # Strip outer quotes/backticks if present
        if len(tool_arg) >= 2 and (
            (tool_arg.startswith('"') and tool_arg.endswith('"')) or
            (tool_arg.startswith("'") and tool_arg.endswith("'")) or
            (tool_arg.startswith("`") and tool_arg.endswith("`"))
        ):
            tool_arg = tool_arg[1:-1].strip()
        
        logger.debug(f"Parsed action: tool={tool_name}, arg_len={len(tool_arg)}")
        return tool_name, tool_arg

    def execute_tool_with_retry(
        self, 
        tool_name: str, 
        tool_arg: str,
        session_id: str = "default"
    ) -> ToolResult:
        """
        Executes a tool with automatic retry and backoff on transient failures.
        
        Args:
            tool_name: Name of the tool to execute
            tool_arg: Argument to pass to the tool
            session_id: Session identifier for logging
            
        Returns:
            ToolResult with execution details
        """
        # Validate tool exists
        tool_def = self.tool_registry.get_tool(tool_name)
        if not tool_def:
            logger.error(f"Tool not found: {tool_name}")
            
            # Record metrics for unknown tool
            error_msg = f"Tool '{tool_name}' not found"
            if tool_name in self.tool_registry.metrics:
                self.tool_registry.record_execution(tool_name, 0, success=False, error=error_msg)
            
            return ToolResult(
                tool_name=tool_name,
                success=False,
                content="",
                duration_ms=0,
                error=error_msg
            )
        
        # Enforce routing tool restrictions
        if tool_name not in self._allowed_tools:
            logger.warning(f"Tool execution forbidden: {tool_name} is not allowed for the selected route.")
            error_msg = f"Execution of tool '{tool_name}' is not allowed for the selected route."
            self.tool_registry.record_execution(tool_name, 0, success=False, error=error_msg)
            return ToolResult(
                tool_name=tool_name,
                success=False,
                content="",
                duration_ms=0,
                error=error_msg
            )
        
        # Validate argument
        is_valid, error_msg = self.tool_registry.validate_tool_argument(tool_name, tool_arg)
        if not is_valid:
            logger.warning(f"Tool argument validation failed for {tool_name}: {error_msg}")
            
            # Record metrics even for validation failures
            self.tool_registry.record_execution(tool_name, 0, success=False, error=error_msg)
            
            return ToolResult(
                tool_name=tool_name,
                success=False,
                content="",
                duration_ms=0,
                error=f"Argument validation failed: {error_msg}"
            )
        
        # Execute with retry logic
        retry_count = 0
        max_retries = AGENT_CONFIG["default_retry_count"]
        last_error = None
        
        while retry_count <= max_retries:
            try:
                start_time = time.time()
                
                # Execute the tool
                result_content = self._execute_tool(tool_name, tool_arg)
                
                duration_ms = (time.time() - start_time) * 1000
                
                logger.info(
                    "tool_execution",
                    extra={
                        "tool_name": tool_name,
                        "duration_ms": duration_ms,
                        "success": True,
                        "retries": retry_count,
                        "session_id": session_id
                    }
                )
                
                # Record metrics
                self.tool_registry.record_execution(tool_name, duration_ms, success=True)
                
                return ToolResult(
                    tool_name=tool_name,
                    success=True,
                    content=result_content,
                    duration_ms=duration_ms,
                    retries_used=retry_count
                )
            
            except ToolTimeoutError as e:
                last_error = str(e)
                logger.warning(
                    f"Tool timeout (retry {retry_count+1}/{max_retries+1}): {tool_name}",
                    extra={"tool_name": tool_name, "retry_count": retry_count}
                )
                retry_count += 1
                
                if retry_count <= max_retries:
                    # Exponential backoff
                    backoff_delay = min(
                        AGENT_CONFIG["max_retry_delay_seconds"],
                        (AGENT_CONFIG["retry_backoff_factor"] ** retry_count)
                    )
                    time.sleep(backoff_delay)
            
            except (ToolExecutionError, LLMCallError) as e:
                last_error = str(e)
                logger.error(f"Tool execution error: {tool_name}: {last_error}")
                
                # Non-transient errors don't retry
                self.tool_registry.record_execution(tool_name, 0, success=False, error=last_error)
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    content="",
                    duration_ms=0,
                    error=last_error,
                    retries_used=retry_count
                )
            
            except Exception as e:
                last_error = str(e)
                logger.error(f"Unexpected error in tool {tool_name}: {last_error}", exc_info=True)
                
                self.tool_registry.record_execution(tool_name, 0, success=False, error=last_error)
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    content="",
                    duration_ms=0,
                    error=f"Unexpected error: {last_error}",
                    retries_used=retry_count
                )
        
        # Exhausted retries
        logger.error(f"Retries exhausted for tool {tool_name}: {last_error}")
        self.tool_registry.record_execution(tool_name, 0, success=False, error=last_error)
        
        return ToolResult(
            tool_name=tool_name,
            success=False,
            content="",
            duration_ms=0,
            error=f"Failed after {max_retries} retries: {last_error}",
            retries_used=max_retries
        )

    def _execute_tool(self, tool_name: str, tool_arg: str) -> str:
        """
        Internal tool execution method. Can be mocked for testing.
        
        Args:
            tool_name: Tool to execute
            tool_arg: Tool argument
            
        Returns:
            Tool output
            
        Raises:
            ToolTimeoutError, ToolExecutionError, LLMCallError
        """
        # Resolve timeout
        timeout = AGENT_CONFIG["tool_timeouts"].get(tool_name)
        if timeout is None:
            tool_def = self.tool_registry.get_tool(tool_name)
            if tool_def:
                timeout = AGENT_CONFIG["tool_timeouts"].get(tool_def.tool_type.value)
                if timeout is None:
                    timeout = tool_def.timeout_seconds
        if timeout is None:
            timeout = 30
        
        try:
            if tool_name == "search_knowledge_base":
                result = self.engine.context_engine_subsystem.retrieve_and_compress(
                    query=tool_arg,
                    max_tokens=1000
                )
                return result or "No matching documents found."
            
            elif tool_name == "web_search":
                results = search_web(tool_arg, timeout=timeout)
                self._last_web_step = {
                    "type": "search",
                    "query": tool_arg,
                    "results": [{"title": r["title"], "url": r["url"]} for r in results]
                }
                if not results:
                    return "No search results found on DuckDuckGo."
                obs_list = []
                for idx, r in enumerate(results[:5]):
                    obs_list.append(f"[{idx+1}] Title: {r['title']}\nURL: {r['url']}\nSnippet: {r['snippet']}\n")
                return "\n".join(obs_list)
            
            elif tool_name == "web_fetch":
                text_content, links = fetch_web_page(tool_arg, timeout=timeout)
                if isinstance(text_content, str) and text_content.startswith("Error"):
                    self._last_web_step = {
                        "type": "fetch",
                        "url": tool_arg,
                        "status": "error",
                        "error": text_content
                    }
                    return f"Failed to fetch page content: {text_content}"
                
                from urllib.parse import urlparse
                domain = urlparse(tool_arg).netloc
                self._last_web_step = {
                    "type": "fetch",
                    "url": tool_arg,
                    "status": "success",
                    "title": f"Fetched {domain}",
                    "length": len(text_content)
                }
                if len(text_content) > 1500:
                    summary = self._summarize_web_content(tool_arg, text_content, "")
                    return f"LLM Summary of {tool_arg}:\n{summary}"
                return f"Raw web page text content from {tool_arg}:\n{text_content}"
            
            elif tool_name == "calculate_math":
                try:
                    res = safe_math_eval(tool_arg)
                    return f"Calculation Result: {res}"
                except Exception as eval_err:
                    return f"Error evaluating expression: {eval_err}"
            
            elif tool_name == "get_current_time":
                return f"Current Time: {format_current_time()}"
            
            elif tool_name == "get_system_stats":
                cpu = psutil.cpu_percent(interval=0.1)
                ram = psutil.virtual_memory()
                doc_count = self.engine.retriever.get_count()
                return f"CPU: {cpu}% | RAM: {ram.percent}% | Indexed Documents: {doc_count}"
            
            elif tool_name == "direct_response":
                return tool_arg
            
            else:
                raise ToolExecutionError(tool_name, f"Unknown tool: {tool_name}")
        
        except (TimeoutError, requests.exceptions.Timeout) as e:
            raise ToolTimeoutError(tool_name, timeout)
        except Exception as e:
            raise ToolExecutionError(tool_name, str(e), original_error=e)

    def _summarize_web_content(self, url: str, content: str, query: str) -> str:
        """
        Uses LLM to summarize web content relative to the user query.
        
        Args:
            url: Source URL
            content: Raw page content
            query: User query for context
            
        Returns:
            Summarized content
        """
        logger.info(f"Summarizing web content from {url}")
        
        summary_prompt = (
            f"Summarize this web content concisely:\n"
            f"Source: {url}\n"
            f"Content: {content[:2000]}\n"
            f"Focus on key facts and metrics."
        )
        
        try:
            response = self.engine.client.chat.completions.create(
                model=self.engine.llm_service.model,
                messages=[
                    {"role": "system", "content": "You are a precise summarizer."},
                    {"role": "user", "content": summary_prompt}
                ],
                temperature=0.2,
                max_tokens=500,
                timeout=self.llm_timeout
            )
            summary = response.choices[0].message.content.strip()
            return summary
        except Exception as e:
            logger.error(f"Error summarizing web content: {e}")
            return f"[Summary failed: {str(e)}]"

    def run_stream(
        self, 
        query: str, 
        session_id: str = "default",
        source_filter: Optional[str] = None,
        context_limit: Optional[int] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Executes the ReAct loop streaming events.
        
        Args:
            query: User query
            session_id: Session identifier
            source_filter: Optional document source filter
            context_limit: Optional token limit for context
            
        Yields:
            Event dictionaries with intermediate state
        """
        # Validate query
        is_valid, error_msg = self.validate_query(query)
        if not is_valid:
            logger.warning(f"Query validation failed: {error_msg}")
            yield {
                "event": "error",
                "text": f"Invalid query: {error_msg}"
            }
            return
        
        logger.info(f"Agent starting query: {query[:50]}... | session={session_id} | limit={context_limit}")
        
        # Get queries handled safely to support test mocks
        queries_handled = 0
        if hasattr(self.engine, "stats") and isinstance(self.engine.stats, dict):
            queries_handled = self.engine.stats.get("queries", 0)

        agent_steps = []
        traversal_path = []
        retrieved_contexts_accumulated = []
        eviction_log_accumulated = []

        def log_step(event):
            allowed_events = {
                "thought", "action", "observation", "planning", 
                "memory_retrieval", "context_assembly", "document_retrieval", 
                "web_traversal", "summarization", "inference", "synthesis",
                "routing_decision"
            }
            if event.get("event") in allowed_events:
                agent_steps.append(event)
            return event

        # 1. PLANNING phase
        yield log_step({"event": "planning", "text": f"Analyzing user query: '{query}' and planning step-by-step resolution."})

        # 2. MEMORY RETRIEVAL phase
        yield log_step({"event": "memory_retrieval", "text": f"Retrieving conversation history context for session '{session_id}'..."})
        memory = self.engine.get_memory(session_id)
        memory_text = memory.get_active_context()

        # 3. CONTEXT ASSEMBLY phase
        yield log_step({"event": "context_assembly", "text": "Verifying memory token boundaries and assembling primary prompt..."})

        # Get unique source filenames and chunk count for routing awareness
        try:
            sources = self.engine.retriever.get_sources()
            if not isinstance(sources, list):
                sources = []
            total_chunks = self.engine.retriever.get_count()
            if not isinstance(total_chunks, (int, float)):
                total_chunks = 0
        except Exception as e:
            logger.error(f"Error getting sources/chunks: {e}")
            sources = []
            total_chunks = 0

        # Perform routing analysis
        yield log_step({"event": "planning", "text": "Performing routing analysis and checking knowledge base awareness..."})

        # Default route configuration
        route = "HYBRID"
        reasoning = "Fallback to hybrid search due to routing analysis exception."

        # Greeting pre-check to bypass LLM routing call for simple greets to save latency
        clean_query = query.lower().strip()
        greetings = AGENT_CONFIG.get("greeting_words", ["hello", "hi", "hey"])
        conversational_words = AGENT_CONFIG.get("conversational_words", ["how", "are", "you"])
        has_conversational_word = any(w in clean_query.split() for w in conversational_words)
        is_short_chat = len(clean_query.split()) <= AGENT_CONFIG.get("short_chat_threshold", 3) and has_conversational_word
        
        is_greeting = clean_query in greetings or is_short_chat

        if is_greeting:
            route = "DIRECT"
            reasoning = "Query is a simple greeting or conversational phrase."
        else:
            routing_prompt = f"""You are the routing and intelligence subsystem of a RAG AI Agent.
Analyze the user's query and conversation history to determine the most efficient retrieval strategy.

Current system time/date: {format_current_time()}

Conversation History:
{memory_text}

User Query: {query}

Available local knowledge base sources (contains {len(sources)} unique files, total {total_chunks} chunks):
{", ".join(sources) if sources else "None (No documents uploaded yet)"}

You must route the query to one of the following strategies:
1. "DIRECT": Use this ONLY if the query is simple chit-chat, a greeting, or asks strictly about previous conversation history (e.g., "what was the last thing I said?"). DO NOT select DIRECT if the query is asking for factual, database, system stats, math, or file-specific information, even if you think you have pre-trained knowledge to answer it.
2. "KNOWLEDGE_BASE": Use this if the query asks about data, concepts, documents, database records, sales, networking, or any topics that might be covered in the available local files.
3. "WEB": Use this if the query requires up-to-date live information, public facts, news, time-sensitive data, or anything not covered in the local knowledge base.
4. "HYBRID": Use this if the query requires cross-referencing information between local files and the live web, or if there is ambiguity.

You MUST respond with a valid raw JSON object. Do not include markdown code block formatting (like ```json ... ```).
Response format:
{{
    "reasoning": "A concise explanation of why this route was chosen, mentioning what sources are needed, time-sensitivity, or conversational nature.",
    "route": "DIRECT" | "KNOWLEDGE_BASE" | "WEB" | "HYBRID"
}}
"""
            try:
                response = self.engine.client.chat.completions.create(
                    model=self.engine.llm_service.model,
                    messages=[
                        {"role": "system", "content": "You are a routing system. You must output ONLY a valid JSON block matching the requested schema."},
                        {"role": "user", "content": routing_prompt}
                    ],
                    temperature=0.0,
                    timeout=10
                )
                raw_response = response.choices[0].message.content.strip()
                
                # Clean markdown code blocks if present
                cleaned_response = raw_response
                if cleaned_response.startswith("```"):
                    lines = cleaned_response.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    cleaned_response = "\n".join(lines).strip()
                
                import json
                data = json.loads(cleaned_response)
                route = data.get("route", "HYBRID").upper()
                reasoning = data.get("reasoning", "No reasoning provided.")
                if route not in ["DIRECT", "KNOWLEDGE_BASE", "WEB", "HYBRID"]:
                    route = "HYBRID"
            except Exception as e:
                logger.error(f"Routing analysis failed, falling back to HYBRID: {e}")

        # Emit the routing decision event
        yield log_step({
            "event": "routing_decision",
            "text": f"Selected route: {route}. Reasoning: {reasoning}",
            "route": route,
            "reasoning": reasoning,
            "sources_count": len(sources),
            "chunks_count": total_chunks
        })

        # Set allowed tool types and restrict tools
        excluded_types = []
        if route == "KNOWLEDGE_BASE":
            excluded_types = [ToolType.WEB]
        elif route == "WEB":
            excluded_types = [ToolType.KNOWLEDGE_BASE]
        elif route == "DIRECT":
            excluded_types = [ToolType.WEB, ToolType.KNOWLEDGE_BASE]
            
        self.system_prompt = self.tool_registry.generate_system_prompt(excluded_types=excluded_types)
        self._allowed_tools = {
            t.name for t in self.tool_registry.list_tools() 
            if t.tool_type not in excluded_types
        }

        if route == "DIRECT":
            logger.info("Agent executing DIRECT route bypassing ReAct loop")
            yield log_step({"event": "thought", "text": f"Direct response decided. Reasoning: {reasoning}"})
            yield log_step({"event": "synthesis", "text": "Synthesizing direct conversation response."})
            
            direct_reply = ""
            if is_greeting:
                direct_reply = "Hello! How can I help you today? I'm ready to answer any questions about your documents."
                yield {"event": "answer_chunk", "text": direct_reply}
            else:
                direct_prompt = f"""You are an advanced RAG Assistant. Answer the user's question directly.
You do not need to use any tools.

Conversation History:
{memory_text}

User Query: {query}
"""
                try:
                    stream = self.engine.client.chat.completions.create(
                        model=self.engine.llm_service.model,
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant."},
                            {"role": "user", "content": direct_prompt}
                        ],
                        temperature=0.3,
                        stream=True
                    )
                    for chunk in stream:
                        delta = chunk.choices[0].delta.content or ""
                        if delta:
                            direct_reply += delta
                            yield {"event": "answer_chunk", "text": delta}
                except Exception as e:
                    logger.error(f"Error streaming direct response: {e}")
                    direct_reply = "I encountered an error while formulating my direct response."
                    yield {"event": "answer_chunk", "text": direct_reply}
            
            # Save to memory
            self.engine.save_memory(session_id, query, "user")
            
            # Telemetry for Direct Route
            prompt_tkn = count_tokens(query) if is_greeting else (count_tokens("You are a helpful assistant.") + count_tokens(direct_prompt))
            telemetry_data = {
                "query": query,
                "raw_prompt": query if is_greeting else direct_prompt,
                "overflow_occurred": False,
                "limit": context_limit,
                "initial_tokens": prompt_tkn,
                "final_tokens": prompt_tkn,
                "steps": [],
                "agent_steps": agent_steps,
                "budget_tracking": {
                    "memory_tokens_used": count_tokens(memory_text),
                    "memory_tokens_limit": 1500,
                    "document_tokens_used": 0,
                    "document_tokens_limit": 0
                },
                "compression_ratio": 1.0,
                "traversal_path": traversal_path,
                "routing": {
                    "route": route,
                    "reasoning": reasoning,
                    "sources_count": len(sources),
                    "chunks_count": total_chunks
                }
            }
            self.engine.save_memory(session_id, direct_reply, "assistant", 0.5, telemetry=telemetry_data)
            
            yield {
                "event": "done",
                "response": direct_reply,
                "stats": {
                    "queries_handled": queries_handled,
                    "cpu_usage_percent": psutil.cpu_percent(interval=None),
                    "memory_usage_percent": psutil.virtual_memory().percent,
                    "tps": 0,
                    "query_cost": "$0.00",
                    "raw_prompt": query if is_greeting else direct_prompt,
                    "overflow_telemetry": {
                        "overflow_occurred": False,
                        "limit": context_limit,
                        "initial_tokens": prompt_tkn,
                        "final_tokens": prompt_tkn,
                        "steps": []
                    },
                    "budget_tracking": {
                        "memory_tokens_used": count_tokens(memory_text),
                        "memory_tokens_limit": 1500,
                        "document_tokens_used": 0,
                        "document_tokens_limit": 0
                    },
                    "traversal_path": traversal_path,
                    "retrieved_context": [],
                    "eviction_log": [],
                    "tool_metrics": [m.to_dict() for m in self.tool_registry.metrics.values()],
                    "routing": {
                        "route": route,
                        "reasoning": reasoning,
                        "sources_count": len(sources),
                        "chunks_count": total_chunks
                    }
                }
            }
            return
        
        # Context overflow handling
        overflow_occurred = False
        overflow_steps = []
        agent_prompt_tokens = count_tokens(self.system_prompt) + count_tokens(memory_text) + count_tokens(query) + 50
        initial_tokens = agent_prompt_tokens

        if context_limit and agent_prompt_tokens > context_limit:
            overflow_occurred = True
            overflow_steps.append(
                f"🚨 [AGENT] OVERFLOW DETECTED: Agent prompt size ({agent_prompt_tokens} tokens) "
                f"exceeds limit ({context_limit} tokens) by {agent_prompt_tokens - context_limit} tokens."
            )
            # Prune memory
            old_mem = count_tokens(memory_text)
            temp_entries = list(memory.entries)
            pruned_count = 0
            while len(temp_entries) > 1 and agent_prompt_tokens > context_limit:
                removed = temp_entries.pop(0)
                pruned_count += 1
                temp_mem_text = "".join([f"[{e.role}]: {e.text}\n" for e in temp_entries])
                agent_prompt_tokens = count_tokens(self.system_prompt) + count_tokens(temp_mem_text) + count_tokens(query) + 50
            
            if pruned_count > 0:
                memory.entries = temp_entries
                memory_text = memory.get_active_context()
                new_mem = count_tokens(memory_text)
                overflow_steps.append(f"   - Evicted {pruned_count} oldest conversational turns. Memory reduced from {old_mem} to {new_mem} tokens.")
            else:
                overflow_steps.append("   - No memory turns available for eviction.")
                
            # If still overflowing, truncate user query
            if agent_prompt_tokens > context_limit:
                allowed_query_len = context_limit - count_tokens(self.system_prompt) - count_tokens(memory_text) - 60
                allowed_query_len = max(5, allowed_query_len)
                query_tokens = tokenizer.encode(query)
                query = tokenizer.decode(query_tokens[:allowed_query_len])
                agent_prompt_tokens = count_tokens(self.system_prompt) + count_tokens(memory_text) + count_tokens(query) + 50
                overflow_steps.append(f"   - Hard truncated user query to {count_tokens(query)} tokens.")
                
            overflow_steps.append(f"✅ [AGENT] RECOVERY COMPLETE: Agent context size is now {agent_prompt_tokens} tokens.")
            
            yield {
                "event": "overflow_detected",
                "limit": context_limit,
                "initial": initial_tokens,
                "final": agent_prompt_tokens,
                "steps": overflow_steps
            }
            for step in overflow_steps:
                yield {"event": "overflow_step", "text": step}
                time.sleep(0.1)

        scratchpad = ""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Active Conversation History:\n{memory_text}\n\nUser Question: {query}"}
        ]

        final_response = ""
        last_thought = ""
        final_answer_streamed = False
        is_direct_answer = False

        # ReAct loop
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            logger.debug(f"ReAct iteration {iteration}/{self.max_iterations}")
            
            current_messages = list(messages)
            if scratchpad:
                current_messages.append({"role": "assistant", "content": scratchpad})

            yield log_step({"event": "inference", "text": f"Analyzing current observations and drafting agent ReAct loop step {iteration}..."})

            response = ""
            final_answer_streamed = False
            is_direct_answer = False
            buffer = ""

            try:
                # LLM Call Streaming
                stream = self.engine.client.chat.completions.create(
                    model=self.engine.llm_service.model,
                    messages=current_messages,
                    temperature=AGENT_CONFIG.get("llm_temperature", 0.1),
                    stream=True
                )
                
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if not delta:
                        continue
                    
                    response += delta
                    buffer += delta
                    
                    if final_answer_streamed or is_direct_answer:
                        yield {"event": "answer_chunk", "text": delta}
                        continue
                    
                    if "Final Answer:" in buffer:
                        final_answer_streamed = True
                        parts = buffer.split("Final Answer:", 1)
                        
                        # Yield Thought if it's there
                        thought_match = re.search(r"Thought:\s*(.*?)(?=Final Answer:|$)", parts[0], re.DOTALL)
                        if thought_match:
                            thought_text = thought_match.group(1).strip()
                            if thought_text and thought_text != last_thought:
                                yield log_step({"event": "thought", "text": thought_text})
                                last_thought = thought_text
                        
                        answer_start = parts[1].strip()
                        if answer_start:
                            yield {"event": "answer_chunk", "text": answer_start}
                        buffer = ""
                        continue
                    
                    # Direct response fallback (doesn't follow ReAct, start streaming immediately)
                    stripped_buf = buffer.strip()
                    if len(stripped_buf) >= 15 and not (stripped_buf.startswith("Thought:") or stripped_buf.startswith("Action:")):
                        is_direct_answer = True
                        yield {"event": "answer_chunk", "text": buffer}
                        buffer = ""
                        continue
            
            except Exception as e:
                logger.error(f"Agent LLM error: {e}")
                err_msg = f"I'm sorry, I encountered an LLM execution error: {e}"
                yield {"event": "answer_chunk", "text": err_msg}
                yield {"event": "done", "response": err_msg, "stats": {}}
                return

            logger.info(f"Agent response:\n{response}")

            # Parse Thought
            thought_match = re.search(r"Thought:\s*(.*?)(?=Action:|Final Answer:|$)", response, re.DOTALL)
            if thought_match:
                thought_text = thought_match.group(1).strip()
                if thought_text and thought_text != last_thought:
                    yield log_step({"event": "thought", "text": thought_text})
                    last_thought = thought_text
            else:
                thought_text = "Analyzing next steps."

            # Parse Action or Final Answer
            action_info = self.parse_action(response)
            final_answer_match = re.search(r"Final Answer:\s*(.*)", response, re.DOTALL)

            if action_info:
                tool_name, tool_arg = action_info
                yield log_step({"event": "action", "tool": tool_name, "input": tool_arg})

                # Yield Phase Telemetry Event before executing tool
                if tool_name == "search_knowledge_base":
                    yield log_step({"event": "document_retrieval", "text": f"Retrieving and compressing private documents for query: '{tool_arg}'"})
                elif tool_name in ("web_search", "web_fetch"):
                    verb = "Initiating web search for query" if tool_name == "web_search" else "Navigating to and fetching contents of"
                    yield log_step({"event": "web_traversal", "text": f"{verb}: '{tool_arg}'"})
                elif tool_name == "calculate_math":
                    yield log_step({"event": "inference", "text": f"Evaluating mathematical expression: {tool_arg}"})
                elif tool_name == "get_current_time":
                    yield log_step({"event": "inference", "text": "Querying current system date and time..."})
                elif tool_name == "get_system_stats":
                    yield log_step({"event": "inference", "text": "Fetching system resource metrics..."})
                elif tool_name == "direct_response":
                    yield log_step({"event": "thought", "text": f"Direct response decided: {tool_arg}"})

                # Execute Tool with Retry/Backoff/Validation
                self._current_memory_text = memory_text
                self._current_source_filter = source_filter
                self._last_raw_results = []
                self._last_ev_log = []
                self._last_web_step = None
                
                tool_result = self.execute_tool_with_retry(tool_name, tool_arg, session_id)
                observation = tool_result.content if tool_result.success else f"Error: {tool_result.error}"

                # Post-Execution Telemetry Harvesting
                if tool_name == "search_knowledge_base":
                    for r in self._last_raw_results:
                        if r not in retrieved_contexts_accumulated:
                            retrieved_contexts_accumulated.append(r)
                    for ev in self._last_ev_log:
                        if ev not in eviction_log_accumulated:
                            eviction_log_accumulated.append(ev)
                
                elif tool_name in ("web_search", "web_fetch") and self._last_web_step:
                    traversal_path.append(self._last_web_step)
                    yield {"event": "web_traversal_step", **self._last_web_step}
                    
                    if tool_name == "web_fetch" and "LLM Summary" in observation:
                        yield log_step({"event": "summarization", "text": f"Web page text length exceeded threshold. Summarized relevant facts."})

                elif tool_name == "direct_response":
                    final_response = tool_arg
                    break

                yield log_step({"event": "observation", "output": observation})
                scratchpad += f"\nThought: {thought_text}\nAction: {tool_name}[{tool_arg}]\nObservation: {observation}"

            elif final_answer_match:
                final_response = final_answer_match.group(1).strip()
                break
            elif is_direct_answer:
                final_response = response.strip()
                break
            else:
                if iteration < self.max_iterations:
                    observation = (
                        "Error: Your response did not contain a valid ReAct Action or Final Answer format. "
                        "Remember to always format your next step exactly as:\n"
                        "Thought: <your thought process>\n"
                        "Action: <tool_name>[<arguments>]\n"
                        "Or if you have the final answer, format it exactly as:\n"
                        "Thought: <your thought process>\n"
                        "Final Answer: <your response>"
                    )
                    yield log_step({"event": "observation", "output": observation})
                    scratchpad += f"\nThought: {thought_text}\nObservation: {observation}"
                    continue
                else:
                    final_response = response.strip()
                    break

        # Yield SYNTHESIS phase
        yield log_step({"event": "synthesis", "text": "Synthesizing final comprehensive response..."})

        # Final response check and synthesis fallback
        if not final_response:
            logger.info("Agent iteration limit reached. Generating final synthesis answer...")
            synthesis_prompt = f"The user asked: {query}\n\nHere is what was found during the investigation:\n{scratchpad}\n\nWrite a final answer to the user summarizing these observations. If the information is not sufficient, state what you know and what is missing."
            try:
                stream = self.engine.client.chat.completions.create(
                    model=self.engine.llm_service.model,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant. Synthesize a clear final answer based on the provided investigation log and cross-reference findings."},
                        {"role": "user", "content": synthesis_prompt}
                    ],
                    temperature=0.3,
                    stream=True
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        final_response += delta
                        yield {"event": "answer_chunk", "text": delta}
            except Exception as e:
                logger.error(f"Error during final synthesis: {e}")
                final_response = "I encountered an issue synthesizing the final answer from observations."
                yield {"event": "answer_chunk", "text": final_response}
        elif not final_answer_streamed and not is_direct_answer:
            yield {"event": "answer_chunk", "text": final_response}

        # Save to memory
        self.engine.save_memory(session_id, query, "user")
        
        telemetry_data = {
            "query": query,
            "raw_prompt": f"SYSTEM_PROMPT:\n{self.system_prompt}\n\nUSER_MESSAGE:\nActive Conversation History:\n{memory_text}\n\nUser Question: {query}",
            "overflow_occurred": overflow_occurred,
            "limit": context_limit,
            "initial_tokens": initial_tokens,
            "final_tokens": agent_prompt_tokens,
            "steps": overflow_steps,
            "agent_steps": agent_steps,
            "budget_tracking": {
                "memory_tokens_used": count_tokens(memory_text),
                "memory_tokens_limit": 1500,
                "document_tokens_used": sum(count_tokens(r["text"]) for r in retrieved_contexts_accumulated),
                "document_tokens_limit": 1500
            },
            "compression_ratio": 1.0,
            "traversal_path": traversal_path,
            "retrieved_context": retrieved_contexts_accumulated,
            "eviction_log": eviction_log_accumulated,
            "routing": {
                "route": route,
                "reasoning": reasoning,
                "sources_count": len(sources),
                "chunks_count": total_chunks
            }
        }
        self.engine.save_memory(session_id, final_response, "assistant", 0.8, telemetry=telemetry_data)
        
        logger.info(f"Agent completed: iterations={iteration}, steps={len(agent_steps)}")

        yield {
            "event": "done",
            "response": final_response,
            "stats": {
                "queries_handled": queries_handled,
                "cpu_usage_percent": psutil.cpu_percent(interval=None),
                "memory_usage_percent": psutil.virtual_memory().percent,
                "tps": 0,
                "query_cost": "$0.00",
                "raw_prompt": f"SYSTEM_PROMPT:\n{self.system_prompt}\n\nUSER_MESSAGE:\nActive Conversation History:\n{memory_text}\n\nUser Question: {query}",
                "overflow_telemetry": {
                    "overflow_occurred": overflow_occurred,
                    "limit": context_limit,
                    "initial_tokens": initial_tokens,
                    "final_tokens": agent_prompt_tokens,
                    "steps": overflow_steps
                },
                "budget_tracking": {
                    "memory_tokens_used": count_tokens(memory_text),
                    "memory_tokens_limit": 1500,
                    "document_tokens_used": sum(count_tokens(r["text"]) for r in retrieved_contexts_accumulated),
                    "document_tokens_limit": 1500
                },
                "traversal_path": traversal_path,
                "retrieved_context": retrieved_contexts_accumulated,
                "eviction_log": eviction_log_accumulated,
                "tool_metrics": [m.to_dict() for m in self.tool_registry.metrics.values()],
                "routing": {
                    "route": route,
                    "reasoning": reasoning,
                    "sources_count": len(sources),
                    "chunks_count": total_chunks
                }
            }
        }
