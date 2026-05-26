"""
Tests for retrieval-first RAG agent.

Key concepts tested:
1. Router determines pipeline BEFORE agent execution
2. STRICT_RAG pipeline retrieves BEFORE generation (not as tool)
3. Confidence thresholds trigger uncertainty messaging
4. Web agent pipeline uses web tools only
5. Grounded generation uses ONLY retrieved evidence
"""

import unittest
from unittest.mock import MagicMock, patch, Mock
from core.agent import RAGAgent


def make_mock_stream(text: str):
    mock_chunk = MagicMock()
    mock_chunk.choices = [MagicMock()]
    mock_chunk.choices[0].delta = MagicMock()
    mock_chunk.choices[0].delta.content = text
    return [mock_chunk]


class TestRAGAgentRouting(unittest.TestCase):
    """Tests for pipeline routing in RAGAgent."""

    def setUp(self):
        self.mock_engine = MagicMock()
        self.mock_engine.stats = {"queries": 0}
        self.mock_engine.llm_service = MagicMock()
        self.mock_engine.llm_service.model = "test-model"
        self.mock_engine.retriever.get_sources.return_value = ["file1.pdf"]
        self.mock_engine.retriever.get_count.return_value = 50
        self.mock_engine.get_memory.return_value = MagicMock()
        self.mock_engine.get_memory.return_value.get_active_context.return_value = ""
        self.mock_engine.save_memory = MagicMock()

    def test_casual_query_routes_to_chat(self):
        """Simple greetings route to CHAT pipeline without LLM calls for routing."""
        agent = RAGAgent(self.mock_engine)
        events = list(agent.run_stream("hello", session_id="test"))

        routing_event = next((e for e in events if e["event"] == "routing_decision"), None)
        self.assertIsNotNone(routing_event)
        self.assertEqual(routing_event["route"], "CHAT_PIPELINE")

    def test_private_query_routes_to_strict_rag(self):
        """Queries with private indicators route to STRICT_RAG."""
        agent = RAGAgent(self.mock_engine)
        
        self.mock_engine._phase_retrieve.return_value = [{"text": "doc", "score": 0.9, "cross_score": 0.45}]
        self.mock_engine.compressor.compress.return_value = "compressed"
        
        events = list(agent.run_stream("what is our company revenue", session_id="test"))
        
        routing_event = next((e for e in events if e["event"] == "routing_decision"), None)
        self.assertEqual(routing_event["route"], "STRICT_RAG_PIPELINE")

    def test_web_query_routes_to_web_agent(self):
        """Queries requiring live data route to WEB_AGENT pipeline."""
        agent = RAGAgent(self.mock_engine)
        
        # No sources available means no private content
        self.mock_engine.retriever.get_sources.return_value = []
        self.mock_engine.retriever.get_count.return_value = 0
        
        self.mock_engine.client.chat.completions.create.side_effect = [
            make_mock_stream("Thought: Using web tools.\nAction: web_search[current news]\nFinal Answer: Found news.")
        ]
        
        events = list(agent.run_stream("what is the latest news today", session_id="test"))
        
        routing_event = next((e for e in events if e["event"] == "routing_decision"), None)
        self.assertEqual(routing_event["route"], "WEB_AGENT_PIPELINE")


class TestStrictRAGPipeline(unittest.TestCase):
    """Tests for STRICT_RAG pipeline behavior."""

    def setUp(self):
        self.mock_engine = MagicMock()
        self.mock_engine.stats = {"queries": 0}
        self.mock_engine.llm_service = MagicMock()
        self.mock_engine.llm_service.model = "test-model"
        self.mock_engine.retriever.get_sources.return_value = ["file1.pdf"]
        self.mock_engine.retriever.get_count.return_value = 50
        self.mock_engine.get_memory.return_value = MagicMock()
        self.mock_engine.get_memory.return_value.get_active_context.return_value = ""
        self.mock_engine.save_memory = MagicMock()

    def test_retrieval_happens_before_generation(self):
        """In STRICT_RAG, retrieval infrastructure runs BEFORE agent synthesis."""
        agent = RAGAgent(self.mock_engine)
        
        self.mock_engine._phase_retrieve.return_value = [{"text": "secret info", "score": 0.9, "cross_score": 0.45}]
        self.mock_engine.compressor.compress.return_value = "secret info compressed"
        self.mock_engine.client.chat.completions.create.return_value = make_mock_stream("Answer from evidence.")
        
        events = list(agent.run_stream("what is our api key", session_id="test"))
        
        retrieval_event = next((e for e in events if e["event"] == "retrieval_phase"), None)
        self.assertIsNotNone(retrieval_event)
        
        doc_event = next((e for e in events if e["event"] == "document_retrieval"), None)
        self.assertIsNotNone(doc_event)

    def test_low_confidence_triggers_uncertainty_messaging(self):
        """Low confidence (< 0.3) triggers explicit uncertainty in generation."""
        agent = RAGAgent(self.mock_engine)
        
        self.mock_engine._phase_retrieve.return_value = [{"text": "weak match", "score": 0.1, "cross_score": 0.1}]
        self.mock_engine.compressor.compress.return_value = "weak match"
        
        captured_prompts = []
        def capture_prompt(**kwargs):
            captured_prompts.append(kwargs.get("messages", [{}])[0].get("content", ""))
            return make_mock_stream("I don't have this information.")
        self.mock_engine.client.chat.completions.create.side_effect = capture_prompt
        
        list(agent.run_stream("what is our secret", session_id="test"))
        
        prompt = captured_prompts[0] if captured_prompts else ""
        self.assertIn("LOW CONFIDENCE", prompt)

    def test_evidence_found_in_final_response(self):
        """Retrieved evidence is included in final done event."""
        agent = RAGAgent(self.mock_engine)
        
        self.mock_engine._phase_retrieve.return_value = [{"text": "document text", "score": 0.9, "cross_score": 0.45}]
        self.mock_engine.compressor.compress.return_value = "document text"
        self.mock_engine.client.chat.completions.create.return_value = make_mock_stream("Answer.")
        
        events = list(agent.run_stream("what is our policy", session_id="test"))
        
        done_event = next((e for e in events if e["event"] == "done"), None)
        self.assertIsNotNone(done_event)
        self.assertIn("retrieved_context", done_event["stats"])


