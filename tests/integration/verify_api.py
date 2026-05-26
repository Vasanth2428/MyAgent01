import os
import requests
import json

url = "http://localhost:8000/query"
data = {"question": "What is the operating system course code?"}
api_key = os.getenv("RAG_API_KEY", "rag-admin-secret-key-2026")
headers = {"Authorization": f"Bearer {api_key}"}
response = requests.post(url, json=data, headers=headers)

print(f"Status Code: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")
