import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from benchmark.utils import run_inference
from src.iris import ModelRole

prompt = """Answer the following multiple-choice question. Briefly reason through each option (2-3 sentences max), then write EXACTLY: 'Answer: X' where X is the correct letter (A, B, C, or D). Do not write anything after 'Answer: X'.

Question: What is the capital of France?

  A. London
  B. Berlin
  C. Paris
  D. Madrid

Reasoning:"""

print("Running MMLU inference with 'Reasoning:'...")
resp, t = run_inference(prompt, role=ModelRole.REASONING, use_routing=False)
print(f"Response: {resp}")
