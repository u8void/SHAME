import os
import torch
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)
from datasets import load_dataset

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

USER_TOKEN = "User:"
BOT_TOKEN  = "Bot:"
EOS_TOKEN  = "<|endoftext|>"

def get_device(force_cpu=False):
    if force_cpu:
        return torch.device("cpu")
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")

def is_degenerate(text):
    s = (text or "").strip()
    if not s:
        return True
    letters = sum(c.isalpha() for c in s)
    alnum   = sum(c.isalnum() for c in s)
    unique  = len(set(s))
    if letters < max(3, int(0.1 * len(s))):
        return True
    if alnum < max(5, int(0.2 * len(s))):
        return True
    if unique < 12 and len(s) > 24:
        return True
    return False

class SFTDataset(Dataset):
    def __init__(self, conversations, tokenizer, max_length=64):
        self.max_length = max_length
        self.samples = []
        texts = []
        prompt_lengths = []
        for user, bot in conversations:
            prompt = f"{USER_TOKEN} {user}\n{BOT_TOKEN} "
            full   = prompt + bot + EOS_TOKEN
            texts.append(full)
            prompt_lengths.append(len(tokenizer.encode(prompt)))

        batch_enc = tokenizer(
            texts,
            truncation=True,
            max_length=max_length,
            padding=False,
            return_length=False,
        )
        iterator = enumerate(zip(batch_enc["input_ids"], prompt_lengths))
        if TQDM_AVAILABLE:
            iterator = tqdm(iterator, total=len(conversations), desc="Encoding")
        for _, (full_ids, orig_prompt_len) in iterator:
            prompt_len = min(orig_prompt_len, len(full_ids))
            loss_mask = [0] * prompt_len + [1] * (len(full_ids) - prompt_len)
            self.samples.append({
                "input_ids":  full_ids,
                "loss_mask":  loss_mask,
            })

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        return self.samples[idx]

def collate_fn(batch, tokenizer):
    pad_val = tokenizer.pad_token_id
    max_len = max(len(s["input_ids"]) for s in batch)
    input_ids, loss_mask = [], []
    for s in batch:
        ids = s["input_ids"]
        m   = s["loss_mask"]
        input_ids.append(ids + [pad_val] * (max_len - len(ids)))
        loss_mask.append(m   + [0]      * (max_len - len(m)))
    return {
        "input_ids":  torch.tensor(input_ids, dtype=torch.long),
        "loss_mask":  torch.tensor(loss_mask, dtype=torch.float),
    }

def prepare_conversations(subset_size=None):
    ds = load_dataset("blended_skill_talk", split="train")
    pairs = []
    for row in ds:
        user_utters = row["previous_utterance"]
        bot_utters  = row["free_messages"]

        for user_text, bot_text in zip(user_utters, bot_utters):
            user_text = user_text.strip()
            bot_text  = bot_text.strip()
            if user_text and bot_text:
                pairs.append((user_text, bot_text))

    total = len(pairs)
    if subset_size and subset_size < total:
        pairs = pairs[:subset_size]
    return pairs

def train_one_epoch(model, loader, optimizer, scheduler, device, accum_steps,
                    max_grad_norm=1.0, epoch=None):
    model.train()
    total_loss = 0.0
    total_toks = 0
    optimizer.zero_grad()

    bar = tqdm(loader, desc=f"Epoch {epoch}", leave=False) if TQDM_AVAILABLE else loader
    for step, batch in enumerate(bar):
        input_ids = batch["input_ids"].to(device)
        loss_mask = batch["loss_mask"].to(device)
        x = input_ids[:, :-1]
        y = input_ids[:, 1:]
        m = loss_mask[:, 1:]

        logits = model(x).logits
        loss_flat = F.cross_entropy(
            logits.reshape(-1, logits.size(-1)),
            y.reshape(-1),
            reduction="none",
            ignore_index=model.config.eos_token_id,
        )
        masked_loss = (loss_flat * m.reshape(-1)).sum()
        n_tokens    = m.sum().clamp(min=1)
        loss = masked_loss / n_tokens / accum_steps
        loss.backward()

        total_loss   += masked_loss.item()
        total_toks   += n_tokens.item()

        if (step + 1) % accum_steps == 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            if device.type == "mps":
                torch.mps.empty_cache()

    if (step + 1) % accum_steps != 0:
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
        optimizer.step()
        scheduler.step()
        optimizer.zero_grad()
        if device.type == "mps":
            torch.mps.empty_cache()

    return total_loss / max(total_toks, 1)

@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    total_loss = 0.0
    total_toks = 0
    for batch in loader:
        input_ids = batch["input_ids"].to(device)
        loss_mask = batch["loss_mask"].to(device)
        x = input_ids[:, :-1]
        y = input_ids[:, 1:]
        m = loss_mask[:, 1:]

        logits = model(x).logits
        loss_flat = F.cross_entropy(
            logits.reshape(-1, logits.size(-1)),
            y.reshape(-1),
            reduction="none",
            ignore_index=model.config.eos_token_id,
        )
        masked_loss = (loss_flat * m.reshape(-1)).sum()
        total_loss += masked_loss.item()
        total_toks += m.sum().item()
    return total_loss / max(total_toks, 1)

