"""
================================================================================
RAG CONTEXT ENGINE - ROUTER PIPELINE
================================================================================
Orchestrator-driven routing that determines execution pipeline BEFORE any
LLM involvement. Retrieval is infrastructure, not a tool choice.
"""

import re
import logging
from typing import Literal, Dict, Any, Optional
from enum import Enum
import tiktoken

logger = logging.getLogger("RAG.Router")
tokenizer = tiktoken.get_encoding("cl100k_base")


class PipelineType(Enum):
    """Execution pipelines determined by the orchestrator."""
    STRICT_RAG = "STRICT_RAG_PIPELINE"
    WEB_AGENT = "WEB_AGENT_PIPELINE"
    CHAT = "CHAT_PIPELINE"
    HYBRID = "HYBRID_PIPELINE"


class Router:
    """
    Stage 1 Router: Determines which execution pipeline should handle the query.
    
    The orchestrator (not the LLM) decides routing. Retrieval is NOT a tool choice.
    """
    
    def __init__(self, retriever=None):
        self.retriever = retriever
        self._private_indicators = [
            "upload", "document", "file", "pdf", "docx", "txt",
            "company", "internal", "private", "confidential", "enterprise",
            "database", "schema", "api key", "password", "config",
            "sales", "revenue", "employee", "customer", "project",
            "codebase", "repository", "knowledge base", "kb",
        ]
        
        self._web_indicators = [
            "current", "latest", "recent", "news", "today", "now",
            "weather", "stock", "price", "live", "real-time",
            "who is", "what is the", "when did", "where is",
        ]
        
        self._casual_indicators = [
            "hi", "hello", "hey", "thanks", "thank you", "bye",
            "how are you", "good morning", "good afternoon",
        ]
    
    def route(self, query: str, sources: list = None, total_chunks: int = 0) -> Dict[str, Any]:
        """
        Determine the execution pipeline for a query.
        
        Returns dict with:
        - pipeline: The PipelineType to use
        - confidence: confidence score 0-1
        - reasoning: Why this pipeline was chosen
        - requires_retrieval: Whether KB retrieval is mandatory
        """
        clean_query = query.lower().strip()
        has_private_content = sources and len(sources) > 0 and total_chunks > 0
        
        # Stage 1: Check for casual conversation
        if self._is_casual(clean_query):
            return {
                "pipeline": PipelineType.CHAT,
                "confidence": 0.95,
                "reasoning": "Query is casual conversation/greeting",
                "requires_retrieval": False
            }
        
        # Stage 2: Check if query mentions private/enterprise content
        mentions_private = any(ind in clean_query for ind in self._private_indicators)
        
        # Stage 3: Check if query requires live web data
        requires_web = any(ind in clean_query for ind in self._web_indicators)
        
        # Stage 4: Routing logic based on indicators
        if mentions_private or has_private_content:
            # Private knowledge query - STRICT RAG pipeline
            confidence = 0.9 if mentions_private else 0.7
            return {
                "pipeline": PipelineType.STRICT_RAG,
                "confidence": confidence,
                "reasoning": "Query references private/enterprise data - retrieval is mandatory",
                "requires_retrieval": True
            }
        
        if requires_web and not mentions_private:
            return {
                "pipeline": PipelineType.WEB_AGENT,
                "confidence": 0.85,
                "reasoning": "Query requires live/current web data",
                "requires_retrieval": False
            }
        
        # Default: HYBRID for ambiguous queries
        return {
            "pipeline": PipelineType.HYBRID,
            "confidence": 0.6,
            "reasoning": "Ambiguous query - will attempt hybrid retrieval",
            "requires_retrieval": True
        }
    
    def _is_casual(self, clean_query: str) -> bool:
        """Check if query is casual conversation."""
        words = clean_query.split()
        
        # Exact greeting match
        if clean_query in self._casual_indicators:
            return True
        
        # Short conversational queries
        if len(words) <= 3 and all(w in self._casual_indicators for w in words):
            return True
        
        return False


def retrieve_first(query: str, engine, source_filter: str = None, 
                   min_confidence: float = 0.7) -> Dict[str, Any]:
    """
    Stage 2: Retrieval-as-infrastructure.
    
    Retrieval happens BEFORE generation. The LLM cannot skip or bypass this.
    
    Returns dict with:
    - context: Retrieved and compressed context
    - raw_results: Raw retrieval results
    - confidence: Confidence score based on reranker
    - evidence_found: Whether useful evidence was found
    """
    # Phase 1: Query Expansion
    search_queries = [query]
    try:
        if len(query.split()) >= 5:
            search_queries = engine._phase_expand(query, "context_engine", {})
    except Exception:
        pass
    
    # Phase 1.5: HyDE (for latent semantic capture)
    hyde_doc = ""
    try:
        hyde_doc = engine._phase_hyde(query, "context_engine", search_queries, {})
    except Exception:
        pass
    
    # Phase 2: Hybrid Retrieval
    all_raw = engine._phase_retrieve(search_queries, 5, source_filter, {})
    
    # Phase 3: Reranking with confidence scoring
    peak_score = 0.0
    reranked = []
    if all_raw:
        try:
            from core.reranker import NeuralReranker
            reranker = NeuralReranker()
            reranked = reranker.rerank(query, all_raw)[:3]
            if reranked:
                peak_score = float(reranked[0].get('cross_score', 0.0))
        except Exception:
            reranked = sorted(all_raw, key=lambda x: x.get('score', 0), reverse=True)[:3]
            peak_score = 0.0
    
    # Calculate confidence
    confidence = min(1.0, peak_score * 2) if peak_score > 0 else 0.0
    
    # Compress context
    context_text = ""
    if reranked:
        try:
            context_text = engine.compressor.compress(
                [r["text"] for r in reranked], query, max_tokens=1000
            )
        except Exception:
            context_text = "\n\n".join(r["text"] for r in reranked[:3])
    
    return {
        "context": context_text or "No relevant documents found.",
        "raw_results": reranked if reranked else all_raw,
        "confidence": confidence,
        "peak_score": peak_score,
        "evidence_found": bool(reranked and confidence >= min_confidence),
        "hyde_doc": hyde_doc,
        "search_queries": search_queries
    }


def ground_generation(query: str, retrieved_context: str, confidence: float,
                    allow_pretrained_knowledge: bool = False) -> str:
    """
    Stage 3 & 4: Ground generation in retrieved evidence.
    
    The prompt enforces: Retrieved context > model memory
    """
    low_confidence_msg = ""
    if confidence < 0.3:
        low_confidence_msg = (
            "\n\nIMPORTANT: The retrieved evidence has LOW CONFIDENCE. "
            "If the answer is not clearly supported by the evidence, "
            "you MUST explicitly state that the information is not found in the knowledge base."
        )
    elif confidence < 0.5:
        low_confidence_msg = (
            "\n\nNOTE: The retrieved evidence has MEDIUM CONFIDENCE. "
            "Answer with appropriate uncertainty indicators."
        )
    
    grounded_prompt = f"""You are answering questions using ONLY the provided retrieved evidence.

CRITICAL RULES:
1. Use ONLY the provided evidence - do not use any external knowledge
2. Retrieved context has HIGHER AUTHORITY than your training data
3. If the answer is missing from the evidence, explicitly state: "The knowledge base does not contain this information."
4. Never fabricate or hallucinate missing information
5. Cite specific parts of the evidence when possible{low_confidence_msg}

### RETRIEVED EVIDENCE:
{retrieved_context}

### QUESTION:
{query}

### ANSWER:"""
    
    return grounded_prompt