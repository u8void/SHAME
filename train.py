"""
train.py — Unified Training Suite for Iris AI
=============================================
Supports GGUF role-based training and post-training GGUF conversion.
Automatically detects Apple Silicon (MLX path) vs CUDA/CPU (Torch path).
"""

import os
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
import sys
import json
import random
import argparse
import subprocess
import platform
import shutil
import tempfile
from typing import List, Tuple

from src.iris import (
    load_blended_skill_talk,
    load_daily_dialog,
    load_markdown_files,
    load_mbzuai_egyptian_mixture,
    load_hf_maliki_dataset,
    load_claude_reasoning_dataset,
    load_dolci_think_dataset,
    load_deepthink_dataset,
    load_openhermes_reasoning,
    load_math_qa,
    load_code_feedback,
    load_oasst1_dataset,
)

SYSTEM_PROMPT = "You are Iris, an intelligent and helpful AI assistant trained to assist the user with their tasks."

ROLE_MODEL_MAP = {
    "triage":    "meta-llama/Llama-3.2-3B-Instruct",
    "router":    "NousResearch/Hermes-3-Llama-3.1-8B",
    "control":   "NousResearch/Hermes-3-Llama-3.1-8B",
    "math":      "Qwen/Qwen2.5-Math-7B-Instruct",
    "code":      "Qwen/Qwen2.5-Coder-14B-Instruct",
    "reasoning": "deepseek-ai/deepseek-llm-14b-chat",
    "general":   "Qwen/Qwen3.5-9B-Instruct",
    "vision":    "Qwen/Qwen3-VL-4B-Instruct",
}

ROLE_TO_GGUF = {
    "triage":    "iris_001.gguf",
    "router":    "iris_002.gguf",
    "control":   "iris_003.gguf",
    "math":      "iris_004.gguf",
    "code":      "iris_005.gguf",
    "reasoning": "iris_006.gguf",
    "general":   "iris_007.gguf",
    "vision":    "iris_008.gguf",
}

# Role → output file numbering
ROLE_NUMBERS = {
    "triage":    "001",
    "router":    "002",
    "control":   "003",
    "math":      "004",
    "code":      "005",
    "reasoning": "006",
    "general":   "007",
    "vision":    "008",
}

SIZE_CONFIG = None  # loaded by apply_size_config


ROLE_TRAINING_DIRS = {
    "triage":    ["training/general",   "training/shared"],
    "router":    ["training/control",   "training/shared"],
    "control":   ["training/control",   "training/shared"],
    "math":      ["training/math",      "training/shared"],
    "code":      ["training/coding",    "training/shared"],
    "reasoning": ["training/reasoning", "training/shared"],
    "general":   ["training/general",   "training/shared"],
    "vision":    ["training/general",   "training/shared"],
}


def load_size_config(size: str) -> dict:
    """Load a size-tier config from config/sizes/{size}.json and return it."""
    import json
    path = os.path.join(os.path.dirname(__file__), "config", "sizes", f"{size}.json")
    if not os.path.exists(path):
        print(f"[WARNING] Size config {size}.json not found — falling back to medium.")
        path = os.path.join(os.path.dirname(__file__), "config", "sizes", "medium.json")
    with open(path) as f:
        return json.load(f)

def apply_size_config(size: str):
    """Override ROLE_MODEL_MAP, ROLE_TO_GGUF, and download URLs from a size config."""
    cfg = load_size_config(size)
    desc = cfg.get("_description", size)
    print(f"[SIZE] Iris AI — {size.upper()} tier")
    print(f"[SIZE] {desc}")
    # Override ROLE_MODEL_MAP
    global ROLE_MODEL_MAP, ROLE_TO_GGUF, SIZE_CONFIG
    ROLE_MODEL_MAP.update(cfg.get("models", {}))
    ROLE_TO_GGUF.update(cfg.get("gguf", {}))
    SIZE_CONFIG = cfg

