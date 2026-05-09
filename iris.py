import os
import re
import glob
import torch
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)
from datasets import load_dataset
import re


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
    if len(s) < 10:
        return True
    letters = sum(c.isalpha() for c in s)
    if letters < 0.5 * len(s):
        return True
    unique = len(set(s.lower()))
    if unique < 15 and len(s) > 20:
        return True
    return False


def load_blended_skill_talk(subset_size=None):
    try:
        ds = load_dataset("blended_skill_talk", split="train", trust_remote_code=True)
    except Exception as e:
        return []

    pairs = []
    for row in ds:
        utterances = row.get("previous_utterance", [])
        free_msgs  = row.get("free_messages", [])
        for i in range(0, len(utterances) - 1, 2):
            u = utterances[i].strip()
            b = utterances[i + 1].strip()
            if u and b:
                pairs.append((u, b))
        if utterances and free_msgs:
            last_user = utterances[-1].strip()
            for reply in free_msgs:
                reply = (reply or "").strip()
                if reply:
                    pairs.append((last_user, reply))
                    break
    total = len(pairs)
    if subset_size and subset_size < total:
        import random
        random.shuffle(pairs)
        pairs = pairs[:subset_size]
    return pairs

def load_daily_dialog(subset_size=None):
    try:
        ds = load_dataset("daily_dialog", split="train",
                          trust_remote_code=False, revision="main")
    except Exception:
        try:
            ds = load_dataset("daily_dialog", split="train",
                              trust_remote_code=True)
        except Exception as e:
            return []

    pairs = []
    for row in ds:
        dialog = row["dialog"]
        for i in range(len(dialog) - 1):
            u = dialog[i].strip()
            b = dialog[i + 1].strip()
            if u and b:
                pairs.append((u, b))
    total = len(pairs)
    if subset_size and subset_size < total:
        import random
        random.shuffle(pairs)
        pairs = pairs[:subset_size]
    return pairs

def load_markdown_files(md_dir="md", pattern="*.md"):
    pairs = []
    search_path = os.path.join(md_dir, pattern)
    files = glob.glob(search_path)
    if not files:
        return pairs
    user_re = re.compile(r"^(?:USER|User)\s*:\s*(.+)", re.IGNORECASE)
    bot_re  = re.compile(r"^(?:BOT|Bot)\s*:\s*(.+)",  re.IGNORECASE)
    for filepath in sorted(files):
        file_pairs = 0
        pending_user = None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if line.strip().startswith("#") or line.strip().startswith("<!--"):
                        continue
                    u_match = user_re.match(line.strip())
                    b_match = bot_re.match(line.strip())
                    if u_match:
                        pending_user = u_match.group(1).strip()
                    elif b_match and pending_user:
                        bot_text = b_match.group(1).strip()
                        if pending_user and bot_text:
                            pairs.append((pending_user, bot_text))
                            file_pairs += 1
                        pending_user = None
        except Exception as e:
            pass
    return pairs


def cleanup_epoch_checkpoints(pattern="gpt2_sft_epoch*.pt"):
    for path in glob.glob(pattern):
        try:
            os.remove(path)
        except OSError as e:
            pass


def prepare_conversations(
    bst_size=10000,
    dd_size=30000,
    md_dir="training_data",
    use_bst=True,
    use_dd=True,
    use_md=True,
):
    import random
    all_pairs = []
    if use_bst:
        all_pairs += load_blended_skill_talk(subset_size=bst_size)
    if use_dd:
        all_pairs += load_daily_dialog(subset_size=dd_size)
    if use_md:
        all_pairs += load_markdown_files(md_dir=md_dir)
    all_pairs = [
        (u, b) for u, b in all_pairs
        if not is_degenerate(u) and not is_degenerate(b)
    ]
    random.shuffle(all_pairs)
    return all_pairs

class SFTDataset(Dataset):
    def __init__(self, conversations, tokenizer, max_length=128):
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
            loss_mask  = [0] * prompt_len + [1] * (len(full_ids) - prompt_len)
            self.samples.append({"input_ids": full_ids, "loss_mask": loss_mask})
    def __len__(self):
        return len(self.samples)
    def __getitem__(self, idx):
        return self.samples[idx]


