<img width="500" height="500" alt="Retina_Eye_Care_Logo__1_-removebg-preview" src="https://github.com/user-attachments/assets/034506ea-4183-46f1-b3ac-b3a987b47db4" />

# Iris AI — Technical Documentation

## Overview

Iris AI is a fine-tuned conversational assistant built on top of `google/gemma-2-2b-it`. The system supports LoRA-based supervised fine-tuning (SFT) across CUDA, MPS (Apple Silicon), and CPU backends, with a Flask web interface and a terminal chat client. Training uses Gemma's native chat template throughout, and inference is handled via a shared generation pipeline in `iris.py`.

---

## Repository Structure

```
iris/
├── iris.py            # Unified Backend: MLX, CUDA, and CPU support + data loaders
├── train.py           # Legacy Torch training entry point
├── app.py             # Flask web server (unified backend)
├── controller.py      # PC Agent controller (unified backend)
├── training/          # Custom markdown training files
├── mlx_data/          # MLX training data (JSONL)
├── iris_14b_model/    # Quantized model
└── templates/
    └── index.html     # Web UI template
```

---

## Hardware Support

Iris AI now uses a **Unified Backend** that automatically detects your hardware:

- **Apple Silicon (M1-M4)**: Uses `mlx_lm` for high-speed inference and training.
- **NVIDIA GPU**: Uses `transformers` with `bitsandbytes` 4-bit quantization.
- **CPU**: Universal fallback using standard `transformers`.

---

## Module Reference

### `iris.py`

The core engine. Automatically routes requests to the correct hardware backend.

#### Functions

- `load_model()`: Loads the appropriate model (Phi-4 by default).
- `generate_reply(model, tokenizer, prompt, ...)`: Unified generation with support for both MLX and Transformers.
- `solve_math(text)`: Sympy-based math interceptor.
- `load_*_dataset()`: Collection of data loaders for training.

### `train_mlx.py`

Recommended for Mac users. A simple wrapper for the MLX LoRA training pipeline.

```bash
python3 train_mlx.py --iters 3000 --batch-size 1 --lr 2e-5
```

#### Constants

| Name | Value | Purpose |
|---|---|---|
| `USER_TOKEN` | `"User:"` | Fallback prompt prefix when no chat template is present |
| `BOT_TOKEN` | `"Bot:"` | Fallback response prefix |
| `EOS_TOKEN` | `"<\|endoftext\|>"` | End-of-sequence marker for non-Gemma tokenizers |

#### `get_device(force_cpu=False) -> torch.device`

Returns the best available device. Priority: CUDA > MPS > CPU. Passing `force_cpu=True` bypasses GPU detection.

#### `is_degenerate(text: str) -> bool`

Filters low-quality training samples. A string is considered degenerate if:
- It is empty or shorter than 10 characters
- Fewer than 50% of characters are alphabetic
- Fewer than 15 unique characters for strings longer than 20 characters

Used inside `prepare_conversations()` to remove noise from BST and DailyDialog before training.

#### `load_blended_skill_talk(subset_size=None) -> list[tuple[str, str]]`

Loads the `blended_skill_talk` HuggingFace dataset. Extracts consecutive utterance pairs from `previous_utterance` and seeds the first `free_messages` reply as an additional pair. Returns a list of `(user, bot)` string tuples.

#### `load_daily_dialog(subset_size=None) -> list[tuple[str, str]]`

Loads the `daily_dialog` HuggingFace dataset. Extracts all consecutive turn pairs from each dialog. Falls back to `trust_remote_code=True` if the default load fails.

#### `load_markdown_files(md_dir="md", pattern="*.md") -> list[tuple[str, str]]`

Parses custom training files from a directory. Expected line format:

```
User: <user message>
Bot: <bot reply>
```

Lines beginning with `#` or `<!--` are skipped. Pairs are only recorded when a `Bot:` line immediately follows a `User:` line. Supports case-insensitive matching (`USER:`, `BOT:`, etc.).

#### `prepare_conversations(bst_size, dd_size, md_dir, use_bst, use_dd, use_md) -> list[tuple[str, str]]`

