import json
import os

transcript_path = r"C:\Users\vasan\.gemini\antigravity-ide\brain\44598dca-bbf6-4575-8ec6-7ceaa3954624\.system_generated\logs\transcript.jsonl"
output_path = r"c:\Users\vasan\Documents\Apphelix Intern\RAG\scratch\matched_steps.txt"

with open(transcript_path, "r", encoding="utf-8") as f, open(output_path, "w", encoding="utf-8") as out:
    for line in f:
        obj = json.loads(line)
        content = obj.get("content", "")
        # Look for keywords about the recommendations
        if any(kw in content.lower() for kw in ["phase 3", "phase 4", "6 edits", "six edits", "to the level of you", "recommend"]):
            out.write(f"=== STEP {obj.get('step_index')} (Source: {obj.get('source')} Type: {obj.get('type')}) ===\n")
            out.write(content + "\n")
            out.write("="*60 + "\n")

print("Matches written to:", output_path)
