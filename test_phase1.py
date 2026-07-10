import os
import sys
import json
import time

# 1. Test WaitMsBeforeAsync
print("--- Testing WaitMsBeforeAsync ---")
from src.tools.coding_tools import execute_command, check_task_status, kill_task

# Run a command that finishes quickly
res_fast = execute_command("echo hello_world", wait_ms_before_async=2000)
print(f"Fast command result: {res_fast}")
assert "hello_world" in res_fast, "Fast command should finish synchronously"

# Run a command that takes 4 seconds (longer than wait_ms_before_async)
res_slow = execute_command("python -c \"import time; print('Waiting...'); time.sleep(4); print('Done!')\"", wait_ms_before_async=2000)
print(f"Slow command result: {res_slow}")
assert "Command is still running" in res_slow, "Slow command should detach to background"

# Extract task ID
res_json = json.loads(res_slow)
task_id = res_json["data"]["task_id"]

print("Waiting for task to finish in background...")
time.sleep(3) # Wait for the 4 second sleep to finish
status = check_task_status(task_id)
print(f"Final task status: {status}")
assert "Done!" in status, "Background task should complete"

print("\n--- WaitMsBeforeAsync Test Passed! ---")
