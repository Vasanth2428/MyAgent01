import os
import sys
from dotenv import load_dotenv

# Add parent directory to path to import core modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.retriever import WeaviateRetriever

def clear_database():
    load_dotenv()
    print("Connecting to Weaviate Cloud...")
    retriever = WeaviateRetriever()
    try:
        # Delete RAGKnowledge first since it references RAGParentKnowledge
        print("Checking 'RAGKnowledge'...")
        if retriever.client.collections.exists("RAGKnowledge"):
            print("Deleting 'RAGKnowledge' collection...")
            retriever.client.collections.delete("RAGKnowledge")
            print("Successfully deleted 'RAGKnowledge'.")

        print("Checking 'RAGParentKnowledge'...")
        if retriever.client.collections.exists("RAGParentKnowledge"):
            print("Deleting 'RAGParentKnowledge' collection...")
            retriever.client.collections.delete("RAGParentKnowledge")
            print("Successfully deleted 'RAGParentKnowledge'.")

        # Now recreate both by just closing and re-initializing the retriever!
        print("Re-initializing WeaviateRetriever to recreate clean collections...")
        retriever.close()
        
        retriever = WeaviateRetriever()
        print("Clean collections successfully recreated via retriever initializer!")
    except Exception as e:
        print(f"Error clearing database: {e}")
    finally:
        retriever.close()
        print("Connection closed.")

if __name__ == "__main__":
    clear_database()
