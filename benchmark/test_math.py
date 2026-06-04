"""
test_math.py — GSM8K benchmark
Evaluates the MATH and REASONING models against Grade School Math 8K.
Samples N random questions from the test split, extracts the final numeric
answer from the model response, and compares it to the ground truth.
"""

import re
import random
from benchmark.utils import run_inference, append_to_csv
from src.iris import ModelRole

NUM_SAMPLES = 50
FIELDNAMES = ["Benchmark", "Role", "Prompt", "Expected", "Model_Answer", "Passed", "Time_Sec"]

def _extract_gsm8k_answer(text: str) -> str | None:
    """Extract the final number after #### in a GSM8K answer string."""
    m = re.search(r"####\s*([\-\d,\.]+)", text)
    if m:
        return m.group(1).replace(",", "").strip()
    return None

def _extract_model_answer(response: str) -> str | None:
    """
    Try to find the model's final numeric answer.
    Looks for patterns like:
      - #### 42
      - The answer is 42
      - = 42
      - **42**
    """
    m = re.search(r"####\s*([\-\d,\.]+)", response)
    if m:
        return m.group(1).replace(",", "").strip()
    m = re.search(r"(?:answer(?:\s+is)?|result(?:\s+is)?)\s*[:\-]?\s*([\-\d,\.]+)", response, re.IGNORECASE)
    if m:
        return m.group(1).replace(",", "").strip()
    m = re.search(r"\*{1,2}([\-\d,\.]+)\*{1,2}\s*$", response.strip())
    if m:
        return m.group(1).replace(",", "").strip()
    nums = re.findall(r"\b([\-]?\d[\d,\.]*)\b", response)
    if nums:
        return nums[-1].replace(",", "").strip()
    return None

def run_math_benchmark(csv_path: str):
    try:
        from datasets import load_dataset
        ds = load_dataset("openai/gsm8k", "main", split="test")
        items = list(ds)
        random.shuffle(items)
        items = items[:NUM_SAMPLES]
        print(f"[GSM8K] Loaded {len(items)} questions from HuggingFace.")
    except Exception as e:
        print(f"[GSM8K] Could not load dataset: {e}. Falling back to built-in questions.")
        items = [
            {"question": "What is 15 + 27?",                                          "answer": "#### 42"},
            {"question": "A train travels 60 mph for 2 hours. How far does it go?",   "answer": "#### 120"},
            {"question": "Solve for x: 3x - 5 = 10",                                  "answer": "#### 5"},
            {"question": "What is the square root of 144?",                            "answer": "#### 12"},
            {"question": "If you have 3 apples and eat 1, how many are left?",         "answer": "#### 2"},
        ]

    for role in [ModelRole.MATH, ModelRole.REASONING]:
        print(f"\n{'='*50}")
        print(f" [GSM8K] Role: {role.value.upper()}  ({len(items)} questions)")
        print(f"{'='*50}")
        passed_count = 0

        for i, item in enumerate(items, 1):
            question      = item["question"]
            ground_truth  = _extract_gsm8k_answer(item["answer"])
            prompt = (
                f"Solve the following math problem step by step. "
                f"At the very end, write your final answer after '####'.\n\n{question}"
            )

            response, t = run_inference(prompt, role=role)
            model_answer = _extract_model_answer(response)
            passed = (model_answer is not None) and (model_answer == ground_truth)
            if passed:
                passed_count += 1

            print(f"  [{i:02d}/{len(items)}] Expected: {ground_truth} | Got: {model_answer} | {'✓' if passed else '✗'} ({t}s)")

            append_to_csv(csv_path, {
                "Benchmark":    "GSM8K",
                "Role":         role.value,
                "Prompt":       question,
                "Expected":     ground_truth,
                "Model_Answer": model_answer,
                "Passed":       passed,
                "Time_Sec":     t,
            }, FIELDNAMES)

        pct = (passed_count / len(items)) * 100 if items else 0
        print(f"\n  [GSM8K][{role.value}] Score: {passed_count}/{len(items)} ({pct:.1f}%)\n")
