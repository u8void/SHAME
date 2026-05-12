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
import pandas as pd
import random
import csv
import json


# ── Math solver ─────────────────────────────────────────────────────────────
# Intercepts math/algebra questions and returns exact answers via sympy,
# bypassing the language model entirely so we never hallucinate numbers.

_MATH_TRIGGER = re.compile(
    r'(?:'
    r'what\s+is\s+|solve\s+|find\s+|calculate\s+|compute\s+'
    r'|simplify\s+|evaluate\s+'
    r')?'
    r'('
    # equation with variable(s): 3x+5=11, 2x^2-4=0, etc.
    r'[0-9a-zA-Z\s\+\-\*\/\^\(\)\.=]+=[0-9a-zA-Z\s\+\-\*\/\^\(\)\.]+\s*\?*'
    r'|'
    # pure arithmetic: what is 6*7, 100/4+3, etc.
    r'[\d\s\+\-\*\/\^\(\)\.]+\s*\?*'
    r')',
    re.IGNORECASE,
)

def solve_math(user_text: str):
    """
    Try to solve the math/algebra in `user_text`.
    Returns a formatted string answer, or None if the text isn't math.
    """
    try:
        from sympy import symbols, solve, Eq, sympify, simplify, S
        from sympy.parsing.sympy_parser import (
            parse_expr, standard_transformations,
            implicit_multiplication_application, convert_xor
        )
    except ImportError:
        return None

    text = user_text.strip().rstrip('?').strip()

    # Normalise: 6x → 6*x, 2x^2 → 2*x**2
    def normalise(expr: str) -> str:
        expr = re.sub(r'([0-9])([a-zA-Z])', r'\1*\2', expr)  # 6x → 6*x
        expr = re.sub(r'\^', '**', expr)                      # ^ → **
        return expr

    transformations = (
        standard_transformations
        + (implicit_multiplication_application, convert_xor)
    )

    # ── Case 1: equation  (contains '=') ─────────────────────────────────
    if '=' in text:
        parts = text.split('=', 1)
        lhs_raw, rhs_raw = normalise(parts[0].strip()), normalise(parts[1].strip())

        # Collect single-letter variable names
        var_names = sorted(set(re.findall(r'\b([a-zA-Z])\b', lhs_raw + ' ' + rhs_raw)))
        if not var_names:
            return None

        try:
            var_syms = {v: symbols(v) for v in var_names}
            lhs = parse_expr(lhs_raw, local_dict=var_syms, transformations=transformations)
            rhs = parse_expr(rhs_raw, local_dict=var_syms, transformations=transformations)
            eq = Eq(lhs, rhs)
            solutions = solve(eq, list(var_syms.values()))
        except Exception:
            return None

        if not solutions:
            return "This equation has no solution."

        var_list = list(var_syms.keys())
        if isinstance(solutions, list):
            if len(solutions) == 1:
                val = solutions[0]
                val_str = str(val) if val == int(val) else str(val)
                return f"{var_list[0]} = {val_str}"
            else:
                parts_str = ", ".join(
                    f"{var_list[0]} = {s}" for s in solutions
                )
                return f"Solutions: {parts_str}"
        elif isinstance(solutions, dict):
            parts_str = ", ".join(f"{k} = {v}" for k, v in solutions.items())
            return parts_str
        return str(solutions)

    _NL_PREFIX = re.compile(
        r'^(?:what\s+is|solve|find|calculate|compute|simplify|evaluate)\s+',
        re.IGNORECASE,
    )
    arith_text = _NL_PREFIX.sub('', text).strip()
    var_names = re.findall(r'\b([a-zA-Z])\b', arith_text)
    if var_names:
        return None  

    arith = normalise(arith_text)
    if not re.fullmatch(r'[\d\s\+\-\*\/\(\)\.]+', arith):
        return None
    try:
        result = sympify(arith)
        result = simplify(result)
        if result == int(result):
            return str(int(result))
        return str(result)
    except Exception:
        return None

