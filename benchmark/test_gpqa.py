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
from benchmark.compare import match, fix_common_format_issues
from src.iris import ModelRole

NUM_SAMPLES = 100
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
        print("[GPQA Diamond] Falling back to local built-in PhD-level science questions.")
        items = [
            {
                "Question": "Two quantum states with energies $E_1$ and $E_2$ have a lifetime of $10^{-9}$ sec and $10^{-8}$ sec, respectively. We want to clearly distinguish these two energy levels. Which one of the following options could be their energy difference so that they can be clearly resolved?",
                "Correct Answer": "10^{-4} eV",
                "Incorrect Answer 1": "10^{-11} eV",
                "Incorrect Answer 2": "10^{-8} eV",
                "Incorrect Answer 3": "10^{-9} eV"
            },
            {
                "Question": "Methylcyclopentadiene was reacted with methyl isoamyl ketone in pyrrolidine to form a derivative of fulvene. The product was reacted with ethyl acrylate in a 1:1 ratio, and the bright yellow color disappeared. Not counting stereoisomers, how many chemically distinct isomers make up the final product?",
                "Correct Answer": "8",
                "Incorrect Answer 1": "2",
                "Incorrect Answer 2": "16",
                "Incorrect Answer 3": "4"
            },
            {
                "Question": "What is the point group symmetry of a perfectly planar molecule of carbonate ($CO_3^{2-}$)?",
                "Correct Answer": "D_3h",
                "Incorrect Answer 1": "C_3v",
                "Incorrect Answer 2": "D_3d",
                "Incorrect Answer 3": "C_2v"
            },
            {
                "Question": "Which of the following describes the function of the accessory protein gp45 in bacteriophage T4 DNA replication?",
                "Correct Answer": "It acts as a sliding clamp that increases the processivity of the DNA polymerase gp43.",
                "Incorrect Answer 1": "It is a helicase that unwinds the double-stranded DNA template ahead of the fork.",
                "Incorrect Answer 2": "It is a single-stranded binding protein that stabilizes the transiently exposed single strands.",
                "Incorrect Answer 3": "It functions as a primase to synthesize RNA primers for lagging strand synthesis."
            },
            {
                "Question": "Under the standard depolarizing channel with parameter p, what is the output state of a qubit initially in the state |0><0|?",
                "Correct Answer": "(1 - 2p/3)|0><0| + (p/3)I",
                "Incorrect Answer 1": "(1 - p)|0><0| + pI",
                "Incorrect Answer 2": "(1 - p/2)|0><0| + (p/2)I",
                "Incorrect Answer 3": "(1 - p)|0><0| + (p/2)I"
            }
        ]
        random.shuffle(items)
        items = items[:NUM_SAMPLES]

    print(f"\n{'='*50}")
    print(f" [GPQA Diamond] Evaluating Iris Tiny  ({len(items)} questions)")
    print(f"{'='*50}")
    passed_count = 0

    for i, item in enumerate(items, 1):
        prompt, correct_letter = _format_gpqa_question(item)
        response, t = run_inference(prompt, role=ModelRole.REASONING, use_routing=False, keep_loaded=True)
        model_letter = _extract_letter(response)
        # Smart comparison: normalize formatting
        if model_letter:
            model_letter = fix_common_format_issues(model_letter)
        passed = (model_letter == correct_letter)
        if passed:
            passed_count += 1

        short_q = item.get("Question", "")[:60]
        print(f"  [{i:02d}/{len(items)}] {short_q}... | Expected: {correct_letter} | Got: {model_letter} | {'✓' if passed else '✗'} ({t}s)")

        append_to_csv(csv_path, {
            "Benchmark":    "GPQA-Diamond",
            "Role":         "Iris Tiny",
            "Prompt":       item.get("Question", "")[:200],
            "Expected":     correct_letter,
            "Model_Answer": model_letter,
            "Passed":       passed,
            "Time_Sec":     t,
        }, FIELDNAMES)

    pct = (passed_count / len(items)) * 100 if items else 0
    print(f"\n  [GPQA Diamond][Iris Tiny] Score: {passed_count}/{len(items)} ({pct:.1f}%)\n")
    print(f"  (Random baseline for 4-choice MCQ: 25.0% — human expert ~65%)")

    # Unload model to prevent Metal GPU destructor crash on macOS
    try:
        from src.iris import unload_model
        unload_model()
    except Exception:
        pass

if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
    os.makedirs(out_dir, exist_ok=True)
    
    from benchmark.utils import get_size_name, write_summary_csv
    size_name = get_size_name()
    raw_csv = os.path.join(out_dir, f"raw_{size_name}.csv")
    summary_csv = os.path.join(out_dir, f"benchmark_{size_name}.csv")
    
    run_gpqa_benchmark(raw_csv)
    write_summary_csv(raw_csv, summary_csv)
    print(f"  Summary updated at: {os.path.abspath(summary_csv)}")
