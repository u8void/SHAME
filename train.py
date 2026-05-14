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
    load_deepthink_dataset
)

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

    if args.claude_reasoning:
        pairs += load_claude_reasoning_dataset(subset_size=args.claude_reasoning, keep_reasoning=not args.strip_reasoning)
    if args.dolci_think:
        pairs += load_dolci_think_dataset(subset_size=args.dolci_think)
    if args.deepthink:
        pairs += load_deepthink_dataset(subset_size=args.deepthink, keep_reasoning=not args.strip_reasoning)

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

    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
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

    texts = []
    for u, b in pairs:
        msgs = [{"role": "user", "content": u}, {"role": "assistant", "content": b}]
        texts.append(tokenizer.apply_chat_template(msgs, tokenize=False))

    encodings = tokenizer(texts, truncation=True, max_length=args.max_seq_length, padding="max_length", return_tensors="pt")
    input_ids = encodings["input_ids"]
    labels = input_ids.clone()
    labels[encodings["attention_mask"] == 0] = -100
    dataset = torch.utils.data.TensorDataset(input_ids, encodings["attention_mask"], labels)

    if device_type == "cuda":
        bnb_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16)
        model = AutoModelForCausalLM.from_pretrained(args.model, quantization_config=bnb_config, device_map="auto")
        model = prepare_model_for_kbit_training(model)
        lora_r = 32
    else:
        model = AutoModelForCausalLM.from_pretrained(args.model).to(device)
        lora_r = 8

    config = LoraConfig(r=lora_r, lora_alpha=lora_r*2, target_modules="all-linear", task_type=TaskType.CAUSAL_LM)
    model = get_peft_model(model, config)

    loader = torch.utils.data.DataLoader(dataset, batch_size=args.batch_size, shuffle=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)

    model.train()
    for epoch in range(args.epochs):
        print(f"Epoch {epoch+1}/{args.epochs}")
        for step, batch in enumerate(loader):
            ids, mask, lbls = [b.to(device) for b in batch]
            loss = model(input_ids=ids, attention_mask=mask, labels=lbls).loss
            loss.backward()
            if (step+1) % args.accum_steps == 0:
                optimizer.step()
                optimizer.zero_grad()
                print(f"  Step {step+1} | Loss: {loss.item():.4f}")

    model.save_pretrained(args.output_dir)
    print(f"[OK] Training complete. Adapters saved to {args.output_dir}")

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
        run_mlx_path(args)
    else:
        run_torch_path(args, target)

if __name__ == "__main__":
    main()