def load_generation_config():
    config_path = os.path.join(os.path.dirname(__file__), "config", "iris.conf")
    default_config = {
        "max_new_tokens": 200,
        "do_sample": True,
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "repetition_penalty": 1.0,
        "no_repeat_ngram_size": 0
    }
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                default_config.update(json.load(f))
        except Exception as e:
            print(f"Warning: Failed to load config from {config_path}: {e}")
    return default_config


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

_HALLUCINATION_SIGNALS = re.compile(
    r'(MigrationBuilder|nakalista'
    r'|\ud795|\ufa4c|#+#'
    r'|http(?:http|https))',
    re.IGNORECASE
)

def truncate_at_hallucination(text: str) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    clean = []
    for sent in sentences:
        if _HALLUCINATION_SIGNALS.search(sent):
            break         
        clean.append(sent)
    result = " ".join(clean).strip() if clean else text.strip()
    return result


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


def load_mbzuai_egyptian_mixture(subset_size=None):
    pairs = []
    try:
        print("[MBZUAI] Downloading MBZUAI-Paris/Egyptian-SFT-Mixture from Hugging Face...")
        ds = load_dataset("MBZUAI-Paris/Egyptian-SFT-Mixture", split="train")
        
        for row in ds:
            messages = row.get("messages", [])
            
            # Ensure there is at least a user prompt and an assistant reply
            if len(messages) >= 2 and messages[0].get("role") == "user" and messages[1].get("role") == "assistant":
                q = str(messages[0].get("content", "")).strip()
                a = str(messages[1].get("content", "")).strip()
                
                if q and a:
                    pairs.append((q, a))
                    
        print(f"[MBZUAI] Successfully loaded {len(pairs)} high-quality Egyptian SFT pairs!")
    except Exception as e:
        print(f"[MBZUAI] Failed to load dataset: {e}")
        return []
        
    if subset_size and len(pairs) > subset_size:
        random.shuffle(pairs)
        pairs = pairs[:subset_size]
        
    return pairs

def load_dolci_think_dataset(subset_size=None):
    pairs = []
    try:
        print("[DOLCI] Streaming Dolci-Think-SFT from Hugging Face...")
        
        # CRITICAL: Added streaming=True. It will not download the massive files!
        ds = load_dataset("allenai/Dolci-Think-SFT-7B", split="train", streaming=True)
        
        count = 0
        for row in ds:
            # Stop pulling from the internet the exact second we reach our subset size
            if subset_size and count >= subset_size:
                break
                
            messages = row.get("messages", [])
            
            if len(messages) >= 2 and messages[0].get("role") == "user" and messages[1].get("role") == "assistant":
                q = str(messages[0].get("content", "")).strip()
                a = str(messages[1].get("content", "")).strip()
                
                if q and a:
                    pairs.append((q, a))
                    count += 1 # Only count valid pairs
                    
        print(f"[DOLCI] Successfully streamed {len(pairs)} reasoning pairs!")
    except Exception as e:
        print(f"[DOLCI] Failed to load dataset: {e}")
        return []
        
    # We don't shuffle here because streaming already gives us a random-ish top slice
    return pairs

def load_hf_maliki_dataset(subset_size=None):
    pairs = []
    try:
        print("[MALIKI] Downloading/Loading Istilah_Maliki_Dataset from Hugging Face...")
        # Load the dataset directly
        ds = load_dataset("islamic-datasets/Istilah_Maliki_Dataset", split="train")
        
        # Loop through and grab the exact column names shown in your screenshot
        for row in ds:
            q = str(row.get('question', '')).strip()
            a = str(row.get('answer', '')).strip()
            
            if q and a: 
                pairs.append((q, a))
                
        print(f"[MALIKI] Successfully loaded {len(pairs)} pairs from Hugging Face")
    except Exception as e:
        print(f"[MALIKI] Failed to load dataset: {e}")
        return []
        
    if subset_size and len(pairs) > subset_size:
        random.shuffle(pairs)
        pairs = pairs[:subset_size]
        
    return pairs

