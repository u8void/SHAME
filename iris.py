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
import math

try:
    from sentence_transformers import SentenceTransformer, util
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False

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

_HERE         = os.path.dirname(os.path.abspath(__file__))
ADAPTER_PATH  = os.path.join(_HERE, "adapters")
PEFT_ADAPTER  = os.path.join(_HERE, "adapters_peft")
FUSED_MODEL_PATH = os.path.join(_HERE, "iris_14b_model")
CONFIG_PATH   = os.path.join(_HERE, "config", "iris.conf")

MLX_MODEL_ID  = "mlx-community/phi-4-4bit"
HF_MODEL_ID   = "microsoft/phi-4"

# ==========================================
# RAG: Retrieval-Augmented Generation Module
# ==========================================
class BookRetriever:
    def __init__(self, raw_data_dir="raw_data"):
        self.raw_data_dir = raw_data_dir
        self.chunks = []
        self.embeddings = None
        self.embedder = None

    def load_and_index(self):
        """Loads markdown/txt files and builds the searchable vector index."""
        if not RAG_AVAILABLE:
            print("[RAG] sentence-transformers not installed. RAG disabled.")
            return

        if not os.path.exists(self.raw_data_dir):
            os.makedirs(self.raw_data_dir, exist_ok=True)
            print(f"[RAG] Created {self.raw_data_dir}/. Drop your markdown books here.")
            return

        print("[RAG] Loading embedding model (all-MiniLM-L6-v2)...")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')

        print(f"[RAG] Reading raw data from {self.raw_data_dir}/...")
        raw_text = ""
        for ext in ["*.md", "*.txt"]:
            for path in glob.glob(os.path.join(self.raw_data_dir, ext)):
                with open(path, "r", encoding="utf-8") as f:
                    raw_text += f.read() + "\n\n"

        if not raw_text.strip():
            print("[RAG] No text found in raw_data/. Skipping index creation.")
            return

        # --- IMPROVED CHUNKING STRATEGY ---
        # Split by double newlines to preserve natural paragraph structure
        paragraphs = re.split(r'\n\s*\n', raw_text)
        self.chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            para = para.strip()
            if not para: continue
            
            # Group short paragraphs together into chunks of ~1500 characters
            if len(current_chunk) + len(para) > 1500 and current_chunk:
                self.chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"
            else:
                current_chunk += para + "\n\n"
                
        # Append the final chunk
        if current_chunk.strip():
            self.chunks.append(current_chunk.strip())

        print(f"[RAG] Created {len(self.chunks)} logical text chunks. Indexing...")
        self.embeddings = self.embedder.encode(self.chunks, convert_to_tensor=True)
        print("[RAG] Indexing complete!")

    def retrieve(self, query: str, top_k=3) -> str:
        """Finds the most relevant chunks for a user's query."""
        if self.embeddings is None or self.embedder is None or not self.chunks:
            return ""

        query_embedding = self.embedder.encode(query, convert_to_tensor=True)
        hits = util.semantic_search(query_embedding, self.embeddings, top_k=top_k)[0]
        
        retrieved_texts = []
        for hit in hits:
            chunk_text = self.chunks[hit['corpus_id']]
            retrieved_texts.append(chunk_text)
            
        return "\n\n---\n\n".join(retrieved_texts)


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
                        lines = sec.strip().split('\n')
                        if len(lines) > 1:
                            title = lines[0].strip()
                            body = "\n".join(lines[1:]).strip()
                            if title and body:
                                file_pairs.append((f"What is {title}?", body))
                                file_pairs.append((f"Explain {title} in detail.", body))
                pairs.extend(file_pairs)
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

def load_deepthink_dataset(subset_size=None, keep_reasoning=True):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("prithivMLmods/Deepthink-Reasoning", split="train")
        pairs = []
        for row in ds:
            u, b = row.get("prompt", "").strip(), row.get("response", "").strip()
            if not keep_reasoning:
                b = re.sub(r'<\|thinking\|>.*?<\/\|thinking\|>', '', b, flags=re.DOTALL).strip()
                b = re.sub(r'<think>.*?<\/think>', '', b, flags=re.DOTALL).strip()
            if u and b:
                pairs.append((u, b))
        if subset_size and len(pairs) > subset_size:
            random.shuffle(pairs)
            return pairs[:subset_size]
        return pairs
    except Exception: return []


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

