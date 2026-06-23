import os
import sys
import time
import threading
import psutil

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set env vars to run locally with the available coder model
os.environ["LLM_PROVIDER"] = "local"
os.environ["LOCAL_LLM_MODEL"] = "qwen2.5-coder:7b"
os.environ["LOCAL_LLM_API_BASE"] = "http://localhost:11434/v1"

from src.core.llm import LLMService

class ResourceMonitor(threading.Thread):
    def __init__(self, interval=0.2):
        super().__init__()
        self.interval = interval
        self.running = True
        self.cpu_samples = []
        self.ram_samples = []
        self.ollama_ram_samples = []
        
        # Warm up CPU percentage baselines
        psutil.Process().cpu_percent(interval=None)
        for proc in psutil.process_iter(['name']):
            try:
                if 'ollama' in proc.info['name'].lower():
                    proc.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def run(self):
        while self.running:
            # Monitor current python process
            try:
                py_proc = psutil.Process()
                py_cpu = py_proc.cpu_percent(interval=None)
                py_ram = py_proc.memory_info().rss / (1024 * 1024)
            except Exception:
                py_cpu = 0.0
                py_ram = 0.0
            
            # Monitor all Ollama processes
            ollama_cpu = 0.0
            ollama_ram = 0.0
            for proc in psutil.process_iter(['name', 'memory_info']):
                try:
                    if 'ollama' in proc.info['name'].lower():
                        ollama_cpu += proc.cpu_percent(interval=None)
                        if proc.info['memory_info']:
                            ollama_ram += proc.info['memory_info'].rss / (1024 * 1024)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Combine resources
            total_cpu = py_cpu + ollama_cpu
            self.cpu_samples.append(total_cpu)
            self.ram_samples.append(py_ram + ollama_ram)
            self.ollama_ram_samples.append(ollama_ram)
            
            time.sleep(self.interval)

    def stop(self):
        self.running = False

# Target prompt
prompt = (
    "Write a complete Python function that performs binary search on a sorted list "
    "and returns the index of the target. Include docstrings and unit tests using pytest."
)

print(f"Initializing LLMService with local model: {os.environ['LOCAL_LLM_MODEL']}")
service = LLMService()

print(f"\nStarting background resource monitor (polling interval = 0.2s)...")
monitor = ResourceMonitor()
monitor.start()

print(f"\nSending prompt to local LLM (Qwen 2.5 Coder 7B):")
print(f"Prompt: '{prompt}'")
print("-" * 60)

start_time = time.time()
try:
    response = service.complete_text(prompt)
    end_time = time.time()
    success = True
except Exception as e:
    end_time = time.time()
    response = f"Error: {e}"
    success = False

monitor.stop()
monitor.join()

elapsed = end_time - start_time
print("-" * 60)

if success:
    # Character count and word-based token estimation (1 word ~= 1.33 tokens)
    word_count = len(response.split())
    estimated_tokens = int(word_count * 1.33)
    tokens_per_sec = estimated_tokens / elapsed
    
    print(f"\nResponse received successfully! ({len(response)} characters)")
    print("\n--- Response Preview (First 250 characters) ---")
    print(response[:250] + "\n...")
    print("-----------------------------------------------")
else:
    print(f"\nRequest failed. Error:\n{response}")
    estimated_tokens = 0
    tokens_per_sec = 0

# Metrics calculations
avg_cpu = sum(monitor.cpu_samples) / len(monitor.cpu_samples) if monitor.cpu_samples else 0
peak_cpu = max(monitor.cpu_samples) if monitor.cpu_samples else 0

start_ollama_ram = monitor.ollama_ram_samples[0] if monitor.ollama_ram_samples else 0
peak_ollama_ram = max(monitor.ollama_ram_samples) if monitor.ollama_ram_samples else 0
ollama_ram_delta = peak_ollama_ram - start_ollama_ram

system_ram = psutil.virtual_memory()
total_system_ram = system_ram.total / (1024**3)
available_system_ram = system_ram.available / (1024**3)

print(f"\n=== PERFORMANCE & EFFICIENCY REPORT ===")
print(f"  Model Used:             {os.environ['LOCAL_LLM_MODEL']}")
print(f"  Total Time Elapsed:     {elapsed:.2f} seconds")
if success:
    print(f"  Estimated Output:       {estimated_tokens} tokens ({word_count} words)")
    print(f"  Generation Speed:       {tokens_per_sec:.2f} tokens/second")
print(f"  Average combined CPU:   {avg_cpu:.1f}%")
print(f"  Peak combined CPU:      {peak_cpu:.1f}%")
print(f"  Ollama Startup RAM:     {start_ollama_ram:.1f} MB")
print(f"  Ollama Peak RAM:        {peak_ollama_ram:.1f} MB")
print(f"  Ollama RAM delta:       +{ollama_ram_delta:.1f} MB")
print(f"  Total System RAM:       {total_system_ram:.2f} GB")
print(f"  Available System RAM:   {available_system_ram:.2f} GB")
print(f"========================================")
