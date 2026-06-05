# Iris AI — Models & Routing

## Role Architecture

Iris uses **8 distinct roles**, each backed by a specialized GGUF model. The role defines the model's system prompt, context window, and training data.

| Role | Enum Value | GGUF File | Context | System Prompt |
|------|-----------|-----------|---------|---------------|
| **Triage** | `triage` | `iris_001.gguf` | 2048 | Classify query intent, output routing tag |
| **Router** | `router` | `iris_002.gguf` | 2048 | Output JSON action matrices for automation |
| **Control** | `control` | `iris_003.gguf` | 2048 | Output automation actions in JSON |
| **Math** | `math` | `iris_004.gguf` | 4096 | Solve math/algorithmic problems step-by-step |
| **Code** | `code` | `iris_005.gguf` | 8192 | Generate working production-quality code |
| **Reasoning** | `reasoning` | `iris_006.gguf` | 2048 | Chain-of-thought for complex problems |
| **General** | `general` | `iris_007.gguf` | 4096 | Broad knowledge, explanations, comparisons |
| **Vision** | `vision` | `iris_008.gguf` | 4096 | Analyze images, describe visual content |

---

## Model Selection By Tier

### Tiny (~15 GB — 4 GB RAM)
| Role | Model | Parameters |
|------|-------|------------|
| Triage | Qwen2.5-0.5B-Instruct | 0.5B |
| Router | Qwen2.5-1.5B-Instruct | 1.5B |
| Math | Qwen2.5-Math-1.5B-Instruct | 1.5B |
| Code | R1-Distill-Qwen-1.5B | 1.5B |
| Reasoning | Qwen2.5-3B-Instruct | 3B |
| General | Qwen2.5-3B-Instruct | 3B |
| Vision | Qwen2.5-VL-3B-Instruct | 3B |

### Small (~30 GB — 8 GB RAM)
| Role | Model | Parameters |
|------|-------|------------|
| Triage | Llama-3.2-3B-Instruct | 3B |
| Router | Qwen2.5-Coder-3B-Instruct | 3B |
| Math | Qwen2.5-Math-7B-Instruct | 7B |
| Code | Qwen2.5-Coder-7B-Instruct | 7B |
| Reasoning | R1-Distill-Qwen-7B | 7B |
| General | Llama-3.2-3B-Instruct | 3B |
| Vision | Qwen3-VL-4B-Instruct | 4B |

### Medium (~45 GB — 16 GB RAM) [DEFAULT]
| Role | Model | Parameters |
|------|-------|------------|
| Triage | Llama-3.2-3B-Instruct | 3B |
| Router | Hermes-3-Llama-3.1-8B | 8B |
| Math | Qwen2.5-Math-7B-Instruct | 7B |
| Code | Qwen2.5-Coder-14B-Instruct | 14B |
| Reasoning | DeepSeek-LLM-14B-Chat | 14B |
| General | Qwen3.5-9B-Instruct | 9B |
| Vision | Qwen3-VL-4B-Instruct | 4B |

### Large (~80 GB — 48 GB RAM)
| Role | Model | Parameters |
|------|-------|------------|
| Triage | Qwen2.5-7B-Instruct | 7B |
| Router | Qwen2.5-Coder-7B-Instruct | 7B |
| Math | R1-Distill-Qwen-14B | 14B |
| Code | R1-Distill-Qwen-32B | 32B |
| Reasoning | R1-Distill-Qwen-32B | 32B |
| General | Qwen3.5-20B-Instruct | 20B |
| Vision | Qwen3-VL-8B-Instruct | 8B |

### Max (~250 GB — 64-128 GB RAM)
| Role | Model | Parameters |
|------|-------|------------|
| Triage | Qwen2.5-32B-Instruct | 32B |
| Router | Qwen2.5-Coder-32B-Instruct | 32B |
| Math | Qwen2.5-Math-72B-Instruct | 72B |
| Code | Qwen3-Coder-Next | Latest |
| Reasoning | DeepSeek-R1-Distill-Llama-70B | 70B |
| General | Llama-3.3-70B-Instruct | 70B |
| Vision | Qwen2.5-VL-72B-Instruct | 72B |

---

## Quantization

All models use **Q4_K_M** quantization (4-bit with medium quality). This provides the best balance of quality, size, and speed:

| Quant | Quality | Size (7B) | Speed |
|-------|---------|-----------|-------|
| Q2_K | Lowest | ~2.5 GB | Fastest |
| Q3_K_M | Low | ~3.5 GB | Fast |
| **Q4_K_M** | **High** | **~4.5 GB** | **Fast** |
| Q5_K_M | Higher | ~5.5 GB | Moderate |
| Q6_K | Very High | ~6.5 GB | Slower |
| Q8_0 | Best | ~7.5 GB | Slow |
| F16 | Lossless | ~14 GB | Slowest |

---

## Model Download

Models are downloaded automatically from HuggingFace using `hf_hub_download`:

```bash
# Download all models for a tier:
python train.py --size medium --download-models

# Download a specific model:
python -c "from src.iris import download_gguf; download_gguf('iris_001.gguf')"
```

Models are cached in `models/`. If a model already exists (non-zero size), download is skipped.

---

## System Prompts

Each role has a dedicated system prompt:

### Triage
```
You are the Iris AI Triage node.
Rules:
1. If the user is just greeting, saying hi/hello, asking simple conversational
   or factual questions, answer them directly. Do NOT output any routing tags.
2. If the query needs a specialist model, output EXACTLY ONE routing tag:
   [ROUTE: GENERAL]     — general knowledge, explanations, broad topics
   [ROUTE: REASONING]   — complex logic, system design, strategy, architecture
   [ROUTE: MATH]        — math, equations, proofs, algorithmic problems
   [ROUTE: CODE_SIMPLE]  — simple single-file code, small functions, snippets
   [ROUTE: CODE_COMPLEX] — large projects, games, multi-file, kernels, bootloaders

Be precise. If unsure, default to [ROUTE: GENERAL].
```

### Code
```
You are the Iris AI Coding Specialist. Generate clean, fully working,
production-quality code. Ensure correctness, edge-case handling, and
error-free syntax. Do NOT include comments in your code. After the code
block, provide a concise explanation of the code, its key features,
and clear instructions on how to compile/run it.
```

### Math
```
You are the Iris AI Math Core. Solve mathematical/algorithmic problems
step-by-step. Use precise notation.
```

### Reasoning
```
You are the Iris AI Reasoning Specialist. Think step-by-step using
chain-of-thought reasoning. Break down complex problems methodically
before giving the final answer.
```

### Reviewer
```
You are the Iris AI Code Reviewer. Review and refine code for correctness,
efficiency, edge cases, and readability. Ensure the final output is
production-ready. Fix any errors, fill missing logic, and optimize
where possible. Return the final code and explanation.
```