def _generate_mlx(model, tokenizer, prompt: str, max_tokens: int, temp: float, top_p: float, rep_pen: float) -> str:
    from mlx_lm import generate
    try:
        from mlx_lm.sample_utils import make_sampler
        try:
            sampler = make_sampler(temp=temp, top_p=top_p, repetition_penalty=rep_pen)
        except TypeError:
            sampler = make_sampler(temp=temp, top_p=top_p)
        return generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens, sampler=sampler, verbose=False)
    except Exception:
        try: return generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens, temp=temp, top_p=top_p, repetition_penalty=rep_pen, verbose=False)
        except Exception: return generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens, verbose=False)

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

# ==========================================
# GENERATION FUNCTIONS
# ==========================================
def generate_reply(model, tokenizer, prompt_text, device=None, raw_output=False, **kwargs):
    """Base generation function connecting to MLX or HF."""
    cfg = load_generation_config()
    max_t = int(kwargs.get("max_new_tokens") or cfg["max_new_tokens"])
    temp  = float(kwargs.get("temperature") or cfg["temperature"])
    top_p = float(kwargs.get("top_p") or cfg["top_p"])
    rep_p = float(kwargs.get("repetition_penalty") or cfg["repetition_penalty"])
    
    try:
        if BACKEND == "mlx": raw = _generate_mlx(model, tokenizer, prompt_text, max_t, temp, top_p, rep_p)
        else: raw = _generate_hf(model, tokenizer, prompt_text, max_t, temp, top_p, rep_p)
        
        reply = raw.strip()

        if raw_output:
            return reply

        sentences = re.split(r'(?<=[.!?])\s+', reply)
        clean = []
        for s in sentences:
            if re.search(r'(MigrationBuilder|nakalista|\ud795|\ufa4c|#+#|http(?:http|https))', s, re.IGNORECASE): break
            clean.append(s)
        return " ".join(clean).strip() or "I'm not sure what to say."
    except Exception as e: return f"Error: {e}"

def generate_rag_reply(model, tokenizer, retriever, user_query, **kwargs):
    """Combines RAG context with the user query before sending to the LLM."""
    
    # 1. Search the raw_data books for relevant paragraphs
    context = retriever.retrieve(user_query, top_k=3)
    
    # 2. Build the messages array using native roles
    if context:
        system_content = (
            "You are Iris, a helpful AI assistant. Use the following excerpt from a "
            "reference book to answer the user's question accurately. If the excerpt "
            "doesn't contain the answer, just say so.\n\n"
            f"REFERENCE EXCERPT:\n{context}"
        )
    else:
        system_content = "You are Iris, a helpful AI assistant."

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_query}
    ]

    # 3. Apply the native chat template
    prompt_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    # 4. Generate the reply
    return generate_reply(model, tokenizer, prompt_text, **kwargs)

# ==========================================
# EXECUTION & TESTING
# ==========================================
if __name__ == "__main__":
    print("\n" + "="*50)
    print(" Initializing Iris AI (Hybrid SFT + RAG Engine)")
    print("="*50)
    
    # 1. Start the RAG engine and load books
    retriever = BookRetriever(raw_data_dir="raw_data")
    retriever.load_and_index()
    
    # 2. Load the LLM Model
    m, t = load_model()
    print(f"\n[SYSTEM] Backend: {BACKEND.upper()} | Model ready.")
    print("="*50)
    
    # 3. Test it out!
    test_queries = [
        "Hello! How are you?",
        "What is the main topic of chapter 1?"
    ]
    
    for q in test_queries:
        print(f"\nUser: {q}")
        reply = generate_rag_reply(m, t, retriever, q)
        print(f"Iris: {reply}")