def parse_args():
    parser = argparse.ArgumentParser(description="Unified GGUF Training for Iris AI")

    parser.add_argument("--role", nargs="+", default=["all"],
                        help="Roles to train: triage, router, math, code, reasoning, general, all")
    parser.add_argument("--quant-type", choices=["q4_k_m", "q8_0", "f16"], default="q4_k_m",
                        help="GGUF quantization level")
    parser.add_argument("--size", choices=["tiny", "small", "medium", "large", "max"], default="medium",
                        help="Iris AI model size tier (tiny/small/medium/large/max)")
    parser.add_argument("--download-models", "--download-all", action="store_true", dest="download_models",
                        help="Download all models for the selected tier and continue automatically")
    parser.add_argument("--download-only", action="store_true", help="Download all models for the selected tier and exit without training")
    parser.add_argument("--skip-gguf", action="store_true", help="Skip merge and GGUF conversion")
    parser.add_argument("--resume", action="store_true", help="Resume training from the last successful checkpoint/model")
    
    parser.add_argument("--model", default=None, help="Override base model ID")
    parser.add_argument("--iters", type=int, default=3000, help="Iterations (MLX) or max pairs (Torch)")
    parser.add_argument("--epochs", type=int, default=3, help="Epochs (Torch path only)")
    parser.add_argument("--lr", type=float, default=2e-5, help="Learning rate")
    parser.add_argument("--batch-size", type=int, default=1, help="Batch size")
    parser.add_argument("--accum-steps", type=int, default=8, help="Gradient accumulation steps")
    parser.add_argument("--max-seq-length", type=int, default=1024, help="Maximum sequence length")
    parser.add_argument("--device", choices=["cuda", "mps", "cpu"], default=None)

    parser.add_argument("--max-pairs", type=int, default=5000)
    parser.add_argument("--no-bst", action="store_true")
    parser.add_argument("--no-dd", action="store_true")
    parser.add_argument("--no-md", action="store_true")
    parser.add_argument("--md-dir", default=None, help="Override Markdown training directory")
    
    parser.add_argument("--claude-reasoning", type=int, default=600)
    parser.add_argument("--dolci-think", type=int, default=600)
    parser.add_argument("--deepthink", type=int, default=600)
    parser.add_argument("--strip-reasoning")

    parser.add_argument("--openhermes", type=int, default=0)
    parser.add_argument("--math-qa", type=int, default=0)
    parser.add_argument("--code-feedback", type=int, default=0)

    parser.add_argument("--fuse", action="store_true", help="Fuse model after training (MLX only)")
    parser.add_argument("--cleanup", action="store_true", help="Clean adapters after fusion (MLX only)")
    parser.add_argument("--num-layers", type=int, default=16, help="Layers to tune (MLX only)")
    parser.add_argument("--output-dir", default=None, help="Override output directory")

    return parser.parse_args()

LOADER_FUNCTIONS = {
    "blended_skill_talk": load_blended_skill_talk,
    "daily_dialog": load_daily_dialog,
    "EleutherAI/hendrycks_math": load_math_qa,
    "m-a-p/CodeFeedback-Filtered-Instruction": load_code_feedback,
    "angrygiraffe/claude-opus-4.6-4.7-reasoning-8.7k": load_claude_reasoning_dataset,
    "allenai/Dolci-Think-SFT-7B": load_dolci_think_dataset,
    "prithivMLmods/Deepthink-Reasoning": load_deepthink_dataset,
    "teknium/OpenHermes-2.5": load_openhermes_reasoning,
    "MBZUAI-Paris/Egyptian-SFT-Mixture": load_mbzuai_egyptian_mixture,
    "islamic-datasets/Istilah_Maliki_Dataset": load_hf_maliki_dataset,
    "OpenAssistant/oasst1": load_oasst1_dataset,
}

