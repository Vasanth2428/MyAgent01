import os
import json
import sys
import time
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

# Load environment
from dotenv import load_dotenv
load_dotenv("config/.env", override=True)
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.graph.supervisor import supervisor_node
from src.agents.coding_worker import coding_worker_node
from src.agents.code_critic_worker import code_critic_worker_node

def test_supervisor_compression():
    print("\n--- Testing Supervisor Compression Edge Case ---")
    messages = [SystemMessage(content="Init")]
    # Create 50 messages, ensuring no orphaned ToolMessages at truncation boundaries
    for i in range(25):
        messages.append(AIMessage(content=f"AI {i}", tool_calls=[{"name": "tool", "args": {}, "id": f"id_{i}"}]))
        messages.append(ToolMessage(content=f"Tool {i}", name="tool", tool_call_id=f"id_{i}"))
    
    state = {
        "messages": messages,
        "steps_remaining": 10,
        "plan": ["Step 1"],
        "retry_counter": 0,
        "active_documents": [],
        "cursor_position": {}
    }
    
    # We don't actually invoke the LLM for the test, we just check if it crashes during the routing prompt construction.
    # We will mock the get_routing_model temporarily.
    import src.graph.supervisor
    original_get = src.graph.supervisor.get_routing_model
    
    class MockModel:
        def invoke(self, prompt):
            # Check prompt
            has_orphan = False
            for idx, msg in enumerate(prompt):
                if isinstance(msg, ToolMessage):
                    prev = prompt[idx - 1]
                    if not isinstance(prev, AIMessage) or not prev.tool_calls or prev.tool_calls[0]['id'] != msg.tool_call_id:
                        print(f"Orphaned tool message detected in supervisor routing prompt at index {idx}!")
                        has_orphan = True
            if has_orphan:
                raise Exception("Orphaned tool message detected!")
            
            class MockResponse:
                plan = ["Step 1"]
                next_agent = "synthesizer"
                current_task = ""
                parallel_tasks = []
                active_project = ""
            return MockResponse()
            
    src.graph.supervisor.get_routing_model = lambda: MockModel()
    
    try:
        res = supervisor_node(state)
        print("Supervisor compression test PASSED (No crashes, safe truncation).")
    except Exception as e:
        print(f"Supervisor compression test FAILED: {e}")
    finally:
        src.graph.supervisor.get_routing_model = original_get

def test_critic_zombie_kill():
    print("\n--- Testing Critic Zombie Process Kill Edge Case ---")
    ws_dir = "./workspace"
    os.makedirs(ws_dir, exist_ok=True)
    pkg_json = os.path.join(ws_dir, "package.json")
    
    # We write a test script that hangs for 20 seconds
    with open(pkg_json, "w") as f:
        json.dump({"scripts": {"test": "python -c \"import time; time.sleep(20)\""}}, f)
        
    state = {
        "scratchpad": "",
        "current_task": "Write some tests",
        "worker_outputs": {"coding_worker": "I wrote the tests."},
        "critic_retry_count": 0
    }
    
    # The critic should automatically run npm run test, realize it detaches (takes >15s), and kill the zombie process.
    # To avoid waiting 15 seconds in this test, we can just run it. The `execute_command` will detach if wait_ms_before_async is hit.
    # Wait, the node hardcodes wait_ms_before_async=15000. So it will actually wait 15 seconds!
    # Let's mock execute_command in the critic
    import src.agents.code_critic_worker
    original_exec = src.agents.code_critic_worker.execute_command
    
    def mock_execute(cmd, wait_ms_before_async=15000):
        if cmd == "npm run test":
            return json.dumps({"status": "ok", "message": "Command is still running...", "data": {"task_id": "zombie_123"}})
        return "{}"
        
    src.agents.code_critic_worker.execute_command = mock_execute
    
    # We also mock kill_task to verify it is called
    killed_tasks = []
    def mock_kill(task_id):
        killed_tasks.append(task_id)
        return "{}"
        
    original_kill = None
    if hasattr(src.agents.code_critic_worker, 'kill_task'):
        original_kill = src.agents.code_critic_worker.kill_task
    src.agents.code_critic_worker.kill_task = mock_kill
    
    # We mock the critic model
    original_critic_model = src.agents.code_critic_worker.get_critic_model
    class MockCritic:
        def invoke(self, prompt):
            # We inspect the prompt to see if the zombie kill system note was injected!
            found_note = False
            for p in prompt:
                if "forcefully terminated" in str(p.content):
                    found_note = True
            if not found_note:
                raise Exception("Zombie kill system note was not injected into critic prompt!")
                
            class MockReport:
                valid = False
                criticism_summary = "Timeout"
                findings = []
            return MockReport()
            
    src.agents.code_critic_worker.get_critic_model = lambda: MockCritic()
    
    try:
        res = code_critic_worker_node(state)
        if "zombie_123" in killed_tasks:
            print("Critic Zombie Process test PASSED (Task explicitly killed and note injected).")
        else:
            print("Critic Zombie Process test FAILED: kill_task was not called.")
    except Exception as e:
        print(f"Critic Zombie Process test FAILED: {e}")
    finally:
        src.agents.code_critic_worker.execute_command = original_exec
        if original_kill:
            src.agents.code_critic_worker.kill_task = original_kill
        src.agents.code_critic_worker.get_critic_model = original_critic_model
        if os.path.exists(pkg_json):
            os.remove(pkg_json)

def main():
    test_supervisor_compression()
    test_critic_zombie_kill()
    print("\nHolistic System Edge Cases Test Complete!")

if __name__ == "__main__":
    main()
