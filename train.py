import argparse
import glob
import os

import torch
from torch.utils.data import DataLoader
from transformers import AutoModelForCausalLM, AutoTokenizer, get_linear_schedule_with_warmup

from iris import (
    USER_TOKEN,
    BOT_TOKEN,
    SFTDataset,
    chat,
    cleanup_epoch_checkpoints,
    collate_fn,
    evaluate,
    generate_reply,
    get_device,
    is_degenerate,
    prepare_conversations,
    train_one_epoch,
)


def main():
    parser = argparse.ArgumentParser(description="Train Iris AI model")

    parser.add_argument("--model-name", type=str, default="microsoft/DialoGPT-medium", help="Base model name")
    parser.add_argument("--checkpoint", type=str, default="gpt2_sft_chatbot_best.pt", help="Best checkpoint path")
    parser.add_argument("--resume", action="store_true", help="Continue training from best checkpoint")

    # Dataset control
    parser.add_argument("--bst-size", type=int, default=10000, help="Max pairs from Blended Skill Talk (default 10k)")
    parser.add_argument("--dd-size", type=int, default=30000, help="Max pairs from DailyDialog (default 30k)")
    parser.add_argument("--md-dir", type=str, default="training", help="Directory containing *.md training files")
    parser.add_argument("--no-bst", action="store_true", help="Disable BST dataset")
    parser.add_argument("--no-dd", action="store_true", help="Disable DailyDialog dataset")
    parser.add_argument("--no-md", action="store_true", help="Disable MD file training")

    # Training hyper-params
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--lr", type=float, default=3e-5, help="Learning rate (default 3e-5)")
    parser.add_argument("--max-length", type=int, default=128, help="Max token length per sample (default 128)")
    parser.add_argument("--batch-size", type=int, default=4, help="Per-device batch size (default 4)")
    parser.add_argument("--accum", type=int, default=4, help="Gradient accumulation steps (default 4)")
    parser.add_argument("--weight-decay", type=float, default=0.01, help="AdamW weight decay")
    parser.add_argument("--warmup-ratio", type=float, default=0.05, help="Warmup ratio of total steps")
    parser.add_argument("--sample-max-new-tokens", type=int, default=50, help="Generated sample length per epoch")
    parser.add_argument("--force-cpu", action="store_true")
    parser.add_argument(
        "--keep-best-only",
        action="store_true",
        help="Delete intermediate epoch checkpoints and keep only best model",
    )
    parser.add_argument("--chat-after-train", action="store_true", help="Launch interactive chat after training")

    args = parser.parse_args()

    device = get_device(force_cpu=args.force_cpu)
    print(f"Using device: {device}   |   FP32")

    checkpoint = args.checkpoint
    model_name = args.model_name

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        low_cpu_mem_usage=True,
        dtype=torch.float32,
    ).to(device)
    model.gradient_checkpointing_enable()

    pairs = prepare_conversations(
        bst_size=args.bst_size,
        dd_size=args.dd_size,
        md_dir=args.md_dir,
        use_bst=not args.no_bst,
        use_dd=not args.no_dd,
        use_md=not args.no_md,
    )
    if not pairs:
        print("ERROR: No training pairs loaded. Check your data sources.")
        return

    split = int(0.9 * len(pairs))
    train_pairs, val_pairs = pairs[:split], pairs[split:]

    train_ds = SFTDataset(train_pairs, tokenizer, max_length=args.max_length)
    val_ds = SFTDataset(val_pairs, tokenizer, max_length=args.max_length)

    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=lambda b: collate_fn(b, tokenizer),
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=args.batch_size,
        shuffle=False,
        collate_fn=lambda b: collate_fn(b, tokenizer),
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    total_steps = (len(train_loader) // args.accum) * args.epochs
    warmup_steps = max(1, int(total_steps * args.warmup_ratio))
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=warmup_steps,
        num_training_steps=total_steps,
    )

    if args.resume and os.path.exists(checkpoint):
        print(f"Resuming from '{checkpoint}'...")
        model.load_state_dict(torch.load(checkpoint, map_location=device))

    best_val_loss = float("inf")
    if args.keep_best_only:
        cleanup_epoch_checkpoints()

    for epoch in range(1, args.epochs + 1):
        print(f"\n--- Epoch {epoch}/{args.epochs} ---")
        train_loss = train_one_epoch(
            model, train_loader, optimizer, scheduler, device, args.accum, epoch=epoch
        )
        if torch.isnan(torch.tensor(train_loss)):
            print("Training diverged (NaN loss). Try lowering --lr.")
            break

        val_loss = evaluate(model, val_loader, device)
        print(f"Train: {train_loss:.4f} | Val: {val_loss:.4f} | LR: {scheduler.get_last_lr()[0]:.2e}")

        epoch_ckpt = f"iris_sft_epoch{epoch}.pt"
        torch.save(model.state_dict(), epoch_ckpt)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), checkpoint)
            print(f"  >> Best model saved ({checkpoint})")
            if args.keep_best_only:
                for old_ckpt in glob.glob("iris_sft_epoch*.pt"):
                    if old_ckpt != epoch_ckpt:
                        try:
                            os.remove(old_ckpt)
                        except OSError as e:
                            print(f"[CKPT] Could not delete '{old_ckpt}': {e}")
        elif args.keep_best_only:
            try:
                os.remove(epoch_ckpt)
            except OSError as e:
                print(f"[CKPT] Could not delete '{epoch_ckpt}': {e}")

        probe = f"{USER_TOKEN} Hello, how are you?\n{BOT_TOKEN} "
        reply = generate_reply(model, tokenizer, probe, device, max_new_tokens=args.sample_max_new_tokens)
        print(f"  [Sample]: {reply!r}")
        if is_degenerate(reply):
            print("  ⚠️  Output still looks noisy.")

    if args.chat_after_train:
        if os.path.exists(checkpoint):
            model.load_state_dict(torch.load(checkpoint, map_location=device))
            print("\nLoaded best checkpoint for chatting.")
        chat(model, tokenizer, device)


if __name__ == "__main__":
    main()