def load_generic_hf_dataset(path: str, limit: int = None) -> List[Tuple[str, str]]:
    try:
        from datasets import load_dataset
    except ImportError:
        print("[ERROR] 'datasets' package is not installed. Run 'pip install datasets'.")
        return []
    
    import re
    print(f"[DATA] Attempting to load dataset {path} with generic loader...")
    try:
        try:
            ds = load_dataset(path, split="train", streaming=True)
        except Exception as e:
            if "Bad split" in str(e) or "Unknown split" in str(e):
                try:
                    ds = load_dataset(path, split="train_sft", streaming=True)
                except Exception:
                    ds = load_dataset(path, split="train_gen", streaming=True)
            else:
                raise e
        if limit:
            try:
                ds = ds.shuffle(buffer_size=10000, seed=42)
            except Exception:
                pass
        pairs = []
        try:
            features = ds.features
        except AttributeError:
            features = None
            
        if not features:
            try:
                features = next(iter(ds))
            except StopIteration:
                return []
        
        if "messages" in features:
            for row in ds:
                if limit and len(pairs) >= limit:
                    break
                m = row.get("messages")
                if m and len(m) >= 2:
                    for i in range(len(m)-1):
                        if m[i].get("role") == "user" and m[i+1].get("role") == "assistant":
                            u, b = m[i].get("content", "").strip(), m[i+1].get("content", "").strip()
                            if u and b:
                                pairs.append((u, b))
                                break
        elif "prompt" in features:
            resp_col = "response" if "response" in features else ("completion" if "completion" in features else ("output" if "output" in features else None))
            if resp_col:
                for row in ds:
                    if limit and len(pairs) >= limit:
                        break
                    u, b = row.get("prompt", "").strip(), row.get(resp_col, "").strip()
                    if u and b:
                        pairs.append((u, b))
        elif "instruction" in features and "output" in features:
            for row in ds:
                if limit and len(pairs) >= limit:
                    break
                u, b = row.get("instruction", "").strip(), row.get("output", "").strip()
                inp = row.get("input", "")
                if inp:
                    u = f"{u}\n\nInput: {inp}"
                if u and b:
                    pairs.append((u, b))
        elif "conversations" in features:
            for row in ds:
                if limit and len(pairs) >= limit:
                    break
                conv = row.get("conversations")
                if conv and len(conv) >= 2:
                    for i in range(len(conv)-1):
                        role_key = "from" if "from" in conv[i] else "role"
                        val_key = "value" if "value" in conv[i] else "content"
                        u_role = str(conv[i].get(role_key, "")).lower()
                        a_role = str(conv[i+1].get(role_key, "")).lower()
                        if u_role in ["user", "human"] and a_role in ["assistant", "gpt"]:
                            u, b = conv[i].get(val_key, "").strip(), conv[i+1].get(val_key, "").strip()
                            if u and b:
                                pairs.append((u, b))
                                break
        else:
            query_cols = ["question", "input", "query", "text", "prompt", "instruction"]
            response_cols = ["answer", "output", "response", "target", "completion"]
            q_col = next((c for c in query_cols if c in features), None)
            r_col = next((c for c in response_cols if c in features), None)
            if q_col and r_col:
                for row in ds:
                    if limit and len(pairs) >= limit:
                        break
                    u, b = str(row.get(q_col, "")).strip(), str(row.get(r_col, "")).strip()
                    if u and b:
                        pairs.append((u, b))
            else:
                keys_list = list(features.keys()) if hasattr(features, "keys") else list(features)
                print(f"[WARNING] Could not determine columns for {path}. Available columns: {keys_list}")
                
        return pairs
    except Exception as e:
        print(f"[WARNING] Generic loader failed for {path}: {e}")
        return []

def load_all_data(role: str, max_pairs: int) -> List[Tuple[str, str]]:
    config_path = "./config/datasets.json"
    if not os.path.exists(config_path):
        print(f"[ERROR] Datasets config file not found at {config_path}")
        return []
        
    with open(config_path, "r", encoding="utf-8") as f:
        datasets_config = json.load(f)
        
    role_config = datasets_config.get(role)
    if not role_config:
        print(f"[WARNING] No dataset configuration found for role: {role}")
        return []
        
    pairs = []
    
    for hf_dataset in role_config.get("huggingface", []):
        path = hf_dataset.get("path")
        limit = hf_dataset.get("max_samples", max_pairs)
        loader = LOADER_FUNCTIONS.get(path)
        if loader:
            print(f"[DATA] Loading HF dataset: {path} (limit={limit})...")
            try:
                pairs += loader(subset_size=limit)
            except Exception as e:
                print(f"[WARNING] Failed to load HF dataset {path}: {e}")
        else:
            print(f"[DATA] No specialized loader for {path}. Trying generic loader...")
            try:
                pairs += load_generic_hf_dataset(path, limit=limit)
            except Exception as e:
                print(f"[WARNING] Failed to load HF dataset {path} using generic loader: {e}")
            
    for local_dir in role_config.get("local_dirs", []):
        if os.path.exists(local_dir):
            print(f"[DATA] Loading local markdown files from: {local_dir}...")
            try:
                pairs += load_markdown_files(md_dir=local_dir)
            except Exception as e:
                print(f"[WARNING] Failed to load local files from {local_dir}: {e}")
                
    random.shuffle(pairs)
    if len(pairs) > max_pairs:
        pairs = pairs[:max_pairs]
        
    # Pre-split massive sequences to prevent OOM and hard truncation
    chunked_pairs = []
    chunk_size = 3500  # Approx 850 tokens, leaves room for prompt and system message
    for prompt, response in pairs:
        if len(response) <= chunk_size:
            chunked_pairs.append((prompt, response))
        else:
            chunks = [response[i:i+chunk_size] for i in range(0, len(response), chunk_size)]
            for i, chunk in enumerate(chunks):
                if i == 0:
                    chunked_pairs.append((prompt, chunk))
                else:
                    chunked_pairs.append(("Please continue.", chunk))
                    
    print(f"[DATA] Loaded {len(pairs)} raw pairs, expanded to {len(chunked_pairs)} pairs after chunking for role '{role}'.")
    return chunked_pairs

