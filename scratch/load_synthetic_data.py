import os
import sys
import json
from dotenv import load_dotenv

# Add parent directory to path to import core modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.retriever import WeaviateRetriever
from core.splitter import ParentChildSplitter

def load_data():
    load_dotenv()
    
    # Path to synthetic data
    workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    jsonl_path = os.path.join(workspace_dir, "synthetic_vector_data.jsonl")
    
    if not os.path.exists(jsonl_path):
        print(f"Error: {jsonl_path} does not exist.")
        return
        
    print("Connecting to Weaviate Cloud...")
    retriever = WeaviateRetriever()
    splitter = ParentChildSplitter()
    
    try:
        print(f"Reading synthetic data from {jsonl_path}...")
        with open(jsonl_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        print(f"Found {len(lines)} records to index.")
        
        for idx, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
                
            record = json.loads(line)
            text = record.get("text", "")
            metadata = record.get("metadata", {})
            tags = metadata.get("tags", [])
            source = metadata.get("source", "unknown")
            
            # Split text using ParentChildSplitter
            # This is robust because if any text is long, it will be properly chunked.
            # If it's short, it will result in a single parent-child pair (where parent == child).
            pairs = splitter.split_text(text)
            
            if not pairs:
                continue
                
            # Index document
            print(f"[{idx}/{len(lines)}] Indexing record from source '{source}' with tags {tags}...")
            retriever.add_parent_child_documents(pairs, tags=tags, source=source)
            
        print("\nVerification: retrieving count of indexed documents...")
        count = retriever.get_count()
        print(f"Total documents in RAGKnowledge collection: {count}")
        
        sources = retriever.get_sources()
        print(f"Indexed sources: {sources}")
        
    except Exception as e:
        print(f"Error during ingestion: {e}")
    finally:
        retriever.close()
        print("Connection closed.")

if __name__ == "__main__":
    load_data()
