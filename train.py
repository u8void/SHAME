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
import torch
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
)

SYSTEM_PROMPT = "You are Iris, an intelligent and helpful AI assistant trained to assist the user with their tasks."

ROLE_MODEL_MAP = {
    "triage":    "Qwen/Qwen2.5-3B-Instruct",
    "router":    "Qwen/Qwen2.5-Coder-7B-Instruct",
    "math":      "Qwen/Qwen2.5-Math-7B-Instruct",
    "code":      "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "reasoning": "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
    "general":   "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
}

ROLE_TRAINING_DIRS = {
    "triage":    ["training/general",   "training/shared"],
    "router":    ["training/control",   "training/shared"],
    "math":      ["training/math",      "training/shared"],
    "code":      ["training/coding",    "training/shared"],
    "reasoning": ["training/reasoning", "training/shared"],
    "general":   ["training/general",   "training/shared"],
}

def parse_args():
    parser = argparse.ArgumentParser(description="Unified GGUF Training for Iris AI")

    parser.add_argument("--train-role", nargs="+", default=["all"],
                        help="Roles to train: triage, router, math, code, reasoning, general, all")
    parser.add_argument("--quant-type", choices=["q4_k_m", "q8_0", "f16"], default="q4_k_m",
                        help="GGUF quantization level")
    parser.add_argument("--skip-gguf", action="store_true", help="Skip merge and GGUF conversion")
    
    parser.add_argument("--model", default=None, help="Override base model ID")
    parser.add_argument("--iters", type=int, default=3000, help="Iterations (MLX) or max pairs (Torch)")
    parser.add_argument("--epochs", type=int, default=3, help="Epochs (Torch path only)")
    parser.add_argument("--lr", type=float, default=2e-5, help="Learning rate")
    parser.add_argument("--batch-size", type=int, default=1, help="Batch size")
    parser.add_argument("--accum-steps", type=int, default=8, help="Gradient accumulation steps")
    parser.add_argument("--max-seq-length", type=int, default=512, help="Maximum sequence length")
    parser.add_argument("--device", choices=["cuda", "mps", "cpu"], default=None)

    parser.add_argument("--max-pairs", type=int, default=5000)
    parser.add_argument("--no-bst", action="store_true")
    parser.add_argument("--no-dd", action="store_true")
    parser.add_argument("--no-md", action="store_true")
    parser.add_argument("--md-dir", default=None, help="Override Markdown training directory")
    
    parser.add_argument("--claude-reasoning", type=int, default=600)
    parser.add_argument("--dolci-think", type=int, default=600)
    parser.add_argument("--deepthink", type=int, default=600)
    parser.add_argument("--strip-reasoning", action="store_true")

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
        ds = load_dataset(path, split="train")
        pairs = []
        features = ds.features
        
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
                print(f"[WARNING] Could not determine columns for {path}. Available columns: {list(features.keys())}")
                
        if limit and len(pairs) > limit:
            random.shuffle(pairs)
            return pairs[:limit]
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
    
    # 1. Load HuggingFace datasets
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
            
    # 2. Load local markdown directories
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
        
    print(f"[DATA] Loaded {len(pairs)} pairs total for role '{role}'.")
    return pairs

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