def export_to_jsonl(pairs: List[Tuple[str, str]], out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    random.shuffle(pairs)
    split = int(len(pairs) * 0.95)
    train_data = pairs[:split]
    valid_data = pairs[split:]

    def write_jsonl(data, filename):
        with open(os.path.join(out_dir, filename), "w", encoding="utf-8") as f:
            for prompt, response in data:
                entry = {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": response}
                    ]
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    write_jsonl(train_data, "train.jsonl")
    write_jsonl(valid_data, "valid.jsonl")
    print(f"[DATA] Exported {len(train_data)} training and {len(valid_data)} validation samples to {out_dir}")

def base_models_match(configured_base: str, existing_base: str) -> bool:
    if not configured_base or not existing_base:
        return False
    import re
    def clean(s: str) -> str:
        s = s.lower()
        s = s.replace("deepseek-ai/", "").replace("qwen/", "")
        s = re.sub(r'[^a-z0-9]', '', s)
        return s
    cfg_clean = clean(configured_base)
    ext_clean = clean(existing_base)
    return (cfg_clean in ext_clean) or (ext_clean in cfg_clean)

def get_gguf_base_model(gguf_path: str):
    from typing import Optional
    try:
        from gguf import GGUFReader
    except ImportError:
        return None
    try:
        reader = GGUFReader(gguf_path)
        for key in ["general.base_model.0.name", "general.base_model.0.repo_url", "general.name"]:
            field = reader.get_field(key)
            if field is not None:
                parts = field.parts
                if not parts:
                    continue
                last_part = parts[-1]
                if isinstance(last_part, (bytes, bytearray)):
                    return last_part.decode('utf-8', errors='ignore')
                elif hasattr(last_part, 'tobytes'):
                    return last_part.tobytes().decode('utf-8', errors='ignore')
                elif isinstance(last_part, list) or hasattr(last_part, '__iter__'):
                    try:
                        return "".join(chr(x) for x in last_part)
                    except Exception:
                        pass
                return str(last_part)
    except Exception as e:
        print(f"[WARNING] Could not read GGUF metadata from {gguf_path}: {e}")
    return None

def check_adapter_base_model_matches(adapter_dir: str, base_model: str) -> bool:
    config_path = os.path.join(adapter_dir, "adapter_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            existing_base = cfg.get("model") or cfg.get("base_model_name_or_path")
            if existing_base:
                return base_models_match(base_model, existing_base)
        except Exception:
            pass
    return True

def run_mlx_path(args, role: str):
    print("\n" + "="*60)
    print("  Iris AI — MLX Training Path (Apple Silicon)")
    print("="*60)

    data_dir = "mlx_data"
    pairs = load_all_data(role, args.max_pairs)
    if not pairs:
        print("[ERROR] No training data found.")
        return False
    export_to_jsonl(pairs, data_dir)

    train_cmd = [
        "python3", "-m", "mlx_lm.lora",
        "--train",
        "--model", args.model,
        "--data", data_dir,
        "--iters", str(args.iters),
        "--batch-size", str(args.batch_size),
        "--learning-rate", str(args.lr),
        "--adapter-path", args.output_dir,
        "--num-layers", str(args.num_layers),
        "--max-seq-length", str(args.max_seq_length),
        "--grad-checkpoint"
    ]

    should_resume = getattr(args, "resume", False)
    if should_resume and os.path.exists(args.output_dir):
        if not check_adapter_base_model_matches(args.output_dir, args.model):
            print(f"[INFO] Existing adapter in {args.output_dir} has a different base model. Starting training from scratch.")
            should_resume = False

    if should_resume and os.path.exists(args.output_dir):
        resume_file = None
        for fname in ["adapters.safetensors", "adapters.npz"]:
            fpath = os.path.join(args.output_dir, fname)
            if os.path.exists(fpath):
                resume_file = fpath
                break
        if resume_file:
            print(f"[INFO] Resuming MLX training from adapter file: {resume_file}")
            train_cmd += ["--resume-adapter-file", resume_file]

    print(f"\n[1/3] Starting MLX Training...")
    try:
        subprocess.run(train_cmd, check=True)
    except Exception as e:
        print(f"[ERROR] MLX Training failed: {e}")
        return False
    return True

def run_torch_path(args, device_type: str, role: str):
    print("\n" + "="*60)
    print(f"  Iris AI — Torch Training Path ({device_type.upper()})")
    print("="*60)

    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, Trainer, TrainingArguments, DataCollatorForSeq2Seq
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, TaskType

    device = torch.device(device_type)
    pairs = load_all_data(role, args.max_pairs)
    if not pairs:
        print("[ERROR] No training data found.")
        return False

    print(f"[INFO] Loading {args.model}...")
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    class ChatDataset(torch.utils.data.Dataset):
        def __init__(self, data_pairs, tokenizer, max_length):
            self.examples = []
            for u, b in data_pairs:
                sys_msg = {"role": "system", "content": SYSTEM_PROMPT}
                user_msg = {"role": "user", "content": u}
                ast_msg = {"role": "assistant", "content": b}
                
                prompt_text = tokenizer.apply_chat_template([sys_msg, user_msg], tokenize=False, add_generation_prompt=True)
                prompt_ids = tokenizer(prompt_text, truncation=True, max_length=max_length)["input_ids"]
                prompt_len = len(prompt_ids)
                
                full_text = tokenizer.apply_chat_template([sys_msg, user_msg, ast_msg], tokenize=False)
                encodings = tokenizer(full_text, truncation=True, max_length=max_length)
                input_ids = encodings["input_ids"]
                
                labels = list(input_ids)
                mask_len = min(prompt_len, len(labels))
                labels[:mask_len] = [-100] * mask_len
                
                self.examples.append({
                    "input_ids": input_ids,
                    "attention_mask": encodings["attention_mask"],
                    "labels": labels
                })

        def __len__(self):
            return len(self.examples)

        def __getitem__(self, i):
            return self.examples[i]

    random.shuffle(pairs)
    split_idx = int(len(pairs) * 0.95)
    train_pairs = pairs[:split_idx]
    eval_pairs = pairs[split_idx:]

    print("[INFO] Processing datasets (masking user prompts)...")
    train_dataset = ChatDataset(train_pairs, tokenizer, args.max_seq_length)
    eval_dataset = ChatDataset(eval_pairs, tokenizer, args.max_seq_length)

    if device_type == "cuda":
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True, 
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16
        )
        model = AutoModelForCausalLM.from_pretrained(args.model, quantization_config=bnb_config, device_map="auto")
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
        lora_r = 16
    else:
        model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=torch.bfloat16).to(device)
        lora_r = 8

    config = LoraConfig(r=lora_r, lora_alpha=lora_r*2, target_modules="all-linear", task_type=TaskType.CAUSAL_LM)
    model = get_peft_model(model, config)

    data_collator = DataCollatorForSeq2Seq(tokenizer, model=model, padding=True)

    bf16_supported = torch.cuda.is_available() and torch.cuda.is_bf16_supported()

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.accum_steps,
        num_train_epochs=args.epochs,
        logging_steps=10,
        learning_rate=args.lr,
        optim="paged_adamw_8bit" if device_type == "cuda" else "adamw_torch",
        bf16=bf16_supported,
        fp16=(device_type == "cuda" and not bf16_supported),
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={'use_reentrant': False},
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        eval_strategy="steps" if len(eval_dataset) > 0 else "no",
        eval_steps=100,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=3,
        report_to="none",
        remove_unused_columns=False
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset if len(eval_dataset) > 0 else None,
        data_collator=data_collator,
    )

    print("\n[INFO] Starting HF Trainer...")
    resume_checkpoint = False
    should_resume = getattr(args, "resume", False)
    if should_resume and os.path.exists(args.output_dir):
        if not check_adapter_base_model_matches(args.output_dir, args.model):
            print(f"[INFO] Existing adapter in {args.output_dir} has a different base model. Starting training from scratch.")
            should_resume = False

    if should_resume and os.path.exists(args.output_dir):
        import glob
        checkpoints = glob.glob(os.path.join(args.output_dir, "checkpoint-*"))
        if checkpoints:
            resume_checkpoint = True

    try:
        if resume_checkpoint:
            print(f"[INFO] Resuming Torch training from checkpoint in {args.output_dir}")
            trainer.train(resume_from_checkpoint=True)
        else:
            trainer.train()
        trainer.save_model(args.output_dir)
        if hasattr(model, "save_pretrained"):
            model.save_pretrained(args.output_dir)
        print(f"\n[OK] Training complete. Adapters saved to {args.output_dir}")
        return True
    except Exception as e:
        print(f"[ERROR] Torch Training failed: {e}")
        return False

