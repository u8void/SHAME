"""
run_all.py — Iris AI Benchmark Orchestrator
Runs the full benchmark suite: GSM8K, HumanEval, MMLU, GPQA Diamond.
Results are written incrementally to outputs/benchmark_results.csv.
A summary table is printed and appended at the end.
"""

import os
import sys
import csv
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmark.test_math   import run_math_benchmark
from benchmark.test_coding import run_coding_benchmark
from benchmark.test_mmlu   import run_mmlu_benchmark
from benchmark.test_gpqa   import run_gpqa_benchmark

CSV_PATH = "outputs/benchmark_results.csv"

def compute_summary(csv_path: str) -> dict[str, dict]:
    """Read the CSV and compute per-benchmark pass rates."""
    summary: dict[str, dict] = {}
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                bench = row.get("Benchmark", "unknown").split("-")[0]
                role  = row.get("Role", "")
                key   = f"{bench} [{role}]"
                if key not in summary:
                    summary[key] = {"passed": 0, "total": 0}
                summary[key]["total"] += 1
                if str(row.get("Passed", "")).lower() in ("true", "1"):
                    summary[key]["passed"] += 1
    except Exception:
        pass
    return summary

def print_summary(summary: dict[str, dict]):
    print("\n" + "="*60)
    print("  BENCHMARK SUMMARY")
    print("="*60)
    print(f"  {'Benchmark + Role':<35} {'Score':>8}  {'%':>6}")
    print("  " + "-"*52)
    for key, counts in sorted(summary.items()):
        p = counts["passed"]
        t = counts["total"]
        pct = (p / t * 100) if t else 0
        bar = "✓" * int(pct // 10) + "·" * (10 - int(pct // 10))
        print(f"  {key:<35} {p:>3}/{t:<3}  {pct:>5.1f}%  [{bar}]")
    print("="*60 + "\n")

def main():
    os.makedirs("outputs", exist_ok=True)

    if os.path.exists(CSV_PATH):
        os.remove(CSV_PATH)

    print("\n" + "="*60)
    print("  IRIS AI — BENCHMARK SUITE")
    print("="*60)
    print(f"  Benchmarks : GSM8K · HumanEval · MMLU · GPQA Diamond")
    print(f"  Output     : {CSV_PATH}")
    print("="*60 + "\n")

    total_start = time.time()

    run_math_benchmark(CSV_PATH)
    run_coding_benchmark(CSV_PATH)
    run_mmlu_benchmark(CSV_PATH)
    run_gpqa_benchmark(CSV_PATH)

    elapsed = round(time.time() - total_start, 1)

    summary = compute_summary(CSV_PATH)
    print_summary(summary)

    print(f"  Total time: {elapsed}s")
    print(f"  Full results saved to: {os.path.abspath(CSV_PATH)}\n")

    try:
        from src.iris import unload_model
        unload_model()
    except Exception:
        pass

if __name__ == "__main__":
    main()
