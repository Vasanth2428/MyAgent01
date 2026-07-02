"""
Retrieval Service - Finding Relevant Documents

This service handles searching through your document database. When you ask a question,
it runs multiple search queries (the original question plus variations) and combines
the results to find the most relevant document chunks.
"""

import time
import logging
import asyncio
import copy
import threading
from collections import OrderedDict
from typing import List, Dict, Tuple, Optional
from src.core.config import MAX_CANDIDATES
from src.core.retriever import WeaviateRetriever

logger = logging.getLogger("RAG.Services.Retrieval")

RETRIEVAL_CACHE_TTL_SECONDS = 120
RETRIEVAL_CACHE_MAX_ENTRIES = 128


class RetrievalService:
    """
    Searches the document database for relevant content.
    
    When you ask a question, this service:
    1. Runs the original question through the search
    2. Runs any query variations through search too
    3. Combines and dedupes results
    4. Returns the top candidates for the AI to use
    
    This helps find the most relevant pieces of your documents to answer questions.
    """

    def __init__(self, retriever: WeaviateRetriever):
        self.retriever = retriever  # Our connection to the document database
        self._cache = OrderedDict()
        self._cache_lock = threading.RLock()

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()

    def _cache_key(self, search_queries: List[str], top_k: int, source_filter: Optional[str]) -> tuple:
        return tuple(search_queries), top_k, source_filter

    def _get_cached(self, key: tuple) -> Optional[List[Dict]]:
        now = time.time()
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is None:
                return None

            created_at, results = cached
            if now - created_at > RETRIEVAL_CACHE_TTL_SECONDS:
                self._cache.pop(key, None)
                return None

            self._cache.move_to_end(key)
            return copy.deepcopy(results)

    def _store_cached(self, key: tuple, results: List[Dict]) -> None:
        with self._cache_lock:
            self._cache[key] = (time.time(), copy.deepcopy(results))
            self._cache.move_to_end(key)
            while len(self._cache) > RETRIEVAL_CACHE_MAX_ENTRIES:
                self._cache.popitem(last=False)

    def _merge_ranked_results(self, query_results: List[Tuple[List[Dict], float, float]]) -> Tuple[List[Dict], float, float]:
        candidates_by_text = {}
        rrf_scores = {}
        k_rrf = 60
        embed_total = 0.0
        db_total = 0.0

        for retrieved, embed_lat, db_lat in query_results:
            for rank, r in enumerate(retrieved, 1):
                text = r["text"]
                score = r.get("score", 0.0)
                if text not in candidates_by_text:
                    candidates_by_text[text] = copy.deepcopy(r)
                elif score > candidates_by_text[text].get("score", 0.0):
                    candidates_by_text[text]["score"] = score

                rrf_scores[text] = rrf_scores.get(text, 0.0) + (1.0 / (k_rrf + rank))
            embed_total += embed_lat
            db_total += db_lat

        for text, candidate in candidates_by_text.items():
            candidate["rrf_score"] = rrf_scores[text]

        sorted_candidates = sorted(candidates_by_text.values(), key=lambda x: x.get("rrf_score", 0.0), reverse=True)
        return sorted_candidates[:MAX_CANDIDATES], round(embed_total, 2), round(db_total, 2)

    def retrieve(self, search_queries: List[str], top_k: int, source_filter: Optional[str] = None) -> Tuple[List[Dict], float, float, float]:
        """
        Search for documents using multiple query variations.
        
        Args:
            search_queries: List of search queries (original + variations)
            top_k: Maximum number of documents to return per query
            source_filter: Optional filter to only search specific documents
            
        Returns:
            - List of unique document results, sorted by relevance (using Reciprocal Rank Fusion)
            - Embedding generation time in ms
            - Database search time in ms
            - Total time in ms
        """
        t = time.time()
        cache_key = self._cache_key(search_queries, top_k, source_filter)
        cached_results = self._get_cached(cache_key)
        if cached_results is not None:
            logger.info("[P2: RETRIEVAL] Cache hit for retrieval query set.")
            return cached_results, 0.0, 0.0, round((time.time() - t) * 1000, 2)

        logger.info("[P2: RETRIEVAL] Searching for relevant documents...")
        query_results = [
            self.retriever.retrieve(q, top_k=top_k, source_filter=source_filter)
            for q in search_queries
        ]
        results, embed_total, db_total = self._merge_ranked_results(query_results)
        self._store_cached(cache_key, results)

        logger.info(f" -> Found {len(results)} unique relevant document chunks.")
        total_ms = round((time.time() - t) * 1000, 2)
        
        return results, round(embed_total, 2), round(db_total, 2), total_ms

    async def retrieve_async(self, search_queries: List[str], top_k: int, source_filter: Optional[str] = None) -> Tuple[List[Dict], float, float, float]:
        """
        Search for documents concurrently using multiple query variations.
        
        This async version runs searches in parallel instead of one after another,
        making it faster when you have multiple search queries.
        
        Args:
            search_queries: List of search queries (original + variations)
            top_k: Maximum number of documents to return per query
            source_filter: Optional filter to only search specific documents
            
        Returns:
            - List of unique document results, sorted by relevance (using Reciprocal Rank Fusion)
            - Embedding generation time in ms
            - Database search time in ms
            - Total time in ms
        """
        t = time.time()
        cache_key = self._cache_key(search_queries, top_k, source_filter)
        cached_results = self._get_cached(cache_key)
        if cached_results is not None:
            logger.info("[P2: RETRIEVAL] Cache hit for retrieval query set.")
            return cached_results, 0.0, 0.0, round((time.time() - t) * 1000, 2)

        logger.info("[P2: RETRIEVAL] Searching concurrently for relevant documents...")
        
        async def single_retrieve(q):
            # Run each search in a thread to avoid blocking
            retrieved, embed_lat, db_lat = await asyncio.to_thread(self.retriever.retrieve, q, top_k=top_k, source_filter=source_filter)
            return retrieved, embed_lat, db_lat

        # Run all searches at once
        tasks = [single_retrieve(q) for q in search_queries]
        query_results = await asyncio.gather(*tasks)
        results, embed_total, db_total = self._merge_ranked_results(query_results)
        self._store_cached(cache_key, results)

        logger.info(f" -> Found {len(results)} unique relevant document chunks (searched in parallel).")
        total_ms = round((time.time() - t) * 1000, 2)
        
        return results, round(embed_total, 2), round(db_total, 2), total_ms
