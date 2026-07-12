import os
import glob
import json
import random
from datasets import load_dataset

DATASETS_AVAILABLE = True
TORCH_AVAILABLE = True
try:
    import torch
    from torch.utils.data import Dataset
except:
    TORCH_AVAILABLE = False

def load_blended_skill_talk(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("blended_skill_talk", split="train", streaming=True)
        if subset_size:
            try: ds = ds.shuffle(buffer_size=10000, seed=42)
            except Exception: pass
        pairs = []
        for row in ds:
            if subset_size and len(pairs) >= subset_size: break
            utts, free = row.get("previous_utterance", []), row.get("free_messages", [])
            for i in range(0, len(utts) - 1, 2):
                if utts[i] and utts[i+1]: pairs.append((utts[i].strip(), utts[i+1].strip()))
            if utts and free:
                for r in free:
                    if r: pairs.append((utts[-1].strip(), r.strip())); break
        return pairs
    except Exception: return []


def load_daily_dialog(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("daily_dialog", split="train", streaming=True)
        if subset_size:
            try: ds = ds.shuffle(buffer_size=10000, seed=42)
            except Exception: pass
        pairs = []
        for row in ds:
            if subset_size and len(pairs) >= subset_size: break
            d = row["dialog"]
            for i in range(len(d)-1):
                if d[i] and d[i+1]: pairs.append((d[i].strip(), d[i+1].strip()))
        return pairs
    except Exception: return []


def load_markdown_files(md_dir="md", pattern="**/*.md"):
    pairs = []
    tag_re = re.compile(r"^(SYSTEM|USER|BOT)\s*:\s*(.*)", re.IGNORECASE)
    for path in glob.glob(os.path.join(md_dir, pattern), recursive=True):
        u, b, s, last = [], [], [], None
        file_pairs = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                f.seek(0)
                for line in f:
                    m = tag_re.match(line)
                    if m:
                        if m.group(1).upper() in ("USER", "SYSTEM") and u and b:
                            file_pairs.append(("\n".join(s+u).strip(), "\n".join(b).strip()))
                            u, b = [], []
                        tag, content_line = m.group(1).upper(), m.group(2)
                        last = tag
                        if tag == "SYSTEM": s.append(content_line)
                        elif tag == "USER": u.append(content_line)
                        elif tag == "BOT": b.append(content_line)
                    elif last:
                        if last == "SYSTEM": s.append(line.rstrip())
                        elif last == "USER": u.append(line.rstrip())
                        elif last == "BOT": b.append(line.rstrip())
                if u and b: file_pairs.append(("\n".join(s+u).strip(), "\n".join(b).strip()))
                if not file_pairs:
                    sections = re.split(r'\n#+\s+', content)
                    for sec in sections:
                        lines = sec.strip().split('\n', 1)
                        if len(lines) == 2:
                            file_pairs.append((lines[0].strip(), lines[1].strip()))
            pairs.extend(file_pairs)
        except Exception:
            pass
    return pairs


def load_mbzuai_egyptian_mixture(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("MBZUAI-Paris/Egyptian-SFT-Mixture", split="train", streaming=True)
        if subset_size:
            try: ds = ds.shuffle(buffer_size=10000, seed=42)
            except Exception: pass
        pairs = []
        for row in ds:
            if subset_size and len(pairs) >= subset_size: break
            m = row.get("messages")
            if m and len(m) >= 2:
                pairs.append((m[0]["content"].strip(), m[1]["content"].strip()))
        return pairs
    except Exception: return []


def load_oasst1_dataset(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("OpenAssistant/oasst1", split="train", streaming=False)
        pairs = []
        messages = {}
        for row in ds:
            messages[row["message_id"]] = row
            
        for row in ds:
            if row["role"] == "assistant" and row.get("parent_id") in messages:
                parent = messages[row["parent_id"]]
                if parent["role"] == "prompter":
                    pairs.append((parent["text"].strip(), row["text"].strip()))
                    
        import random
        random.shuffle(pairs)
        if subset_size:
            pairs = pairs[:subset_size]
        return pairs
    except Exception as e: 
        print(f"[WARNING] OASST1 load error: {e}")
        return []


def load_hf_maliki_dataset(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("islamic-datasets/Istilah_Maliki_Dataset", split="train", streaming=True)
        if subset_size:
            try: ds = ds.shuffle(buffer_size=10000, seed=42)
            except Exception: pass
        pairs = []
        for row in ds:
            if subset_size and len(pairs) >= subset_size: break
            m = row.get("messages")
            if m and len(m) >= 2:
                pairs.append((m[0]["content"].strip(), m[1]["content"].strip()))
        return pairs
    except Exception: return []


def load_claude_reasoning_dataset(subset_size=None, keep_reasoning=True):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("angrygiraffe/claude-opus-4.6-4.7-reasoning-8.7k", split="train", streaming=True)
        if subset_size:
            try: ds = ds.shuffle(buffer_size=10000, seed=42)
            except Exception: pass
        pairs = []
        for row in ds:
            if subset_size and len(pairs) >= subset_size: break
            m = row.get("messages")
            if m and len(m) >= 2:
                content = m[1].get("content", "").strip()
                if not keep_reasoning:
                    content = re.sub(r'<\|thinking\|>.*?<\/\|thinking\|>', '', content, flags=re.DOTALL).strip()
                if content:
                    pairs.append((m[0]["content"].strip(), content))
        return pairs
    except Exception: return []


def load_dolci_think_dataset(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("allenai/Dolci-Think-SFT-7B", split="train", streaming=True)
        if subset_size:
            try: ds = ds.shuffle(buffer_size=10000, seed=42)
            except Exception: pass
        pairs = []
        for row in ds:
            if subset_size and len(pairs) >= subset_size: break
            m = row.get("messages")
            if m and len(m) >= 2:
                pairs.append((m[0]["content"].strip(), m[1]["content"].strip()))
        return pairs
    except Exception: return []


def load_deepthink_dataset(subset_size=None, keep_reasoning=True):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("prithivMLmods/Deepthink-Reasoning", split="train", streaming=True)
        if subset_size:
            try: ds = ds.shuffle(buffer_size=10000, seed=42)
            except Exception: pass
        pairs = []
        for row in ds:
            if subset_size and len(pairs) >= subset_size: break
            u, b = row.get("prompt", "").strip(), row.get("response", "").strip()
            if not keep_reasoning:
                b = re.sub(r'<\|thinking\|>.*?<\/\|thinking\|>', '', b, flags=re.DOTALL).strip()
                b = re.sub(r'<think>.*?<\/think>', '', b, flags=re.DOTALL).strip()
            if u and b:
                pairs.append((u, b))
        return pairs
    except Exception: return []


def load_openhermes_reasoning(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("teknium/OpenHermes-2.5", split="train", streaming=True)
        if subset_size:
            try: ds = ds.shuffle(buffer_size=10000, seed=42)
            except Exception: pass
        pairs = []
        for row in ds:
            if subset_size and len(pairs) >= subset_size: break
            m = row.get("messages")
            if m and len(m) >= 2:
                pairs.append((m[0]["content"].strip(), m[1]["content"].strip()))
        return pairs
    except Exception: return []


def load_math_qa(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("EleutherAI/hendrycks_math", name="algebra", split="train", streaming=True)
        if subset_size:
            try: ds = ds.shuffle(buffer_size=10000, seed=42)
            except Exception: pass
        pairs = []
        for row in ds:
            if subset_size and len(pairs) >= subset_size: break
            prob = row.get("problem", "").strip()
            sol = row.get("solution", "").strip()
            if prob and sol: pairs.append((prob, sol))
        return pairs
    except Exception: return []


def load_code_feedback(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("m-a-p/CodeFeedback-Filtered-Instruction", split="train", streaming=True)
        if subset_size:
            try: ds = ds.shuffle(buffer_size=10000, seed=42)
            except Exception: pass
        pairs = []
        for row in ds:
            if subset_size and len(pairs) >= subset_size: break
            m = row.get("messages")
            if m and len(m) >= 2:
                pairs.append((m[0]["content"].strip(), m[1]["content"].strip()))
        return pairs
    except Exception: return []


def load_magicoder_dataset(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("ise-uiuc/Magicoder-OSS-Instruct-75K", split="train", streaming=True)
        if subset_size:
            try: ds = ds.shuffle(buffer_size=10000, seed=42)
            except Exception: pass
        pairs = []
        for row in ds:
            if subset_size and len(pairs) >= subset_size: break
            prob = row.get("problem", "").strip()
            sol = row.get("solution", "").strip()
            if prob and sol:
                pairs.append((prob, sol))
        return pairs
    except Exception: return []


def load_open_code_reasoning(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("nvidia/OpenCodeReasoning", name="split_0", split="split_0", streaming=True)
        if subset_size:
            try: ds = ds.shuffle(buffer_size=10000, seed=42)
            except Exception: pass
        pairs = []
        for row in ds:
            if subset_size and len(pairs) >= subset_size: break
            u = row.get("instruction") or row.get("input") or ""
            b = row.get("output") or row.get("response") or ""
            u, b = u.strip(), b.strip()
            if u and b:
                pairs.append((u, b))
        return pairs
    except Exception: return []


def load_self_oss_instruct(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("bigcode/self-oss-instruct-sc2-exec-filter-50k", split="train", streaming=True)
        if subset_size:
            try: ds = ds.shuffle(buffer_size=10000, seed=42)
            except Exception: pass
        pairs = []
        for row in ds:
            if subset_size and len(pairs) >= subset_size: break
            u = row.get("instruction") or row.get("prompt") or ""
            b = row.get("response") or row.get("output") or ""
            u, b = u.strip(), b.strip()
            if u and b:
                pairs.append((u, b))
        return pairs
    except Exception: return []


# ---------------------------------------------------------------------------
# Generic helper: load any instruction-following / alpaca-style / chat dataset
# Handles: {instruction, output}, {prompt, response}, {messages:[...]}, {input, output}
# ---------------------------------------------------------------------------
def _load_generic(hf_path, subset_size=None, split="train", name=None):
    if not DATASETS_AVAILABLE: return []
    try:
        kwargs = dict(split=split, streaming=True)
        if name: kwargs["name"] = name
        ds = load_dataset(hf_path, **kwargs)
        if subset_size:
            try: ds = ds.shuffle(buffer_size=10000, seed=42)
            except Exception: pass
        pairs = []
        for row in ds:
            if subset_size and len(pairs) >= subset_size: break
            # --- messages list (ChatML) ---
            msgs = row.get("messages") or row.get("conversations") or []
            if msgs and isinstance(msgs, list) and len(msgs) >= 2:
                user_turn = next((m.get("content","") or m.get("value","") for m in msgs if m.get("role","") in ("user","human")), "")
                asst_turn = next((m.get("content","") or m.get("value","") for m in msgs if m.get("role","") in ("assistant","gpt","bot")), "")
                if user_turn and asst_turn:
                    pairs.append((user_turn.strip(), asst_turn.strip()))
                    continue
            # --- alpaca / instruction style ---
            u = (row.get("instruction") or row.get("prompt") or row.get("input") or row.get("question") or "").strip()
            b = (row.get("output") or row.get("response") or row.get("answer") or row.get("completion") or "").strip()
            ctx = (row.get("context") or row.get("input") or "").strip()
            if ctx and u and ctx != u:
                u = f"{u}\n\n{ctx}"
            if u and b:
                pairs.append((u, b))
        return pairs
    except Exception as e:
        print(f"[WARNING] Failed to load {hf_path}: {e}")
        return []


# ---------------------------------------------------------------------------
# Named loaders (thin wrappers around _load_generic) — registered in train.py
# ---------------------------------------------------------------------------

def load_code_alpaca_20k(subset_size=None):
    return _load_generic("sahil2801/CodeAlpaca-20k", subset_size)

def load_python_code_instructions_18k(subset_size=None):
    return _load_generic("iamtarun/python_code_instructions_18k_alpaca", subset_size)

def load_code_instructions_122k(subset_size=None):
    return _load_generic("TokenBender/code_instructions_122k_alpaca_style", subset_size)

def load_python_codes_25k(subset_size=None):
    return _load_generic("flytech/python-codes-25k", subset_size)

def load_code_74k_sharegpt(subset_size=None):
    return _load_generic("ajibawa-2023/Code-74k-ShareGPT", subset_size)

def load_glaive_code_assistant_v3(subset_size=None):
    return _load_generic("glaiveai/glaive-code-assistant-v3", subset_size)

def load_evol_codealpaca_v1(subset_size=None):
    return _load_generic("theblackcat102/evol-codealpaca-v1", subset_size)

def load_tiny_codes(subset_size=None):
    return _load_generic("nampdn-ai/tiny-codes", subset_size)

def load_hf4_code_alpaca_20k(subset_size=None):
    return _load_generic("HuggingFaceH4/CodeAlpaca_20K", subset_size)

def load_stack_exchange_preferences(subset_size=None):
    return _load_generic("mlabonne/stack-exchange-preferences", subset_size)

def load_tested_22k_python_alpaca(subset_size=None):
    return _load_generic("Vezora/Tested-22k-Python-Alpaca", subset_size)

def load_javascript_typescript_instructions(subset_size=None):
    return _load_generic("semipro/javascript-typescript-code-instructions", subset_size)

def load_leetcode_dataset(subset_size=None):
    return _load_generic("greengerong/leetcode", subset_size)

def load_stackoverflow_javascript(subset_size=None):
    return _load_generic("koutch/stackoverflow_javascript", subset_size)

def load_nodejs_code_instructions(subset_size=None):
    return _load_generic("Zhendi/node.js-code-instructions", subset_size)

def load_evol_instruct_code_80k(subset_size=None):
    return _load_generic("nickrosh/Evol-Instruct-Code-80k", subset_size)

def load_webdev_coding_dataset(subset_size=None):
    return _load_generic("Hoglet-33/webdev-coding-dataset", subset_size)

def load_ui_reasoning(subset_size=None):
    return _load_generic("smirki/UI_REASONING_v1.01", subset_size)





if TORCH_AVAILABLE:
    class SFTDataset(Dataset):
        def __init__(self, conversations, tokenizer, max_length=128):
            self.samples = []
            for u, b in conversations:
                msgs = [{"role": "user", "content": u}, {"role": "assistant", "content": b}]
                full_text = tokenizer.apply_chat_template(msgs, tokenize=False)
                full_ids = tokenizer.encode(full_text, truncation=True, max_length=max_length)
                prompt_text = tokenizer.apply_chat_template(msgs[:1], tokenize=False, add_generation_prompt=True)
                prompt_ids = tokenizer.encode(prompt_text, truncation=True, max_length=max_length)
                prompt_len = min(len(prompt_ids), len(full_ids))
                mask = [0]*prompt_len + [1]*(len(full_ids)-prompt_len)
                self.samples.append({"input_ids": full_ids, "loss_mask": mask})
        def __len__(self): return len(self.samples)
        def __getitem__(self, idx): return self.samples[idx]

    def collate_fn(batch, tokenizer):
        pad = tokenizer.pad_token_id
        max_len = max(len(s["input_ids"]) for s in batch)
        ids, masks = [], []
        for s in batch:
            ids.append(s["input_ids"] + [pad]*(max_len - len(s["input_ids"])))
            masks.append(s["loss_mask"] + [0]*(max_len - len(s["loss_mask"])))
        return {"input_ids": torch.tensor(ids, dtype=torch.long), "loss_mask": torch.tensor(masks, dtype=torch.float)}


def cleanup_epoch_checkpoints(pattern="*.pt"):
    for p in glob.glob(pattern):
        try: os.remove(p)
        except Exception: pass



