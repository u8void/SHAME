#!/usr/bin/env python3
import os, glob, argparse, torch
from torch.utils.data import DataLoader, TensorDataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
    BitsAndBytesConfig, 
    TrainingArguments, 
    Trainer,
    DataCollatorForLanguageModeling,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, TaskType
from datasets import Dataset, load_dataset                 
 
from iris import (
    load_blended_skill_talk,
    load_daily_dialog,
    load_markdown_files,
    load_mbzuai_egyptian_mixture,
    chat,
    load_hf_maliki_dataset,
    load_claude_reasoning_dataset,
    load_dolci_think_dataset
)
import random

def parse_args():
    parser = argparse.ArgumentParser(description="Train Iris AI on any device")
    parser.add_argument("--model-name", default="google/gemma-2-2b-it")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--max-pairs", type=int, default=5000,
                        help="Maximum training pairs to use")
    parser.add_argument("--bst-size", type=int, default=None,
                        help="Max BST pairs (overrides --max-pairs if set)")
    parser.add_argument("--dd-size", type=int, default=None,
                        help="Max DailyDialog pairs (unused if dataset broken)")
    parser.add_argument("--md-dir", default="training",
                        help="Folder with *.md training files")
    parser.add_argument("--no-bst", action="store_true")
    parser.add_argument("--no-dd", action="store_true")
    parser.add_argument("--no-md", action="store_true")
    parser.add_argument("--max-length", type=int, default=64,
                        help="Max token length (reduce for low VRAM/RAM)")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--accum-steps", type=int, default=8,
                        help="Gradient accumulation steps")
    parser.add_argument("--force-cpu", action="store_true",
                        help="Force CPU training even if GPU available")
    parser.add_argument("--device", choices=["cuda", "mps", "cpu"], default=None,
                        help="Manually select device")
    parser.add_argument("--output-dir", default="./iris_lora_unified")
    parser.add_argument("--chat-after-train", action="store_true")
    parser.add_argument("--keep-best-only", action="store_true")
    parser.add_argument("--use-mbzuai", action="store_true")
    parser.add_argument("--maliki-size", type=int, default=None,
                    help="Number of Maliki Fiqh pairs to include")
    parser.add_argument("--claude-reasoning", type=int, default=None,
                    help="Number of Claude reasoning pairs to include")
    parser.add_argument("--strip-reasoning", action="store_true",
                    help="Remove <think> blocks from Claude reasoning data")
    parser.add_argument("--dolci-think", type=int, default=None,
                    help="Number of Dolci-Think reasoning pairs to include")
    parser.add_argument("--deepthink", type=int, default=None,
                    help="Number of Deepthink Reasoning pairs to include")
    parser.add_argument("--openhermes", type=int, default=None,
                    help="Number of OpenHermes-2.5 pairs to include")
    parser.add_argument("--orca-math", type=int, default=None,
                    help="Number of Orca-Math reasoning pairs to include")
    return parser.parse_args()

def load_conversations(args):
    pairs = []

    if not args.no_bst:
        pairs += load_blended_skill_talk(
            subset_size=args.bst_size if args.bst_size else args.max_pairs
        )
    if not args.no_dd:
        pairs += load_daily_dialog(
            subset_size=args.dd_size if args.dd_size else None
        )
    if not args.no_md:
        pairs += load_markdown_files(md_dir=args.md_dir)
    if args.use_mbzuai:
        pairs += load_mbzuai_egyptian_mixture(subset_size=args.max_pairs)
    if args.maliki_size:
        pairs += load_hf_maliki_dataset(subset_size=args.maliki_size)
    if args.claude_reasoning:
        pairs += load_claude_reasoning_dataset(
            subset_size=args.claude_reasoning,
            keep_reasoning=not args.strip_reasoning,
        )
    if args.dolci_think:
        pairs += load_dolci_think_dataset(subset_size=args.dolci_think)
    if args.deepthink:
        from iris import load_deepthink_dataset
        pairs += load_deepthink_dataset(
            subset_size=args.deepthink,
            keep_reasoning=not args.strip_reasoning
        )
    if args.openhermes:
        from iris import load_openhermes_dataset
        pairs += load_openhermes_dataset(subset_size=args.openhermes)
    if args.orca_math:
        from iris import load_orcamath_dataset
        pairs += load_orcamath_dataset(subset_size=args.orca_math)

    
    random.shuffle(pairs)
    if len(pairs) > args.max_pairs:
        pairs = pairs[:args.max_pairs]
    print(f"Total training pairs: {len(pairs)}")
    return pairs

def get_device_and_mode(force_cpu=False, manual_device=None):
    if manual_device:
        device_str = manual_device
    elif force_cpu:
        device_str = "cpu"
    elif torch.cuda.is_available():
        device_str = "cuda"
    elif torch.backends.mps.is_available():
        device_str = "mps"
    else:
        device_str = "cpu"

    device = torch.device(device_str)
    if device_str == "cuda":
        print("CUDA detected → QLoRA (4‑bit) + HuggingFace Trainer")
        return device, "cuda_qlora"
    elif device_str == "mps":
        print("MPS detected → LoRA FP16 + manual loop (no autocast)")
        return device, "mps_fp16"
    else:
        print("CPU detected → LoRA FP32 + manual loop")
        return device, "cpu_fp32"

from transformers import default_data_collator

def train_cuda(model, tokenizer, dataset, args):
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.accum_steps,
        learning_rate=args.lr,
        fp16=True,
        logging_steps=10,
        save_strategy="epoch",
        save_total_limit=2,
        remove_unused_columns=False,
        report_to="none",
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        data_collator=default_data_collator,
    )
    trainer.train()