def merge_and_save(base_model_id: str, adapter_dir: str, out_dir: str):
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel
    print(f"[GGUF] Loading base model {base_model_id} for merging...")
    tokenizer = AutoTokenizer.from_pretrained(base_model_id)
    model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        torch_dtype=torch.float16,
        device_map="cpu"
    )
    print(f"[GGUF] Loading PEFT adapter from {adapter_dir}...")
    model = PeftModel.from_pretrained(model, adapter_dir)
    print("[GGUF] Merging weights...")
    model = model.merge_and_unload()
    print(f"[GGUF] Saving merged model to {out_dir}...")
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)


def convert_to_gguf(hf_adapter_dir: str, role: str, base_model_id: str, is_mlx: bool, quant_type: str = "q4_k_m") -> str:
    convert_script = None
    for candidate in [
        "./scripts/convert_hf_to_gguf.py",
        "llama.cpp/convert_hf_to_gguf.py",
        "llama.cpp/tools/convert_hf_to_gguf.py",
    ]:
        if os.path.exists(candidate):
            convert_script = candidate
            break
    if convert_script is None:
        print("[GGUF] GGUF converter script not found — run: bash setup.sh")
        return ""

    temp_dir = tempfile.mkdtemp()
    try:
        print(f"[GGUF] Merging model for role '{role}'...")
        if is_mlx:
            fuse_cmd = [
                "python3", "-m", "mlx_lm.fuse",
                "--model", base_model_id,
                "--adapter-path", hf_adapter_dir,
                "--save-path", temp_dir
            ]
            subprocess.run(fuse_cmd, check=True)
        else:
            merge_and_save(base_model_id, hf_adapter_dir, temp_dir)

        os.makedirs("./models", exist_ok=True)
        f16_gguf = f"./models/iris_{ROLE_NUMBERS.get(role, role)}_f16.gguf"
        print(f"[GGUF] Converting merged model to F16 GGUF...")
        convert_cmd = [
            "python3", convert_script, temp_dir,
            "--outtype", "f16",
            "--outfile", f16_gguf
        ]
        subprocess.run(convert_cmd, check=True)

        quant_type_upper = quant_type.upper()
        final_gguf = f"./models/iris_{ROLE_NUMBERS.get(role, role)}.gguf"

        if quant_type_upper == "F16":
            os.rename(f16_gguf, final_gguf)
            print(f"[GGUF] ✓ Saved: {final_gguf}")
            return final_gguf

        quantize_tool = "llama-quantize"
        found_quantize = False
        for path in [
            "llama-quantize",
            "quantize",
            "./scripts/llama-quantize",
            "./llama.cpp/build/bin/llama-quantize",
            "./llama.cpp/build/llama-quantize",
            "./llama.cpp/llama-quantize",
        ]:
            resolved = shutil.which(path) if "/" not in path else (path if os.path.exists(path) else None)
            if resolved:
                quantize_tool = resolved
                found_quantize = True
                break

        if not found_quantize:
            print("[GGUF] llama-quantize not found. Run 'brew install llama.cpp' to enable quantization. Skipping quantization.")
            os.rename(f16_gguf, final_gguf)
            print(f"[GGUF] ✓ Saved (F16 fallback): {final_gguf}")
            return final_gguf

        print(f"[GGUF] Quantizing to {quant_type_upper}...")
        quant_cmd = [
            quantize_tool,
            f16_gguf,
            final_gguf,
            quant_type_upper
        ]
        subprocess.run(quant_cmd, check=True)

        try:
            os.unlink(f16_gguf)
        except OSError:
            pass

        print(f"[GGUF] ✓ Saved: {final_gguf}")
        return final_gguf
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def resolve_roles(train_role: List[str]) -> List[str]:
    if "all" in train_role:
        return list(ROLE_MODEL_MAP.keys())
    
    resolved = []
    for r in train_role:
        if r in ROLE_MODEL_MAP:
            resolved.append(r)
    return resolved

