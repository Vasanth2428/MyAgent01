import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.retriever import WeaviateRetriever
from core.engine import AgenticSystem

def main():
    print("Initializing retriever and engine...")
    retriever = WeaviateRetriever()
    rag = AgenticSystem(retriever)
    
    query = "what is your knowledge base?"
    print(f"\n--- Running ask_stream for query: '{query}' ---")
    
    for event in rag.ask_stream(query, session_id="test_stream_session", mode="agentic"):
        print(event)

if __name__ == "__main__":
    main()
