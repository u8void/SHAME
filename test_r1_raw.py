import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.iris import ask_stream, ModelRole

prompt = "What is the capital of France?"
print("Running R1 raw stream...")
stream = ask_stream(prompt, [], force_role=ModelRole.REASONING, keep_loaded=True)

for ev in stream:
    if ev["type"] == "token":
        print(ev["content"], end="", flush=True)
    elif ev["type"] == "thinking":
        print(f"\n<THINKING>\n{ev['content']}\n</THINKING>\n", end="", flush=True)

print("\n")
