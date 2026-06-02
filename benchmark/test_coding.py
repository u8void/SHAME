"""
test_coding.py — HumanEval benchmark
Evaluates the CODE and REASONING models against OpenAI's HumanEval dataset.
Samples N problems, prompts the model to complete the function, extracts the
code block, and validates it using syntax_checker.py.
"""

import re
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmark.utils import run_inference, append_to_csv
from src.iris import ModelRole
from src.syntax_checker import check_syntax

NUM_SAMPLES = 30
FIELDNAMES = ["Benchmark", "Role", "Prompt", "Expected", "Model_Answer", "Passed", "Time_Sec"]

def _extract_python_code(response: str) -> str:
    """Extract the first Python code block from the model response."""
    # Fenced code block
    m = re.search(r"```(?:python)?\s*\n(.*?)```", response, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # If no fence, treat everything after the first def as code
    m = re.search(r"(def\s+\w+.*)", response, re.DOTALL)
    if m:
        return m.group(1).strip()
    return response.strip()

def run_coding_benchmark(csv_path: str):
    try:
        from datasets import load_dataset
        ds = load_dataset("openai/openai_humaneval", split="test")
        items = list(ds)
        random.shuffle(items)
        items = items[:NUM_SAMPLES]
        print(f"[HumanEval] Loaded {len(items)} problems from HuggingFace.")
        use_humaneval = True
    except Exception as e:
        print(f"[HumanEval] Could not load dataset: {e}. Falling back to built-in prompts.")
        use_humaneval = False
        items = [
            {"prompt": "def add(a, b):\n    \"\"\"Return sum of a and b.\"\"\"\n", "entry_point": "add"},
            {"prompt": "def is_palindrome(s):\n    \"\"\"Return True if s is a palindrome.\"\"\"\n", "entry_point": "is_palindrome"},
            {"prompt": "def factorial(n):\n    \"\"\"Return n!.\"\"\"\n", "entry_point": "factorial"},
            {"prompt": "def fizzbuzz(n):\n    \"\"\"Return FizzBuzz list up to n.\"\"\"\n", "entry_point": "fizzbuzz"},
        ]

    for role in [ModelRole.CODE, ModelRole.REASONING]:
        print(f"\n{'='*50}")
        print(f" [HumanEval] Role: {role.value.upper()}  ({len(items)} problems)")
        print(f"{'='*50}")
        passed_count = 0

        for i, item in enumerate(items, 1):
            func_signature = item["prompt"]
            entry_point    = item.get("entry_point", "function")

            prompt = (
                f"Complete the following Python function. "
                f"Return ONLY valid Python code inside a ```python``` block.\n\n"
                f"```python\n{func_signature}\n```"
            )

            response, t = run_inference(prompt, role=role)
            extracted_code = _extract_python_code(response)

            # Syntax check using existing syntax_checker
            try:
                is_valid, err = check_syntax(extracted_code, "python")
                passed = is_valid
                syntax_note = "" if is_valid else str(err)
            except Exception as ex:
                passed = False
                syntax_note = str(ex)

            if passed:
                passed_count += 1

            short_sig = func_signature.split("\n")[0][:60]
            print(f"  [{i:02d}/{len(items)}] {short_sig} | Syntax: {'✓' if passed else '✗'} ({t}s)")

            append_to_csv(csv_path, {
                "Benchmark":    "HumanEval",
                "Role":         role.value,
                "Prompt":       func_signature.replace("\n", " "),
                "Expected":     f"Valid Python for {entry_point}()",
                "Model_Answer": extracted_code.replace("\n", " ")[:300],
                "Passed":       passed,
                "Time_Sec":     t,
            }, FIELDNAMES)

        pct = (passed_count / len(items)) * 100 if items else 0
        print(f"\n  [HumanEval][{role.value}] Score: {passed_count}/{len(items)} ({pct:.1f}%)\n")
