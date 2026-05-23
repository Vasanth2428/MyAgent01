"""
================================================================================
RAG CONTEXT ENGINE - COMPRESSOR MODULE
================================================================================
Extractive context compression: scores sentences by query relevance and
selects the top-K within a token budget.
"""

import re
import time
import logging
from typing import List
import tiktoken

from core.config import TOKENIZER_ENCODING, COMPRESSION_SCORE_THRESHOLD

logger = logging.getLogger("RAG.Compressor")
tokenizer = tiktoken.get_encoding(TOKENIZER_ENCODING)

# Pre-compiled regex for sentence boundary detection.
# Avoids splitting on abbreviations (e.g., "Dr.") and decimals (e.g., "3.14").
_SENTENCE_END = re.compile(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)\s')

# Stopwords for filtering common words in relevance scoring
STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must", "to", "of",
    "in", "for", "on", "with", "at", "by", "from", "as", "into", "about",
    "it", "its", "this", "that", "these", "those", "i", "me", "my", "we",
    "our", "you", "your", "he", "him", "his", "she", "her", "they", "them",
    "their", "what", "which", "who", "when", "where", "how", "not", "no",
    "and", "or", "but", "if", "then", "so", "than", "too", "very", "just",
}


class Compressor:
    """
    Implements extractive context compression to fit relevant facts
    into the LLM's token budget.
    """

    # Class-level eviction log for backward compatibility with static method calls
    _eviction_log: list = []

    def __init__(self):
        # Instance-level eviction log (mirrors class-level for instance method calls)
        self.last_eviction_log = []

    @staticmethod
    def _split_into_segments(documents: List[str]) -> List[str]:
        """
        Splits documents into coherent text segments (paragraphs or complete code blocks).
        Prevents breaking code blocks, lists, or tables into disjointed sentences.
        """
        segments = []
        for doc in documents:
            lines = doc.split("\n")
            in_code_block = False
            current_code = []
            current_text = []
            
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("```"):
                    if in_code_block:
                        current_code.append(line)
                        segments.append("\n".join(current_code))
                        current_code = []
                        in_code_block = False
                    else:
                        if current_text:
                            segments.append("\n".join(current_text))
                            current_text = []
                        in_code_block = True
                        current_code.append(line)
                elif in_code_block:
                    current_code.append(line)
                else:
                    if not stripped:
                        if current_text:
                            segments.append("\n".join(current_text))
                            current_text = []
                    else:
                        current_text.append(line)
            
            if current_code:
                segments.append("\n".join(current_code))
            if current_text:
                segments.append("\n".join(current_text))
                
        return [s.strip() for s in segments if len(s.strip()) > 10]

    @staticmethod
    def compress(documents: List[str], query: str, max_tokens: int = 500) -> str:
        """
        Scores individual segments (paragraphs/code blocks) by query overlap and selects the top-K
        until the token budget is reached.
        """
        if not documents:
            return ""

        t_start = time.time()
        full_text = "\n\n".join(documents)
        initial_tokens = len(tokenizer.encode(full_text))

        # FAST PATH: If already under budget, skip expensive splitting/scoring
        if initial_tokens < max_tokens:
            logger.debug(f"Fast path: {initial_tokens} < {max_tokens} budget.")
            return full_text

        # Split all documents into coherent segments
        all_segments = Compressor._split_into_segments(documents)

        if not all_segments:
            tokens = tokenizer.encode(documents[0])[:max_tokens]
            return tokenizer.decode(tokens)

        # Lexical overlap scoring with stopword filtering
        raw_query_words = set(re.findall(r'\w+', query.lower()))
        filtered_query = raw_query_words - STOPWORDS
        query_words = filtered_query if filtered_query else raw_query_words

        scored = []
        for segment in all_segments:
            raw_seg_words = set(re.findall(r'\w+', segment.lower()))
            filtered_seg = raw_seg_words - STOPWORDS
            segment_words = filtered_seg if filtered_seg else raw_seg_words
            overlap = len(query_words & segment_words) / (len(query_words) + 1)
            scored.append(overlap)

        # Greedy selection by descending score until budget exhausted
        indexed = sorted(enumerate(scored), key=lambda x: x[1], reverse=True)
        selected = set()
        current_tokens = 0
        eviction_log = []
        for idx, score in indexed:
            segment_len = len(tokenizer.encode(all_segments[idx]))
            if current_tokens + segment_len <= max_tokens and score > COMPRESSION_SCORE_THRESHOLD:
                selected.add(idx)
                current_tokens += segment_len
                eviction_log.append({
                    "status": "KEPT",
                    "score": round(score, 4),
                    "tokens": segment_len,
                    "text": all_segments[idx][:200]  # preview
                })
            else:
                reason = "Below score threshold" if score <= COMPRESSION_SCORE_THRESHOLD else "Budget exceeded"
                eviction_log.append({
                    "status": "DROPPED",
                    "score": round(score, 4),
                    "tokens": segment_len,
                    "text": all_segments[idx][:200],  # preview
                    "reason": reason
                })
        
        # Store eviction log at class level for backward compatibility
        Compressor._eviction_log = eviction_log

        # Maintain original document order for logical flow
        final = [s for i, s in enumerate(all_segments) if i in selected]
        compressed = "\n\n".join(final)
        final_tokens = len(tokenizer.encode(compressed))

        t_ms = (time.time() - t_start) * 1000
        logger.info(
            f"Reduced {len(all_segments)} segments -> {len(final)}. "
            f"Tokens: {initial_tokens} -> {final_tokens}. Time: {t_ms:.1f}ms"
        )
        return compressed