def train_manual(model, tokenizer, train_dataset, device, args, use_fp16=False):
    loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    total_steps = (len(loader) // args.accum_steps) * args.epochs
    warmup_steps = max(1, int(total_steps * 0.05))
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=warmup_steps,
        num_training_steps=total_steps,
    )

    model.train()
    for epoch in range(1, args.epochs + 1):
        print(f"\n--- Epoch {epoch}/{args.epochs} ---")
        total_loss = 0.0
        optimizer.zero_grad()
        for step, batch in enumerate(loader):
            input_ids, attention_mask, labels = [b.to(device) for b in batch]
            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=labels,
            )
            loss = outputs.loss / args.accum_steps
            loss.backward()
            total_loss += loss.item()

            if (step + 1) % args.accum_steps == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
                if device.type == "mps":
                    torch.mps.empty_cache()

            if (step + 1) % 50 == 0:
                print(f"  Step {step+1:5d}/{len(loader)} | loss = {loss.item() * args.accum_steps:.4f}")

        avg_loss = total_loss / max(1, step + 1) * args.accum_steps
        print(f"Epoch {epoch} avg loss: {avg_loss:.4f} | LR: {scheduler.get_last_lr()[0]:.2e}")

        epoch_dir = f"{args.output_dir}_epoch{epoch}"
        os.makedirs(epoch_dir, exist_ok=True)
        model.save_pretrained(epoch_dir)
        tokenizer.save_pretrained(epoch_dir)
        print(f"💾 Adapter saved to {epoch_dir}")

def main():
    args = parse_args()
    device, mode = get_device_and_mode(
        force_cpu=args.force_cpu,
        manual_device=args.device,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    tokenizer.padding_side = "right"
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    global EOS_TOKEN 
    EOS_TOKEN = tokenizer.eos_token

    pairs = load_conversations(args)

    def format_chat(user, bot):
        messages = [
            {"role": "user", "content": user},
            {"role": "assistant", "content": bot},
        ]
        return tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=False,
        )

    texts = [format_chat(u, b) for u, b in pairs]

    encodings = tokenizer(
        texts,
        truncation=True,
        max_length=args.max_length,
        padding="max_length",
        return_tensors="pt" if mode != "cuda_qlora" else None,
    )

    if mode == "cuda_qlora":
        dataset_dicts = []
        for i in range(len(encodings["input_ids"])):
            input_ids = encodings["input_ids"][i]
            attention_mask = encodings["attention_mask"][i]
            
            # Create labels and mask padding tokens based on attention_mask
            # This preserves the legitimate eos_token
            labels = list(input_ids)
            for j in range(len(labels)):
                if attention_mask[j] == 0:
                    labels[j] = -100
                    
            dataset_dicts.append({
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "labels": labels,
            })
        dataset = Dataset.from_list(dataset_dicts)
    else:
        labels = encodings["input_ids"].clone()
        labels[encodings["attention_mask"] == 0] = -100
        dataset = TensorDataset(
            encodings["input_ids"],
            encodings["attention_mask"],
            labels,  
        )

    if mode == "cuda_qlora":
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
        )
        model = AutoModelForCausalLM.from_pretrained(
            args.model_name,
            quantization_config=bnb_config,
            device_map="auto",
            low_cpu_mem_usage=True,
        )
        model = prepare_model_for_kbit_training(model)
        model.gradient_checkpointing_enable()
        lora_r = 32
        lora_alpha = 64
    elif mode == "mps_fp16":
        model = AutoModelForCausalLM.from_pretrained(
            args.model_name,
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True,
        ).to(device)
        model.gradient_checkpointing_enable()
        lora_r = 16
        lora_alpha = 32
    else:  
        torch.set_num_threads(4)
        model = AutoModelForCausalLM.from_pretrained(
            args.model_name,
            torch_dtype=torch.float32,
            low_cpu_mem_usage=True,
        ).to(device)
        model.gradient_checkpointing_enable()
        lora_r = 8
        lora_alpha = 16

    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        target_modules="all-linear",
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    if mode == "cuda_qlora":
        train_cuda(model, tokenizer, dataset, args)
    else:
        train_manual(model, tokenizer, dataset, device, args,
                     use_fp16=(mode == "mps_fp16"))

    os.makedirs(args.output_dir, exist_ok=True)
    model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    print(f"[INFO] Final adapter saved to {args.output_dir}")

    print("Merging adapter into full model …")
    
    # CRITICAL BUG FIX: Untie embeddings before merging for models with tied embeddings (like Gemma).
    # Because lm_head is tied to embed_tokens, merging the LoRA adapter directly into lm_head 
    # corrupts the input embeddings of the model, completely destroying the tokenizer mappings.
    base_model_to_merge = model.base_model.model
    if hasattr(base_model_to_merge, "lm_head") and hasattr(base_model_to_merge.model, "embed_tokens"):
        if base_model_to_merge.lm_head.weight is base_model_to_merge.model.embed_tokens.weight:
            print("[INFO] Untying lm_head from embed_tokens to prevent input embedding corruption...")
            base_model_to_merge.lm_head.weight = torch.nn.Parameter(base_model_to_merge.lm_head.weight.clone())
            
    merged_model = model.merge_and_unload()
    merged_model.save_pretrained("./iris_merged_model", safe_serialization=True)
    tokenizer.save_pretrained("./iris_merged_model")
    print("[SUCCESS] Merged model saved to ./iris_merged_model")

    if args.chat_after_train:
        
        chat_model = AutoModelForCausalLM.from_pretrained(
            "./iris_merged_model",
            torch_dtype=torch.float16 if device.type != "cpu" else torch.float32,
            low_cpu_mem_usage=True,
        ).to(device)
        chat(chat_model, tokenizer, device)


if __name__ == "__main__":
    main()