def ensure_training_subdirs():
    subdirs = {
        "training/coding": "Place coding tutorials, code examples, debugging guides, and programming Q&A here.",
        "training/reasoning": "Place logic puzzles, system design documents, architecture discussions, and analytical essays here.",
        "training/math": "Place math textbook excerpts, worked problems, equation explanations, and proofs here.",
        "training/general": "Place general knowledge documents, conversational examples, and factual reference material here.",
        "training/control": "Place tool-use examples, JSON action schemas, and agent instruction documents here.",
        "training/shared": "Documents here are included in training for all roles."
    }
    for directory, readme_text in subdirs.items():
        os.makedirs(directory, exist_ok=True)
        readme_file = os.path.join(directory, "README.md")
        if not os.path.exists(readme_file):
            with open(readme_file, "w", encoding="utf-8") as f:
                f.write(readme_text + "\n")

def main():
    args = parse_args()

    # Apply size-tier config (overrides ROLE_MODEL_MAP + ROLE_TO_GGUF)
    apply_size_config(args.size)

    roles_to_train = resolve_roles(args.role)
    if not roles_to_train:
        print(f"[ERROR] No valid training roles resolved from: {args.role}")
        sys.exit(1)

    if getattr(args, "download_only", False):
        download_all_models(roles_to_train)
        print("[Pre-Training] Models downloaded successfully. Exiting due to --download-only.")
        sys.exit(0)

    has_downloaded = False
    if getattr(args, "download_models", False):
        download_all_models(roles_to_train)
        has_downloaded = True
        print("[Pre-Training] Model downloading check complete. Continuing automatically...")

    ensure_training_subdirs()

    if args.device:
        target = args.device
    elif platform.system() == "Darwin" and platform.machine() == "arm64":
        target = "mps"
    elif torch.cuda.is_available():
        target = "cuda"
    else:
        target = "cpu"

    print(f"[INFO] Target training device: {target.upper()}")
    print(f"[INFO] Roles to train: {roles_to_train}")

    if not has_downloaded:
        download_all_models(roles_to_train)

    model_override = getattr(args, "_model_override", None)
    if model_override is None:
        model_override = args.model
        args._model_override = model_override

    for role in roles_to_train:
        print(f"\n{'='*60}\n  Training: {role.upper()} — {ROLE_MODEL_MAP[role]}\n{'='*60}\n")
        
        base_model = model_override if model_override else ROLE_MODEL_MAP[role]
        
        args.model = base_model
        args.output_dir = f"./iris_adapters/{role}"
        args.md_dir = ROLE_TRAINING_DIRS[role]

        final_gguf = f"./models/iris_{ROLE_NUMBERS.get(role, role)}.gguf"
        
        has_finished_adapter = False
        if os.path.exists(args.output_dir):
            has_mlx = os.path.exists(os.path.join(args.output_dir, "adapters.safetensors")) or os.path.exists(os.path.join(args.output_dir, "adapters.npz"))
            has_torch = os.path.exists(os.path.join(args.output_dir, "adapter_config.json")) and (
                os.path.exists(os.path.join(args.output_dir, "adapter_model.safetensors")) or 
                os.path.exists(os.path.join(args.output_dir, "adapter_model.bin"))
            )
            if has_mlx or has_torch:
                has_finished_adapter = True

        adapter_matches = True
        if has_finished_adapter:
            adapter_matches = check_adapter_base_model_matches(args.output_dir, base_model)
            
        gguf_matches = True
        if os.path.exists(final_gguf) and not args.skip_gguf:
            gguf_base = get_gguf_base_model(final_gguf)
            if gguf_base:
                gguf_matches = base_models_match(base_model, gguf_base)

        skip_training = False
        if args.resume:
            if (has_finished_adapter and adapter_matches) or (not args.skip_gguf and os.path.exists(final_gguf) and gguf_matches):
                skip_training = True
                print(f"[INFO] Existing model/adapter matches base model '{base_model}' for role '{role}'. Skipping training.")
            else:
                if has_finished_adapter and not adapter_matches:
                    print(f"[INFO] Existing adapter in {args.output_dir} has a different base model. Will train from scratch.")
                if os.path.exists(final_gguf) and not gguf_matches:
                    print(f"[INFO] Existing GGUF model {final_gguf} has a different base model. Will train/convert from scratch.")

        training_success = True
        if not skip_training:
            if target == "mps":
                training_success = run_mlx_path(args, role)
            else:
                training_success = run_torch_path(args, target, role)

        if not training_success:
            print(f"[ERROR] Training failed or was aborted for role '{role}'. Skipping GGUF conversion.")
        elif not args.skip_gguf:
            if not args.resume or not os.path.exists(final_gguf) or not gguf_matches:
                convert_to_gguf(
                    hf_adapter_dir=args.output_dir,
                    role=role,
                    base_model_id=base_model,
                    is_mlx=(target == "mps"),
                    quant_type=args.quant_type
                )
            else:
                print(f"[INFO] GGUF model {final_gguf} already exists and matches base model. Skipping GGUF conversion.")


