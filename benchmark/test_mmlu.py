"""
test_mmlu.py — MMLU benchmark
Evaluates the TRIAGE and GENERAL models against MMLU (cais/mmlu).
Samples N questions across several subjects, formats them as multiple-choice,
and checks if the model picks the correct letter (A/B/C/D).
"""

import re
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmark.utils import run_inference, append_to_csv
from src.iris import ModelRole

NUM_SAMPLES    = 50   # total questions across all subjects
FIELDNAMES     = ["Benchmark", "Role", "Prompt", "Expected", "Model_Answer", "Passed", "Time_Sec"]
CHOICE_LABELS  = ["A", "B", "C", "D"]

SUBJECTS = [
    "abstract_algebra",
    "high_school_mathematics",
    "high_school_physics",
    "high_school_computer_science",
    "logical_fallacies",
    "world_history",
    "philosophy",
    "college_medicine",
]

def _format_question(item: dict) -> tuple[str, str]:
    """Return (formatted_prompt, correct_letter)."""
    q       = item["question"]
    choices = item["choices"]       # list of 4 strings
    answer  = item["answer"]        # int 0-3

    choices_text = "\n".join(f"  {CHOICE_LABELS[i]}. {choices[i]}" for i in range(len(choices)))
    prompt = (
        f"Answer the following multiple-choice question. "
        f"Respond with ONLY the letter (A, B, C, or D) of the correct answer.\n\n"
        f"Question: {q}\n\n{choices_text}\n\nAnswer:"
    )
    correct_letter = CHOICE_LABELS[answer]
    return prompt, correct_letter

def _extract_letter(response: str) -> str | None:
    """Extract the first A/B/C/D letter from the model response."""
    response = response.strip()
    # Direct single-letter answer
    m = re.match(r"^\s*([ABCD])\b", response, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # "The answer is B" style
    m = re.search(r"(?:answer(?:\s+is)?|correct(?:\s+answer)?(?:\s+is)?)\s*[:\-]?\s*([ABCD])\b",
                  response, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # Bold letter **B**
    m = re.search(r"\*{1,2}([ABCD])\*{1,2}", response, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # Fallback: first standalone letter
    m = re.search(r"\b([ABCD])\b", response, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return None

def run_mmlu_benchmark(csv_path: str):
    per_subject = max(1, NUM_SAMPLES // len(SUBJECTS))
    items_with_subject: list[tuple[str, dict]] = []

    try:
        from datasets import load_dataset
        for subject in SUBJECTS:
            try:
                ds = load_dataset("cais/mmlu", subject, split="test")
                sample = list(ds)
                random.shuffle(sample)
                for row in sample[:per_subject]:
                    items_with_subject.append((subject, row))
            except Exception as e:
                print(f"[MMLU] Could not load subject '{subject}': {e}")

        print(f"[MMLU] Loaded {len(items_with_subject)} questions across {len(SUBJECTS)} subjects.")
    except Exception as e:
        print(f"[MMLU] Could not load dataset: {e}. Skipping MMLU benchmark.")
        return

    if not items_with_subject:
        print("[MMLU] No questions loaded. Skipping.")
        return

    for role in [ModelRole.TRIAGE, ModelRole.GENERAL]:
        print(f"\n{'='*50}")
        print(f" [MMLU] Role: {role.value.upper()}  ({len(items_with_subject)} questions)")
        print(f"{'='*50}")
        passed_count = 0

        for i, (subject, item) in enumerate(items_with_subject, 1):
            prompt, correct_letter = _format_question(item)
            response, t = run_inference(prompt, role=role)
            model_letter = _extract_letter(response)
            passed = (model_letter == correct_letter)
            if passed:
                passed_count += 1

            print(f"  [{i:02d}/{len(items_with_subject)}] [{subject}] Expected: {correct_letter} | Got: {model_letter} | {'✓' if passed else '✗'} ({t}s)")

            append_to_csv(csv_path, {
                "Benchmark":    f"MMLU-{subject}",
                "Role":         role.value,
                "Prompt":       item["question"][:200],
                "Expected":     correct_letter,
                "Model_Answer": model_letter,
                "Passed":       passed,
                "Time_Sec":     t,
            }, FIELDNAMES)

        pct = (passed_count / len(items_with_subject)) * 100 if items_with_subject else 0
        print(f"\n  [MMLU][{role.value}] Score: {passed_count}/{len(items_with_subject)} ({pct:.1f}%)\n")
