import re
import logging
import psutil
from typing import Dict, Generator, Optional, List
import tiktoken
from core.config import TOKENIZER_ENCODING, COST_PER_INPUT_TOKEN, COST_PER_OUTPUT_TOKEN
from core.web_traversal import search_web, fetch_web_page
from core.router import Router, PipelineType, retrieve_first, ground_generation

logger = logging.getLogger("RAG.Agent")
tokenizer = tiktoken.get_encoding(TOKENIZER_ENCODING)

def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(tokenizer.encode(text))


class RAGAgent:
    """
    Retrieval-First ReAct Agent.
    
    Architecture:
    1. Router determines pipeline BEFORE agent execution
    2. Retrieval is infrastructure (not a tool choice) in STRICT_RAG
    3. Agent synthesizes from pre-retrieved context
    4. Web tools only available in WEB_AGENT pipeline
    """

    def __init__(self, engine):
        self.engine = engine
        self.max_iterations = 5
        self.router = Router(engine.retriever)

    def parse_action(self, text: str) -> Optional[tuple]:
        """Parses action from LLM response. E.g. Action: web_search[my query]"""
        match = re.search(r"Action:\s*([\w\-]+)\s*(?:\[(.*?)\])?", text, re.IGNORECASE)
        if match:
            tool_name = match.group(1).strip().lower()
            tool_arg = match.group(2) or ""
            tool_arg = tool_arg.strip()
            if len(tool_arg) >= 2 and (
                (tool_arg.startswith('"') and tool_arg.endswith('"')) or
                (tool_arg.startswith("'") and tool_arg.endswith("'")) or
                (tool_arg.startswith("`") and tool_arg.endswith("`"))
            ):
                tool_arg = tool_arg[1:-1].strip()
            return tool_name, tool_arg
        return None

    def _summarize_web_content(self, url: str, content: str, query: str) -> str:
        """Uses LLM to summarize web content relative to the user query."""
        logger.info(f"Summarizing web content from {url} for query: {query}")
        summary_prompt = (
            f"You are a helpful assistant summarizing web content to answer the user query: '{query}'.\n"
            f"Source URL: {url}\n\n"
            f"Here is the page content:\n{content}\n\n"
            f"Provide a concise, detailed summary of findings relevant to the user query. "
            f"Focus on factual information, key metrics, and direct answers to the query."
        )
        try:
            response = self.engine.client.chat.completions.create(
                model=self.engine.llm_service.model,
                messages=[
                    {"role": "system", "content": "You are a precise data synthesizer and summarizer."},
                    {"role": "user", "content": summary_prompt}
                ],
                temperature=0.2,
                max_tokens=800
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error summarizing web content: {e}")
            return f"Error summarizing content: {str(e)}. Raw content: {content[:800]}..."

    def run_stream(self, query: str, session_id: str = "default", 
                   source_filter: Optional[str] = None, 
                   context_limit: Optional[int] = None) -> Generator[Dict, None, None]:
        """
        Executes the retrieval-first ReAct loop and yields intermediate events.
        
        STAGE 1 - Router: Determine pipeline BEFORE any LLM involvement
        STAGE 2 - Retrieval: Infrastructure, not tool choice (STRICT_RAG)
        STAGE 3 - Grounding: LLM synthesizes from pre-retrieved context
        """
        import time
        logger.info(f"Agent starting for query: {query[:50]}... | Limit: {context_limit}")
        
        agent_steps = []
        traversal_path = []
        retrieved_contexts_accumulated = []
        eviction_log_accumulated = []

        def log_step(event):
            allowed_events = {
                "thought", "action", "observation", "planning", 
                "memory_retrieval", "context_assembly", "document_retrieval", 
                "web_traversal", "summarization", "inference", "synthesis",
                "routing_decision", "retrieval_phase"
            }
            if event.get("event") in allowed_events:
                agent_steps.append(event)
            return event

        # 1. PLANNING phase
        yield log_step({"event": "planning", "text": f"Analyzing user query: '{query}'"})

        # 2. MEMORY RETRIEVAL phase
        yield log_step({"event": "memory_retrieval", "text": f"Retrieving conversation history for session '{session_id}'..."})
        memory = self.engine.get_memory(session_id)
        memory_text = memory.get_active_context()

        # 3. ROUTING - STAGE 1 (ORCHESTRATOR DECIDES)
        yield log_step({"event": "planning", "text": "Determining execution pipeline..."})
        
        sources = []
        total_chunks = 0
        try:
            sources = self.engine.retriever.get_sources() or []
            total_chunks = self.engine.retriever.get_count() or 0
        except Exception:
            pass

        route_result = self.router.route(query, sources, total_chunks)
        route = route_result["pipeline"].value
        route_reasoning = route_result["reasoning"]
        requires_retrieval = route_result["requires_retrieval"]
        
        yield log_step({
            "event": "routing_decision",
            "text": f"Pipeline: {route}. Reasoning: {route_reasoning}",
            "route": route,
            "reasoning": route_reasoning
        })

        # 4. RETRIEVAL PHASE - STAGE 2 (INFRASTRUCTURE, NOT TOOL CHOICE)
        retrieval_result = {"context": "", "confidence": 0.0, "evidence_found": False}
        
        if route == "STRICT_RAG_PIPELINE" and requires_retrieval:
            yield log_step({"event": "retrieval_phase", "text": "Executing mandatory knowledge base retrieval..."})
            
            try:
                retrieval_result = retrieve_first(query, self.engine, source_filter)
                retrieved_contexts_accumulated = retrieval_result.get("raw_results", [])
                
                yield log_step({
                    "event": "document_retrieval",
                    "text": f"Retrieved {len(retrieved_contexts_accumulated)} documents. Confidence: {retrieval_result['confidence']:.2f}"
                })
            except Exception as e:
                logger.error(f"Retrieval failed: {e}")
                retrieval_result["context"] = "Retrieval failed. No evidence available."
                retrieval_result["confidence"] = 0.0

            # 5. SYNTHESIS - STAGE 3 (GROUNDED GENERATION)
            yield log_step({"event": "synthesis", "text": "Synthesizing answer from retrieved evidence..."})
            
            context_text = retrieval_result["context"]
            confidence = retrieval_result["confidence"]
            
            # Low confidence handling
            if confidence < 0.3:
                prompt = f"""You are answering questions using ONLY the provided retrieved evidence.

CRITICAL: The retrieved evidence has LOW CONFIDENCE ({confidence:.2f}). 
If the answer is not clearly supported by the evidence, you MUST explicitly state that.

### EVIDENCE:
{context_text}

### QUESTION:
{query}

### ANSWER:"""
            else:
                prompt = ground_generation(query, context_text, confidence)
            
            yield log_step({"event": "inference", "text": "Generating grounded response..."})
            
            final_response = ""
            try:
                stream = self.engine.client.chat.completions.create(
                    model=self.engine.llm_service.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    stream=True
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        final_response += delta
                        yield {"event": "answer_chunk", "text": delta}
            except Exception as e:
                logger.error(f"LLM error: {e}")
                final_response = "I encountered an error generating the response."
                yield {"event": "answer_chunk", "text": final_response}

            # Persist and return
            self.engine.save_memory(session_id, query, "user")
            
            telemetry = {
                "query": query,
                "routing": {"route": route, "reasoning": route_reasoning},
                "retrieval_confidence": confidence,
                "evidence_found": retrieval_result.get("evidence_found", False),
                "retrieved_context": retrieved_contexts_accumulated
            }
            self.engine.save_memory(session_id, final_response, "assistant", 0.8, telemetry=telemetry)

            yield {
                "event": "done",
                "response": final_response,
                "stats": {
                    "queries_handled": self.engine.stats.get("queries", 0),
                    "cpu_usage_percent": psutil.cpu_percent(interval=None),
                    "memory_usage_percent": psutil.virtual_memory().percent,
                    "tps": 0,
                    "query_cost": "$0.00",
                    "routing": {"route": route, "reasoning": route_reasoning},
                    "retrieval_confidence": confidence,
                    "retrieved_context": retrieved_contexts_accumulated
                }
            }
            return

        # WEB_AGENT or HYBRID pipeline - use web tools
        if route in ["WEB_AGENT_PIPELINE", "HYBRID_PIPELINE"]:
            yield log_step({"event": "planning", "text": f"Entering {route} pipeline..."})
            
            # Use web agent mode
            messages = [
                {"role": "system", "content": WEB_AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": f"Active Conversation History:\n{memory_text}\n\nUser Question: {query}"}
            ]
            
            scratchpad = ""
            final_response = ""
            
            for iteration in range(self.max_iterations):
                current_messages = list(messages)
                if scratchpad:
                    current_messages.append({"role": "assistant", "content": scratchpad})

                yield log_step({"event": "inference", "text": f"Processing web search step {iteration + 1}..."})

                response_text = ""
                buffer = ""
                
                try:
                    stream = self.engine.client.chat.completions.create(
                        model=self.engine.llm_service.model,
                        messages=current_messages,
                        temperature=0.1,
                        stream=True
                    )
                    for chunk in stream:
                        delta = chunk.choices[0].delta.content or ""
                        if not delta:
                            continue
                        response_text += delta
                        buffer += delta
                        
                        if "Final Answer:" in buffer:
                            parts = buffer.split("Final Answer:", 1)
                            answer = parts[1].strip() if len(parts) > 1 else ""
                            if answer:
                                yield {"event": "answer_chunk", "text": answer}
                                final_response = answer
                            break
                except Exception as e:
                    logger.error(f"LLM error: {e}")
                    final_response = "I encountered an error."
                    yield {"event": "answer_chunk", "text": final_response}
                    break

                action_info = self.parse_action(response_text)
                final_match = re.search(r"Final Answer:\s*(.*)", response_text, re.DOTALL)
                
                if action_info:
                    tool_name, tool_arg = action_info
                    yield log_step({"event": "action", "tool": tool_name, "input": tool_arg})
                    
                    observation = ""
                    try:
                        if tool_name == "web_search":
                            yield log_step({"event": "web_traversal", "text": f"Searching web for: '{tool_arg}'"})
                            results = search_web(tool_arg)
                            if results:
                                obs_list = [f"[{i+1}] {r['title']}\n{r['url']}\n{r['snippet']}\n" for i, r in enumerate(results[:5])]
                                observation = "\n".join(obs_list)
                            else:
                                observation = "No web results found."
                        
                        elif tool_name == "web_fetch":
                            yield log_step({"event": "web_traversal", "text": f"Fetching: {tool_arg}"})
                            text, _ = fetch_web_page(tool_arg)
                            if text and not text.startswith("Error"):
                                if len(text) > 1500:
                                    text = self._summarize_web_content(tool_arg, text, query)
                                observation = f"Content from {tool_arg}:\n{text[:1000]}"
                            else:
                                observation = f"Failed to fetch: {text}"
                        
                        elif tool_name == "get_system_stats":
                            doc_count = self.engine.retriever.get_count()
                            observation = f"CPU: {psutil.cpu_percent()}% | RAM: {psutil.virtual_memory().percent}% | Docs: {doc_count}"
                        
                        elif tool_name == "calculate_math":
                            import ast
                            try:
                                observation = f"Result: {ast.literal_eval(tool_arg)}"
                            except:
                                observation = "Could not calculate"
                        
                        elif tool_name == "get_current_time":
                            from datetime import datetime
                            observation = f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        else:
                            observation = "Unknown tool"
                    
                    except Exception as e:
                        observation = f"Error: {e}"
                    
                    yield log_step({"event": "observation", "output": observation})
                    scratchpad += f"\nThought: Analyzing\nAction: {tool_name}[{tool_arg}]\nObservation: {observation}"
                
                elif final_match:
                    final_response = final_match.group(1).strip()
                    yield {"event": "answer_chunk", "text": final_response}
                    break

            if not final_response:
                final_response = "No answer generated."
                yield {"event": "answer_chunk", "text": final_response}

            self.engine.save_memory(session_id, query, "user")
            self.engine.save_memory(session_id, final_response, "assistant", 0.8, telemetry={"routing": {"route": route}})

            yield {"event": "done", "response": final_response, "stats": {}}
            return

        # CHAT pipeline - direct response
        yield log_step({"event": "synthesis", "text": "Generating direct response..."})
        direct_prompt = f"""You are a helpful assistant. Answer the user's question directly.

Conversation History:
{memory_text}

User Query: {query}"""
        
        final_response = ""
        try:
            stream = self.engine.client.chat.completions.create(
                model=self.engine.llm_service.model,
                messages=[{"role": "user", "content": direct_prompt}],
                temperature=0.3,
                stream=True
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    final_response += delta
                    yield {"event": "answer_chunk", "text": delta}
        except Exception as e:
            final_response = "Error generating response."
            yield {"event": "answer_chunk", "text": final_response}

        self.engine.save_memory(session_id, query, "user")
        self.engine.save_memory(session_id, final_response, "assistant", 0.5, telemetry={"routing": {"route": route}})

        yield {"event": "done", "response": final_response, "stats": {}}


# System prompt for web agent mode
WEB_AGENT_SYSTEM_PROMPT = """You are an advanced RAG Assistant with access to web search tools.

You must solve the user's request step-by-step using a ReAct loop.
You must use the following format:

Thought: Write what you need to do next to answer the user query.
Action: tool_name[arguments]
Observation: The output result from the tool.
... (this loop can repeat at most 5 times)
Thought: I have enough information to write the final response.
Final Answer: Write the response to the user.

Available tools:
1. web_search[query]: Searches the web for public facts, news, and details using DuckDuckGo.
2. web_fetch[url]: Fetches and extracts main text content from a web page URL.
3. get_system_stats[]: Returns current CPU/RAM usage and indexed document count.
4. calculate_math[expression]: Evaluates mathematical expressions safely.
5. get_current_time[]: Returns the current local date and time.

Strict rules:
1. ONLY call one tool at a time.
2. You MUST use the exact format "Action: tool_name[arguments]".
3. Do NOT put quotes or backticks around tool arguments.
4. If tools do not return enough relevant information, state that you do not know.
"""