def run_mlx_path(args, role: str):
    print("\n" + "="*60)
    print("  Iris AI — MLX Training Path (Apple Silicon)")
    print("="*60)

    data_dir = "mlx_data"
    pairs = load_all_data(role, args.max_pairs)
    if not pairs:
        print("[ERROR] No training data found.")
        return
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

    print(f"\n[1/3] Starting MLX Training...")
    try:
        subprocess.run(train_cmd, check=True)
    except Exception as e:
        print(f"[ERROR] MLX Training failed: {e}")
        return

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
        return

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
        model = AutoModelForCausalLM.from_pretrained(args.model).to(device)
        lora_r = 8

    config = LoraConfig(r=lora_r, lora_alpha=lora_r*2, target_modules="all-linear", task_type=TaskType.CAUSAL_LM)
    model = get_peft_model(model, config)

    data_collator = DataCollatorForSeq2Seq(tokenizer, model=model, padding=True)

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.accum_steps,
        num_train_epochs=args.epochs,
        logging_steps=10,
        learning_rate=args.lr,
        optim="paged_adamw_8bit" if device_type == "cuda" else "adamw_torch",
        fp16=(device_type == "cuda"),
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
    trainer.train()
    trainer.save_model(args.output_dir)
    print(f"\n[OK] Training complete. Adapters saved to {args.output_dir}")

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
    convert_script = "llama.cpp/convert_hf_to_gguf.py"
    if not os.path.exists(convert_script):
        print(f"[GGUF] llama.cpp not found — clone it: git clone https://github.com/ggerganov/llama.cpp")
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
        f16_gguf = f"./models/iris-{role}_f16.gguf"
        print(f"[GGUF] Converting merged model to F16 GGUF...")
        convert_cmd = [
            "python3", convert_script, temp_dir,
            "--outtype", "f16",
            "--outfile", f16_gguf
        ]
        subprocess.run(convert_cmd, check=True)

        quant_type_upper = quant_type.upper()
        final_gguf = f"./models/iris-{role}.gguf"

        if quant_type_upper == "F16":
            os.rename(f16_gguf, final_gguf)
            print(f"[GGUF] ✓ Saved: {final_gguf}")
            return final_gguf

        quantize_tool = "./llama.cpp/llama-quantize"
        found_quantize = False
        for path in ["./llama.cpp/llama-quantize", "./llama.cpp/build/bin/llama-quantize", "llama-quantize"]:
            if os.path.exists(path) or (shutil.which(path) if "/" not in path else False):
                quantize_tool = path
                found_quantize = True
                break

        if not found_quantize:
            print("[GGUF] llama-quantize not found. Please compile llama.cpp first (e.g. run 'make' in llama.cpp). Skipping quantization.")
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

    ensure_training_subdirs()

    if args.device:
        target = args.device
    elif platform.system() == "Darwin" and platform.machine() == "arm64":
        target = "mps"
    elif torch.cuda.is_available():
        target = "cuda"
    else:
        target = "cpu"

    roles_to_train = resolve_roles(args.train_role)
    if not roles_to_train:
        print(f"[ERROR] No valid training roles resolved from: {args.train_role}")
        sys.exit(1)

    print(f"[INFO] Target training device: {target.upper()}")
    print(f"[INFO] Roles to train: {roles_to_train}")

    for role in roles_to_train:
        print(f"\n{'='*60}\n  Training: {role.upper()} — {ROLE_MODEL_MAP[role]}\n{'='*60}\n")
        
        base_model = args.model if args.model else ROLE_MODEL_MAP[role]
        
        args.model = base_model
        args.output_dir = f"./iris_adapters/{role}"
        args.md_dir = ROLE_TRAINING_DIRS[role]

        if target == "mps":
            run_mlx_path(args, role)
        else:
            run_torch_path(args, target, role)

        if not args.skip_gguf:
            convert_to_gguf(
                hf_adapter_dir=args.output_dir,
                role=role,
                base_model_id=base_model,
                is_mlx=(target == "mps"),
                quant_type=args.quant_type
            )

    check_and_download_default_models()

def check_and_download_default_models():
    import urllib.request
    import time
    
    default_urls = {
        #"iris-triage.gguf":    "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q8_0.gguf",
        #"iris-router.gguf":    "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf",
        #"iris-math.gguf":      "https://huggingface.co/Qwen/Qwen2.5-Math-7B-Instruct-GGUF/resolve/main/qwen2.5-math-7b-instruct-q4_k_m.gguf",
        #"iris-code.gguf":      "https://huggingface.co/Bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",
        #"iris-reasoning.gguf": "https://huggingface.co/Bartowski/DeepSeek-R1-Distill-Qwen-14B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf",
        #"iris-general.gguf":   "https://huggingface.co/Bartowski/DeepSeek-R1-Distill-Qwen-14B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf",
        "iris-vision.gguf":    "https://huggingface.co/ggml-org/InternVL2_5-4B-GGUF/resolve/main/ggml-model-q4_k.gguf",
        "iris-clip.bin":       "https://huggingface.co/ggml-org/InternVL2_5-4B-GGUF/resolve/main/mmproj-model-f16.gguf"
    }

    os.makedirs("./models", exist_ok=True)
    
    for filename, url in default_urls.items():
        dest_path = os.path.join("./models", filename)
        if not os.path.exists(dest_path):
            print(f"\n[Auto-Download] Missing model file detected: {filename}")
            print(f"[Auto-Download] Starting download from Hugging Face...")
            start_time = time.time()
            try:
                def progress_hook(count, block_size, total_size):
                    duration = time.time() - start_time
                    progress_size = int(count * block_size)
                    speed = int(progress_size / (1024 * 1024 * max(duration, 0.001))) # MB/s
                    percent = int(count * block_size * 100 / total_size) if total_size > 0 else 0
                    sys.stdout.write(f"\r... {percent}% | {progress_size / (1024*1024):.1f} MB | {speed} MB/s | {duration:.1f}s")
                    sys.stdout.flush()
                
                urllib.request.urlretrieve(url, dest_path, progress_hook)
                print(f"\n[Auto-Download] Successfully saved: {dest_path} ({time.time() - start_time:.1f}s)")
            except Exception as e:
                print(f"\n[Auto-Download] Failed to download {filename}: {e}")

if __name__ == "__main__":
    main()
