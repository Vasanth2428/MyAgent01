import requests
import json
import sys
import uuid

# Ensure stdout uses UTF-8 to prevent charmap errors on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

url = "http://127.0.0.1:8000/query_stream"
payload = {
    "question": "Build a stunning, modern landing page for a fictional AI startup called 'NexusAI'. Create a new React project in `workspace/nexus_ai` using Vite. The landing page should feature glassmorphism, smooth gradients, a dark mode aesthetic, and include a hero section, features list, and a contact form. Focus heavily on premium aesthetics and responsive design. Do not stop until the frontend is fully scaffolded and the components are written. You must write actual code.",
    "session_id": "test_website_" + uuid.uuid4().hex[:6],
    "mode": "agentic",
    "bypass_hitl": True
}

print("Sending request to RAG Engine Stream for Website Build...")
try:
    with requests.post(url, json=payload, stream=True) as response:
        print(f"Status Code: {response.status_code}")
        for line in response.iter_lines():
            if line:
                decoded = line.decode("utf-8", errors="replace")
                if decoded.startswith("data: "):
                    try:
                        data = json.loads(decoded[6:])
                        event = data.get("event")
                        if event == "node_start":
                            print(f"\n[{data.get('node').upper()}] Started")
                        elif event == "thought":
                            print(f"Thought: {data.get('text')}")
                        elif event == "observation":
                            print(f"Observation: {data.get('output')[:300]}...")
                        elif event == "answer_chunk":
                            print(data.get("text"), end="", flush=True)
                        elif event == "error":
                            print(f"\nERROR: {data.get('message')}")
                        elif event == "done":
                            print("\n[STREAM COMPLETE]")
                    except json.JSONDecodeError:
                        pass
except Exception as e:
    print(f"Connection failed: {e}")