@torch.no_grad()
def generate_reply(model, tokenizer, prompt_text, device,
                   max_new_tokens=64, temperature=0.5, top_p=0.9, top_k=50,
                   repetition_penalty=1.4):
    model.eval()
    enc = tokenizer(prompt_text, return_tensors="pt")
    input_ids = enc["input_ids"].to(device)
    attention_mask = enc["attention_mask"].to(device)
    max_ctx = model.config.n_positions - max_new_tokens
    if input_ids.size(1) > max_ctx:
        input_ids = input_ids[:, -max_ctx:]
        attention_mask = attention_mask[:, -max_ctx:]

    output_ids = model.generate(
        input_ids=input_ids,
        attention_mask=attention_mask,
        max_new_tokens=max_new_tokens,
        do_sample=True,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        repetition_penalty=repetition_penalty,
        no_repeat_ngram_size=4,
        remove_invalid_values=True,
        renormalize_logits=True,
        eos_token_id=tokenizer.eos_token_id,
        pad_token_id=tokenizer.eos_token_id,
    )
    generated = output_ids[0, input_ids.size(1):]
    reply = tokenizer.decode(
        generated,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False
    ).strip()
    for stop in [f"\n{USER_TOKEN}", "\nYou:"]:
        if stop in reply:
            reply = reply.split(stop)[0].strip()
    return reply or "I'm not sure what to say."

def chat(model, tokenizer, device):
    history = ""
    while True:
        user = input("You: ").strip()
        if user.lower() in ("quit", "exit", "q"):
            break
        if not user:
            continue
        turn   = f"{USER_TOKEN} {user}\n{BOT_TOKEN} "
        prompt = history + turn
        reply  = generate_reply(model, tokenizer, prompt, device)
        print(f"Bot: {reply}\n")
        history += turn + reply + "\n"
        if len(tokenizer.encode(history)) > 800:
            lines = history.strip().split("\n")
            history = "\n".join(lines[2:]) + "\n" if len(lines) > 2 else ""

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--chat-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--subset", type=int, default=50000)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--force-cpu", action="store_true")
    parser.add_argument("--lr", type=float, default=5e-6)
    args = parser.parse_args()

    device = get_device(force_cpu=args.force_cpu)

    CHECKPOINT  = "gpt2_sft_chatbot_best.pt"
    MODEL_NAME  = "microsoft/DialoGPT-medium"
    MAX_LENGTH  = 64
    BATCH_SIZE  = 1
    ACCUM_STEPS = 8
    LR          = args.lr
    WARMUP_RATIO = 0.1

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        low_cpu_mem_usage=True,
        torch_dtype=torch.float32,
    )
    model = model.to(device)
    model.gradient_checkpointing_enable()

    if args.chat_only:
        if os.path.exists(CHECKPOINT):
            model.load_state_dict(torch.load(CHECKPOINT, map_location=device))
        chat(model, tokenizer, device)
        return

    pairs = prepare_conversations(subset_size=args.subset)
    split = int(0.9 * len(pairs))
    train_pairs, val_pairs = pairs[:split], pairs[split:]

    train_ds = SFTDataset(train_pairs, tokenizer, max_length=MAX_LENGTH)
    val_ds   = SFTDataset(val_pairs,   tokenizer, max_length=MAX_LENGTH)

    train_loader = DataLoader(
        train_ds, batch_size=BATCH_SIZE, shuffle=True,
        collate_fn=lambda b: collate_fn(b, tokenizer)
    )
    val_loader = DataLoader(
        val_ds, batch_size=BATCH_SIZE, shuffle=False,
        collate_fn=lambda b: collate_fn(b, tokenizer)
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    total_steps = (len(train_loader) // ACCUM_STEPS) * args.epochs
    warmup_steps = int(total_steps * WARMUP_RATIO)
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=warmup_steps,
        num_training_steps=total_steps,
    )

    start_epoch = 1
    if args.resume and os.path.exists(CHECKPOINT):
        model.load_state_dict(torch.load(CHECKPOINT, map_location=device))

    best_val_loss = float("inf")
    for epoch in range(start_epoch, args.epochs + 1):
        train_loss = train_one_epoch(
            model, train_loader, optimizer, scheduler, device, ACCUM_STEPS,
            epoch=epoch
        )
        if torch.isnan(torch.tensor(train_loss)):
            break

        val_loss = evaluate(model, val_loader, device)

        torch.save(model.state_dict(), f"gpt2_sft_epoch{epoch}.pt")
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), CHECKPOINT)

        probe = f"{USER_TOKEN} Hello\n{BOT_TOKEN} "
        reply = generate_reply(model, tokenizer, probe, device, max_new_tokens=32)
        if is_degenerate(reply):
            pass

    if os.path.exists(CHECKPOINT):
        model.load_state_dict(torch.load(CHECKPOINT, map_location=device))
    chat(model, tokenizer, device)

if __name__ == "__main__":
    main()