import re
import logging
import psutil
from typing import Dict, Generator, Optional, List
import tiktoken
from core.config import TOKENIZER_ENCODING, COST_PER_INPUT_TOKEN, COST_PER_OUTPUT_TOKEN
from core.web_traversal import search_web, fetch_web_page

logger = logging.getLogger("RAG.Agent")
tokenizer = tiktoken.get_encoding(TOKENIZER_ENCODING)

def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(tokenizer.encode(text))


SYSTEM_PROMPT = """You are an advanced RAG Assistant with access to tools to help answer user questions.
You must solve the user's request step-by-step using a ReAct loop.
You must use the following format:

Thought: Write what you need to do next to answer the user query.
Action: tool_name[arguments]
Observation: The output result from the tool.
... (this loop can repeat at most 5 times)
Thought: I have enough information to write the final response.
Final Answer: Write the response to the user.

Available tools:
1. search_knowledge_base[query]: Searches the document database and returns compressed relevant segments. Use this when the query asks about technical facts, documentation, or uploaded files.
2. web_search[query]: Searches the web for public facts, news, and details using DuckDuckGo. Use this to find live web data or cross-reference private database findings with public facts.
3. web_fetch[url]: Fetches and extracts main text content from a web page URL. Use this to navigate and inspect details on web pages.
4. get_system_stats[]: Returns current CPU usage, RAM usage, and total indexed documents.
5. direct_response[response]: Use this to respond directly to the user for general greetings, chit-chat, or if you can answer using the conversation history alone.

Strict rules:
1. ONLY call one tool at a time.
2. You MUST use the exact format "Action: tool_name[arguments]". For example: "Action: search_knowledge_base[database password]" or "Action: web_search[artificial intelligence]".
3. Do NOT put quotes or backticks around tool arguments.
4. If the tools do not return enough relevant information, state that you do not know in the Final Answer.
5. You should cross-reference findings from the local knowledge base with public web search results to synthesize comprehensive, grounded insights.
"""

