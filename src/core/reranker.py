"""
RAG Reranker - Finding the Best Documents

When we search for documents, we get a list of candidates. This module re-scores
them more carefully to find the truly best matches using FlashrankRerank — a
LangChain-native document compressor backed by the Flashrank cross-encoder library.

Flashrank is CPU-only, fast, and encapsulates model loading, tokenisation, and
sigmoid scoring internally.
"""

import time
import logging
import asyncio
from typing import List, Dict

from src.core.config import RERANKER_MODEL

logger = logging.getLogger("RAG.Reranker")

import threading

_reranker_lock = threading.Lock()
_reranker_instance = None


def _get_flashrank_reranker():
    global _reranker_instance
    if _reranker_instance is None:
        with _reranker_lock:
            if _reranker_instance is None:
                model_name = RERANKER_MODEL.split("/")[-1] if "/" in RERANKER_MODEL else RERANKER_MODEL
                # Map config cross-encoder model to supported Flashrank models
                if "minilm" in model_name.lower():
                    model_name = "ms-marco-MiniLM-L-12-v2"
                elif "tinybert" in model_name.lower():
                    model_name = "ms-marco-TinyBERT-L-6-v2"
                else:
                    model_name = "ms-marco-MultiBERT-L-12"
                    
                logger.info(f"Lazy-loading raw Flashrank Ranker (model: {model_name})")
                from flashrank import Ranker
                _reranker_instance = Ranker(model_name=model_name)
    return _reranker_instance


class NeuralReranker:
    """
    Uses Flashrank to re-score search results for better accuracy.

    After we find documents that match your question, this class looks at each one
    more carefully to rank them by true relevance. Flashrank handles cross-encoder
    model loading, tokenisation, and scoring internally.

    The model is loaded only when first needed (lazy loading) to keep startup fast.
    """

    def __init__(self, model_name: str = RERANKER_MODEL):
        self._model_name = model_name
        self._model = None
        logger.info("NeuralReranker ready (model will load on first use via Flashrank)")

    @property
    def model(self):
        """Get the model, supporting backward compatibility and test mock setting."""
        return self._model

    def rerank(self, query: str, candidates: List[Dict]) -> List[Dict]:
        """
        Re-score document candidates by how well they match your question.

        This gives us a more accurate ranking than the initial search, helping the AI
        focus on the most useful documents.
        """
        if not candidates:
            return []

        t_start = time.time()

        # Check if a custom mock model is injected
        model = getattr(self, "_model", None)
        if model is not None:
            try:
                import math
                pairs = [[query, cand["text"]] for cand in candidates]
                scores = model.predict(pairs)
                for i, score in enumerate(scores):
                    raw_val = float(score)
                    normalized = 1 / (1 + math.exp(-raw_val))
                    candidates[i]["cross_score"] = normalized
                    candidates[i]["raw_score"] = raw_val
                return sorted(candidates, key=lambda x: x["cross_score"], reverse=True)
            except Exception as e:
                logger.warning(f"Injected mock model rerank failed: {e}")
                return candidates

        try:
            ranker = _get_flashrank_reranker()
            from flashrank import RerankRequest
            passages = [{"id": i, "text": cand["text"]} for i, cand in enumerate(candidates)]
            req = RerankRequest(query=query, passages=passages)
            reranked = ranker.rerank(req)
            
            # Map back to original candidate dict shape
            original_by_text = {c["text"]: c for c in candidates}
            result = []
            for rank_item in reranked:
                text = rank_item["text"]
                score = float(rank_item["score"])
                candidate = dict(original_by_text.get(text, {"text": text}))
                candidate["cross_score"] = score
                candidate["raw_score"] = score
                result.append(candidate)
        except Exception as e:
            logger.warning(f"Flashrank rerank failed, returning original order: {e}")
            result = candidates

        t_ms = (time.time() - t_start) * 1000
        if result:
            lo = result[-1].get("cross_score", 0)
            hi = result[0].get("cross_score", 0)
            logger.info(
                f"Re-ranked {len(candidates)} documents in {t_ms:.1f}ms. "
                f"Best score: {hi:.4f}, Worst: {lo:.4f}"
            )
        return result

    async def rerank_async(self, query: str, candidates: List[Dict]) -> List[Dict]:
        """
        Asynchronously re-scores query-document pairs.
        Runs the blocking reranker in a thread pool via asyncio.to_thread.
        """
        if not candidates:
            return []

        t_start = time.time()

        # Check if a custom mock model is injected
        model = getattr(self, "_model", None)
        if model is not None:
            def _do_cc_rerank():
                import math
                pairs = [[query, cand["text"]] for cand in candidates]
                scores = model.predict(pairs)
                for i, score in enumerate(scores):
                    raw_val = float(score)
                    normalized = 1 / (1 + math.exp(-raw_val))
                    candidates[i]["cross_score"] = normalized
                    candidates[i]["raw_score"] = raw_val
                return sorted(candidates, key=lambda x: x["cross_score"], reverse=True)

            try:
                return await asyncio.to_thread(_do_cc_rerank)
            except RuntimeError:
                # Fallback for thread restricted sandbox testing environments
                return _do_cc_rerank()

        def _do_rerank():
            ranker = _get_flashrank_reranker()
            from flashrank import RerankRequest
            passages = [{"id": i, "text": cand["text"]} for i, cand in enumerate(candidates)]
            req = RerankRequest(query=query, passages=passages)
            reranked = ranker.rerank(req)
            
            # Map back to original candidate dict shape
            original_by_text = {c["text"]: c for c in candidates}
            result = []
            for rank_item in reranked:
                text = rank_item["text"]
                score = float(rank_item["score"])
                candidate = dict(original_by_text.get(text, {"text": text}))
                candidate["cross_score"] = score
                candidate["raw_score"] = score
                result.append(candidate)
            return result

        try:
            result = await asyncio.to_thread(_do_rerank)
        except RuntimeError:
            # Fallback for thread restricted sandbox testing environments
            try:
                result = _do_rerank()
            except Exception as e:
                logger.warning(f"Fallback async Flashrank rerank failed: {e}")
                result = candidates
        except Exception as e:
            logger.warning(f"Async Flashrank rerank failed, returning original order: {e}")
            result = candidates

        t_ms = (time.time() - t_start) * 1000
        if result:
            lo = result[-1].get("cross_score", 0)
            hi = result[0].get("cross_score", 0)
            logger.info(
                f"Scored {len(candidates)} pairs async in {t_ms:.1f}ms. "
                f"Range: [{lo:.4f}, {hi:.4f}]"
            )
        return result
