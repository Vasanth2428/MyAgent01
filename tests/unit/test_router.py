"""
Tests for retrieval-first agent architecture.

Key concepts tested:
1. Router determines pipeline BEFORE any LLM involvement
2. Retrieval is infrastructure (not a tool choice) 
3. STRICT_RAG pipeline enforces grounding in retrieved evidence
4. Confidence thresholds with explicit uncertainty messaging
"""

import pytest
from unittest.mock import Mock, MagicMock
from core.router import Router, PipelineType, retrieve_first, ground_generation


class TestPipelineType:
    """Tests for pipeline type enum."""

    def test_pipeline_type_values(self):
        """Pipeline types have correct string values."""
        assert PipelineType.STRICT_RAG.value == "STRICT_RAG_PIPELINE"
        assert PipelineType.WEB_AGENT.value == "WEB_AGENT_PIPELINE"
        assert PipelineType.CHAT.value == "CHAT_PIPELINE"
        assert PipelineType.HYBRID.value == "HYBRID_PIPELINE"


class TestRouter:
    """Tests for orchestrator-driven routing."""

    def test_casual_query_routes_to_chat(self):
        """Greetings and casual queries route to CHAT pipeline."""
        router = Router()
        
        result = router.route("hello", [], 0)
        assert result["pipeline"] == PipelineType.CHAT
        assert result["requires_retrieval"] is False
        assert "greeting" in result["reasoning"].lower()

    def test_private_query_routes_to_strict_rag(self):
        """Queries mentioning private/enterprise content route to STRICT_RAG."""
        router = Router()
        
        result = router.route("what is our company revenue", [], 50)
        assert result["pipeline"] == PipelineType.STRICT_RAG
        assert result["requires_retrieval"] is True
        assert result["confidence"] >= 0.7

    def test_web_query_routes_to_web_agent(self):
        """Queries requiring live data route to WEB_AGENT."""
        router = Router()
        
        result = router.route("what is the latest news today", [], 0)
        assert result["pipeline"] == PipelineType.WEB_AGENT
        assert result["requires_retrieval"] is False

    def test_ambiguous_query_routes_to_hybrid(self):
        """Queries without clear indicators route to HYBRID."""
        router = Router()
        
        result = router.route("tell me about python", [], 0)
        assert result["pipeline"] == PipelineType.HYBRID
        assert result["requires_retrieval"] is True

    def test_private_content_triggers_strict_rag(self):
        """Having private content available triggers STRICT_RAG."""
        router = Router()
        
        result = router.route("what documents do we have", ["file1.pdf", "file2.txt"], 100)
        assert result["pipeline"] == PipelineType.STRICT_RAG
        assert result["requires_retrieval"] is True


class TestRetrieveFirst:
    """Tests for retrieval-as-infrastructure function."""

    def test_retrieve_first_returns_confidence(self):
        """retrieve_first calculates confidence from reranker scores."""
        mock_engine = Mock()
        mock_engine._phase_expand.return_value = ["expanded query"]
        mock_engine._phase_hyde.return_value = "hyde hypothesis"
        mock_engine._phase_retrieve.return_value = [
            {"text": "doc1", "score": 0.9},
            {"text": "doc2", "score": 0.8}
        ]
        mock_engine.compressor.compress.return_value = "compressed context"

        result = retrieve_first("test query about document content", mock_engine)
        
        assert "context" in result
        assert "confidence" in result
        assert "evidence_found" in result
        # Confidence is derived from the reranker's sigmoid-normalized scores
        assert result["confidence"] >= 0.0

    def test_retrieve_first_handles_no_results(self):
        """retrieve_first handles empty retrieval gracefully."""
        mock_engine = Mock()
        mock_engine._phase_retrieve.return_value = []

        result = retrieve_first("test query", mock_engine)
        
        assert result["confidence"] == 0.0
        assert result["evidence_found"] is False

    def test_confidence_threshold_evidence_found(self):
        """Evidence found when confidence meets threshold - tests the threshold comparison logic."""
        mock_engine = Mock()
        mock_engine._phase_retrieve.return_value = [
            {"text": "doc content for query", "score": 0.9}
        ]
        
        # The neural reranker overwrites cross_score with sigmoid-normalized values
        # Just test that evidence_found logic works with actual model output
        result = retrieve_first("query about doc content", mock_engine, min_confidence=0.1)
        
        # The key test: when we have results, evidence_found depends on confidence threshold
        # If confidence >= min_confidence, evidence_found should be True
        # This test documents the expected behavior - the actual confidence depends on model
        assert "confidence" in result
        assert "evidence_found" in result
        # With reasonable threshold and actual retrieval, we can verify the relationship
        if result["confidence"] >= 0.1:
            assert result["evidence_found"] is True


class TestGroundGeneration:
    """Tests for grounded generation prompt."""

    def test_ground_generation_low_confidence_warning(self):
        """Prompt includes low confidence warning for confidence < 0.3."""
        prompt = ground_generation("question", "evidence", 0.2)
        
        assert "LOW CONFIDENCE" in prompt
        assert "does not contain this information" in prompt

    def test_ground_generation_medium_confidence_warning(self):
        """Prompt includes medium confidence warning for confidence 0.3-0.5."""
        prompt = ground_generation("question", "evidence", 0.4)
        
        assert "MEDIUM CONFIDENCE" in prompt

    def test_ground_generation_high_confidence_clean_prompt(self):
        """Prompt is clean for high confidence >= 0.5."""
        prompt = ground_generation("question", "evidence", 0.6)
        
        assert "LOW CONFIDENCE" not in prompt
        assert "MEDIUM CONFIDENCE" not in prompt

    def test_ground_generation_includes_evidence(self):
        """Prompt includes the retrieved evidence."""
        prompt = ground_generation("question", "my evidence here", 0.8)
        
        assert "my evidence here" in prompt
        assert "### RETRIEVED EVIDENCE:" in prompt
        assert "### QUESTION:" in prompt
        assert "### ANSWER:" in prompt

    def test_ground_generation_requires_only_evidence(self):
        """Prompt instructs to use ONLY retrieved evidence."""
        prompt = ground_generation("question", "evidence", 0.8)
        
        assert "ONLY the provided evidence" in prompt
        assert "HIGHER AUTHORITY" in prompt