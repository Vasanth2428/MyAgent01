import os
import sys
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
    
    # Simple query
    query = "Create a full stack website for a prestigious university (University of Advanced Sciences). It must be at the level of an actual premium college website, including admissions, academics, campus life, and an admin dashboard. Use a Node.js Express backend and a React frontend. Place it in `./workspace/college_website`."
    config = get_graph_config(f"live_build_{int(time.time())}")
    
    from src.graph.state_2pipeline import create_initial_state
    initial_state = create_initial_state([HumanMessage(content=query)], bypass_hitl=True)
    initial_state.update({
        "steps_remaining": 15,
        "active_project": "college_website",
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