class RAGAgent:
    """
    An autonomous ReAct agent running on top of RAGContextEngine.
    """

    def __init__(self, engine):
        self.engine = engine
        self.max_iterations = 5

    def parse_action(self, text: str) -> Optional[tuple]:
        """Parses action from LLM response. E.g. Action: search_knowledge_base[my query]"""
        # Match "Action: tool_name[arguments]" or "Action: tool_name" with optional brackets
        match = re.search(r"Action:\s*([\w\-]+)\s*(?:\[(.*?)\])?", text, re.IGNORECASE)
        if match:
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
            return tool_name, tool_arg
        return None

    def _summarize_web_content(self, url: str, content: str, query: str) -> str:
        """
        Uses LLM to summarize web content relative to the user query.
        """
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
            summary = response.choices[0].message.content.strip()
            return summary
        except Exception as e:
            logger.error(f"Error summarizing web content: {e}")
            return f"Error summarizing content: {str(e)}. Raw content: {content[:800]}..."

    def run_stream(self, query: str, session_id: str = "default", source_filter: Optional[str] = None, context_limit: Optional[int] = None) -> Generator[Dict, None, None]:
        """
        Executes the ReAct loop and yields intermediate events for streaming.
        """
        import time
        logger.info(f"Agent starting for query: {query[:50]}... | Limit: {context_limit}")
        
        # Initialize steps collection and traversal path
        agent_steps = []
        traversal_path = []
        retrieved_contexts_accumulated = []
        eviction_log_accumulated = []

        def log_step(event):
            allowed_events = {
                "thought", "action", "observation", "planning", 
                "memory_retrieval", "context_assembly", "document_retrieval", 
                "web_traversal", "summarization", "inference", "synthesis"
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

        # Early exit check: greetings or extremely simple chat
        clean_query = query.lower().strip()
        greetings = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening", "how are you"}
        conversational_words = {"hi", "hello", "hey", "thanks", "thank", "bye", "okay", "ok", "sure", "yes", "no", "please"}
        has_conversational_word = any(w in clean_query.split() for w in conversational_words)
        is_short_chat = len(clean_query.split()) <= 2 and has_conversational_word
        if (clean_query in greetings) or (is_short_chat):
            logger.info("Agent early exit: Simple greeting/chat.")
            t_event = {"event": "thought", "text": "This is a simple query or greeting. I can respond directly without searching the knowledge base."}
            yield log_step(t_event)
            
            # Synthesis phase
            yield log_step({"event": "synthesis", "text": "Synthesizing direct conversation response."})
            
            direct_reply = f"Hello! How can I help you today? I'm ready to answer any questions about your uploaded documents or system configuration."
            yield {"event": "answer_chunk", "text": direct_reply}
            self.engine.save_memory(session_id, query, "user")
            
            telemetry_data = {
                "query": query,
                "raw_prompt": query,
                "overflow_occurred": False,
                "limit": context_limit,
                "initial_tokens": count_tokens(query),
                "final_tokens": count_tokens(query),
                "steps": [],
                "agent_steps": agent_steps,
                "budget_tracking": {
                    "memory_tokens_used": count_tokens(memory_text),
                    "memory_tokens_limit": 1500,
                    "document_tokens_used": 0,
                    "document_tokens_limit": 0
                },
                "compression_ratio": 1.0,
                "traversal_path": traversal_path
            }
            self.engine.save_memory(session_id, direct_reply, "assistant", 0.5, telemetry=telemetry_data)
            yield {"event": "done", "response": direct_reply, "stats": {}}
            return

        # Perform overflow detection on the Agent prompt (system prompt + memory + user query)
        overflow_occurred = False
        overflow_steps = []
        agent_prompt_tokens = count_tokens(SYSTEM_PROMPT) + count_tokens(memory_text) + count_tokens(query) + 50
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
                agent_prompt_tokens = count_tokens(SYSTEM_PROMPT) + count_tokens(temp_mem_text) + count_tokens(query) + 50
            
            if pruned_count > 0:
                memory.entries = temp_entries
                memory_text = memory.get_active_context()
                new_mem = count_tokens(memory_text)
                overflow_steps.append(f"   - Evicted {pruned_count} oldest conversational turns. Memory reduced from {old_mem} to {new_mem} tokens.")
            else:
                overflow_steps.append("   - No memory turns available for eviction.")
                
            # If still overflowing, truncate user query
            if agent_prompt_tokens > context_limit:
                allowed_query_len = context_limit - count_tokens(SYSTEM_PROMPT) - count_tokens(memory_text) - 60
                allowed_query_len = max(5, allowed_query_len)
                query_tokens = tokenizer.encode(query)
                query = tokenizer.decode(query_tokens[:allowed_query_len])
                agent_prompt_tokens = count_tokens(SYSTEM_PROMPT) + count_tokens(memory_text) + count_tokens(query) + 50
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
                time.sleep(0.4)

        # Initialize scratchpad
        scratchpad = ""
        search_cache = {} # Simple in-memory cache to prevent redundant search calls

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Active Conversation History:\n{memory_text}\n\nUser Question: {query}"}
        ]

        final_response = ""
        last_thought = ""
        final_answer_streamed = False
        is_direct_answer = False

        for iteration in range(self.max_iterations):
            # Update messages with the scratchpad history of thoughts/actions
            current_messages = list(messages)
            if scratchpad:
                current_messages.append({"role": "assistant", "content": scratchpad})

            # Call LLM (Streaming)
            logger.info(f"Agent Iteration {iteration+1} calling LLM (streaming)...")
            
            # Yield INFERENCE state
            yield log_step({"event": "inference", "text": f"Analyzing current observations and drafting agent ReAct loop step {iteration+1}..."})
            
            response = ""
            final_answer_streamed = False
            is_direct_answer = False
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

            # Parse Action or Final Answer
            action_info = self.parse_action(response)
            final_answer_match = re.search(r"Final Answer:\s*(.*)", response, re.DOTALL)

            if action_info:
                tool_name, tool_arg = action_info
                yield log_step({"event": "action", "tool": tool_name, "input": tool_arg})

                # Execute Tool
                observation = ""
                try:
                    if tool_name == "search_knowledge_base":
                        # Yield document retrieval phase
                        yield log_step({"event": "document_retrieval", "text": f"Retrieving and compressing private documents for query: '{tool_arg}'"})
                        
                        # Check cache first
                        if tool_arg in search_cache:
                            logger.info(f"Search cache hit for: {tool_arg}")
                            observation, raw_results, ev_log = search_cache[tool_arg]
                        else:
                            logger.info(f"Executing search_knowledge_base for: {tool_arg}")
                            # Compress with remaining budget
                            mem_tokens = count_tokens(memory_text)
                            doc_budget = max(300, 1500 - mem_tokens)
                            search_queries = self.engine._phase_expand(tool_arg, "context_engine", {})
                            raw_results = self.engine._phase_retrieve(search_queries, 5, source_filter, {})
                            compressed = self.engine.compressor.compress(
                                [r["text"] for r in raw_results], tool_arg, max_tokens=doc_budget
                            )
                            observation = compressed if (isinstance(compressed, str) and compressed.strip()) else "No matching documents found in database."
                            ev_log = getattr(self.engine.compressor, "_eviction_log", [])
                            search_cache[tool_arg] = (observation, raw_results, ev_log)

                        # Accumulate retrieved results and eviction logs
                        for r in raw_results:
                            if r not in retrieved_contexts_accumulated:
                                retrieved_contexts_accumulated.append(r)
                        for ev in ev_log:
                            if ev not in eviction_log_accumulated:
                                eviction_log_accumulated.append(ev)

                    elif tool_name == "web_search":
                        # Yield web search traversal phase
                        yield log_step({"event": "web_traversal", "text": f"Initiating web search for query: '{tool_arg}'"})
                        
                        results = search_web(tool_arg)
                        if results:
                            obs_list = []
                            for idx, r in enumerate(results[:5]):
                                obs_list.append(f"[{idx+1}] Title: {r['title']}\nURL: {r['url']}\nSnippet: {r['snippet']}\n")
                            observation = "\n".join(obs_list)
                            
                            traversal_path.append({
                                "type": "search",
                                "query": tool_arg,
                                "results_count": len(results),
                                "results": results[:5]
                            })
                            yield {"event": "web_traversal_step", "type": "search", "query": tool_arg, "results": results[:5]}
                        else:
                            observation = "No search results found on DuckDuckGo."
                            traversal_path.append({
                                "type": "search",
                                "query": tool_arg,
                                "results_count": 0,
                                "results": []
                            })
                            yield {"event": "web_traversal_step", "type": "search", "query": tool_arg, "results": []}

                    elif tool_name == "web_fetch":
                        # Yield web page navigation phase
                        yield log_step({"event": "web_traversal", "text": f"Navigating to and fetching contents of: {tool_arg}"})
                        
                        text_content, links = fetch_web_page(tool_arg)
                        
                        from urllib.parse import urlparse
                        domain = urlparse(tool_arg).netloc
                        title = domain
                        
                        if text_content.startswith("Error"):
                            observation = f"Failed to fetch page content: {text_content}"
                            traversal_path.append({
                                "type": "fetch",
                                "url": tool_arg,
                                "title": title,
                                "status": "error",
                                "error": text_content
                            })
                            yield {"event": "web_traversal_step", "type": "fetch", "url": tool_arg, "status": "error", "error": text_content}
                        else:
                            # Apply LLM summarization if page content exceeds 1,500 characters
                            if len(text_content) > 1500:
                                yield log_step({"event": "summarization", "text": f"Web page text length ({len(text_content)} chars) exceeds 1,500 characters threshold. Summarizing relevant facts..."})
                                summary = self._summarize_web_content(tool_arg, text_content, query)
                                observation = f"LLM Summary of {tool_arg}:\n{summary}"
                            else:
                                observation = f"Raw web page text content from {tool_arg}:\n{text_content}"
                            
                            traversal_path.append({
                                "type": "fetch",
                                "url": tool_arg,
                                "title": title,
                                "status": "success",
                                "length": len(text_content)
                            })
                            yield {"event": "web_traversal_step", "type": "fetch", "url": tool_arg, "status": "success", "title": title, "length": len(text_content)}

                    elif tool_name == "get_system_stats":
                        yield log_step({"event": "inference", "text": "Fetching system resource metrics..."})
                        doc_count = self.engine.retriever.get_count()
                        cpu = psutil.cpu_percent(interval=None)
                        ram = psutil.virtual_memory().percent
                        observation = f"System Stats: CPU={cpu}%, RAM={ram}%, Total Indexed Documents={doc_count}"

                    elif tool_name == "direct_response":
                        logger.info("Executing direct_response tool")
                        observation = f"Direct Response Executed: '{tool_arg}'"
                        final_response = tool_arg
                        yield log_step({"event": "thought", "text": f"Direct response decided: {tool_arg}"})
                        break
                    else:
                        observation = (
                            f"Error: Unknown tool '{tool_name}'. "
                            "Available tools are: search_knowledge_base[query], web_search[query], web_fetch[url], get_system_stats[], or direct_response[response]."
                        )
                except Exception as tool_err:
                    logger.error(f"Agent tool execution error for '{tool_name}': {tool_err}", exc_info=True)
                    observation = f"Error executing tool '{tool_name}': {type(tool_err).__name__}: {tool_err}"

                yield log_step({"event": "observation", "output": observation})
                scratchpad += f"\nThought: {thought_text}\nAction: {tool_name}[{tool_arg}]\nObservation: {observation}"

            elif final_answer_match:
                final_response = final_answer_match.group(1).strip()
                break
            else:
                # If we have iterations left, feed a formatting error observation to the LLM to allow it to self-correct
                if iteration < self.max_iterations - 1:
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
                    t_text = thought_text if 'thought_text' in locals() and thought_text else "Analyzing next steps."
                    scratchpad += f"\nThought: {t_text}\nObservation: {observation}"
                    continue
                else:
                    # Fallback if model exhausted iterations without proper structure
                    final_response = response.strip()
                    break

        # Yield SYNTHESIS phase
        yield log_step({"event": "synthesis", "text": "Synthesizing final comprehensive response..."})

        # If loop limit exhausted without generating final response, run final synthesis
        if not final_response:
            yield log_step({"event": "thought", "text": "Iteration limit reached. Synthesizing final answer from observations."})
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
            # Yield final answer chunk-by-chunk to simulate streaming if not already streamed
            yield {"event": "answer_chunk", "text": final_response}

        # Persist memory
        self.engine.save_memory(session_id, query, "user")
        
        telemetry_data = {
            "query": query,
            "raw_prompt": f"SYSTEM_PROMPT:\n{SYSTEM_PROMPT}\n\nUSER_MESSAGE:\nActive Conversation History:\n{memory_text}\n\nUser Question: {query}",
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
            "eviction_log": eviction_log_accumulated
        }
        self.engine.save_memory(session_id, final_response, "assistant", 0.8, telemetry=telemetry_data)

        yield {"event": "done", "response": final_response, "stats": {
            "queries_handled": self.engine.stats["queries"],
            "cpu_usage_percent": psutil.cpu_percent(interval=None),
            "memory_usage_percent": psutil.virtual_memory().percent,
            "tps": 0,
            "query_cost": "$0.00",
            "raw_prompt": f"SYSTEM_PROMPT:\n{SYSTEM_PROMPT}\n\nUSER_MESSAGE:\nActive Conversation History:\n{memory_text}\n\nUser Question: {query}",
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
            "eviction_log": eviction_log_accumulated
        }}
