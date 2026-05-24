"""
iris.py — AI Intelligence Engine for Iris AI
==================================================
Consolidated backend supporting MLX, CUDA, and CPU.
Includes data loaders, training utilities, and a math solver.
"""

import os
import re
import json
import glob
import pickle
import hashlib
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

# ── Vision model availability ─────────────────────────────────────────────────
_VISION_MODEL_CACHE: dict = {}   # {"model": ..., "processor": ..., "backend": ...}
_VISION_LOCK = threading.Lock()

_IRIS_DIR = os.path.dirname(os.path.abspath(__file__))
MLX_VISION_MODEL_ID = os.path.join(_IRIS_DIR, "iris_vision_model")

# ── Prompt-prefix KV cache (avoids JIT recompilation on similar prompts) ─────
_kv_cache: Dict[int, Any] = {}  # hash(prompt[-2048:]) -> prompt_cache object
_KV_CACHE_MAX = 4               # max distinct cached prefixes

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

MLX_MODEL_ID  = "mlx-community/Qwen3.6-27B-4bit"
HF_MODEL_ID   = "Qwen/Qwen3.6-27B"

# ==========================================
# RAG: Retrieval-Augmented Generation Module
# ==========================================
class BookRetriever:
    """
    RAG retriever with task-aware category support.

    Chunk storage format (self.chunks is a list of dicts):
        {
            "text":        str,   # the chunk content
            "source_file": str,   # absolute path of the source file
            "category":    str,   # subfolder name, or "general" for top-level files
        }

    Directory convention:
        raw_data/                 → category "general"
        raw_data/medical/         → category "medical"
        raw_data/coding/          → category "coding"
        raw_data/finance/         → category "finance"
        raw_data/<any>/           → category "<any>"
    """

    def __init__(self, raw_data_dir="raw_data"):
        self.raw_data_dir = raw_data_dir
        self.chunks: list  = []           # list of {text, source_file, category}
        self.embeddings    = None         # tensor of all chunk embeddings
        self.embedder      = None
        self._cat_index: Dict[str, list] = {}  # category → list of chunk indices

    # ------------------------------------------------------------------ #
    #  Indexing                                                            #
    # ------------------------------------------------------------------ #
    def _cache_key(self, file_entries: list) -> str:
        """Stable hash of (path, mtime) pairs — changes when any file is added/edited."""
        parts = sorted(
            f"{path}:{os.path.getmtime(path):.3f}" for path, _ in file_entries
        )
        return hashlib.md5("\n".join(parts).encode()).hexdigest()

    def _cache_path(self) -> str:
        return os.path.join(self.raw_data_dir, ".rag_index_cache.pkl")

    def load_and_index(self):
        """Scan raw_data/ (including subdirectories) and build the vector index.

        Embeddings are persisted to .rag_index_cache.pkl so subsequent startups
        skip the expensive encode() call entirely (saves 30-120 s on large corpora).
        """
        if not RAG_AVAILABLE:
            print("[RAG] sentence-transformers not installed. RAG disabled.")
            return

        if not os.path.exists(self.raw_data_dir):
            os.makedirs(self.raw_data_dir, exist_ok=True)
            print(f"[RAG] Created {self.raw_data_dir}/. Drop markdown/txt files here.")
            return

        print("[RAG] Loading embedding model (all-MiniLM-L6-v2)...")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')

        # ── Collect (path, category) pairs ───────────────────────────────
        file_entries: list = []   # list of (path, category)
        abs_root = os.path.abspath(self.raw_data_dir)

        for ext in ["*.md", "*.txt"]:
            # Top-level files → category "general"
            for path in glob.glob(os.path.join(abs_root, ext)):
                file_entries.append((path, "general"))
            # Subdirectory files → category = subfolder name
            for path in glob.glob(os.path.join(abs_root, "**", ext), recursive=True):
                rel = os.path.relpath(path, abs_root)
                parts = rel.split(os.sep)
                category = parts[0] if len(parts) > 1 else "general"
                file_entries.append((path, category))

        # Deduplicate (recursive glob re-finds top-level files)
        seen: set = set()
        unique_entries = []
        for path, cat in file_entries:
            if path not in seen:
                seen.add(path)
                unique_entries.append((path, cat))
        file_entries = unique_entries

        if not file_entries:
            print("[RAG] No text found in raw_data/. Skipping index creation.")
            return

        categories_found = sorted({c for _, c in file_entries})
        print(f"[RAG] Found {len(file_entries)} files across categories: {categories_found}")

        # ── Try loading from disk cache first ────────────────────────────
        cache_key = self._cache_key(file_entries)
        cache_file = self._cache_path()
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "rb") as f:
                    cached = pickle.load(f)
                if cached.get("key") == cache_key:
                    self.chunks      = cached["chunks"]
                    self.embeddings  = cached["embeddings"]
                    self._cat_index  = cached["cat_index"]
                    print(f"[RAG] Loaded {len(self.chunks)} chunks from disk cache (skipped re-encode).")
                    return
                else:
                    print("[RAG] Cache stale (files changed) — rebuilding index.")
            except Exception as e:
                print(f"[RAG] Cache load failed ({e}) — rebuilding index.")

        # ── Chunk all files and record metadata ──────────────────────────
        self.chunks = []
        self._cat_index = {}

        for path, category in file_entries:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw_text = f.read()
            except Exception as e:
                print(f"[RAG] Could not read {path}: {e}")
                continue

            paragraphs = re.split(r'\n\s*\n', raw_text)
            current_chunk = ""
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                if len(current_chunk) + len(para) > 1500 and current_chunk:
                    self._add_chunk(current_chunk.strip(), path, category)
                    current_chunk = para + "\n\n"
                else:
                    current_chunk += para + "\n\n"
            if current_chunk.strip():
                self._add_chunk(current_chunk.strip(), path, category)

        if not self.chunks:
            print("[RAG] No chunks created. Check that files contain text.")
            return

        # ── Build category index ─────────────────────────────────────────
        for idx, chunk in enumerate(self.chunks):
            cat = chunk["category"]
            self._cat_index.setdefault(cat, []).append(idx)

        cat_summary = {c: len(v) for c, v in self._cat_index.items()}
        print(f"[RAG] {len(self.chunks)} chunks indexed. Distribution: {cat_summary}")

        chunk_texts = [c["text"] for c in self.chunks]
        self.embeddings = self.embedder.encode(chunk_texts, convert_to_tensor=True)
        print("[RAG] Indexing complete!")

        # ── Persist to disk so next startup skips encode() ───────────────
        try:
            with open(cache_file, "wb") as f:
                pickle.dump({
                    "key":        cache_key,
                    "chunks":     self.chunks,
                    "embeddings": self.embeddings,
                    "cat_index":  self._cat_index,
                }, f)
            print(f"[RAG] Index cached to {cache_file} — future startups will be instant.")
        except Exception as e:
            print(f"[RAG] Could not save cache ({e}) — index will rebuild next time.")

    def _add_chunk(self, text: str, source_file: str, category: str) -> None:
        self.chunks.append({"text": text, "source_file": source_file, "category": category})

    # ------------------------------------------------------------------ #
    #  Retrieval                                                           #
    # ------------------------------------------------------------------ #
    def retrieve(self, query: str, top_k: int = 3, category: Optional[str] = None) -> str:
        """
        Retrieve the top-k most relevant chunks.

        Args:
            query:    The user's query string.
            top_k:    Maximum number of chunks to return.
            category: If provided, restrict search to chunks in that category.
                      Falls back to "general" chunks, then all chunks, if the
                      requested category has too few results.
        """
        if self.embeddings is None or self.embedder is None or not self.chunks:
            return ""

        query_embedding = self.embedder.encode(query, convert_to_tensor=True)

        # ── Determine the candidate index pool ───────────────────────────
        candidate_indices: Optional[list] = None

        if category is not None:
            pool = self._cat_index.get(category, [])
            if len(pool) < max(1, top_k):
                # Too few chunks in requested category → try "general" fallback
                fallback = self._cat_index.get("general", [])
                pool = pool + [i for i in fallback if i not in set(pool)]
            if len(pool) < max(1, top_k):
                # Still not enough → use all chunks
                pool = list(range(len(self.chunks)))
                print(f"[RAG] Category '{category}' sparse; using full index.")
            candidate_indices = pool

        # ── Semantic search over the selected pool ────────────────────────
        if candidate_indices is not None:
            import torch
            subset_embeddings = self.embeddings[candidate_indices]
            hits_raw = util.semantic_search(query_embedding, subset_embeddings, top_k=top_k)[0]
            # Map subset positions back to global chunk indices
            hits_global = [
                {"corpus_id": candidate_indices[h["corpus_id"]], "score": h["score"]}
                for h in hits_raw
            ]
        else:
            hits_global = util.semantic_search(query_embedding, self.embeddings, top_k=top_k)[0]

        retrieved_texts = [self.chunks[h["corpus_id"]]["text"] for h in hits_global]
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


