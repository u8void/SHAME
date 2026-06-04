# Iris AI — Training Guide

A full reference for fine-tuning, converting, and deploying Iris AI's specialist GGUF models.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Model Architecture](#model-architecture)
4. [Training Data](#training-data)
5. [Training Workflows](#training-workflows)
   - [Apple Silicon (MLX)](#apple-silicon-mlx)
   - [CUDA / CPU (Torch)](#cuda--cpu-torch)
6. [CLI Reference](#cli-reference)
7. [GGUF Conversion](#gguf-conversion)
8. [Adding Custom Training Data](#adding-custom-training-data)
9. [Configuring Datasets](#configuring-datasets)
10. [Tips & Best Practices](#tips--best-practices)

---

## Overview

Iris AI uses a **multi-role GGUF routing system**. Each specialist model is fine-tuned independently for its domain, then quantized to GGUF format and served locally via `llama-cpp-python`.

The unified training script `train.py` handles everything:
- Loading and mixing HuggingFace + local Markdown datasets
- Running LoRA fine-tuning (via MLX on Apple Silicon, or HF Trainer on CUDA/CPU)
- Merging LoRA adapters into the base model
- Converting and quantizing to GGUF

---

## Prerequisites

### Quick setup (recommended)

Run the one-shot setup script from the repo root:

```bash
bash setup.sh
```

This automatically:
- Checks your system for `llama-quantize` (warning you if it is missing)
- Downloads the self-contained `convert_hf_to_gguf.py` script from a stable `llama.cpp` release into `./scripts/`
- Installs all Python dependencies from `requirements.txt`

**Options:**

| Flag | Description |
|------|-------------|
| `--no-pip` | Skip Python dependency installation |
| `--no-script` | Skip downloading the GGUF converter script |

```bash
# Example: skip pip installation
bash setup.sh --no-pip
```

> [!IMPORTANT]
> Since we are using a standalone Python converter, the heavy `llama.cpp` submodule is **no longer needed**. GGUF quantization (e.g. `q4_k_m`) requires the compiled `llama-quantize` utility. On macOS, the easiest way to install it globally is via Homebrew:
> ```bash
> brew install llama.cpp
> ```
> If `llama-quantize` is not found, the script will fall back to exporting the unquantized `F16` GGUF model.

### Manual setup

If you prefer to set up manually:

```bash
# 1. Download the convert script
mkdir -p scripts
curl -L -o scripts/convert_hf_to_gguf.py "https://raw.githubusercontent.com/ggerganov/llama.cpp/b9000/convert_hf_to_gguf.py"
chmod +x scripts/convert_hf_to_gguf.py

# 2. (Optional) Install llama.cpp globally for quantization
brew install llama.cpp

# 3. Install Python deps
pip install -r requirements.txt
```

### HuggingFace login (for gated models)

```bash
huggingface-cli login
```

---

## Model Architecture

Iris uses **6 specialist roles**, each backed by a different base model:

| Role | Base Model | Purpose |
|------|-----------|---------|
| `triage` | `Qwen2.5-3B-Instruct` | Fast query routing & conversational fallback |
| `router` | `Qwen2.5-Coder-7B-Instruct` | JSON action generation & tool routing |
| `math` | `Qwen2.5-Math-7B-Instruct` | Equations, proofs, algorithmic derivations |
| `code` | `DeepSeek-R1-Distill-Qwen-7B` | Code generation, debugging, reasoning about code |
| `reasoning` | `DeepSeek-R1-Distill-Qwen-14B` | Deep reasoning, architecture, complex code review |
| `general` | `DeepSeek-R1-Distill-Qwen-14B` | General knowledge & open-ended questions |

After fine-tuning, each model is saved as `./models/iris-{role}.gguf`.

---

## Size Tiers

Iris AI supports **four size tiers** controlled by `--size` in `train.py` and `size` in `iris.conf`.
Size configs live in `config/sizes/{size}.json`.

| Tier | Total Size | RAM Needed | Description |
|------|-----------|------------|-------------|
| `tiny` | ~15 GB | 8 GB | All models ≤3B. Ultra-fast, runs on anything. |
| `small` | ~30 GB | 16 GB | 3B–8B models. Fits M2/M3 MacBook Air. |
| `medium` | ~45 GB | 32 GB | 3B–14B models. Current default. |
| `large` | ~80 GB | 64 GB / CUDA 48 GB | Top-tier 14B–32B models. Desktop/server room. |

| Tier | Triage | Router | Math | Code | Reasoning | General | Vision |
|------|--------|--------|------|------|-----------|---------|--------|
| `tiny` | Qwen2.5-0.5B | Qwen2.5-1.5B | Qwen2.5-Math-1.5B | R1-Distill-Qwen-1.5B | Qwen2.5-3B | Qwen2.5-3B | Qwen2.5-VL-3B |
| `small` | Llama-3.2-3B | Qwen2.5-Coder-3B | Qwen2.5-Math-7B | Qwen2.5-Coder-7B | R1-Distill-Qwen-7B | Llama-3.2-3B | Qwen3-VL-4B |
| `medium` | Llama-3.2-3B | Hermes-3-8B | Qwen2.5-Math-7B | Qwen2.5-Coder-14B | DeepSeek-LLM-14B | Qwen3.5-9B | Qwen3-VL-4B |
| `large` | Qwen2.5-7B | Qwen2.5-Coder-7B | R1-Distill-Qwen-14B | R1-Distill-Qwen-32B | R1-Distill-Qwen-32B | Qwen3.5-20B | Qwen3-VL-8B |

**Usage:**
```bash
# Training — auto-downloads the right GGUFs for the tier
python train.py --size small --train-role math

# Inference — set in config/iris.conf
# "size": "medium"  — then models block should match config/sizes/medium.json
```

---

## Training Data

### Data Sources

The trainer pulls from two places, configured in [`config/datasets.json`](config/datasets.json):

1. **HuggingFace datasets** — downloaded automatically at training time
2. **Local Markdown files** — placed in the `training/` subdirectories

### Training Directories

Each role has its own dedicated folder. Drop `.md` or `.txt` files there to inject custom data:

| Directory | Role(s) | What to put here |
|-----------|---------|-----------------|
| `training/general/` | `triage`, `general` | General knowledge, conversational examples, factual reference |
| `training/coding/` | `code` | Code tutorials, debugging guides, programming Q&A |
| `training/math/` | `math` | Worked problems, proofs, equation explanations |
| `training/reasoning/` | `reasoning` | Logic puzzles, system design docs, analytical essays |
| `training/control/` | `router` | Tool-use examples, JSON action schemas, agent instructions |
| `training/shared/` | **all roles** | Documents included in every role's training run |

> [!TIP]
> Format Markdown files with `USER:`, `BOT:`, and optionally `SYSTEM:` prefixes on each turn to create structured conversation pairs. Unstructured files are also supported — each section heading becomes a Q&A pair automatically.

### HuggingFace Datasets (per role)

| Role | Dataset | Samples |
|------|---------|---------|
| `triage` | `blended_skill_talk` | 5 000 |
| `triage` | `daily_dialog` | 5 000 |
| `math` | `EleutherAI/hendrycks_math` | 5 000 |
| `math` | `deepmind/math_dataset` | 5 000 |
| `code` | `m-a-p/CodeFeedback-Filtered-Instruction` | 5 000 |
| `reasoning` | `angrygiraffe/claude-opus-4.6-4.7-reasoning-8.7k` | 8 000 |
| `reasoning` | `allenai/Dolci-Think-SFT-7B` | 8 000 |
| `reasoning` | `prithivMLmods/Deepthink-Reasoning` | 8 000 |
| `reasoning` | `trjxter/DeepSeek-V4-Pro-Reasoning-8000x` | 8 000 |
| `reasoning` | `teknium/OpenHermes-2.5` | 8 000 |
| `general` | `blended_skill_talk` | 5 000 |
| `general` | `daily_dialog` | 5 000 |
| `general` | `teknium/OpenHermes-2.5` | 5 000 |

---

## Training Workflows

The script auto-detects your hardware and picks the right backend:

| Hardware | Backend | Notes |
|----------|---------|-------|
| Apple Silicon (M1/M2/M3/M4) | **MLX** via `mlx_lm.lora` | Fastest on Mac, uses Unified Memory |
| NVIDIA GPU (CUDA) | **HF Trainer** + QLoRA (4-bit) | Quantized with bitsandbytes |
| CPU / other | **HF Trainer** + LoRA (fp32) | Slow, only for testing |

### Apple Silicon (MLX)

The MLX path trains using `mlx_lm.lora` and exports a fused HuggingFace model before GGUF conversion.

**Train all roles:**
```bash
python train.py
```

**Train a single role:**
```bash
python train.py --train-role general
```

**Train multiple specific roles:**
```bash
python train.py --train-role code reasoning
```

**Typical run with custom settings:**
```bash
python train.py \
  --train-role reasoning \
  --iters 5000 \
  --lr 1e-5 \
  --batch-size 2 \
  --max-seq-length 1024 \
  --num-layers 32 \
  --quant-type q4_k_m
```

### CUDA / CPU (Torch)

The Torch path uses QLoRA on CUDA (4-bit NF4 with `bitsandbytes`) or standard LoRA on CPU.

**Train with CUDA:**
```bash
python train.py --device cuda --train-role code --epochs 3 --batch-size 2 --accum-steps 8
```

**Force CPU (testing only):**
```bash
python train.py --device cpu --train-role triage --max-pairs 500
```

---

## CLI Reference

```
python train.py [OPTIONS]
```

### Role Selection

| Flag | Default | Description |
|------|---------|-------------|
| `--train-role ROLE [ROLE ...]` | `all` | Roles to train. Options: `triage`, `router`, `math`, `code`, `reasoning`, `general`, `all` |

### Data Options

| Flag | Default | Description |
|------|---------|-------------|
| `--max-pairs N` | `5000` | Maximum training pairs to load per role |
| `--no-bst` | off | Skip `blended_skill_talk` dataset |
| `--no-dd` | off | Skip `daily_dialog` dataset |
| `--no-md` | off | Skip local Markdown files |
| `--md-dir PATH` | auto | Override the Markdown training directory |
| `--claude-reasoning N` | `600` | Samples from claude-opus reasoning dataset |
| `--dolci-think N` | `600` | Samples from Dolci-Think-SFT-7B |
| `--deepthink N` | `600` | Samples from Deepthink-Reasoning |
| `--strip-reasoning` | off | Remove `<think>…</think>` blocks from reasoning datasets |
| `--openhermes N` | `0` | Samples from OpenHermes-2.5 (disabled by default) |
| `--math-qa N` | `0` | Samples from hendrycks_math (disabled by default) |
| `--code-feedback N` | `0` | Samples from CodeFeedback (disabled by default) |

### Model & Training Hyperparameters

| Flag | Default | Description |
|------|---------|-------------|
| `--model MODEL_ID` | role default | Override base HuggingFace model ID |
| `--iters N` | `3000` | Training iterations (MLX) or max sample count (Torch) |
| `--epochs N` | `3` | Training epochs (Torch path only) |
| `--lr FLOAT` | `2e-5` | Learning rate |
| `--batch-size N` | `1` | Per-device batch size |
| `--accum-steps N` | `8` | Gradient accumulation steps (effective batch = batch × accum) |
| `--max-seq-length N` | `512` | Maximum token length per sample |
| `--device cuda\|mps\|cpu` | auto | Force a specific compute device |
| `--num-layers N` | `16` | Number of LoRA layers to tune (MLX only) |
| `--output-dir PATH` | `./iris_adapters/{role}` | Where to save LoRA adapters |

### GGUF Conversion

| Flag | Default | Description |
|------|---------|-------------|
| `--quant-type q4_k_m\|q8_0\|f16` | `q4_k_m` | GGUF quantization level |
| `--skip-gguf` | off | Skip merge & GGUF conversion (keep adapters only) |
| `--fuse` | off | Fuse adapter into base model before export (MLX only) |
| `--cleanup` | off | Delete adapters after fusion (MLX only) |

---

## GGUF Conversion

GGUF conversion runs **automatically** after each role's training (unless `--skip-gguf` is set). The pipeline:

1. **Merge** — LoRA adapters are merged into the base model weights
2. **Convert** — `./scripts/convert_hf_to_gguf.py` produces an F16 GGUF
3. **Quantize** — `llama-quantize` (installed via brew or on PATH) compresses to the target format

**Output files:**

```
./models/
├── iris-triage.gguf
├── iris-router.gguf
├── iris-math.gguf
├── iris-code.gguf
├── iris-reasoning.gguf
└── iris-general.gguf
```

**Quantization levels:**

| Level | Size (7B example) | Quality | Speed |
|-------|------------------|---------|-------|
| `f16` | ~14 GB | Best | Slowest |
| `q8_0` | ~7 GB | Very High | Fast |
| `q4_k_m` *(default)* | ~4 GB | High | Fastest |

> [!NOTE]
> You can convert an existing adapter manually without retraining by running `train.py --skip-training` (adapters must already exist in `./iris_adapters/{role}/`).

---

## Adding Custom Training Data

### Method 1 — Local Markdown files

1. Write a `.md` file using tagged conversation format:

```markdown
USER: What is the time complexity of quicksort?
BOT: Quicksort has an average time complexity of O(n log n) and a worst-case of O(n²) when the pivot is always the smallest or largest element.

USER: How do I avoid the worst case?
BOT: Use randomized pivot selection or the median-of-three strategy to minimize the chance of hitting O(n²) performance.
```

2. Drop it in the appropriate `training/` subfolder (e.g., `training/reasoning/` for reasoning tasks, `training/shared/` to include in all roles).

3. Run training — the file is picked up automatically.

### Method 2 — HuggingFace datasets

Edit [`config/datasets.json`](config/datasets.json) and add an entry under the target role:

```json
"code": {
  "huggingface": [
    {"path": "your-org/your-dataset", "max_samples": 3000}
  ],
  "local_dirs": ["training/coding", "training/shared"]
}
```

The generic loader auto-detects common dataset schemas (`messages`, `prompt`/`response`, `instruction`/`output`, `conversations`).

### Method 3 — Pass a dataset via CLI

```bash
python train.py --train-role code --code-feedback 2000
```

---

## Configuring Datasets

The file [`config/datasets.json`](config/datasets.json) controls exactly which datasets each role trains on:

```json
{
  "role_name": {
    "huggingface": [
      {"path": "org/dataset-name", "max_samples": 5000}
    ],
    "local_dirs": [
      "training/subfolder",
      "training/shared"
    ]
  }
}
```

- `path` — HuggingFace dataset identifier (used with `datasets.load_dataset`)
- `max_samples` — cap on how many pairs to load from that dataset
- `local_dirs` — list of local directories containing `.md` / `.txt` files

> [!WARNING]
> The `training/shared/` directory is included for **every** role. Be careful what you put there — it will affect all models including `triage` and `router`.

---

## Tips & Best Practices

### Memory management

- On Apple Silicon, training a 14B model (reasoning/general) requires **≥ 32 GB RAM**. For 7B models, 16 GB is usually sufficient. At 16GB, train triage, router, math, and code only; use pre-quantized GGUF inference for 14B roles.
- On CUDA, 4-bit QLoRA allows training a 14B model on a 24 GB GPU (e.g., RTX 3090/4090).
- Reduce `--max-seq-length` (e.g., to `256`) to cut VRAM usage at the cost of shorter training samples.

### Effective batch size

The actual batch size is `--batch-size × --accum-steps`. The default (`1 × 8 = 8`) is a good starting point. For better stability:

```bash
--batch-size 2 --accum-steps 4   # same effective batch, faster on modern GPUs
```

### Learning rate

| Model size | Recommended LR |
|-----------|---------------|
| 3B | `3e-5` – `5e-5` |
| 7B | `2e-5` – `3e-5` |
| 14B | `1e-5` – `2e-5` |

### Number of LoRA layers (MLX)

`--num-layers` controls how many transformer layers receive LoRA adapters. More layers = more capacity but slower training and larger adapters.

| Goal | `--num-layers` |
|------|---------------|
| Fast experiment | `8` |
| Balanced (default) | `16` |
| Maximum quality | `32` – all |

### Training only one role

If you only need to update one specialist (e.g., after adding new math data), train it in isolation to save time:

```bash
python train.py --train-role math --iters 2000 --quant-type q4_k_m
```

### Skip GGUF for faster iteration

During experimentation, skip the conversion step and test the raw adapter:

```bash
python train.py --train-role code --skip-gguf
```

Re-run conversion later when you're happy with the adapter:

```bash
python train.py --train-role code --iters 0 --skip-training  
# (or just don't pass --skip-gguf on the real run)
```

### Inspect inference config

Runtime inference settings (temperature, context length, GPU layers, etc.) are in [`config/iris.conf`](config/iris.conf). Changes take effect immediately without restarting — the config is hot-reloaded on each request.
