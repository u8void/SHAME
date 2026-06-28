import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from benchmark.utils import run_inference
from src.iris import ModelRole

prompt = """Answer the following multiple-choice question.

Question: What is the capital of France?

  A. London
  B. Berlin
  C. Paris
  D. Madrid

Reason through each option. After your reasoning, write EXACTLY: 'Answer: X' where X is the correct letter (A, B, C, or D)."""

print("Running MMLU inference...")
resp, t = run_inference(prompt, role=ModelRole.REASONING, use_routing=False)
print(f"Response: {resp}")