def load_openhermes_reasoning(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("teknium/OpenHermes-2.5", split="train")
        pairs = [(m[0]["content"].strip(), m[1]["content"].strip()) 
                 for row in ds if (m := row.get("messages")) and len(m) >= 2]
        if subset_size and len(pairs) > subset_size: 
            random.shuffle(pairs); return pairs[:subset_size]
        return pairs
    except Exception: return []

def load_math_qa(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("EleutherAI/hendrycks_math", name="algebra", split="train")
        pairs = [(row.get("problem", "").strip(), row.get("solution", "").strip()) for row in ds]
        if subset_size and len(pairs) > subset_size: 
            random.shuffle(pairs); return pairs[:subset_size]
        return pairs
    except Exception: return []

def load_code_feedback(subset_size=None):
    if not DATASETS_AVAILABLE: return []
    try:
        ds = load_dataset("m-a-p/CodeFeedback-Filtered-Instruction", split="train")
        pairs = []
        for row in ds:
            m = row.get("messages")
            if m and len(m) >= 2:
                pairs.append((m[0]["content"].strip(), m[1]["content"].strip()))
        if subset_size and len(pairs) > subset_size: 
            random.shuffle(pairs); return pairs[:subset_size]
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

_gen_config_cache: dict | None = None
_gen_config_mtime: float | None = None

def load_generation_config() -> dict:
    """Reads iris.conf once and caches it; only reloads when the file changes on disk."""
    global _gen_config_cache, _gen_config_mtime
    defaults = {
        "max_new_tokens": 256,
        "temperature": 0.7,
        "top_p": 0.9,
        "repetition_penalty": 1.0,
        "disable_rag": False,   # set true in iris.conf for speed tests
    }
    if os.path.exists(CONFIG_PATH):
        try:
            mtime = os.path.getmtime(CONFIG_PATH)
            if _gen_config_cache is None or mtime != _gen_config_mtime:
                with open(CONFIG_PATH) as f:
                    _gen_config_cache = {**defaults, **json.load(f)}
                _gen_config_mtime = mtime
            return _gen_config_cache
        except Exception:
            pass
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
            # ── MLX memory management: cap Metal JIT kernel cache at 1 GB ──
            # Without this, MLX can hoard multiple GB of compiled kernels,
            # pushing everything else into swap and causing 60s+ responses.
            try:
                import mlx.core as mx
                mx.metal.set_cache_limit(1 * 1024 * 1024 * 1024)  # 1 GB cap
                print("[iris] MLX Metal cache capped at 1 GB.")
            except Exception:
                pass
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
def generate_reply_stream(model, tokenizer, prompt_text, device=None, **kwargs):
    """
    Generator that yields text chunks one by one.

    Uses ``mlx_lm.stream_generate`` which is the correct API in mlx_lm 0.31.x.
    Sampler and repetition_penalty are applied via guarded kwargs and degrade
    gracefully on older/newer versions.
    """
    cfg   = load_generation_config()
    max_t = int(kwargs.get("max_new_tokens") or cfg["max_new_tokens"])
    temp  = float(kwargs.get("temperature")  or cfg["temperature"])
    top_p = float(kwargs.get("top_p")        or cfg["top_p"])
    rep_p = float(kwargs.get("repetition_penalty") or cfg.get("repetition_penalty", 1.0))

    if BACKEND == "mlx":
        import mlx.core as mx

        # Metal availability check
        try:
            if not mx.metal.is_available():
                print("[WARNING] MLX Metal GPU not available — running on CPU. "
                      "Ensure you are NOT under Rosetta and mlx is Apple-Silicon native.")
        except Exception:
            pass

        from mlx_lm import stream_generate

        # ── Build sampler / generation kwargs ────────────────────────────
        stream_kwargs: Dict[str, Any] = {}
        try:
            from mlx_lm.sample_utils import make_sampler
            stream_kwargs["sampler"] = make_sampler(temp=temp, top_p=top_p)
        except Exception:
            stream_kwargs["temp"]  = temp
            stream_kwargs["top_p"] = top_p
        if rep_p != 1.0:
            stream_kwargs["repetition_penalty"] = rep_p

        # ── Stream tokens ─────────────────────────────────────────────────
        # GenerationResponse.text is the incremental decoded text per step.
        try:
            for response in stream_generate(
                model=model,
                tokenizer=tokenizer,
                prompt=prompt_text,
                max_tokens=max_t,
                **stream_kwargs,
            ):
                chunk = response.text
                if chunk:
                    yield chunk
        finally:
            # Free accumulated Metal kernel cache between requests so it does
            # not pile up and push model weights into swap.
            try:
                mx.metal.clear_cache()
            except Exception:
                pass

    else:
        # HF path — non-streaming fallback
        yield generate_reply(model, tokenizer, prompt_text, device, **kwargs)


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

def generate_rag_reply(
    model,
    tokenizer,
    retriever,
    user_query: str,
    category: Optional[str] = None,
    **kwargs,
):
    """Combines RAG context with the user query before sending to the LLM.

    Args:
        category: Optional task category ("medical", "coding", "finance", …)
                  determined by the router in controller.py.  When provided,
                  retrieval is limited to chunks in that category (with graceful
                  fallback to "general" / all chunks when the category is sparse).

    Lazy-RAG behaviours controlled by iris.conf:
        rag_mode = "task_aware"  → use category filter (default)
        rag_mode = "all"         → ignore category, search all chunks
        rag_mode = "disabled"    → skip RAG entirely
    Also skips retrieval for queries shorter than 8 words.
    """
    cfg      = load_generation_config()
    rag_mode = str(cfg.get("rag_mode", "task_aware")).lower()

    short_query = len(user_query.split()) < 8

    # 1. Conditionally retrieve relevant paragraphs
    context = ""
    if rag_mode == "disabled":
        print("[RAG] Skipped — rag_mode=disabled in iris.conf.")
    elif short_query:
        print(f"[RAG] Skipped — query too short ({len(user_query.split())} words < 8).")
    else:
        # Choose retrieval strategy
        effective_category = category if rag_mode == "task_aware" else None
        context = retriever.retrieve(user_query, top_k=3, category=effective_category)
        if effective_category:
            print(f"[RAG] Retrieved from category='{effective_category}'.")

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
        {"role": "user", "content": user_query},
    ]

    # 3. Apply the native chat template
    prompt_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    # 4. Generate the reply
    return generate_reply(model, tokenizer, prompt_text, **kwargs)

def _load_vision_model():
    """
    Lazily load and cache the vision model.
    mlx_vlm imports are deferred here so the ~9 GB model only occupies
    unified memory when an image is actually being analysed.
    """
    global _VISION_MODEL_CACHE
    if _VISION_MODEL_CACHE:
        return _VISION_MODEL_CACHE

    with _VISION_LOCK:
        if _VISION_MODEL_CACHE:
            return _VISION_MODEL_CACHE

        try:
            from mlx_vlm import load as vlm_load                    # lazy
            from mlx_vlm.utils import load_config as vlm_load_config  # lazy
            print(f"[Vision] Loading MLX vision model: {MLX_VISION_MODEL_ID}...")
            model, processor = vlm_load(MLX_VISION_MODEL_ID)
            config = vlm_load_config(MLX_VISION_MODEL_ID)
            _VISION_MODEL_CACHE = {
                "model": model,
                "processor": processor,
                "config": config,
                "backend": "mlx",
            }
            print("[Vision] MLX vision model ready.")
            return _VISION_MODEL_CACHE
        except Exception as e:
            print(f"[Vision] MLX VLM load failed: {e}")
            return {}


def unload_vision_model() -> None:
    """
    Release the vision model from unified memory.
    Call this after image analysis to free the ~9 GB footprint so the
    main Phi-4 model has full access to the memory bus.
    """
    global _VISION_MODEL_CACHE
    with _VISION_LOCK:
        if not _VISION_MODEL_CACHE:
            return
        _VISION_MODEL_CACHE.clear()
        _VISION_MODEL_CACHE = {}
        try:
            import mlx.core as mx
            mx.metal.clear_cache()
        except Exception:
            pass
        print("[Vision] Vision model unloaded — unified memory reclaimed.")


def analyze_image(
    image_path: str,
    prompt: str = "Describe this image in detail.",
    unload_after: bool = True,
) -> str:
    """
    Analyse an image using the local vision model.

    Args:
        image_path:    Path to the image file.
        prompt:        Instruction passed to the vision model.
        unload_after:  If True (default), unload the vision model from
                       unified memory after the analysis so that Phi-4
                       reclaims the full 16 GB for inference.
    """
    vision = _load_vision_model()
    if not vision:
        return "[Vision] Vision model not available. Ensure mlx-vlm is installed."

    model = vision["model"]
    proc  = vision["processor"]
    conf  = vision.get("config")

    try:
        from mlx_vlm import generate as vlm_generate            # lazy
        from mlx_vlm.prompt_utils import apply_chat_template    # lazy
        formatted = apply_chat_template(proc, conf, prompt, num_images=1)
        result = vlm_generate(
            model,
            proc,
            formatted,
            image_path,
            max_tokens=512,
            verbose=False,
        )
        if hasattr(result, "text"):
            return result.text.strip()
        return str(result).strip()
    except Exception as e:
        return f"[Vision] Analysis failed: {e}"
    finally:
        if unload_after:
            unload_vision_model()


if __name__ == "__main__":
    print("\n" + "="*50)
    print(" Initializing Iris AI (Hybrid SFT + RAG Engine)")
    print("="*50)
    
    retriever = BookRetriever(raw_data_dir="raw_data")
    retriever.load_and_index()
    
    m, t = load_model()
    print(f"\n[SYSTEM] Backend: {BACKEND.upper()} | Model ready.")
    print("="*50)
    
    test_queries = [
        "Hello! How are you?",
        "What is the main topic of chapter 1?"
    ]
    
    for q in test_queries:
        print(f"\nUser: {q}")
        reply = generate_rag_reply(m, t, retriever, q)
        print(f"Iris: {reply}")