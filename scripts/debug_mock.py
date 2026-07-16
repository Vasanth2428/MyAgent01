import os
import sys
from unittest.mock import MagicMock, patch

# Ensure RAG is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.core.model_provider import build_chat_model

base = MagicMock()
bound = MagicMock()
base.bind_tools.return_value = bound
tools = [MagicMock()]

with patch.dict(os.environ, {"LLM_PROVIDER": "groq"}, clear=True), patch(
    "langchain_groq.ChatGroq", return_value=base
) as constructor:
    from langchain_groq import ChatGroq
    print("TYPE OF ChatGroq:", type(ChatGroq))
    print("MOCK ATTRIBUTES CHECK:")
    print("  hasattr assert_called:", hasattr(ChatGroq, "assert_called"))
    print("  hasattr _mock_return_value:", hasattr(ChatGroq, "_mock_return_value"))
    print("  hasattr return_value:", hasattr(ChatGroq, "return_value"))
    result = build_chat_model("test_role", "test-model", tools=tools)
    print("Result matches bound:", result is bound)
