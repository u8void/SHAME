"""
iris.py — Unified Intelligence Engine for Iris AI
==================================================
Consolidated backend supporting MLX, CUDA, and CPU.
Includes data loaders, training utilities, and a math solver.
"""

import os
import re
import json
import glob
import platform
import threading
import random
from typing import Optional, Tuple, Dict, Any

# ── Imports ──────────────────────────────────────────────────────────────────
try:
    import torch
    import torch.nn.functional as F
    from torch.utils.data import Dataset, DataLoader
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False

try:
    from datasets import load_dataset
    DATASETS_AVAILABLE = True
except ImportError:
    DATASETS_AVAILABLE = False

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# ── Constants ─────────────────────────────────────────────────────────────────
USER_TOKEN = "User:"
BOT_TOKEN  = "Bot:"
EOS_TOKEN  = "<|endoftext|>"

_HERE         = os.path.dirname(os.path.abspath(__file__))
ADAPTER_PATH  = os.path.join(_HERE, "adapters")
PEFT_ADAPTER  = os.path.join(_HERE, "adapters_peft")
FUSED_MODEL_PATH = os.path.join(_HERE, "iris_14b_model")
CONFIG_PATH   = os.path.join(_HERE, "config", "iris.conf")

# Default Models
MLX_MODEL_ID  = "mlx-community/phi-4-4bit"
HF_MODEL_ID   = "microsoft/phi-4"

# ─────────────────────────────────────────────────────────────────────────────
# 1.  Backend Detection & Device Shim
# ─────────────────────────────────────────────────────────────────────────────

def _detect_backend() -> str:
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        try:
            import mlx.core
            return "mlx"
        except ImportError:
            pass
    if TORCH_AVAILABLE and torch.cuda.is_available():
        return "cuda"
    return "cpu"

BACKEND = _detect_backend()

class _Device:
    def __init__(self, type_: str):
        self.type = type_
    def __repr__(self):
        return f"device(type='{self.type}')"

def get_device(force_cpu=False):
    if force_cpu: return _Device("cpu")
    return _Device(BACKEND)

# ─────────────────────────────────────────────────────────────────────────────
# 2.  Math Solver (Sympy)
# ─────────────────────────────────────────────────────────────────────────────

_MATH_TRIGGER = re.compile(
    r'(?:what\s+is\s+|solve\s+|find\s+|calculate\s+|compute\s+|simplify\s+|evaluate\s+)?'
    r'([0-9a-zA-Z\s\+\-\*\/\^\(\)\.=]+=[0-9a-zA-Z\s\+\-\*\/\^\(\)\.]+\s*\?*|[\d\s\+\-\*\/\^\(\)\.]+\s*\?*)',
    re.IGNORECASE
)

def solve_math(user_text: str) -> Optional[str]:
    try:
        from sympy import symbols, solve, Eq, sympify, simplify
        from sympy.parsing.sympy_parser import (
            parse_expr, standard_transformations,
            implicit_multiplication_application, convert_xor
        )
    except ImportError:
        return None

    text = user_text.strip().rstrip('?').strip()
    def normalise(expr: str) -> str:
        expr = re.sub(r'([0-9])([a-zA-Z])', r'\1*\2', expr)
        expr = re.sub(r'\^', '**', expr)
        return expr

    transformations = standard_transformations + (implicit_multiplication_application, convert_xor)

    if '=' in text:
        parts = text.split('=', 1)
        lhs_raw, rhs_raw = normalise(parts[0].strip()), normalise(parts[1].strip())
        var_names = sorted(set(re.findall(r'\b([a-zA-Z])\b', lhs_raw + ' ' + rhs_raw)))
        if not var_names: return None
        try:
            var_syms = {v: symbols(v) for v in var_names}
            lhs = parse_expr(lhs_raw, local_dict=var_syms, transformations=transformations)
            rhs = parse_expr(rhs_raw, local_dict=var_syms, transformations=transformations)
            eq = Eq(lhs, rhs)
            solutions = solve(eq, list(var_syms.values()))
        except Exception: return None
        if not solutions: return "This equation has no solution."
        if isinstance(solutions, list):
            if len(solutions) == 1: return f"{var_names[0]} = {solutions[0]}"
            return "Solutions: " + ", ".join(f"{var_names[0]} = {s}" for s in solutions)
        return str(solutions)

    arith_text = re.sub(r'^(?:what\s+is|solve|find|calculate|compute|simplify|evaluate)\s+', '', text, flags=re.IGNORECASE).strip()
    if re.findall(r'\b([a-zA-Z])\b', arith_text): return None
    arith = normalise(arith_text)
    if not re.fullmatch(r'[\d\s\+\-\*\/\(\)\.]+', arith): return None
    try:
        res = simplify(sympify(arith))
        return str(int(res)) if res == int(res) else str(res)
    except Exception: return None