Aggregates pairs from all enabled sources, applies the `is_degenerate` filter, and shuffles the result. Called from `train.py`'s data loading step.

#### `SFTDataset`

A `torch.utils.data.Dataset` that tokenizes `(user, bot)` pairs using the `User:/Bot:` format (non-chat-template path). Computes a per-token `loss_mask` that masks the prompt tokens, ensuring loss is computed only on the bot response. Used by the legacy training path in `iris.py` — not used by the current `train.py`.

#### `collate_fn(batch, tokenizer)`

Pads a batch of variable-length samples to the longest sequence in the batch. Returns a dict with `input_ids` and `loss_mask` tensors.

#### `train_one_epoch(...)`

Manual training loop with gradient accumulation and gradient clipping. Calls `torch.mps.empty_cache()` after each accumulation step on MPS to prevent memory fragmentation.

#### `evaluate(model, loader, device) -> float`

Runs a masked cross-entropy evaluation pass with `torch.no_grad()`. Returns average loss per token.

#### `generate_reply(model, tokenizer, prompt_text, device, ...) -> str`

Core inference function. Parameters:

| Parameter | Default | Description |
|---|---|---|
| `max_new_tokens` | 300 | Maximum tokens to generate |
| `temperature` | 0.3 | Sampling temperature (lower = more deterministic) |
| `top_p` | 0.85 | Nucleus sampling cutoff |
| `top_k` | 40 | Top-k sampling cutoff |
| `repetition_penalty` | 1.25 | Penalises repeated n-grams |

Stop token behaviour: resolves `<end_of_turn>` from the tokenizer vocabulary and appends it to `eos_token_id` so Gemma stops cleanly at the end of its turn. Generated tokens are decoded with `skip_special_tokens=True`, then residual HTML-like tags are stripped with a regex.

#### `chat(model, tokenizer, device)`

Interactive terminal chat loop. Maintains a rolling message history (capped at 20 entries). Uses `tokenizer.apply_chat_template()` when a chat template is present, falling back to `User:/Bot:` formatting otherwise. Initialises the history with a system-style primer exchange to establish Iris's identity and language-mirroring behaviour before the user speaks.

---

### `train.py`

Unified training entry point. Detects the hardware backend and applies the appropriate LoRA configuration and training loop.

#### Device Modes

| Device | Mode | Precision | LoRA r | Loop |
|---|---|---|---|---|
| CUDA | `cuda_qlora` | 4-bit NF4 + FP16 compute | 32 | HuggingFace Trainer |
| MPS | `mps_fp16` | FP16 (no autocast) | 16 | Manual loop |
| CPU | `cpu_fp32` | FP32 | 8 | Manual loop |

#### Arguments

| Argument | Default | Description |
|---|---|---|
| `--model-name` | `google/gemma-2-2b-it` | HuggingFace model ID or local path |
| `--epochs` | 5 | Number of training epochs |
| `--lr` | 2e-4 | AdamW learning rate |
| `--max-pairs` | 5000 | Maximum training pairs (global cap) |
| `--bst-size` | None | Override pair count for BST specifically |
| `--dd-size` | None | Override pair count for DailyDialog specifically |
| `--md-dir` | `training` | Directory containing `*.md` training files |
| `--no-bst` | false | Disable BlendedSkillTalk |
| `--no-dd` | false | Disable DailyDialog |
| `--no-md` | false | Disable markdown files |
| `--max-length` | 64 | Max tokenized sequence length |
| `--batch-size` | 1 | Per-device batch size |
| `--accum-steps` | 8 | Gradient accumulation steps |
| `--device` | auto | Manually override device (`cuda`, `mps`, `cpu`) |
| `--force-cpu` | false | Force CPU even if GPU is available |
| `--output-dir` | `./iris_lora_unified` | Directory for LoRA adapter checkpoints |
| `--chat-after-train` | false | Launch terminal chat after training completes |

#### Training Pipeline