def load_claude_reasoning_dataset(subset_size=None, keep_reasoning=True):
    ds = load_dataset("angrygiraffe/claude-opus-4.6-4.7-reasoning-8.7k", split="train")
    
    pairs = []
    for row in ds:
        messages = row["messages"]
        # Find the last user→assistant turn
        for i in range(len(messages) - 1):
            if messages[i]["role"] == "user" and messages[i + 1]["role"] == "assistant":
                user = messages[i]["content"].strip()
                bot = messages[i + 1]["content"].strip()
                
                if not keep_reasoning:
                    bot = re.sub(r'<think>.*?</think>', '', bot, flags=re.DOTALL).strip()
                
                if len(bot) < 3000 and user and bot:
                    pairs.append((user, bot))
    
    print(f"[CLAUDE] Loaded {len(pairs)} reasoning pairs")
    
    if subset_size and len(pairs) > subset_size:
        import random
        random.shuffle(pairs)
        pairs = pairs[:subset_size]
    return pairs

def load_deepthink_dataset(subset_size=None, keep_reasoning=True):
    """Loads the Deepthink Reasoning dataset from Hugging Face."""
    try:
        from datasets import load_dataset
        ds = load_dataset("prithivMLmods/Deepthink-Reasoning", split="train")
    except Exception as e:
        print(f"[DEEPTHINK] Failed to load dataset: {e}")
        return []
    
    pairs = []
    for row in ds:
        # Check common key patterns for instruction/response datasets
        user = row.get("instruction") or row.get("prompt") or row.get("user")
        bot = row.get("output") or row.get("response") or row.get("assistant")
        
        if user and bot:
            user = user.strip()
            bot = bot.strip()
            
            if not keep_reasoning:
                bot = re.sub(r'<think>.*?</think>', '', bot, flags=re.DOTALL).strip()
            
            if len(bot) < 4000 and user and bot:
                pairs.append((user, bot))
    
    print(f"[DEEPTHINK] Loaded {len(pairs)} reasoning pairs")
    
    if subset_size and len(pairs) > subset_size:
        import random
        random.shuffle(pairs)
        pairs = pairs[:subset_size]
    return pairs