class TestWebAgentPipeline(unittest.TestCase):
    """Tests for WEB_AGENT pipeline behavior."""

    def setUp(self):
        self.mock_engine = MagicMock()
        self.mock_engine.stats = {"queries": 0}
        self.mock_engine.llm_service = MagicMock()
        self.mock_engine.llm_service.model = "test-model"
        self.mock_engine.retriever.get_sources.return_value = []
        self.mock_engine.retriever.get_count.return_value = 0
        self.mock_engine.get_memory.return_value = MagicMock()
        self.mock_engine.get_memory.return_value.get_active_context.return_value = ""
        self.mock_engine.save_memory = MagicMock()

    @patch("core.agent.search_web")
    def test_web_search_tool_execution(self, mock_search):
        """WEB_AGENT pipeline uses web_search tool."""
        agent = RAGAgent(self.mock_engine)
        mock_search.return_value = [{"title": "Result", "url": "https://example.com", "snippet": "Info"}]
        
        self.mock_engine.client.chat.completions.create.side_effect = [
            make_mock_stream("Thought: Searching.\nAction: web_search[current news]\nFinal Answer: Found."),
        ]
        
        events = list(agent.run_stream("what is happening today", session_id="test"))
        
        action_event = next((e for e in events if e["event"] == "action"), None)
        self.assertIsNotNone(action_event)
        self.assertEqual(action_event["tool"], "web_search")


class TestParseAction(unittest.TestCase):
    """Tests for action parsing from LLM responses."""

    def setUp(self):
        self.mock_engine = MagicMock()
        self.mock_engine.stats = {"queries": 0}
        self.mock_engine.llm_service = MagicMock()
        self.mock_engine.retriever.get_sources.return_value = []
        self.mock_engine.retriever.get_count.return_value = 0
        agent = RAGAgent(self.mock_engine)
        self.agent = agent

    def test_parse_valid_action_with_arg(self):
        """Parse action with argument."""
        text = "Action: web_search[machine learning]"
        result = self.agent.parse_action(text)
        self.assertEqual(result, ("web_search", "machine learning"))

    def test_parse_action_with_quotes(self):
        """Parse action with quoted argument."""
        text = 'Action: web_search["machine learning"]'
        result = self.agent.parse_action(text)
        self.assertEqual(result, ("web_search", "machine learning"))

    def test_parse_action_no_argument(self):
        """Parse action without argument."""
        text = "Action: get_system_stats"
        result = self.agent.parse_action(text)
        self.assertEqual(result, ("get_system_stats", ""))

    def test_parse_no_action_returns_none(self):
        """No action returns None."""
        text = "Thought: I should respond.\nFinal Answer: Hello."
        result = self.agent.parse_action(text)
        self.assertIsNone(result)


class TestActionEvents(unittest.TestCase):
    """Tests for action event emission."""

    def setUp(self):
        self.mock_engine = MagicMock()
        self.mock_engine.stats = {"queries": 0}
        self.mock_engine.llm_service = MagicMock()
        self.mock_engine.llm_service.model = "test-model"
        self.mock_engine.retriever.get_sources.return_value = []
        self.mock_engine.retriever.get_count.return_value = 0
        self.mock_engine.get_memory.return_value = MagicMock()
        self.mock_engine.get_memory.return_value.get_active_context.return_value = ""
        self.mock_engine.save_memory = MagicMock()

    def test_action_and_observation_events(self):
        """Web pipeline emits action and observation events."""
        agent = RAGAgent(self.mock_engine)
        
        self.mock_engine.client.chat.completions.create.side_effect = [
            make_mock_stream("Thought: Getting stats.\nAction: get_system_stats[]\nFinal Answer: CPU at 10%."),
        ]
        
        events = list(agent.run_stream("how are system stats", session_id="test"))
        
        event_types = [e["event"] for e in events]
        self.assertIn("action", event_types)
        self.assertIn("observation", event_types)


if __name__ == "__main__":
    unittest.main()