1. Tokenizer loaded from `--model-name`. `pad_token` is set to `eos_token` if absent.
2. Conversation pairs loaded via `load_conversations()`, formatted with `tokenizer.apply_chat_template()`.
3. Tokenized with fixed padding to `--max-length`. For CUDA, stored as a HuggingFace `Dataset`; for MPS/CPU, stored as a `TensorDataset`.
4. Base model loaded in the appropriate precision. Gradient checkpointing enabled on all paths.
5. LoRA applied via `peft.get_peft_model()` with `target_modules="all-linear"`.
6. Training runs via `train_cuda()` (Trainer API) or `train_manual()` (manual loop).
7. LoRA adapter saved per epoch to `{output_dir}_epoch{n}/`.
8. Final adapter merged into the full model weights via `model.merge_and_unload()` and saved to `./iris_merged_model`.

#### LoRA Configuration

```python
LoraConfig(
    r=16,                      # rank (varies by device: 32 CUDA, 16 MPS, 8 CPU)
    lora_alpha=32,             # scaling factor (2x r)
    target_modules="all-linear",
    lora_dropout=0.05,
    bias="none",
    task_type=TaskType.CAUSAL_LM,
)
```

#### Optimizer and Scheduler

AdamW with `weight_decay=0.01`. Linear warmup over 5% of total steps, then linear decay to zero. Gradient norm clipped to 1.0.

---

### `chat.py`

Terminal chat client. Loads the merged model from `./iris_merged_model` and delegates to `iris.chat()`.

Model loading behaviour by device:

| Device | Precision | Quantization |
|---|---|---|
| CUDA | FP16 | 4-bit NF4 via bitsandbytes (falls back to FP16 if unavailable) |
| MPS | FP16 | None |
| CPU | FP32 | None |

#### Usage

```bash
python3 chat.py
python3 chat.py --device cpu
python3 chat.py --device cuda
python3 chat.py --device mps
```

Requires `./iris_merged_model` to exist. Run `train.py` first to produce this directory.

---

### `app.py`

Flask web server exposing the chat and training pipeline over HTTP. Runs on `127.0.0.1:5050` by default.

#### Startup Flags

| Flag | Description |
|---|---|
| `--preview-only` | Start the server without loading the model. All `/chat` requests return a mock response. Useful for UI development. |
| `--force-cpu` | Load and run the model on CPU in FP32 regardless of available hardware. |

The `FORCE_CPU` environment variable (`1`, `true`, or `yes`) has the same effect as `--force-cpu`.

#### Model Loading

`init_model()` is called lazily on the first request via `@app.before_request`. It is thread-safe (protected by `threading.Lock`). If `./iris_merged_model` does not exist, it falls back to loading `google/gemma-2-2b-it` directly from HuggingFace.

#### Endpoints

**`GET /`**
Renders `templates/index.html`.

**`POST /chat`**

Accepts JSON:
```json
{
  "chat_id": "string",
  "message": "string",
  "history": "string",
  "settings": {
    "max_new_tokens": 40,
    "temperature": 0.6,
    "top_p": 0.9,
    "top_k": 40,
    "repetition_penalty": 1.3,
    "max_sentences": 1
  }
}
```

`history` is a plain-text string of prior turns. It is trimmed to the last 6 non-empty lines before being prepended to the prompt. The bot reply is appended to `logs/{chat_id}.txt`.

Returns:
```json
{ "reply": "string" }
```

**`POST /train`**

Launches `train.py` as a subprocess. Accepts JSON matching the `train.py` argument set. Output is streamed to `outputs/train_output.txt`. Returns `{"status": "already_running"}` if a training process is active.

**`GET /train_logs`**

Returns the contents of `outputs/train_output.txt` as `{"logs": "string"}`.

**`GET /train_status`**

Returns `{"running": true|false}`.

**`POST /stop_train`**

Sends `SIGTERM` to the training subprocess. Waits up to 5 seconds, then sends `SIGKILL` if it has not exited.

#### Chat History Format in `app.py`

