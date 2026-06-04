"""
test_gpqa.py — GPQA Diamond benchmark
Evaluates the REASONING model on PhD-level science questions.
Uses the Idavidrein/gpqa dataset (diamond subset).
Questions are formatted as multiple-choice and graded on letter selection.
"""

import re
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmark.utils import run_inference, append_to_csv
from src.iris import ModelRole

NUM_SAMPLES = 30
FIELDNAMES  = ["Benchmark", "Role", "Prompt", "Expected", "Model_Answer", "Passed", "Time_Sec"]

def _format_gpqa_question(item: dict) -> tuple[str, str]:
    """Format a GPQA item into a multiple-choice prompt and return (prompt, correct_letter)."""
    question         = item.get("Question", "")
    correct_answer   = item.get("Correct Answer", "")
    incorrect_1      = item.get("Incorrect Answer 1", "")
    incorrect_2      = item.get("Incorrect Answer 2", "")
    incorrect_3      = item.get("Incorrect Answer 3", "")

    choices = [correct_answer, incorrect_1, incorrect_2, incorrect_3]
    random.shuffle(choices)
    correct_letter = ["A", "B", "C", "D"][choices.index(correct_answer)]

    choices_text = "\n".join(f"  {chr(65+i)}. {c}" for i, c in enumerate(choices))
    prompt = (
        f"This is a PhD-level science question. Think carefully and answer with "
        f"ONLY the letter (A, B, C, or D) of the correct choice.\n\n"
        f"Question: {question}\n\n{choices_text}\n\nAnswer:"
    )
    return prompt, correct_letter

def _extract_letter(response: str) -> str | None:
    """Extract the first A/B/C/D letter from the model response."""
    response = response.strip()
    m = re.match(r"^\s*([ABCD])\b", response, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.search(r"(?:answer(?:\s+is)?|correct(?:\s+is)?)\s*[:\-]?\s*([ABCD])\b",
                  response, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.search(r"\*{1,2}([ABCD])\*{1,2}", response, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b([ABCD])\b", response, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return None

def run_gpqa_benchmark(csv_path: str):
    dataset_options = [
        ("lighteval/GPQA", "gpqa_diamond", "train"),
        ("Idavidrein/gpqa", "gpqa_diamond", "train"),
    ]
    items = []
    for repo, config, split in dataset_options:
        try:
            from datasets import load_dataset
            ds = load_dataset(repo, config, split=split)
            items = list(ds)
            random.shuffle(items)
            items = items[:NUM_SAMPLES]
            print(f"[GPQA Diamond] Loaded {len(items)} questions from {repo}.")
            break
        except Exception as e:
            print(f"[GPQA Diamond] Could not load {repo}: {e}")

    if not items:
        print("[GPQA Diamond] No accessible dataset found. Skipping GPQA benchmark.")
        print("  Tip: Set HF_TOKEN in your environment to access gated datasets.")
        return

    for role in [ModelRole.REASONING]:
        print(f"\n{'='*50}")
        print(f" [GPQA Diamond] Role: {role.value.upper()}  ({len(items)} questions)")
        print(f"{'='*50}")
        passed_count = 0

        for i, item in enumerate(items, 1):
            prompt, correct_letter = _format_gpqa_question(item)
            response, t = run_inference(prompt, role=role)
            model_letter = _extract_letter(response)
            passed = (model_letter == correct_letter)
            if passed:
                passed_count += 1

            short_q = item.get("Question", "")[:60]
            print(f"  [{i:02d}/{len(items)}] {short_q}... | Expected: {correct_letter} | Got: {model_letter} | {'✓' if passed else '✗'} ({t}s)")

            append_to_csv(csv_path, {
                "Benchmark":    "GPQA-Diamond",
                "Role":         role.value,
                "Prompt":       item.get("Question", "")[:200],
                "Expected":     correct_letter,
                "Model_Answer": model_letter,
                "Passed":       passed,
                "Time_Sec":     t,
            }, FIELDNAMES)

        pct = (passed_count / len(items)) * 100 if items else 0
        print(f"\n  [GPQA Diamond][{role.value}] Score: {passed_count}/{len(items)} ({pct:.1f}%)\n")
        random_baseline = 25.0
        print(f"  (Random baseline for 4-choice MCQ: 25.0% — human expert ~65%)")
