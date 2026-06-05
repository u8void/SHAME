# Iris AI — Benchmarks

## Overview

Iris AI includes an automated benchmark suite that evaluates each specialist model against standard benchmarks. Results are written to `outputs/benchmark_results.csv`.

## Running Benchmarks

```bash
# Full suite
python benchmark/run_all.py

# Individual benchmarks
python benchmark/test_math.py
python benchmark/test_coding.py
python benchmark/test_mmlu.py
python benchmark/test_gpqa.py
```

## Benchmarks Covered

| Benchmark | Type | Description | Dataset |
|-----------|------|-------------|---------|
| **GSM8K** | Math | Grade-school math word problems | 1,319 test problems |
| **MATH** | Math | Competition math (AMC, AIME) | 5,000 problems |
| **HumanEval** | Code | Python function generation from docstrings | 164 problems |
| **MMLU** | Knowledge | 57 subjects (STEM, humanities, social science) | 14,042 questions |
| **GPQA Diamond** | Science | Graduate-level physics, chemistry, biology | 198 questions |

## Results Format

```csv
Benchmark,Role,Problem,Passed,Tokens,Time
GSM8K,math,"Janet has 16 eggs...",true,45,1.2
HumanEval,code,"def has_close_elements...",true,120,2.1
MMLU,general,"What is the capital of...",true,12,0.3
```

## Scoring

| Benchmark | Scoring Method |
|-----------|---------------|
| GSM8K | Exact match of numeric answer |
| MATH | Symbolic comparison of final answer |
| HumanEval | `pass@1` — functional correctness via unit tests |
| MMLU | Multiple choice accuracy |
| GPQA | Multiple choice accuracy |

## Benchmark Architecture

```
benchmark/
├── run_all.py      # Orchestrator — runs all benchmarks, computes summary
├── test_math.py    # GSM8K + MATH benchmarks
├── test_coding.py  # HumanEval benchmark
├── test_mmlu.py    # MMLU benchmark (57 subjects)
├── test_gpqa.py    # GPQA Diamond benchmark
├── utils.py        # Shared utilities (model loading, scoring)
└── outputs/
    └── benchmark_results.csv
```

## Expected Performance (Medium Tier)

| Benchmark | Expected Score | Notes |
|-----------|---------------|-------|
| GSM8K | 55-65% | 7B math model, Q4_K_M quantization |
| HumanEval | 40-50% | 14B code model, constrained context |
| MMLU | 55-65% | 9B general model across 57 subjects |
| GPQA Diamond | 25-35% | Graduate-level science is hard for small models |

**Max tier** would approximately double these scores — the jump from 14B → 70B models with DeepSeek-R1 reasoning is significant.

## Running a Single Test

```python
from benchmark.test_math import run_math_benchmark

# Run GSM8K on the math role, 50 problems max
run_math_benchmark(role="math", max_problems=50, benchmark="gsm8k")
```

## Adding New Benchmarks

1. Create `benchmark/test_yourbench.py`
2. Implement `run_your_benchmark()` function
3. Register in `benchmark/run_all.py`:
```python
from benchmark.test_yourbench import run_your_benchmark
# Add to main() loop
```

## Interpreting Results

- **High variance between runs**: Normal for small models — temperature sampling adds randomness
- **Math scores significantly lower than expected**: Check that the math model loaded correctly (not the general model)
- **All scores near zero**: Model not loaded, wrong GGUF file, or context too small
- **Code benchmark passes 0**: Syntax errors in generated code — check `syntax_checker.py`
