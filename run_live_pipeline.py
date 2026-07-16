import os
import sys
import codecs
sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())
import time
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

# Load environment variables
load_dotenv("config/.env", override=True)

# Ensure workspace root is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.graph.workflow import build_multi_agent_graph, get_graph_config

def main():
    print("Initializing Live Multi-Agent Workflow...")
    # Initialize graph checkpointer
    from src.graph.checkpointer import setup_checkpointer
    checkpointer = setup_checkpointer()
    graph = build_multi_agent_graph(checkpointer)
    
    # Detailed prompt for a rigorous end-to-end fullstack test
    default_query = """
Build a truly functional, production-ready Fullstack AI Dashboard Platform.
You must strictly build this inside `./workspace/ai_dashboard`.

Requirements:
1. Frontend: React + Vite + TailwindCSS. Create a stunning, highly responsive UI with glassmorphism, animated charts, and dark mode.
2. Backend: Node.js + Express API (or FastAPI if you prefer Python).
3. Data: Implement a robust mock database (JSON/memory) tracking realtime metrics for 5 AI models.
4. Core Features:
   - A dynamic dashboard layout with a sidebar and top navigation.
   - Live metrics (Latency, Tokens/sec, Cost) fetched from the backend API.
   - A "Model Settings" page that updates the backend configuration.
5. Automated Validation: You MUST write a unit test suite for the backend API and ensure it passes successfully via the Headless Critic.

Execute this end-to-end. Do not stop until the application is fully functional, styled, and validated.
"""
    query = sys.argv[1] if len(sys.argv) > 1 else default_query
    config = get_graph_config(f"live_build_{int(time.time())}")
    
    from src.graph.state_2pipeline import create_initial_state
    initial_state = create_initial_state([HumanMessage(content=query)], bypass_hitl=True)
    initial_state.update({
        "steps_remaining": 15,
        "active_project": "my-react-app",
        "session_id": f"live_build_{int(time.time())}"
    })
    
    print("\nRunning Live Multi-Agent pipeline (calling real LLMs)...")
    import traceback
    try:
        result = graph.invoke(initial_state, config=config)
        print("\nPipeline run completed successfully.")
        print("\nFinal Answer from Synthesizer:")
        print(result.get("final_answer", "(No final answer found)"))
    except Exception as e:
        print("\nPipeline execution encountered an error:", e)
        traceback.print_exc()

if __name__ == "__main__":
    main()
