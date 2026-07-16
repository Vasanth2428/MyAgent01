from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
import json

def safe_truncate(messages, max_len=40):
    if len(messages) <= max_len:
        return messages
        
    head = messages[:2]
    tail = messages[-(max_len - 3):]
    
    # Check if tail[0] is an orphaned ToolMessage
    # Or if tail[0] is an AIMessage with tool_calls but its corresponding ToolMessages aren't fully in the tail (not possible since we cut from the left)
    
    # Find where tail actually starts in the original array
    start_idx = len(messages) - len(tail)
    
    # Walk backwards from start_idx until we find a message that is NOT a ToolMessage
    while start_idx > 2 and isinstance(messages[start_idx], ToolMessage):
        start_idx -= 1
        
    tail = messages[start_idx:]
    summary_msg = SystemMessage(content="[SYSTEM NOTE] Truncated.")
    return head + [summary_msg] + tail

# Mimic the setup
agent_messages = [
    SystemMessage(content="You are a coder."),
    HumanMessage(content="Do this task.")
]

for i in range(25):
    agent_messages.append(AIMessage(content="", tool_calls=[{"name": "test_tool", "args": {}, "id": f"call_{i}"}]))
    agent_messages.append(ToolMessage(content="Success", name="test_tool", tool_call_id=f"call_{i}"))

print(f"Original length: {len(agent_messages)}")

agent_messages = safe_truncate(agent_messages)
print(f"Truncated length: {len(agent_messages)}")

has_error = False
for idx, msg in enumerate(agent_messages):
    if isinstance(msg, ToolMessage):
        prev = agent_messages[idx - 1]
        if not isinstance(prev, AIMessage) or not prev.tool_calls or prev.tool_calls[0]['id'] != msg.tool_call_id:
            print(f"ERROR: Orphaned ToolMessage at index {idx} with id {msg.tool_call_id}!")
            print(f"Preceding message is: {type(prev)}")
            has_error = True

if has_error:
    print("FAILED: Context compression breaks tool call message ordering!")
    import sys
    sys.exit(1)
else:
    print("PASSED: No orphaned tool messages.")
