import requests
import json
import sys

# Ensure stdout uses UTF-8 to prevent charmap errors on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

url = "http://127.0.0.1:8000/query_stream"
payload = {
    "question": "Please build a full-stack React and Python website that serves as a sample dashboard application. The application should include a modern frontend built with React, featuring a dashboard with mock data charts and statistics. The backend should be a Python server (FastAPI) that serves this mock data via REST endpoints. Ensure the UI has a sleek, responsive design with a glassmorphic navigation bar. The mock data should include user statistics, recent activity feeds, and system health metrics. Please create the necessary React components, hook them up to the backend API, and ensure CORS is handled properly. Include a robust error handling mechanism on the frontend to gracefully manage loading states and failed requests. Use Vite for the frontend build setup. Write the files into the workspace/ai_dashboard directory.",
    "session_id": "test_coding_subsystem_3",
    "mode": "agentic",
    "bypass_hitl": True
}

print("Sending request to RAG Engine Stream...")
try:
    with requests.post(url, json=payload, stream=True) as response:
        print(f"Status Code: {response.status_code}")
        for line in response.iter_lines():
            if line:
                decoded = line.decode("utf-8")
                if decoded.startswith("data: "):
                    try:
                        data = json.loads(decoded[6:])
                        event = data.get("event")
                        if event == "node_start":
                            print(f"\n[{data.get('node').upper()}] Started")
                        elif event == "thought":
                            print(f"Thought: {data.get('text')}")
                        elif event == "observation":
                            print(f"Observation: {data.get('output')[:200]}...")
                        elif event == "answer_chunk":
                            print(data.get("text"), end="", flush=True)
                        elif event == "error":
                            print(f"\nERROR: {data.get('message')}")
                        elif event == "done":
                            print("\n[STREAM COMPLETE]")
                        else:
                            print(f"Event: {event}")
                    except json.JSONDecodeError:
                        print(decoded)
except Exception as e:
    print(f"Connection failed: {e}")