`app.py` uses the legacy `User:/Bot:` prompt format rather than Gemma's chat template. The `history` string is constructed on the client side and passed as a plain-text block. This is distinct from the chat-template-aware loop in `iris.chat()`.

---

## Data Sources

### BlendedSkillTalk (BST)

HuggingFace dataset `blended_skill_talk`. Multi-skill crowdsourced conversations blending persona, empathy, and knowledge. Contains casual English chitchat. Recommended to disable with `--no-bst` if identity stability is a priority, as it introduces human persona patterns that override the model's configured identity.

### DailyDialog

HuggingFace dataset `daily_dialog`. English daily-life dialogues across 10 topic categories. Similar caveats to BST regarding persona leakage.

### Markdown Files

Custom training data in `*.md` files. This is the recommended primary data source for domain-specific or identity-defining behaviour. Format:

```
User: What is your name?
Bot: My name is Iris. I am an AI assistant.

User: Write hello world in Python.
Bot: print("Hello, World!")
```

Multi-line bot responses are not supported. Only the content on the same line as `Bot:` is captured.

---

## Model Artifacts

| Path | Contents |
|---|---|
| `./iris_lora_unified/` | Final LoRA adapter (PEFT format) |
| `./iris_lora_unified_epoch{n}/` | Per-epoch adapter checkpoints |
| `./iris_merged_model/` | Full merged model weights (used at inference) |

The merged model is produced by `model.merge_and_unload()`, which folds the LoRA delta weights into the base model parameters and removes the adapter structure. This is what `chat.py` and `app.py` load.

---

## Dependencies

Core:
```
torch >= 2.1
transformers >= 4.40
peft >= 0.10
datasets
flask
tqdm
```

Optional (CUDA only):
```
bitsandbytes >= 0.41
```
Required for 4-bit QLoRA training and 4-bit inference in `chat.py` on CUDA. Not required for MPS or CPU paths.

Install:
```bash
pip install torch transformers peft datasets flask tqdm
pip install bitsandbytes  # CUDA only
```

---

## Quickstart

**Train on custom markdown data only (recommended):**
```bash
python3 train.py --no-bst --no-dd --md-dir training --epochs 3 --lr 1e-4
```

**Train with all data sources:**
```bash
python3 train.py --md-dir training --epochs 5 --max-pairs 5000
```

**Run terminal chat:**
```bash
python3 chat.py
```

**Run web interface:**
```bash
python3 app.py
# or in preview mode (no model loaded):
python3 app.py --preview-only
```

---

## Training Recommendations

Disable BST and DailyDialog for assistant-style fine-tuning. Both datasets contain human personas that override the model's identity when trained at any significant volume.

Keep epoch count low. Over-training on a small markdown dataset causes the model to memorise responses verbatim. 2-5 epochs is sufficient for identity grounding.

Use a low learning rate for identity-only fine-tuning. The base Gemma 2 model has strong general capabilities. A learning rate of `1e-4` or lower minimises degradation of those capabilities while allowing personality and identity tuning.

The base model outperforms the fine-tuned model for general tasks such as coding, multilingual output, and factual Q&A. If those capabilities are the primary requirement, use `google/gemma-2-2b-it` directly with a system prompt via `iris.chat()` rather than a fine-tuned merged model.

---

## Known Limitations

- `app.py` uses the `User:/Bot:` prompt format rather than Gemma's chat template. This is inconsistent with the training format used in `train.py` and may cause response quality degradation through the web interface.
- Multi-line `Bot:` responses in markdown files are not supported. Only the first line after `Bot:` is captured by `load_markdown_files()`.
- The `max_sentences` parameter is accepted by `app.py` and forwarded to `generate_reply()`, but `generate_reply()` in `iris.py` does not implement sentence-count truncation. Passing this argument will raise a `TypeError`.
- MPS does not support `torch.autocast`, so training runs in raw FP16 without mixed-precision gradient scaling. This is stable for Gemma 2 but may cause gradient underflow on other architectures.
- `iris.py` imports the `re` module twice at the module level.
- Per-epoch adapter checkpoints are not cleaned up automatically. Disk usage grows by one full adapter per epoch.
