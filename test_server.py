import urllib.request
import json
import sys

def test_server():
    url = "http://localhost:8000/query"
    data = {
        "question": "Create a React frontend and Python FastAPI backend for a crypto portfolio website inside `./workspace/crypto_portfolio` (place frontend files under 'crypto_portfolio/frontend' and backend files under 'crypto_portfolio/backend')",
        "mode": "agentic",
        "bypass_hitl": True
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    print(f"Sending request to {url}...", flush=True)
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_server()
