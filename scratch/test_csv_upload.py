import os
import sys
import requests
from dotenv import load_dotenv

# Add parent directory to path to import core modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_test():
    load_dotenv()
    
    api_key = os.getenv("RAG_API_KEY", "rag-admin-secret-key-2026")
    server_url = "http://localhost:8000"
    
    # 1. Create a temporary test CSV file
    test_csv_path = r"c:\Users\vasan\Documents\Apphelix Intern\RAG\scratch\test_upload_products.csv"
    csv_content = """product_id,product_name,category,unit_price,supplier,stock_quantity
9999,Super Test Ingestion Widget,Electronics,123.45,TestSupplierCorp,999
"""
    with open(test_csv_path, "w", encoding="utf-8") as f:
        f.write(csv_content)
        
    print(f"Created temporary CSV file at {test_csv_path}")
    
    # 2. Upload the CSV to the server
    upload_url = f"{server_url}/upload"
    headers = {
        "X-API-Key": api_key
    }
    
    print(f"Uploading file to {upload_url}...")
    with open(test_csv_path, "rb") as f:
        files = {
            "file": (os.path.basename(test_csv_path), f, "text/csv")
        }
        response = requests.post(upload_url, headers=headers, files=files)
        
    print(f"Upload Response Status Code: {response.status_code}")
    print(f"Upload Response JSON: {response.json()}")
    
    # Clean up temp file
    if os.path.exists(test_csv_path):
        os.remove(test_csv_path)
        print("Removed temporary CSV file.")
        
    # 3. Query the RAG engine to verify semantic search retrieval of the uploaded record
    if response.status_code == 200:
        query_url = f"{server_url}/query"
        query_payload = {
            "question": "What is the unit price and stock quantity of the Super Test Ingestion Widget?",
            "session_id": "test_session_csv",
            "mode": "context_engine"
        }
        print(f"\nQuerying the RAG engine at {query_url}...")
        query_response = requests.post(query_url, headers=headers, json=query_payload)
        
        print(f"Query Response Status Code: {query_response.status_code}")
        print("Query Answer:")
        print(query_response.json().get("response"))
        print("\nRetrieved Context:")
        for doc in query_response.json().get("retrieved_context", []):
            print(f"- Source: {doc.get('source')} | Text: {doc.get('text')}")

if __name__ == "__main__":
    run_test()
