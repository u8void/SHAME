import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from benchmark.utils import run_inference
from src.iris import ModelRole

prompt = "What is the capital of France?"
print("Running R1 inference...")
resp, t = run_inference(prompt, role=ModelRole.REASONING, use_routing=False)
print(f"Response: {resp}")
