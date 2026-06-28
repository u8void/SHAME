import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from benchmark.utils import run_inference
from src.iris import ModelRole
import time

prompt = "Solve the following competition math problem step by step. At the very end, write your final answer in LaTeX inside a \\boxed{} block. Problem: 1 + 1"
print("Running inference...")
resp, t = run_inference(prompt, role=ModelRole.MATH, use_routing=False)
print(f"Response: {resp}")