# ─────────────────────────────────────────────────────────────────────────────
# 3.  Data Loaders
# ─────────────────────────────────────────────────────────────────────────────

def load_blended_skill_talk(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("blended_skill_talk", split="train", trust_remote_code=True)
        pairs = []
        for row in ds:
            utts, free = row.get("previous_utterance", []), row.get("free_messages", [])
            for i in range(0, len(utts) - 1, 2):
                if utts[i] and utts[i+1]: pairs.append((utts[i].strip(), utts[i+1].strip()))
            if utts and free:
                for r in free:
                    if r: pairs.append((utts[-1].strip(), r.strip())); break
        if subset_size and subset_size < len(pairs):
            random.shuffle(pairs); return pairs[:subset_size]
        return pairs
    except Exception: return []

def load_daily_dialog(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("daily_dialog", split="train", trust_remote_code=True)
        pairs = []
        for row in ds:
            d = row["dialog"]
            for i in range(len(d)-1):
                if d[i] and d[i+1]: pairs.append((d[i].strip(), d[i+1].strip()))
        if subset_size and subset_size < len(pairs):
            random.shuffle(pairs); return pairs[:subset_size]
        return pairs
    except Exception: return []

def load_markdown_files(md_dir="md", pattern="*.md"):
    pairs = []
    tag_re = re.compile(r"^(SYSTEM|USER|BOT)\s*:\s*(.*)", re.IGNORECASE)
    for path in glob.glob(os.path.join(md_dir, pattern)):
        u, b, s, last = [], [], [], None
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    m = tag_re.match(line)
                    if m:
                        if m.group(1).upper() in ("USER", "SYSTEM") and u and b:
                            pairs.append(("\n".join(s+u).strip(), "\n".join(b).strip()))
                            u, b = [], []
                        tag, content = m.group(1).upper(), m.group(2)
                        last = tag
                        if tag == "SYSTEM": s.append(content)
                        elif tag == "USER": u.append(content)
                        elif tag == "BOT": b.append(content)
                    elif last:
                        if last == "SYSTEM": s.append(line.rstrip())
                        elif last == "USER": u.append(line.rstrip())
                        elif last == "BOT": b.append(line.rstrip())
                if u and b: pairs.append(("\n".join(s+u).strip(), "\n".join(b).strip()))
        except Exception: pass
    return pairs

def load_mbzuai_egyptian_mixture(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("MBZUAI-Paris/Egyptian-SFT-Mixture", split="train")
        pairs = [(m[0]["content"].strip(), m[1]["content"].strip()) for row in ds if (m := row.get("messages")) and len(m) >= 2]
        if subset_size and len(pairs) > subset_size: random.shuffle(pairs); return pairs[:subset_size]
        return pairs
    except Exception: return []

def load_hf_maliki_dataset(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("islamic-datasets/Istilah_Maliki_Dataset", split="train")
        pairs = [(row.get("question","").strip(), row.get("answer","").strip()) for row in ds]
        if subset_size and len(pairs) > subset_size: random.shuffle(pairs); return pairs[:subset_size]
        return pairs
    except Exception: return []

def load_claude_reasoning_dataset(subset_size=None, keep_reasoning=True):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("angrygiraffe/claude-opus-4.6-4.7-reasoning-8.7k", split="train")
        pairs = []
        for row in ds:
            m = row["messages"]
            for i in range(len(m)-1):
                if m[i]["role"] == "user" and m[i+1]["role"] == "assistant":
                    u, b = m[i]["content"].strip(), m[i+1]["content"].strip()
                    if not keep_reasoning: b = re.sub(r'<think>.*?</think>', '', b, flags=re.DOTALL).strip()
                    if u and b: pairs.append((u,b))
        if subset_size and len(pairs) > subset_size: random.shuffle(pairs); return pairs[:subset_size]
        return pairs
    except Exception: return []

def load_dolci_think_dataset(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("allenai/Dolci-Think-SFT-7B", split="train", streaming=True)
        pairs = []
        for row in ds:
            if subset_size and len(pairs) >= subset_size: break
            m = row.get("messages")
            if m and len(m) >= 2: pairs.append((m[0]["content"].strip(), m[1]["content"].strip()))
        return pairs
    except Exception: return []

# ─────────────────────────────────────────────────────────────────────────────
# 4.  Training Utilities (Torch)
# ─────────────────────────────────────────────────────────────────────────────

if TORCH_AVAILABLE:
    class SFTDataset(Dataset):
        def __init__(self, conversations, tokenizer, max_length=128):
            self.samples = []
            for u, b in conversations:
                prompt = f"{USER_TOKEN} {u}\n{BOT_TOKEN} "
                full = prompt + b + EOS_TOKEN
                full_ids = tokenizer.encode(full, truncation=True, max_length=max_length)
                prompt_len = min(len(tokenizer.encode(prompt)), len(full_ids))
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

# ─────────────────────────────────────────────────────────────────────────────
# 5.  Unified Inference Backend
# ─────────────────────────────────────────────────────────────────────────────

_model_lock = threading.Lock()
_cached_model = None
_cached_tok   = None

def load_generation_config() -> dict:
    defaults = {"max_new_tokens": 512, "temperature": 0.7, "top_p": 0.9, "repetition_penalty": 1.0}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f: defaults.update(json.load(f))
        except Exception: pass
    return defaults

# ── MLX Generation ──
def _generate_mlx(model, tokenizer, prompt: str, max_tokens: int, temp: float, top_p: float, rep_pen: float) -> str:
    from mlx_lm import generate
    try:
        from mlx_lm.sample_utils import make_sampler
        sampler = make_sampler(temp=temp, top_p=top_p, repetition_penalty=rep_pen)
        return generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens, sampler=sampler, verbose=False)
    except Exception:
        try: return generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens, temp=temp, top_p=top_p, repetition_penalty=rep_pen, verbose=False)
        except Exception: return generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens, verbose=False)

# ── Transformers Generation ──
def _generate_hf(model, tokenizer, prompt: str, max_tokens: int, temp: float, top_p: float, rep_pen: float) -> str:
    device = next(model.parameters()).device
    enc = tokenizer(prompt, return_tensors="pt")
    input_ids = enc["input_ids"].to(device)
    with torch.inference_mode():
        out = model.generate(input_ids=input_ids, max_new_tokens=max_tokens, do_sample=(temp > 0), temperature=temp, top_p=top_p, repetition_penalty=rep_pen, pad_token_id=tokenizer.eos_token_id)
    return tokenizer.decode(out[0, input_ids.size(1):], skip_special_tokens=True).strip()

def load_model():
    global _cached_model, _cached_tok
    if _cached_model: return _cached_model, _cached_tok
    with _model_lock:
        if _cached_model: return _cached_model, _cached_tok
        if BACKEND == "mlx":
            from mlx_lm import load
            if os.path.isdir(FUSED_MODEL_PATH):
                print(f"[iris] Loading FUSED model from {FUSED_MODEL_PATH}...")
                _cached_model, _cached_tok = load(FUSED_MODEL_PATH)
            else:
                adapter = ADAPTER_PATH if os.path.isdir(ADAPTER_PATH) else None
                tag = f" + adapters from {adapter}" if adapter else ""
                print(f"[iris] Loading {MLX_MODEL_ID}{tag}...")
                _cached_model, _cached_tok = load(MLX_MODEL_ID, adapter_path=adapter)
        else:
            device = torch.device("cuda" if BACKEND == "cuda" else "cpu")
            _cached_tok = AutoTokenizer.from_pretrained(HF_MODEL_ID)
            if _cached_tok.pad_token is None: _cached_tok.pad_token = _cached_tok.eos_token
            if BACKEND == "cuda":
                _cached_model = AutoModelForCausalLM.from_pretrained(HF_MODEL_ID, device_map="auto", load_in_4bit=True)
            else:
                _cached_model = AutoModelForCausalLM.from_pretrained(HF_MODEL_ID).to(device)
            if os.path.isdir(PEFT_ADAPTER):
                from peft import PeftModel
                _cached_model = PeftModel.from_pretrained(_cached_model, PEFT_ADAPTER).merge_and_unload()
        return _cached_model, _cached_tok

def generate_reply(model, tokenizer, prompt_text, device=None, **kwargs):
    cfg = load_generation_config()
    max_t = int(kwargs.get("max_new_tokens") or cfg["max_new_tokens"])
    temp  = float(kwargs.get("temperature") or cfg["temperature"])
    top_p = float(kwargs.get("top_p") or cfg["top_p"])
    rep_p = float(kwargs.get("repetition_penalty") or cfg["repetition_penalty"])
    
    try:
        if BACKEND == "mlx": raw = _generate_mlx(model, tokenizer, prompt_text, max_t, temp, top_p, rep_p)
        else: raw = _generate_hf(model, tokenizer, prompt_text, max_t, temp, top_p, rep_p)
        
        # Cleanup
        reply = raw.strip()
        reply = re.split(r'\n\s*(?:User|Bot|You)\s*[:\-]', reply, flags=re.IGNORECASE)[0].strip()
        # Hallucination cleanup
        sentences = re.split(r'(?<=[.!?])\s+', reply)
        clean = []
        for s in sentences:
            if re.search(r'(MigrationBuilder|nakalista|\ud795|\ufa4c|#+#|http(?:http|https))', s, re.IGNORECASE): break
            clean.append(s)
        return " ".join(clean).strip() or "I'm not sure what to say."
    except Exception as e: return f"Error: {e}"

if __name__ == "__main__":
    m, t = load_model()
    print(f"Backend: {BACKEND} | Model ready.")
    print("Iris: " + generate_reply(m, t, "User: Hello!\nBot: "))