def load_markdown_files(md_dir="md", pattern="*.md"):
    """
    Robustly loads USER/BOT pairs from markdown files.
    Supports multi-line content by accumulating lines until the next tag.
    Also supports an optional SYSTEM tag.
    """
    pairs = []
    search_path = os.path.join(md_dir, pattern)
    files = glob.glob(search_path)
    if not files:
        return pairs

    # Regex to catch tags at the start of a line
    tag_re = re.compile(r"^(SYSTEM|USER|BOT|User|Bot)\s*:\s*(.*)", re.IGNORECASE)

    for filepath in sorted(files):
        current_user = []
        current_bot = []
        current_system = []
        last_tag = None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    # Skip comments/headers but NOT if they are part of a multi-line block
                    if not last_tag and (stripped.startswith("#") or stripped.startswith("<!--")):
                        continue
                    
                    match = tag_re.match(line) # Don't strip() to preserve indent in content
                    if match:
                        # If we hit a new tag and had a pair pending, save it
                        if match.group(1).upper() in ("USER", "SYSTEM") and current_user and current_bot:
                            user_text = "\n".join(current_user).strip()
                            bot_text = "\n".join(current_bot).strip()
                            if current_system:
                                sys_text = "\n".join(current_system).strip()
                                user_text = f"{sys_text}\n\n{user_text}"
                            pairs.append((user_text, bot_text))
                            current_user = []
                            current_bot = []

                        tag = match.group(1).upper()
                        content = match.group(2)
                        last_tag = tag
                        if tag == "SYSTEM":
                            current_system.append(content)
                        elif tag == "USER":
                            current_user.append(content)
                        elif tag == "BOT":
                            current_bot.append(content)
                    else:
                        # Continue accumulating content for the last tag
                        if last_tag == "SYSTEM":
                            current_system.append(line.rstrip())
                        elif last_tag == "USER":
                            current_user.append(line.rstrip())
                        elif last_tag == "BOT":
                            current_bot.append(line.rstrip())

                # End of file: save last pair
                if current_user and current_bot:
                    user_text = "\n".join(current_user).strip()
                    bot_text = "\n".join(current_bot).strip()
                    if current_system:
                        sys_text = "\n".join(current_system).strip()
                        user_text = f"{sys_text}\n\n{user_text}"
                    pairs.append((user_text, bot_text))
        except Exception as e:
            print(f"[Warning] Error reading {filepath}: {e}")
    
    print(f"[Markdown] Loaded {len(pairs)} pairs from {len(files)} files.")
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
                   max_new_tokens=None, temperature=None, top_p=None, top_k=None,
                   repetition_penalty=None):
    gen_config = load_generation_config()
    max_new_tokens = max_new_tokens if max_new_tokens is not None else gen_config.get("max_new_tokens", 200)
    temperature = temperature if temperature is not None else gen_config.get("temperature", 0.7)
    top_p = top_p if top_p is not None else gen_config.get("top_p", 0.9)
    top_k = top_k if top_k is not None else gen_config.get("top_k", 40)
    repetition_penalty = repetition_penalty if repetition_penalty is not None else gen_config.get("repetition_penalty", 1.0)
    do_sample = gen_config.get("do_sample", True)
    no_repeat_ngram_size = gen_config.get("no_repeat_ngram_size", 0)
    # Minimum mean token probability below which the model admits it doesn't know.
    # Range 0.0–1.0. Lower = more permissive. Raise to be stricter.
    confidence_threshold = float(gen_config.get("confidence_threshold", 0.10))

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
        gen_out = model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=max_new_tokens,
            do_sample=do_sample,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            repetition_penalty=repetition_penalty,
            no_repeat_ngram_size=no_repeat_ngram_size,
            use_cache=True,
            renormalize_logits=True,
            eos_token_id=stop_ids,
            pad_token_id=tokenizer.eos_token_id,
            output_scores=True,
            return_dict_in_generate=True,
        )
        output_ids = gen_out.sequences
        scores = gen_out.scores  # tuple of (vocab_size,) tensors, one per generated token

    generated = output_ids[0, input_ids.size(1):]

    if scores and confidence_threshold > 0.0:
        import math
        entropies = []
        for i, s in enumerate(scores):
            if i >= len(generated):
                break
            probs = F.softmax(s[0].float(), dim=-1)
            entropy = -(probs * probs.clamp(min=1e-9).log()).sum().item()
            entropies.append(entropy)
        mean_entropy = sum(entropies) / len(entropies) if entropies else 0.0
        if mean_entropy > confidence_threshold:
            return "I'm not sure about that — it seems to be outside what I've been trained on."

    reply = tokenizer.decode(
        generated,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    ).strip()
    stop_match = _STOP_RE.search(reply)
    if stop_match:
        reply = reply[:stop_match.start()].strip()

    if reply and reply.rstrip().endswith(':') and '\n' not in reply:
        return "I'm not sure about that — it seems to be outside what I've been trained on."

    reply = truncate_at_hallucination(reply)
    return reply or "I'm not sure what to say."

def chat(model, tokenizer, device):
    print("Chat started! Type 'quit' to exit.")
    
    messages = []
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["quit", "exit"]:
            break
            
        messages.append({"role": "user", "content": user_input})
        
        # Apply the exact template Gemma expects
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        
        # Use generate_reply to handle inference_mode, context length, and config
        response = generate_reply(model, tokenizer, prompt, device)
        print(f"Bot: {response}\n")
        
        messages.append({"role": "assistant", "content": response})