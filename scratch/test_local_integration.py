import os
import sys

# Add root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set environment variables for local testing
os.environ["LLM_PROVIDER"] = "local"
os.environ["LOCAL_LLM_API_BASE"] = "http://localhost:11434/v1"
os.environ["LOCAL_LLM_MODEL"] = "qwen2.5:7b"

# Import our updated modules
from src.core.model_provider import build_chat_model, resolve_provider, resolve_model
from src.core.llm import LLMService

print("Testing model resolver configuration:")
provider = resolve_provider("coding_worker")
model_name = resolve_model("coding_worker", "llama-3.1-8b-instant")
print(f"  Resolved provider: {provider} (expected: 'local')")
print(f"  Resolved model: {model_name} (expected: 'qwen2.5:7b')")

assert provider == "local"
assert model_name == "qwen2.5:7b"

print("\nBuilding Chat Model:")
try:
    model = build_chat_model("coding_worker", "llama-3.1-8b-instant")
    print(f"  Successfully built model of type: {type(model).__name__}")
    # Verify it is ChatOpenAI
    from langchain_openai import ChatOpenAI
    assert isinstance(model, ChatOpenAI)
    print("  Model is verified as ChatOpenAI instance.")
except Exception as e:
    print(f"  Error building model: {e}")
    sys.exit(1)

print("\nInitializing LLMService in local mode:")
try:
    service = LLMService()
    print(f"  Successfully initialized LLMService.")
    print(f"  Service mock mode: {service.is_mock} (expected: False)")
    print(f"  Service client type: {type(service._raw_sync).__name__} (expected: OpenAI)")
    
    from openai import OpenAI
    assert isinstance(service._raw_sync, OpenAI)
    assert service.is_mock is False
    print("  LLMService is verified pointing to OpenAI local server adapter.")
except Exception as e:
    print(f"  Error initializing LLMService: {e}")
    sys.exit(1)

print("\nAll integration verification checks passed successfully!")