def download_all_models(roles_to_train: List[str] = None):
    """Download all required GGUF models from Hugging Face before training.

    Downloads the source-named files, then renames to iris_NNN.gguf.
    If a size config is active, uses its download_urls and source_filenames.
    """
    import urllib.request
    import time

    os.makedirs("./models", exist_ok=True)

    # Build download map: target_name → (url, source_filename)
    download_map = {}

    if SIZE_CONFIG and "download_urls" in SIZE_CONFIG and "source_filenames" in SIZE_CONFIG:
        source_map = SIZE_CONFIG["source_filenames"]  # role → source filename
        url_map = SIZE_CONFIG["download_urls"]         # source_filename → url
        target_map = SIZE_CONFIG["gguf"]               # role → target filename
        import re
        
        target_roles = roles_to_train if roles_to_train else list(target_map.keys())
        
        for role in target_roles:
            if role not in target_map:
                continue
            target_name = target_map.get(role)
            src_name = source_map.get(role)
            url = url_map.get(src_name) if src_name else None
            if url and src_name:
                shard_match = re.search(r'-(\d+)-of-(\d+)\.gguf$', src_name)
                if shard_match:
                    num_shards = int(shard_match.group(2))
                    base_src = src_name[:shard_match.start()]
                    target_pattern_idx = target_name.find(shard_match.group(0))
                    if target_pattern_idx != -1:
                        base_target = target_name[:target_pattern_idx]
                    else:
                        base_target = target_name.replace(".gguf", "")
                    base_url = url[:url.find(src_name)]
                    for i in range(1, num_shards + 1):
                        s_name = f"{base_src}-{i:05d}-of-{num_shards:05d}.gguf"
                        t_name = f"{base_target}-{i:05d}-of-{num_shards:05d}.gguf"
                        u = f"{base_url}{s_name}"
                        download_map[t_name] = (u, s_name)
                else:
                    download_map[target_name] = (url, src_name)
        # Also handle clip
        if not roles_to_train or "vision" in roles_to_train:
            clip_src = SIZE_CONFIG.get("clip")
            if clip_src and clip_src in url_map:
                download_map[clip_src] = (url_map[clip_src], clip_src)
    else:
        # Fallback — hardcoded medium tier
        fallback = {
            "iris_001.gguf": ("https://huggingface.co/unsloth/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf", "Qwen3-4B-Q4_K_M.gguf"),
            "iris_002.gguf": ("https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf", "qwen2.5-coder-7b-instruct-q4_k_m.gguf"),
            "iris_003.gguf": ("https://huggingface.co/Qwen/Qwen2.5-Math-7B-Instruct-GGUF/resolve/main/qwen2.5-math-7b-instruct-q4_k_m.gguf", "qwen2.5-math-7b-instruct-q4_k_m.gguf"),
            "iris_004.gguf": ("https://huggingface.co/unsloth/Qwen3-Coder-14B-GGUF/resolve/main/Qwen3-Coder-14B-Q4_K_M.gguf", "Qwen3-Coder-14B-Q4_K_M.gguf"),
            "iris_005.gguf": ("https://huggingface.co/unsloth/DeepSeek-R1-Distill-Qwen-14B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf", "DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf"),
            "iris_006.gguf": ("https://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF/resolve/main/Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf", "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"),
            "iris_007.gguf": ("https://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF/resolve/main/mmproj-F16.gguf", "mmproj-F16.gguf"),
        }
        if roles_to_train:
            needed_ggufs = set()
            for r in roles_to_train:
                if r in ("triage", "router", "general"):
                    needed_ggufs.add("iris_001.gguf")
                elif r == "control":
                    needed_ggufs.add("iris_002.gguf")
                elif r == "math":
                    needed_ggufs.add("iris_003.gguf")
                elif r == "code":
                    needed_ggufs.add("iris_004.gguf")
                elif r == "reasoning":
                    needed_ggufs.add("iris_005.gguf")
                elif r == "vision":
                    needed_ggufs.add("iris_006.gguf")
                    needed_ggufs.add("iris_007.gguf")
            download_map = {k: v for k, v in fallback.items() if k in needed_ggufs}
        else:
            download_map = fallback

    print("\n" + "="*60)
    print("[Pre-Training] Checking all required GGUF models...")
    print("="*60)

    missing = {}
    for target_name, (url, src_name) in download_map.items():
        dest_path = os.path.join("./models", target_name)
        if not os.path.exists(dest_path) or os.path.getsize(dest_path) < 1024:
            missing[target_name] = (url, src_name)

    if not missing:
        print("[Pre-Training] All GGUF models already present. Nothing to download.\n")
        return

    print(f"[Pre-Training] {len(missing)} model(s) missing. Starting downloads...\n")
    for target_name, (url, src_name) in missing.items():
        temp_path = os.path.join("./models", f"_dl_{src_name}")
        dest_path = os.path.join("./models", target_name)
        print(f"[Download] {target_name}")
        print(f"  ← {src_name}")
        print(f"  URL: {url}")
        start_time = time.time()
        try:
            def progress_hook(count, block_size, total_size):
                duration = time.time() - start_time
                progress_size = int(count * block_size)
                speed = int(progress_size / (1024 * 1024 * max(duration, 0.001)))
                percent = int(count * block_size * 100 / total_size) if total_size > 0 else 0
                sys.stdout.write(
                    f"\r  ... {percent}% | {progress_size / (1024*1024):.1f} MB "
                    f"| {speed} MB/s | {duration:.1f}s"
                )
                sys.stdout.flush()

            urllib.request.urlretrieve(url, temp_path, progress_hook)
            elapsed = time.time() - start_time
            size_mb = os.path.getsize(temp_path) / (1024 * 1024)
            # Rename downloaded file to target name
            if os.path.exists(dest_path):
                os.remove(dest_path)
            os.rename(temp_path, dest_path)
            print(f"\n  Done → {target_name}: {size_mb:.0f} MB in {elapsed:.0f}s\n")
        except Exception as e:
            print(f"\n  Failed: {e}\n")
            print(f"  Please download manually to {dest_path}")

    print("[Pre-Training] Model download phase complete. All models → iris_NNN.gguf")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
