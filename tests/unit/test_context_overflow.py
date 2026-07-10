import unittest
from unittest.mock import MagicMock, patch
from src.core.engine import RAGContextEngine

class TestContextOverflow(unittest.TestCase):

    def setUp(self):
        self.retriever = MagicMock()
        self.retriever.get_count.return_value = 10
        with patch('src.core.engine.LLMService') as mock_llm_service:
            mock_llm = MagicMock()
            mock_llm_service.return_value = mock_llm
            self.engine = RAGContextEngine(self.retriever)
if __name__ == '__main__':
    unittest.main()