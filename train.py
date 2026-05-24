"""
train.py — Unified Training Suite for Iris AI
=============================================
Automatically detects hardware and selects the best training path:
- Apple Silicon (MPS) → MLX (LoRA + Optional Fusion)
- NVIDIA GPU (CUDA)  → Torch (QLoRA 4-bit + Trainer)
- CPU                → Torch (LoRA FP32)
"""

import os
import sys
import json
import torch
import random
import argparse
import subprocess
import platform
from typing import List, Tuple

from iris import (
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

def parse_args():
    parser = argparse.ArgumentParser(description="Unified Training for Iris AI")

    parser.add_argument("--model", default="mlx-community/phi-4-4bit",
                        help="Base model ID (e.g. mlx-community/phi-4-4bit or google/gemma-2-2b-it)")
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
    parser.add_argument("--md-dir", default="training")
    parser.add_argument("--claude-reasoning", type=int, default=600)
    parser.add_argument("--dolci-think", type=int, default=600)
    parser.add_argument("--deepthink", type=int, default=600)
    parser.add_argument("--strip-reasoning", action="store_true")

    parser.add_argument("--openhermes", type=int, default=0,
                        help="Number of OpenHermes-2.5 instruction pairs (0 = skip)")
    parser.add_argument("--math-qa", type=int, default=0,
                        help="Number of MATH competition problems (0 = skip)")
    parser.add_argument("--code-feedback", type=int, default=0,
                        help="Number of CodeFeedback coding pairs (0 = skip)")

    parser.add_argument("--fuse", action="store_true", help="Fuse model after training (MLX only)")
    parser.add_argument("--cleanup", action="store_true", help="Clean adapters after fusion (MLX only)")
    parser.add_argument("--num-layers", type=int, default=16, help="Layers to tune (MLX only)")

    parser.add_argument("--output-dir", default="./iris_lora_unified")

    return parser.parse_args()

def load_all_data(args) -> List[Tuple[str, str]]:
    pairs = []
    if not args.no_bst:
        pairs += load_blended_skill_talk(subset_size=args.max_pairs)
    if not args.no_dd:
        pairs += load_daily_dialog(subset_size=args.max_pairs)
    if not args.no_md:
        pairs += load_markdown_files(md_dir=args.md_dir)

    print("[DATA] Loading MBZUAI Egyptian Mixture & Maliki datasets...")
    pairs += load_mbzuai_egyptian_mixture(subset_size=args.max_pairs)
    pairs += load_hf_maliki_dataset(subset_size=args.max_pairs)

    if args.claude_reasoning:
        pairs += load_claude_reasoning_dataset(subset_size=args.claude_reasoning, keep_reasoning=not args.strip_reasoning)
    if args.dolci_think:
        pairs += load_dolci_think_dataset(subset_size=args.dolci_think)
    if args.deepthink:
        pairs += load_deepthink_dataset(subset_size=args.deepthink, keep_reasoning=not args.strip_reasoning)
    if getattr(args, 'openhermes', 0):
        print(f"[DATA] Loading OpenHermes-2.5 ({args.openhermes} pairs)...")
        pairs += load_openhermes_reasoning(subset_size=args.openhermes)
    if getattr(args, 'math_qa', 0):
        print(f"[DATA] Loading MATH competition dataset ({args.math_qa} pairs)...")
        pairs += load_math_qa(subset_size=args.math_qa)
    if getattr(args, 'code_feedback', 0):
        print(f"[DATA] Loading CodeFeedback dataset ({args.code_feedback} pairs)...")
        pairs += load_code_feedback(subset_size=args.code_feedback)

    random.shuffle(pairs)
    if len(pairs) > args.max_pairs:
        pairs = pairs[:args.max_pairs]

    print(f"[DATA] Loaded {len(pairs)} pairs total.")
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

def run_mlx_path(args):
    print("\n" + "="*60)
    print("  Iris AI — MLX Training Path (Apple Silicon)")
    print("="*60)

    data_dir = "mlx_data"
    pairs = load_all_data(args)
    if not pairs:
        print("[ERROR] No training data found.")
        return
    export_to_jsonl(pairs, data_dir)

    adapter_path = "adapters"
    train_cmd = [
        "python3", "-m", "mlx_lm.lora",
        "--train",
        "--model", args.model,
        "--data", data_dir,
        "--iters", str(args.iters),
        "--batch-size", str(args.batch_size),
        "--learning-rate", str(args.lr),
        "--adapter-path", adapter_path,
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

    if args.fuse:
        save_path = "iris_14b_model"
        print(f"\n[2/3] Fusing model into {save_path}...")
        fuse_cmd = [
            "python3", "-m", "mlx_lm.fuse",
            "--model", args.model,
            "--adapter-path", adapter_path,
            "--save-path", save_path
        ]
        try:
            subprocess.run(fuse_cmd, check=True)
            print(f"[OK] Fused model saved to {save_path}")

            if args.cleanup:
                print(f"\n[3/3] Cleaning up adapters...")
                import shutil
                if os.path.exists(adapter_path):
                    shutil.rmtree(adapter_path)
                print("[OK] Adapters removed.")
        except Exception as e:
            print(f"[ERROR] Fusion failed: {e}")

def run_torch_path(args, device_type: str):
    print("\n" + "="*60)
    print(f"  Iris AI — Torch Training Path ({device_type.upper()})")
    print("="*60)

    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, Trainer, TrainingArguments, DataCollatorForSeq2Seq
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, TaskType

    device = torch.device(device_type)
    pairs = load_all_data(args)
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

    # Split dataset into 95% train and 5% eval
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

    # Dynamic padding collator
    data_collator = DataCollatorForSeq2Seq(tokenizer, model=model, padding=True)

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.accum_steps,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        optim="paged_adamw_8bit",
        fp16=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={'use_reentrant': False},
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        logging_steps=10,
        eval_strategy="steps" if len(eval_dataset) > 0 else "no",
        eval_steps=100,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=3,
        report_to="auto",
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

def main():
    args = parse_args()

    if args.device:
        target = args.device
    elif platform.system() == "Darwin" and platform.machine() == "arm64":
        target = "mps"
    elif torch.cuda.is_available():
        target = "cuda"
    else:
        target = "cpu"

    if target == "mps":
        args.model = "mlx-community/phi-4-4bit"
        run_mlx_path(args)
    else:
        args.model = "microsoft/phi-4"
        run_torch_path(args, target)

if __name__ == "__main__":
    main()