def collate_fn(batch, tokenizer):
    pad_val = tokenizer.pad_token_id
    max_len  = max(len(s["input_ids"]) for s in batch)
    input_ids, loss_mask = [], []
    for s in batch:
        ids = s["input_ids"]
        m   = s["loss_mask"]
        input_ids.append(ids + [pad_val] * (max_len - len(ids)))
        loss_mask.append(m   + [0]       * (max_len - len(m)))
    return {
        "input_ids": torch.tensor(input_ids, dtype=torch.long),
        "loss_mask": torch.tensor(loss_mask, dtype=torch.float),
    }


def train_one_epoch(model, loader, optimizer, scheduler, device, accum_steps,
                    max_grad_norm=1.0, epoch=None):
    model.train()
    total_loss = 0.0
    total_toks = 0
    optimizer.zero_grad()
    bar  = tqdm(loader, desc=f"Epoch {epoch}", leave=False) if TQDM_AVAILABLE else loader
    step = 0
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
        loss        = masked_loss / n_tokens / accum_steps
        loss.backward()
        total_loss += masked_loss.item()
        total_toks += n_tokens.item()
        if (step + 1) % accum_steps == 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            if device.type == "mps":
                torch.mps.empty_cache()
            if TQDM_AVAILABLE:
                bar.set_postfix(loss=f"{masked_loss.item()/n_tokens.item():.4f}")
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
        logits    = model(x).logits
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


_CLEANUP_RE = re.compile(r'</?[a-zA-Z0-9]+[^>]*>|\|[a-zA-Z_]+\|')
_SPACE_RE   = re.compile(r'\s+')
_STOP_RE = re.compile(
    r'\n\s*(?:User|Bot|You|modelo|modell|zabud)\s*[:\-]?',
    re.IGNORECASE
)

def generate_reply(model, tokenizer, prompt_text, device,
                   max_new_tokens=300, temperature=0.3, top_p=0.85, top_k=40,
                   repetition_penalty=1.25):
    end_of_turn_id = tokenizer.convert_tokens_to_ids("<end_of_turn>")
    stop_ids = [tokenizer.eos_token_id]
    if end_of_turn_id is not None:
        stop_ids.append(end_of_turn_id)
    with torch.inference_mode():
        enc = tokenizer(prompt_text, return_tensors="pt", truncation=False)
        input_ids = enc["input_ids"].to(device)
        attention_mask = enc["attention_mask"].to(device)
        max_ctx = getattr(model.config, "max_position_embeddings", 8192) - max_new_tokens
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
            use_cache=True,
            renormalize_logits=True,
            eos_token_id=stop_ids,
            pad_token_id=tokenizer.eos_token_id,
        )
    generated = output_ids[0, input_ids.size(1):]
    reply = tokenizer.decode(
        generated,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    ).strip()
    reply = re.sub(r'<[^>]+>', '', reply).strip()
    reply = _SPACE_RE.sub(' ', reply).strip()
    return reply or "I'm not sure what to say."

def chat(model, tokenizer, device):
    messages = [
        {
            "role": "user",
            "content": (
                "You are Iris, an AI assistant. You are not human and have no personal life. "
                "Always reply in the same language the user writes in. "
                "If the user writes in Arabic, reply in Arabic. "
                "If the user writes in English, reply in English. "
                "Keep answers helpful and concise."
            )
        },
        {
            "role": "assistant",
            "content": "Understood. I am Iris, an AI assistant. How can I help you?"
        }
    ]
    while True:
        user = input("You: ").strip()
        if user.lower() in ("quit", "exit", "q"):
            break
        if not user:
            continue
        messages.append({"role": "user", "content": user})
        if tokenizer.chat_template is not None:
            prompt = tokenizer.apply_chat_template(
                messages, 
                tokenize=False,
                add_generation_prompt=True
            )
        else:
            prompt = ""
            for msg in messages:
                role = USER_TOKEN if msg["role"] == "user" else BOT_TOKEN
                prompt += f"{role} {msg['content']}\n"
            prompt += f"{BOT_TOKEN} "
        reply = generate_reply(
            model, tokenizer, prompt, device,
            max_new_tokens=50,
        )
        print(f"Bot: {reply}\n")
        messages.append({"role": "assistant", "content": reply})
        if len(messages) > 20:
            messages = messages[-20:]