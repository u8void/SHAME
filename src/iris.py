"""
iris.py — Local GGUF Multi-Model Routing System for Iris AI
==========================================================
Replaces the single-model inference engine with a GGUF router.
Powered by llama-cpp-python. Sequential loading frees RAM.
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
import time
import gc
import warnings
import concurrent.futures
from enum import Enum
from typing import Optional, Tuple, Dict, Any, Generator, List, Union

warnings.filterwarnings("ignore")

try:
    from sentence_transformers import SentenceTransformer, util
    RAG_AVAILABLE = True
except Exception as e:
    print(f"[WARNING] RAG disabled due to library error: {e}")
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

# Import llama_cpp and syntax checker
from llama_cpp import Llama
from .syntax_checker import check_syntax

# ── Model Registry ────────────────────────────────────────────────────────────

class ModelRole(str, Enum):
    TRIAGE    = "triage"     # Qwen2.5-3B-Instruct — fast triage + conversational answers
    ROUTER    = "router"     # Qwen2.5-Coder-7B-Instruct — JSON action / routing
    MATH      = "math"       # Qwen2.5-Math-7B-Instruct
    CODE      = "code"       # DeepSeek-R1-Distill-Qwen-7B
    REASONING = "reasoning"  # DeepSeek-R1-Distill-Qwen-14B
    GENERAL   = "general"    # DeepSeek-R1-Distill-Qwen-14B

class TaskType(str, Enum):
    CODING_SIMPLE  = "coding_simple"
    CODING_COMPLEX = "coding_complex"
    MATH           = "math"
    REASONING      = "reasoning"
    GENERAL        = "general"

ROLE_CTX = {
    ModelRole.TRIAGE:    2048,
    ModelRole.ROUTER:    2048,
    ModelRole.MATH:      4096,
    ModelRole.CODE:      4096,   # Reduced from 8192 — less KV-cache pressure
    ModelRole.REASONING: 4096,   # Reduced from 8192 — less KV-cache pressure
    ModelRole.GENERAL:   4096,
}

ROLE_MAX_TOKENS = {
    ModelRole.TRIAGE:    512,
    ModelRole.ROUTER:    256,
    ModelRole.MATH:      4096,
    ModelRole.CODE:      3072,   # Capped to fit within 4096 n_ctx
    ModelRole.REASONING: 3072,   # Capped to fit within 4096 n_ctx
    ModelRole.GENERAL:   4096,
}

TASK_TO_MODEL = {
    TaskType.MATH:           ModelRole.MATH,
    TaskType.CODING_SIMPLE:  ModelRole.CODE,
    TaskType.CODING_COMPLEX: ModelRole.CODE,
    TaskType.REASONING:      ModelRole.REASONING,
    TaskType.GENERAL:        ModelRole.GENERAL,
}

TASK_TO_RAG_CATEGORY = {
    TaskType.CODING_SIMPLE:  "coding",
    TaskType.CODING_COMPLEX: "coding",
    TaskType.MATH:           "math",
    TaskType.REASONING:      "reasoning",
    TaskType.GENERAL:        "general",
}

# Signals that Stage 3 deep review is warranted (truly complex / multi-model output tasks)
_DEEP_REVIEW_SIGNALS = {
    "kernel", "bootloader", "operating system", "emulator", "qemu",
    "compiler", "interpreter", "game engine", "firmware", "driver",
    "multi-file", "multiple files", "full project", "entire project",
    "pong", "game", "asm", "assembly", "nasm",
}

# System Prompt Constants
IRIS_IDENTITY = (
    "You are Iris AI. Answer directly without introducing yourself or saying 'I am Iris AI' at the start. "
    "Never mention underlying model names (e.g., MiMo, Xiaomi, DeepSeek) or pipeline architecture. "
    "If asked who you are, identify as Iris AI."
)

MATH_SYSTEM_PROMPT = (
    "You are the Iris AI Math Core. Solve mathematical/algorithmic problems step-by-step. "
    "Use precise notation."
)

CODE_SYSTEM_PROMPT = (
    "You are the Iris AI Coding Specialist. Generate clean, fully working, and production-quality code. "
    "Make sure that any code you write or fix is 100% correct, handles all edge cases, compiles successfully, "
    "and has absolutely no syntax errors, logical bugs, or defects. "
    "CRITICAL: Do NOT include comments in your code.\n\n"
    "After the closing of the code block and its file_card tag, you MUST provide a concise explanation of the code, "
    "its key features, and clear instructions on how to compile/run it.\n\n"
    "RULE — FILE CARDS:\n"
    "When you produce a response that contains a complete, self-contained file (not just a snippet "
    "or a fragment), you MUST emit a special machine-readable tag immediately after the closing "
    "triple-backtick of that code block. The tag looks like this:\n"
    "<file_card filename=\"FILENAME.EXT\" lang=\"LANGUAGE\"></file_card>\n\n"
    "Guidelines for choosing the filename:\n"
    "- Make it descriptive of what the file actually does (e.g. 'weather_dashboard.html', 'user_auth.py', 'api_client.js').\n"
    "- Use the correct extension for the language (py, js, ts, html, css, json, sh, md, etc.).\n"
    "- Never use generic names like 'code.py' or 'script.js'.\n"
    "- Use snake_case for Python/shell, camelCase or kebab-case for JS/HTML as appropriate.\n\n"
    "Guidelines for choosing lang:\n"
    "- Must exactly match the language identifier used in the opening fence (e.g. python, javascript, typescript, html, css, bash, json, etc.).\n\n"
    "A complete file means: the code could be saved as-is to disk and run / opened without needing "
    "the user to add missing imports, function bodies, class definitions, or boilerplate. "
    "Do not emit file_card for snippets, partial code, or pseudocode."
)

CODE_REVIEWER_SYSTEM_PROMPT = (
    "You are the Iris AI Lead Engineering Reviewer. Review the draft code thoroughly. "
    "Your main goal is to identify and fix any hidden bugs, syntax errors, edge cases, type issues, or logical defects. "
    "Return the final code directly, fully optimized, robust, and 100% correct. No introductory notes or filler before the code block. "
    "CRITICAL: Wrap code in markdown blocks (e.g. ```python ... ```). Do NOT write any comments in code.\n\n"
    "After the closing of the code block and its file_card tag, you MUST provide a concise explanation of the code, "
    "its features, what optimizations/bug fixes were made, and clear step-by-step instructions on how to compile and run the code.\n\n"
    "RULE — FILE CARDS:\n"
    "When you produce a response that contains a complete, self-contained file (not just a snippet "
    "or a fragment), you MUST emit a special machine-readable tag immediately after the closing "
    "triple-backtick of that code block. The tag looks like this:\n"
    "<file_card filename=\"FILENAME.EXT\" lang=\"LANGUAGE\"></file_card>\n\n"
    "Guidelines for choosing the filename:\n"
    "- Make it descriptive of what the file actually does (e.g. 'weather_dashboard.html', 'user_auth.py', 'api_client.js').\n"
    "- Use the correct extension for the language (py, js, ts, html, css, json, sh, md, etc.).\n"
    "- Never use generic names like 'code.py' or 'script.js'.\n"
    "- Use snake_case for Python/shell, camelCase or kebab-case for JS/HTML as appropriate.\n\n"
    "Guidelines for choosing lang:\n"
    "- Must exactly match the language identifier used in the opening fence (e.g. python, javascript, typescript, html, css, bash, json, etc.).\n\n"
    "A complete file means: the code could be saved as-is to disk and run / opened without needing "
    "the user to add missing imports, function bodies, class definitions, or boilerplate. "
    "Do not emit file_card for snippets, partial code, or pseudocode."
)

REASONING_SYSTEM_PROMPT = (
    "You are the Iris AI Reasoning Specialist. Think step-by-step using deep reasoning. "
    "State your reasoning process before the final answer."
)

GENERAL_SYSTEM_PROMPT = (
    f"{IRIS_IDENTITY}\nProvide a helpful, direct response. "
    "CRITICAL: Do NOT include comments in code blocks."
)

_VISION_MODEL_CACHE: dict = {}
_VISION_LOCK = threading.Lock()
_HERE = os.path.dirname(os.path.abspath(__file__))
MLX_VISION_MODEL_ID = os.path.join(_HERE, "iris_vision_model")
CONFIG_PATH = os.path.join(_HERE, "config", "iris.conf")

# Registry and loader state
_active_model: Dict[str, Any] = {}

# Triage model — loaded once and kept resident (3B, ~2 GB RAM)
_triage_llm: Optional[Llama] = None
_triage_lock = threading.Lock()

def unload_model():
    global _active_model
    if not _active_model:
        return
    role = _active_model["role"]
    llm = _active_model.pop("llm")
    _active_model = {}
    try:
        llm.reset()
    except Exception:
        pass
    del llm
    gc.collect()
    print(f"[Iris] Unloaded {role.value}.")

def _warmup(llm: Llama) -> None:
    try:
        llm.create_chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
            temperature=0.2,
        )
    except Exception:
        pass

def _get_or_load_triage() -> Llama:
    """Return the resident triage model, loading it once on first call."""
    global _triage_llm
    if _triage_llm is not None:
        return _triage_llm
    with _triage_lock:
        if _triage_llm is not None:  # double-checked locking
            return _triage_llm
        cfg = load_generation_config()
        models_dict = cfg.get("models", {})
        filename = models_dict.get("triage", "iris-triage.gguf")
        model_path = os.path.join(_HERE, "models", filename)
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Triage model not found: {model_path}"
            )
        print(f"[Iris] Loading triage model (resident): {filename}...")
        _triage_llm = Llama(
            model_path=model_path,
            n_ctx=ROLE_CTX[ModelRole.TRIAGE],
            n_gpu_layers=cfg.get("n_gpu_layers", -1),
            n_threads=cfg.get("n_threads", 8),
            use_mmap=True,
            use_mlock=False,
            flash_attn=True,
            n_batch=1024,
            verbose=False,
        )
        print("[Iris] Triage model ready (resident — stays loaded between calls).")
        return _triage_llm

def load_model(role: Optional[ModelRole] = None) -> Llama:
    global _active_model
    if role is None:
        role = ModelRole.GENERAL

    if _active_model:
        if _active_model["role"] == role:
            return _active_model["llm"]
        unload_model()

    cfg = load_generation_config()
    models_dict = cfg.get("models", {})
    filename = models_dict.get(role.value)
    if not filename:
        defaults = {
            "triage":    "iris-triage.gguf",
            "router":    "iris-router.gguf",
            "math":      "iris-math.gguf",
            "code":      "iris-code.gguf",
            "reasoning": "iris-reasoning.gguf",
            "general":   "iris-general.gguf"
        }
        filename = defaults[role.value]

    model_path = os.path.join(_HERE, "models", filename)
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"GGUF model file not found for role '{role.value}': expected at {model_path}. Please place it there.")

    print(f"[Iris] Loading {role.value} ({filename})...")

    n_ctx_ceiling = cfg.get("n_ctx", 4096)
    n_ctx_val = min(ROLE_CTX.get(role, 4096), n_ctx_ceiling)
    n_gpu_layers = cfg.get("n_gpu_layers", -1)
    n_threads = cfg.get("n_threads", 8)

    llm = Llama(
        model_path=model_path,
        n_ctx=n_ctx_val,
        n_gpu_layers=n_gpu_layers,
        n_threads=n_threads,
        use_mmap=True,
        use_mlock=False,
        flash_attn=True,
        n_batch=1024,   # Increased from 512 — faster prompt prefill
        verbose=False,
    )

    if role in (ModelRole.REASONING, ModelRole.CODE, ModelRole.GENERAL):
        _warmup(llm)

    _active_model = {"role": role, "llm": llm}
    return llm

# ==========================================
# RAG: Retrieval-Augmented Generation Module
# ==========================================
class BookRetriever:
    def __init__(self, raw_data_dir="raw_data"):
        self.raw_data_dir = raw_data_dir
        self.chunks: list = []
        self.embeddings = None
        self.embedder = None
        self._cat_index: Dict[str, list] = {}

    def _cache_key(self, file_entries: list) -> str:
        parts = sorted(f"{path}:{os.path.getmtime(path):.3f}" for path, _ in file_entries)
        return hashlib.md5("\n".join(parts).encode()).hexdigest()

    def _cache_path(self) -> str:
        return os.path.join(self.raw_data_dir, ".rag_index_cache.pkl")

    def load_and_index(self):
        if not RAG_AVAILABLE:
            print("[RAG] sentence-transformers not installed. RAG disabled.")
            return

        if not os.path.exists(self.raw_data_dir):
            os.makedirs(self.raw_data_dir, exist_ok=True)
            print(f"[RAG] Created {self.raw_data_dir}/. Drop markdown/txt files here.")
            return

        print("[RAG] Loading embedding model (all-MiniLM-L6-v2)...")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')

        file_entries: list = []
        abs_root = os.path.abspath(self.raw_data_dir)

        for ext in ["*.md", "*.txt"]:
            for path in glob.glob(os.path.join(abs_root, ext)):
                file_entries.append((path, "general"))
            for path in glob.glob(os.path.join(abs_root, "**", ext), recursive=True):
                rel = os.path.relpath(path, abs_root)
                parts = rel.split(os.sep)
                category = parts[0] if len(parts) > 1 else "general"
                file_entries.append((path, category))

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

        cache_key = self._cache_key(file_entries)
        cache_file = self._cache_path()
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "rb") as f:
                    cached = pickle.load(f)
                if cached.get("key") == cache_key:
                    self.chunks = cached["chunks"]
                    self.embeddings = cached["embeddings"]
                    self._cat_index = cached["cat_index"]
                    print(f"[RAG] Loaded {len(self.chunks)} chunks from disk cache (skipped re-encode).")
                    return
                else:
                    print("[RAG] Cache stale (files changed) — rebuilding index.")
            except Exception as e:
                print(f"[RAG] Cache load failed ({e}) — rebuilding index.")

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

        for idx, chunk in enumerate(self.chunks):
            cat = chunk["category"]
            self._cat_index.setdefault(cat, []).append(idx)

        cat_summary = {c: len(v) for c, v in self._cat_index.items()}
        print(f"[RAG] {len(self.chunks)} chunks indexed. Distribution: {cat_summary}")

        chunk_texts = [c["text"] for c in self.chunks]
        self.embeddings = self.embedder.encode(chunk_texts, convert_to_tensor=True)
        print("[RAG] Indexing complete!")

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

    def retrieve(self, query: str, top_k: int = 3, category: Optional[str] = None) -> str:
        if self.embeddings is None or self.embedder is None or not self.chunks:
            return ""

        query_embedding = self.embedder.encode(query, convert_to_tensor=True)
        candidate_indices: Optional[list] = None

        if category is not None:
            pool = self._cat_index.get(category, [])
            if len(pool) < max(1, top_k):
                fallback = self._cat_index.get("general", [])
                pool = pool + [i for i in fallback if i not in set(pool)]
            if len(pool) < max(1, top_k):
                pool = list(range(len(self.chunks)))
                print(f"[RAG] Category '{category}' sparse; using full index.")
            candidate_indices = pool

        if candidate_indices is not None:
            subset_embeddings = self.embeddings[candidate_indices]
            hits_raw = util.semantic_search(query_embedding, subset_embeddings, top_k=top_k)[0]
            hits_global = [
                {"corpus_id": candidate_indices[h["corpus_id"]], "score": h["score"]}
                for h in hits_raw
            ]
        else:
            hits_global = util.semantic_search(query_embedding, self.embeddings, top_k=top_k)[0]

        retrieved_texts = [self.chunks[h["corpus_id"]]["text"] for h in hits_global]
        return "\n\n---\n\n".join(retrieved_texts)


def _detect_backend() -> str:
    return "gguf"

BACKEND = _detect_backend()

class _Device:
    def __init__(self, type_: str):
        self.type = type_
    def __repr__(self):
        return f"device(type='{self.type}')"

def get_device(force_cpu=False):
    return _Device("cpu" if force_cpu else "gpu")

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

# Dataset Loaders
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

_gen_config_cache: dict | None = None
_gen_config_mtime: float | None = None

def load_generation_config() -> dict:
    global _gen_config_cache, _gen_config_mtime
    defaults = {
        "max_new_tokens": 256,
        "temperature": 0.7,
        "top_p": 0.9,
        "repetition_penalty": 1.0,
        "disable_rag": False,
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

# Vision Helpers
def _load_vision_model():
    global _VISION_MODEL_CACHE
    if _VISION_MODEL_CACHE:
        return _VISION_MODEL_CACHE

    with _VISION_LOCK:
        if _VISION_MODEL_CACHE:
            return _VISION_MODEL_CACHE

        cfg = load_generation_config()
        models_dict = cfg.get("models", {})
        
        vision_file = models_dict.get("vision", "iris-vision.gguf")
        clip_file = models_dict.get("clip", "iris-clip.bin")
        
        vision_path = os.path.join(_HERE, "models", vision_file)
        clip_path = os.path.join(_HERE, "models", clip_file)

        # 1. Try GGUF vision backend if files exist
        if os.path.exists(vision_path) and os.path.exists(clip_path):
            print(f"[Vision] Loading GGUF vision model: {vision_file} with {clip_file}...")
            try:
                from llama_cpp.llama_chat_format import Llava15ChatHandler
                n_gpu_layers = cfg.get("n_gpu_layers", -1)
                n_threads = cfg.get("n_threads", 8)
                
                chat_handler = Llava15ChatHandler(clip_model_path=clip_path, verbose=False)
                model = Llama(
                    model_path=vision_path,
                    chat_handler=chat_handler,
                    n_ctx=2048,
                    n_gpu_layers=n_gpu_layers,
                    n_threads=n_threads,
                    verbose=False
                )
                _VISION_MODEL_CACHE = {
                    "model": model,
                    "backend": "gguf",
                }
                print("[Vision] GGUF vision model ready.")
                return _VISION_MODEL_CACHE
            except Exception as e:
                print(f"[Vision] GGUF VLM load failed: {e}. Falling back to MLX...")

        # 2. Fall back to MLX vision backend
        try:
            from mlx_vlm import load as vlm_load
            from mlx_vlm.utils import load_config as vlm_load_config
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
    global _VISION_MODEL_CACHE
    with _VISION_LOCK:
        if not _VISION_MODEL_CACHE:
            return
        backend = _VISION_MODEL_CACHE.get("backend")
        model = _VISION_MODEL_CACHE.pop("model")
        _VISION_MODEL_CACHE.clear()
        _VISION_MODEL_CACHE = {}

        if backend == "gguf":
            del model
        else:
            try:
                import mlx.core as mx
                mx.clear_cache()
            except Exception:
                pass
        gc.collect()
        print(f"[Vision] Vision model ({backend}) unloaded — unified memory reclaimed.")

def analyze_image(
    image_path: str,
    prompt: str = "Describe this image in detail.",
    unload_after: bool = True,
) -> str:
    vision = _load_vision_model()
    if not vision:
        return "[Vision] Vision model not available. Please ensure GGUF or MLX VLM files are present."

    backend = vision.get("backend")
    model = vision["model"]

    if backend == "gguf":
        try:
            import base64
            with open(image_path, "rb") as f:
                img_data = f.read()
            img_b64 = base64.b64encode(img_data).decode("utf-8")
            
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                    ]
                }
            ]
            
            res = model.create_chat_completion(
                messages=messages,
                max_tokens=512,
            )
            return res["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return f"[Vision] GGUF Analysis failed: {e}"
        finally:
            if unload_after:
                unload_vision_model()

    elif backend == "mlx":
        proc  = vision["processor"]
        conf  = vision.get("config")

        try:
            from mlx_vlm import generate as vlm_generate
            from mlx_vlm.prompt_utils import apply_chat_template
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
            return f"[Vision] MLX Analysis failed: {e}"
        finally:
            if unload_after:
                unload_vision_model()

    return "[Vision] Unknown backend."

# Triage & Harness helpers

def fallback_classify(query: str) -> Optional[TaskType]:
    q = query.lower()
    
    if re.search(r'\b\w+\.(c|cpp|h|py|js|ts|html|css|sh|java|go|rs|json|yml|yaml|asm|s|md)\b', q):
        return TaskType.CODING_COMPLEX
        
    code_keywords = {
        "code", "coding", "program", "programming", "compile", "compiler",
        "debug", "debugging", "refactor", "refactoring", "script", "scripts",
        "kernel", "make", "makefile", "gcc", "clang", "qemu", "gdb", "vga", "driver", "bootloader",
        "assembly", "nasm", "masm", "link", "linker", "pong", "game", "controls", "keyboard",
        "function", "variable", "class", "struct", "method", "loop", "array", "pointer",
        "database", "sql", "api", "json", "xml", "html", "css", "docker", "git", "github",
        "repo", "repository", "commit", "push", "pull", "merge", "conflict"
    }
    
    complex_keywords = {"kernel", "gcc", "clang", "qemu", "driver", "bootloader", "pong", "game", "make", "makefile"}
    
    for kw in code_keywords:
        if re.search(rf"\b{re.escape(kw)}\b", q):
            if kw in complex_keywords or len(q) > 500:  # Raised from 300 — prefer simple path
                return TaskType.CODING_COMPLEX
            else:
                return TaskType.CODING_SIMPLE

    math_keywords = {
        "math", "mathematics", "equation", "equations", "formula", "formulas",
        "derivative", "derivatives", "integral", "integrals", "calculus",
        "algebra", "geometry", "trigonometry", "matrix", "matrices", "vector", "vectors",
        "theorem", "proof", "prove", "probability", "statistics", "combinatorics"
    }
    for kw in math_keywords:
        if re.search(rf"\b{re.escape(kw)}\b", q):
            return TaskType.MATH
            
    if re.search(r'[\d\s]+[\+\-\*\/=]+[\d\s]+', q):
        return TaskType.MATH

    reasoning_keywords = {
        "logic", "logical", "puzzle", "puzzles", "riddle", "riddles",
        "reasoning", "system design", "architecture"
    }
    for kw in reasoning_keywords:
        if re.search(rf"\b{re.escape(kw)}\b", q):
            return TaskType.REASONING

    return None

def classify_task(user_query: str, history: list[dict]) -> Tuple[Optional[TaskType], Optional[str]]:
    t_type = fallback_classify(user_query)
    if t_type is not None:
        return t_type, None

    triage_prompt = (
        "You are the Iris AI query router.\n"
        "If the user asks a conversational/general knowledge question, do NOT output any tags; answer directly.\n\n"
        "Otherwise, output EXACTLY ONE tag and NOTHING ELSE. DO NOT answer the query yourself:\n"
        "- [TASK_TYPE: coding_simple] (for simple coding questions, explaining code, syntax, basic functions, single script edits)\n"
        "- [TASK_TYPE: coding_complex] (for large projects, writing games, custom emulators/drivers, multi-file codebases, or complex logic coding)\n"
        "- [TASK_TYPE: math] (for equations, proofs, algorithmic derivations)\n"
        "- [TASK_TYPE: reasoning] (for deep logic puzzles, architecture design, long analysis)\n\n"
        "CRITICAL: If the query mentions writing a complete game (e.g. Pong), building compilers, operating system "
        "bootloaders, or complex hardware simulation, output [TASK_TYPE: coding_complex]."
    )

    minimized_history = []
    if history:
        last_msg = history[-1]
        content = last_msg.get("content", "")
        content_clean = re.sub(r'```[\s\S]*?```', '```\n[code omitted]\n```', content)
        if len(content_clean) > 500:
            content_clean = content_clean[:500] + "\n...[truncated]"
        minimized_history.append({"role": last_msg.get("role"), "content": content_clean})

    triage_messages = [{"role": "system", "content": triage_prompt}]
    for msg in minimized_history:
        triage_messages.append({"role": msg["role"], "content": msg["content"]})
    triage_messages.append({"role": "user", "content": user_query})

    llm = _get_or_load_triage()   # resident model — no load/unload overhead
    res = llm.create_chat_completion(
        messages=triage_messages,
        max_tokens=ROLE_MAX_TOKENS.get(ModelRole.TRIAGE, 512),
        temperature=0.2,
    )
    triage_answer = res["choices"][0]["message"]["content"]
    # Triage model stays resident — intentionally no unload_model() call here

    if re.search(r'\[\s*task_type:\s*coding_complex\s*\]', triage_answer, re.IGNORECASE):
        return TaskType.CODING_COMPLEX, None
    if re.search(r'\[\s*task_type:\s*coding_simple\s*\]', triage_answer, re.IGNORECASE):
        return TaskType.CODING_SIMPLE, None
    if re.search(r'\[\s*task_type:\s*coding\s*\]', triage_answer, re.IGNORECASE):
        return TaskType.CODING_SIMPLE, None
    if re.search(r'\[\s*task_type:\s*math\s*\]', triage_answer, re.IGNORECASE):
        return TaskType.MATH, None
    if re.search(r'\[\s*task_type:\s*reasoning\s*\]', triage_answer, re.IGNORECASE):
        return TaskType.REASONING, None
    if re.search(r'\[\s*task_type:\s*general\s*\]', triage_answer, re.IGNORECASE):
        return TaskType.GENERAL, None

    return None, triage_answer

def is_continuation_query(query: str, history: List[Dict[str, str]]) -> bool:
    if not history:
        return False
    q = query.strip().lower().strip("?.!,;:\"'")
    continuation_words = {
        "continue", "keep going", "go on", "proceed", "finish", 
        "finish the code", "finish code", "more", "complete", "next"
    }
    is_intent = False
    if q in continuation_words:
        is_intent = True
    elif re.match(r'^(continue|finish|complete)\s+(writing|code|the\s+code|generating|developing)$', q):
        is_intent = True

    if not is_intent:
        return False

    has_code = False
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if "```" in content or "<file_card" in content or "<thinking" in content or "<think>" in content:
                has_code = True
                break
    return has_code

def detect_language(text: str) -> Optional[str]:
    from .syntax_checker import extract_code_blocks
    blocks = extract_code_blocks(text)
    if blocks:
        lang = blocks[0][0]
        if lang != "unknown":
            return lang
    return None

def quality_guard(text: str) -> str:
    text = re.sub(
        r"(?i)(I('m| am) (DeepSeek|Qwen|a large language model|an AI language model)[^.]*\.?\s*)",
        "",
        text
    ).strip()
    sentences = re.split(r'(?<=[.!?])\s+', text)
    clean = []
    for s in sentences:
        if re.search(r'(MigrationBuilder|nakalista|\ud795|\ufa4c|#+#|http(?:http|https))', s, re.IGNORECASE):
            break
        clean.append(s)
    return " ".join(clean).strip() or text

def optimize_messages(history: list[dict], user_query: str, max_messages: int = 6) -> list[dict]:
    if not history:
        return [{"role": "user", "content": user_query}]
    recent = history[-max_messages:]
    optimized = []
    for i, msg in enumerate(recent):
        content = msg.get("content", "")
        # Only strip code blocks from turns older than the last user and assistant turn (index len(recent) - 2)
        if i < len(recent) - 2:
            content = re.sub(r'```[\s\S]*?```', '```\n[code omitted]\n```', content)
            if len(content) > 1000:
                content = content[:1000] + "\n...[truncated]"
        optimized.append({"role": msg["role"], "content": content})
    optimized.append({"role": "user", "content": user_query})
    return optimized

# Streaming processing engine
def stream_with_thinking_handling(stream, role: ModelRole, task_type: TaskType, raw_collector: Optional[list] = None):
    strip_thinking = task_type in (TaskType.CODING_SIMPLE, TaskType.MATH)
    in_thinking = False
    buffer = ""

    for chunk in stream:
        choices = chunk.get("choices", [])
        if not choices:
            continue
        choice = choices[0]
        token = choice.get("delta", {}).get("content", "")
        if not token:
            continue

        if raw_collector is not None:
            raw_collector.append(token)

        if not strip_thinking:
            yield {"type": "token", "content": token}
            continue

        buffer += token
        while True:
            if not in_thinking:
                if "<think>" in buffer:
                    idx = buffer.index("<think>")
                    before = buffer[:idx]
                    if before:
                        yield {"type": "token", "content": before}
                    yield {"type": "status", "content": "Thinking..."}
                    in_thinking = True
                    buffer = buffer[idx + len("<think>"):]
                    continue
                
                partial_matched = False
                for i in range(1, len("<think>")):
                    if buffer.endswith("<think>"[:i]):
                        before = buffer[:-i]
                        if before:
                            yield {"type": "token", "content": before}
                        buffer = buffer[-i:]
                        partial_matched = True
                        break
                if partial_matched:
                    break
                
                yield {"type": "token", "content": buffer}
                buffer = ""
                break
            else:
                if "</think>" in buffer:
                    idx = buffer.index("</think>")
                    in_thinking = False
                    buffer = buffer[idx + len("</think>"):]
                    continue
                
                partial_matched = False
                for i in range(1, len("</think>")):
                    if buffer.endswith("</think>"[:i]):
                        buffer = buffer[-i:]
                        partial_matched = True
                        break
                if partial_matched:
                    break
                
                buffer = ""
                break

    if buffer and not in_thinking:
        yield {"type": "token", "content": buffer}

def generate_stream(
    role: ModelRole,
    messages: list[dict],
    system_prompt: str,
    max_tokens: Optional[int] = None,
    temperature: float = 0.2
) -> Generator[dict, None, None]:
    llm = load_model(role)
    if max_tokens is None:
        max_tokens = ROLE_MAX_TOKENS.get(role, 4096)

    full_messages = [{"role": "system", "content": system_prompt}] + messages

    for loop_idx in range(5):
        stream = llm.create_chat_completion(
            messages=full_messages,
            stream=True,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        loop_content = ""
        finish_reason = "stop"

        for chunk in stream:
            choices = chunk.get("choices", [])
            if not choices:
                continue
            choice = choices[0]
            token = choice.get("delta", {}).get("content", "")
            if token:
                loop_content += token
                yield {"type": "token", "content": token}
            if "finish_reason" in choice and choice["finish_reason"]:
                finish_reason = choice["finish_reason"]

        if finish_reason == "length":
            full_messages.append({"role": "assistant", "content": loop_content})
            if role in (ModelRole.CODE, ModelRole.REASONING):
                instruct = "Continue exactly where you left off, from the very next character. Do not repeat anything, do not write intro text or markdown blocks, just the raw continuation."
            else:
                instruct = "Continue exactly where you left off, from the very next character. Do not repeat anything."
            full_messages.append({"role": "user", "content": instruct})
        else:
            break

# Public entrypoint
def ask_stream(user_query: str, history: list[dict], retriever=None, force_role: Optional[ModelRole] = None) -> Generator[dict, None, None]:
    if force_role is not None:
        if isinstance(force_role, str):
            force_role = ModelRole(force_role)
            
        yield {"type": "status", "content": f"Testing forced model role: {force_role.value}..."}
        
        context = ""
        if retriever is not None and len(user_query.split()) >= 8:
            context = retriever.retrieve(user_query, top_k=3, category="general")
            
        system_prompt = GENERAL_SYSTEM_PROMPT
        if force_role == ModelRole.CODE:
            system_prompt = CODE_SYSTEM_PROMPT
        elif force_role == ModelRole.MATH:
            system_prompt = MATH_SYSTEM_PROMPT
        elif force_role == ModelRole.REASONING:
            system_prompt = REASONING_SYSTEM_PROMPT
        elif force_role == ModelRole.ROUTER:
            system_prompt = "You are the Iris AI Router. Output actions in JSON format."
            
        if context:
            system_prompt = f"REFERENCE EXCERPT:\n{context}\n\n{system_prompt}"
            
        optimized = optimize_messages(history, user_query)
        llm = load_model(force_role)
        
        stream = llm.create_chat_completion(
            messages=[{"role": "system", "content": system_prompt}] + optimized,
            stream=True,
            max_tokens=ROLE_MAX_TOKENS.get(force_role, 4096),
            temperature=0.2 if force_role != ModelRole.REASONING else 0.5,
        )
        
        full_content = ""
        raw_collector = []
        for chunk_event in stream_with_thinking_handling(stream, force_role, TaskType.GENERAL, raw_collector):
            yield chunk_event
            if chunk_event["type"] == "token":
                full_content += chunk_event["content"]
                
        unload_model()
        
        cleaned = quality_guard(full_content)
        if cleaned != full_content:
            yield {"type": "clear"}
            yield {"type": "token", "content": cleaned}
            
        yield {"type": "raw_response", "content": cleaned}
        return

    is_continuation = is_continuation_query(user_query, history)

    if is_continuation:
        yield {"type": "status", "content": "Resuming code generation..."}
        task_type = TaskType.CODING_COMPLEX
    else:
        yield {"type": "status", "content": "Analyzing query..."}
        task_type, direct_answer = classify_task(user_query, history)
        if task_type is None:
            if direct_answer:
                yield {"type": "token", "content": direct_answer}
            return
        yield {"type": "status", "content": f"Task: {task_type.value.upper()}..."}

    context = ""
    if retriever is not None and len(user_query.split()) >= 8:
        category = TASK_TO_RAG_CATEGORY.get(task_type)
        context = retriever.retrieve(user_query, top_k=3, category=category)

    # Dispatch to Tier pipelines
    if task_type == TaskType.CODING_COMPLEX:
        # Tier 3 — Three-stage pipeline
        raw_reasoning = ""
        raw_code = ""

        # Stage 3 review is expensive — only run it for truly complex outputs
        _q_lower = user_query.lower()
        needs_review = any(sig in _q_lower for sig in _DEEP_REVIEW_SIGNALS)

        # Stage 1 — Deep reasoning (silent)
        if is_continuation:
            raw_reasoning = "Continuation requested. Continuing from the previous truncated code."
        else:
            yield {"type": "status", "content": "Stage 1 — Deep reasoning..."}
            llm_reasoning = load_model(ModelRole.REASONING)
            
            reasoning_prompt = REASONING_SYSTEM_PROMPT
            if context:
                reasoning_prompt = f"REFERENCE EXCERPT:\n{context}\n\n{REASONING_SYSTEM_PROMPT}"
                
            optimized = optimize_messages(history, user_query)
            reasoning_messages = [{"role": "system", "content": reasoning_prompt}] + optimized

            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(
                llm_reasoning.create_chat_completion,
                messages=reasoning_messages,
                stream=False,
                max_tokens=ROLE_MAX_TOKENS.get(ModelRole.REASONING, 8192),
                temperature=0.6,
            )

            while not future.done():
                yield {"type": "status", "content": "Stage 1 — Deep reasoning..."}
                for _ in range(20):
                    if future.done():
                        break
                    time.sleep(0.1)

            res = future.result()
            raw_reasoning = res["choices"][0]["message"]["content"]
            unload_model()

        # Stage 2 — Code generation (streamed live)
        yield {"type": "status", "content": "Stage 2 — Writing code..."}
        llm_code = load_model(ModelRole.CODE)

        code_sys_prompt = CODE_SYSTEM_PROMPT
        if context:
            code_sys_prompt = f"REFERENCE EXCERPT:\n{context}\n\n{CODE_SYSTEM_PROMPT}"
        if is_continuation:
            code_sys_prompt += (
                "\n\nIMPORTANT: The previous code was truncated. Please continue writing the code exactly "
                "from where it cut off in the previous turn. Do NOT rewrite the entire file from the beginning. "
                "Start writing immediately from the next character/line, without introducing it, and do not wrap it "
                "in new markdown code blocks unless you are continuing inside one."
            )

        optimized = optimize_messages(history, user_query)
        code_messages = [
            *optimized[:-1],
            {"role": "user", "content": f"User Query: {user_query}\n\nArchitecture/Plan:\n{raw_reasoning[-8000:]}"}
        ]

        stream2 = llm_code.create_chat_completion(
            messages=[{"role": "system", "content": code_sys_prompt}] + code_messages,
            stream=True,
            max_tokens=ROLE_MAX_TOKENS.get(ModelRole.CODE, 8192),
            temperature=0.2,
        )

        for chunk_event in stream_with_thinking_handling(stream2, ModelRole.CODE, TaskType.CODING_COMPLEX):
            yield chunk_event
            if chunk_event["type"] == "token":
                raw_code += chunk_event["content"]

        unload_model()

        if needs_review:
            # Stage 3 — Code review (streamed live, only for truly complex tasks)
            yield {"type": "clear"}
            yield {"type": "status", "content": "Stage 3 — Reviewing and optimizing..."}
            llm_review = load_model(ModelRole.REASONING)

            reviewer_sys_prompt = CODE_REVIEWER_SYSTEM_PROMPT
            if context:
                reviewer_sys_prompt = f"REFERENCE EXCERPT:\n{context}\n\n{CODE_REVIEWER_SYSTEM_PROMPT}"
            if is_continuation:
                reviewer_sys_prompt += (
                    "\n\nIMPORTANT: The previous code was truncated. Please only review and output the final code continuation, "
                    "beginning exactly from where the previous code cut off. Do NOT rewrite the entire file from the beginning. "
                    "Start writing the code immediately from the next character/line without introductory text."
                )

            review_messages = [
                *optimized[:-1],
                {"role": "user", "content": f"User Query: {user_query}\n\nDraft Code:\n{raw_code[-8000:]}"}
            ]

            stream3 = llm_review.create_chat_completion(
                messages=[{"role": "system", "content": reviewer_sys_prompt}] + review_messages,
                stream=True,
                max_tokens=ROLE_MAX_TOKENS.get(ModelRole.REASONING, 3072),
                temperature=0.2,
            )

            final_code = ""
            raw_review_collector = []
            for chunk_event in stream_with_thinking_handling(stream3, ModelRole.REASONING, TaskType.CODING_COMPLEX, raw_review_collector):
                yield chunk_event
                if chunk_event["type"] == "token":
                    final_code += chunk_event["content"]

            unload_model()
        else:
            # Medium-complexity task — skip Stage 3, use Stage 2 output directly
            final_code = raw_code

        # Syntax check
        lang = detect_language(final_code)
        err = check_syntax(final_code, lang)
        if err:
            yield {"type": "syntax_error", "content": f"Syntax error detected in {lang or 'code'}: {err}"}
            yield {"type": "clear"}
            yield {"type": "status", "content": "Syntax error detected — auto-correcting..."}
            
            correction_messages = [
                *optimized,
                {"role": "assistant", "content": final_code},
                {"role": "user", "content": (
                    f"Your previous code has the following syntax error(s):\n\n{err}\n\n"
                    "Fix ONLY the syntax errors. Return the complete corrected code."
                )}
            ]
            
            llm_correct = load_model(ModelRole.REASONING)
            stream_correct = llm_correct.create_chat_completion(
                messages=[{"role": "system", "content": CODE_REVIEWER_SYSTEM_PROMPT}] + correction_messages,
                stream=True,
                max_tokens=ROLE_MAX_TOKENS.get(ModelRole.REASONING, 8192),
                temperature=0.2,
            )
            
            corrected_output = ""
            raw_correct_collector = []
            for chunk_event in stream_with_thinking_handling(stream_correct, ModelRole.REASONING, TaskType.CODING_COMPLEX, raw_correct_collector):
                yield chunk_event
                if chunk_event["type"] == "token":
                    corrected_output += chunk_event["content"]
            
            unload_model()
            
            # Check errors on corrected output
            second_errors = check_syntax(corrected_output, lang)
            if second_errors:
                yield {"type": "token", "content": "\n\n> ⚠️ Auto-correction attempted but errors may remain. Please review the code."}
            
            final_code = corrected_output

        yield {"type": "raw_response", "content": final_code}

    else:
        # Tier 1 — Single specialist direct stream
        role = TASK_TO_MODEL[task_type]
        status_msgs = {
            TaskType.GENERAL:   "Thinking...",
            TaskType.CODING_SIMPLE: "Writing code...",
            TaskType.MATH:      "Solving...",
            TaskType.REASONING: "Reasoning...",
        }
        yield {"type": "status", "content": status_msgs.get(task_type, "Thinking...")}

        system_prompt = {
            TaskType.GENERAL:   GENERAL_SYSTEM_PROMPT,
            TaskType.CODING_SIMPLE: CODE_SYSTEM_PROMPT,
            TaskType.MATH:      MATH_SYSTEM_PROMPT,
            TaskType.REASONING: REASONING_SYSTEM_PROMPT,
        }[task_type]

        if context:
            system_prompt = f"REFERENCE EXCERPT:\n{context}\n\n{system_prompt}"

        optimized = optimize_messages(history, user_query)
        llm = load_model(role)

        stream = llm.create_chat_completion(
            messages=[{"role": "system", "content": system_prompt}] + optimized,
            stream=True,
            max_tokens=ROLE_MAX_TOKENS.get(role, 4096),
            temperature=0.2 if task_type != TaskType.REASONING else 0.5,
        )

        full_content = ""
        raw_collector = []
        for chunk_event in stream_with_thinking_handling(stream, role, task_type, raw_collector):
            yield chunk_event
            if chunk_event["type"] == "token":
                full_content += chunk_event["content"]

        unload_model()

        # Quality guard post-processing
        cleaned = quality_guard(full_content)
        if cleaned != full_content:
            yield {"type": "clear"}
            yield {"type": "token", "content": cleaned}

        raw_response = cleaned
        # Reconstruct raw_response to include thinking block if present
        if task_type in (TaskType.CODING_SIMPLE, TaskType.MATH):
            raw_str = "".join(raw_collector)
            match = re.search(r'(<think>.*?</think>)', raw_str, re.DOTALL)
            if match:
                raw_response = match.group(1) + "\n" + cleaned

        # Self-correction check (CODING_SIMPLE only)
        if task_type == TaskType.CODING_SIMPLE:
            lang = detect_language(cleaned)
            errors = check_syntax(cleaned, lang)
            if errors:
                yield {"type": "syntax_error", "content": f"Syntax error detected in {lang or 'code'}: {errors}"}
                yield {"type": "clear"}
                yield {"type": "status", "content": "Syntax error detected — auto-correcting..."}
                
                correction_messages = [
                    *optimized,
                    {"role": "assistant", "content": cleaned},
                    {"role": "user", "content": (
                        f"Your previous code has the following syntax error(s):\n\n{errors}\n\n"
                        "Fix ONLY the syntax errors. Return the complete corrected code."
                    )}
                ]
                
                llm_correct = load_model(ModelRole.CODE)
                stream_correct = llm_correct.create_chat_completion(
                    messages=[{"role": "system", "content": CODE_SYSTEM_PROMPT}] + correction_messages,
                    stream=True,
                    max_tokens=ROLE_MAX_TOKENS.get(ModelRole.CODE, 8192),
                    temperature=0.2,
                )
                
                corrected_output = ""
                raw_correct_collector = []
                for chunk_event in stream_with_thinking_handling(stream_correct, ModelRole.CODE, TaskType.CODING_SIMPLE, raw_correct_collector):
                    yield chunk_event
                    if chunk_event["type"] == "token":
                        corrected_output += chunk_event["content"]
                
                unload_model()
                
                # Check errors on corrected output
                second_errors = check_syntax(corrected_output, lang)
                if second_errors:
                    yield {"type": "token", "content": "\n\n> ⚠️ Auto-correction attempted but errors may remain. Please review the code."}

                raw_response = corrected_output
                raw_correct_str = "".join(raw_correct_collector)
                match = re.search(r'(<think>.*?</think>)', raw_correct_str, re.DOTALL)
                if match:
                    raw_response = match.group(1) + "\n" + corrected_output

        yield {"type": "raw_response", "content": raw_response}


if __name__ == "__main__":
    print("\n" + "="*50)
    print(" Initializing Iris AI (Local GGUF Router)")
    print("="*50)
    
    retriever = BookRetriever(raw_data_dir="raw_data")
    retriever.load_and_index()
    
    print(f"\n[SYSTEM] Local GGUF Engine Ready.")
    print("="*50)