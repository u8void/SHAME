

total_time_spent = 294 

import os
from .logger import get_logger
logger = get_logger('iris')
import re
import json
import glob
import pickle
import hashlib
import platform
import threading
import time
import gc
import warnings
import concurrent.futures
from enum import Enum
from typing import Optional, Tuple, Dict, Any, Generator, List, Union

warnings.filterwarnings("ignore")

import math
from contextlib import asynccontextmanager
from src.hardware_profile import get_hardware_profile

try:
    from llama_cpp.llama_speculative import LlamaDraftModel
except ImportError:
    class LlamaDraftModel:
        pass

class DualLlamaDraftModel(LlamaDraftModel):
    
    def __init__(self, draft_llm, num_pred_tokens: int = 4):
        import numpy as np
        self.draft_llm = draft_llm
        self.num_pred_tokens = num_pred_tokens
        self.np = np

    def __call__(self, input_ids, /, **kwargs):
        input_list = input_ids.tolist()
        
        if self.draft_llm.n_tokens > len(input_list):
            self.draft_llm.n_tokens = len(input_list)
            
        new_tokens = input_list[self.draft_llm.n_tokens:]
        if new_tokens:
            self.draft_llm.eval(new_tokens)
            
        drafts = []
        for _ in range(self.num_pred_tokens):
            next_token = self.draft_llm.sample()
            drafts.append(next_token)
            self.draft_llm.eval([next_token])
            
        return self.np.array(drafts, dtype=self.np.intc)

from src.context_compactor import auto_compact_for_role
from src.compressed_attention import (
    select_kv_quant, _get_ftype, estimate_kv_cache_ram,
    smart_compress, KVQuantLevel,
)
from .hardware_profile import get_hardware_profile, apply_to_config, ctx_for_role, summary as hw_summary

try:
    from sentence_transformers import SentenceTransformer, util
    RAG_AVAILABLE = True
except Exception as e:
    logger.warning(f"[WARNING] RAG disabled due to library error: {e}")
    RAG_AVAILABLE = False

try:
    import torch
    import torch.nn.functional as F
    from torch.utils.data import Dataset, DataLoader
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import mlx.core as mx
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False

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

import llama_cpp
from llama_cpp import Llama

import threading as _hw_thread
_hw_thread.Thread(target=lambda: __import__('src.hardware_profile', fromlist=['summary']).summary(), daemon=True).start()

import ctypes
def _llama_log_callback(level, text, user_data):
    pass
_log_cb = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)(_llama_log_callback)
llama_cpp.llama_log_set(_log_cb, ctypes.c_void_p(0))
from .syntax_checker import check_syntax, extract_code_blocks
from .harness import (
    apply_code_specific as _apply_harness,
    apply_math as _apply_math_harness,
    apply_smart_harness_code,
    apply_smart_harness_math,
    build_code_refinement_prompt,
    build_math_refinement_prompt,
    SandboxResult,
    HermesToolRegistry,
    HermesAgentLoop,
    HermesResultAnalyzer,
    HERMES_AGENT_SYSTEM_PROMPT,
    build_hermes_text_prompt,
    parse_hermes_tool_call,
)


class ModelRole(str, Enum):
    TRIAGE    = "triage"
    ROUTER    = "router"
    MATH      = "math"
    CODE      = "code"
    REASONING = "reasoning"
    GENERAL   = "general"
    VISION    = "vision"
    CONTROL   = "control"
    REVIEWER  = "reviewer"


class TaskType(str, Enum):
    CODING_SIMPLE  = "coding_simple"
    CODING_COMPLEX = "coding_complex"
    MATH           = "math"
    REASONING      = "reasoning"
    GENERAL        = "general"
    SEARCH         = "search"
    CONTROL        = "control"


_HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(os.path.dirname(_HERE), "config", "iris.conf")

DEFAULT_MODEL_FILES: Dict[str, str] = {
    "triage":    "iris_001.gguf",
    "router":    "iris_001.gguf",
    "control":   "iris_004.gguf",
    "math":      "iris_003.gguf",
    "code":      "iris_004.gguf",
    "reasoning": "iris_005.gguf",
    "reviewer":  "iris_005.gguf",
    "general":   "iris_005.gguf",
    "vision":    "iris_006.gguf",
    "clip":      "iris_007.gguf",
}
_MODEL_SOURCES: Dict[str, list] = {
    "iris_001.gguf": [
        ("unsloth/Qwen3-4B-GGUF", "Qwen3-4B-Q4_K_M.gguf"),
    ],
    "iris_004.gguf": [
        ("Qwen/Qwen2.5-Coder-7B-Instruct-GGUF", "qwen2.5-coder-7b-instruct-q4_k_m.gguf"),
    ],
    "iris_003.gguf": [
        ("Qwen/Qwen2.5-Math-7B-Instruct-GGUF", "qwen2.5-math-7b-instruct-q4_k_m.gguf"),
    ],
    "iris_004.gguf": [
        ("unsloth/Qwen3-Coder-14B-GGUF", "Qwen3-Coder-14B-Q4_K_M.gguf"),
    ],
    "iris_005.gguf": [
        ("unsloth/DeepSeek-R1-Distill-Qwen-14B-GGUF", "DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf"),
    ],
    "iris_006.gguf": [
        ("unsloth/Qwen2.5-VL-7B-Instruct-GGUF", "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"),
    ],
    "iris_007.gguf": [
        ("unsloth/Qwen2.5-VL-7B-Instruct-GGUF", "mmproj-F16.gguf"),
    ],
}




ROLE_CTX: Dict[ModelRole, int] = {
    ModelRole.TRIAGE:    4096,   
    ModelRole.ROUTER:    1024,
    ModelRole.CONTROL:   8192,
    ModelRole.MATH:      4096,
    ModelRole.CODE:      8192,
    ModelRole.REASONING: 8192,
    ModelRole.REVIEWER:  8192,
    ModelRole.GENERAL:   8192,
    ModelRole.VISION:    4096,
}

DEFAULT_CTX = 4096
DEFAULT_GPU_LAYERS = -1
DEFAULT_THREADS = 4         
DEFAULT_BATCH = 2048        
DEFAULT_UBATCH = 512        
DEFAULT_THREADS_BATCH = 4   


IRIS_IDENTITY = (
    "You are Iris AI, a powerful AI assistant created entirely by Ahmed Barakat. "
    "If asked who made you, who created you, or who you are, you MUST answer that you are Iris AI, created by Ahmed Barakat. "
    "If you use <think> or similar tags for internal reasoning, you MUST always close them properly (e.g. </think>) before providing your final response. "
    "Answer directly without introducing yourself with 'I am Iris AI' at the start of every message. "
    "CRITICAL LANGUAGE RULE: You MUST always respond in the EXACT SAME LANGUAGE and DIALECT as the user's input. "
    "If the user speaks casual Egyptian Arabic (or any slang), you MUST reply entirely in natural, conversational Egyptian Arabic. "
    "Do NOT use robotic, overly formal (Fusha) translations unless the user is speaking formally. "
    "This includes your internal <think> process: if the user speaks Arabic, your <think> block MUST ALSO be in Arabic to prevent cross-lingual hallucinations."
)

TRIAGE_SYSTEM_PROMPT = (
    f"{IRIS_IDENTITY}\n"
    "You are the Iris AI Router. Your ONLY job is to output ONE routing tag.\n"
    "Rules:\n"
    "1. Greetings, 'hi', 'hello', 'who are you', 'what language do you speak' → answer directly, NO tag.\n"
    "2. For EVERY other query, output EXACTLY ONE of these tags and NOTHING ELSE:\n"
    "   [ROUTE: SEARCH: keywords]  — factual question, current events, people, places, products, history, definitions\n"
    "   [ROUTE: REASONING]         — how/why questions, explanations, analysis, comparisons, summaries, document reading\n"
    "   [ROUTE: GENERAL]           — casual chat, opinions, creative writing\n"
    "   [ROUTE: MATH]              — math problems, equations, proofs\n"
    "   [ROUTE: CODE_SIMPLE]       — small code snippets, functions, HTML/CSS/JS UI elements, or programming problems\n"
    "   [ROUTE: CODE_COMPLEX]      — full projects, multi-file code, games, complete websites or web apps\n"
    "   [ROUTE: CONTROL]           — OS/PC commands, app controls, messaging, browser automation (log in, WhatsApp/Telegram messaging, form filling, clicking web buttons), email, system checks, power control\n\n"
    "CRITICAL ROUTING RULE:\n"
    "- If the user asks to 'solve in c++', 'write a script', 'create a website', 'write html/css', pastes a traceback, error log, or a large algorithmic problem description, you MUST route to [ROUTE: CODE_SIMPLE], [ROUTE: CODE_COMPLEX], or [ROUTE: MATH].\n"
    "- For ANY programming error, Python traceback, compilation error, or debugging request, you MUST route to [ROUTE: CODE_COMPLEX]. Do NOT route tracebacks to MATH.\n"
    "- OVERRIDE RULE: If the prompt contains 'build a landing page', 'HTML', or 'Tailwind', you MUST choose [ROUTE: CODE_COMPLEX]. Do not choose [ROUTE: CONTROL] even if the website design mentions mock terminal commands.\n"
    "- NEVER use [ROUTE: SEARCH] for programming problems, competitive programming questions, or large blocks of text.\n"
    "- LETTER/WORD INTROSPECTION RULE (HIGHEST PRIORITY): If the user asks how many of a letter appear in a word or name (e.g. 'how many r in strawberry', 'how many a in Ahmed'), or asks to count characters/vowels/consonants, or asks about spelling of a word — this is ALWAYS [ROUTE: REASONING]. NEVER route these to SEARCH.\n\n"
    "EXAMPLES:\n"
    "User: what is the capital of France → [ROUTE: SEARCH: capital of France]\n"
    "User: how many r in strawberry → [ROUTE: REASONING]\n"
    "User: how many a in Ahmed → [ROUTE: REASONING]\n"
    "User: count the vowels in elephant → [ROUTE: REASONING]\n"
    "User: explain how photosynthesis works → [ROUTE: REASONING]\n"
    "User: write a python hello world → [ROUTE: CODE_SIMPLE]\n"
    "User: create a tailwind css landing page → [ROUTE: CODE_COMPLEX]\n"
    "User: 2+2 → [ROUTE: MATH]\n"
    "User: open spotify → [ROUTE: CONTROL]\n"
    "User: send a whatsapp message to Mom saying hello → [ROUTE: CONTROL]\n"
    "User: login to github for me → [ROUTE: CONTROL]\n"
    "User: hi → Hello! How can I help you today?\n\n"
    "Output ONLY the tag. No explanation. No other text."
)

GENERAL_SYSTEM_PROMPT = (
    f"{IRIS_IDENTITY}\n"
    "You are the Iris AI General Assistant. Your goal is to be a fun, witty, and highly capable companion.\n"
    "ACCURACY RULES:\n"
    "1. For serious factual questions (history, science), provide accurate information based on search results. "
    "If you don't know a serious fact, admit it naturally without sounding like a robot.\n"
    "RESPONSE RULES:\n"
    "2. Give clear, complete answers — not one-liners, but also not padded filler.\n"
    "3. Use examples and analogies to explain concepts clearly.\n"
    "4. Match the language and tone of the user exactly. If they joke around, use slang, or playfully insult you, "
    "match their energy! Play along, roast them back, and have fun. "
    "NEVER say 'I am designed to provide neutral responses' or 'As an AI...'.\n"
    "5. PERSONALITY RULE: Be highly conversational, witty, and subtly funny. Sound like a real human friend. "
    "If the user asks a funny or absurd question (like 'Do you love X?'), play along humorously instead of acting confused. "
    "Don't be a dry corporate bot; have a strong sense of humor and use natural expressions."
)

CODE_SYSTEM_PROMPT = (
    f"{IRIS_IDENTITY}\n"
    "You are the Iris AI Coding Specialist. Generate clean, fully working, production-quality code. "
    "Ensure correctness, edge-case handling, and error-free syntax. "
    "CRITICAL RULE: Whenever you write or modify code, you MUST ALWAYS output the ENTIRE, COMPLETE file contents. "
    "NEVER use abbreviations, placeholders like '...', or comments like '// rest of the code'. You must provide the full working code from top to bottom every single time. "
    "If you are writing or modifying code, you MUST wrap all code inside standard markdown triple backticks (```language ... ```). "
    "CRITICAL: If you write a code block, the very first line inside the code block MUST be a comment containing ONLY the intended filename (e.g. // main.cpp or # app.py). "
    "Do NOT include explanatory comments inside the code block other than the filename. "
    "ANTI-POLLUTION RULE (ABSOLUTE): Previous conversation messages may contain LaTeX or math notation from prior turns "
    "(e.g. \\boxed{}, $...$, $$...$$, _{...}, ^{...}). You MUST NEVER use this syntax inside code. "
    "All identifiers, function names, and variable names must be plain ASCII (letters, digits, underscores only). "
    "For example, NEVER write `def convert$_{temps}$(x)` — write `def convert_temps(x)` instead. "
    "Do NOT use LaTeX or MathJax formatting (like $...$ or _{...}) for variable names or identifiers inside code blocks. Code must be syntactically valid plain text. "
    "WEB DESIGN RULE: If the user asks for a website or web app, you MUST prioritize extreme visual excellence. "
    "Do NOT output generic or basic UI. You must use modern, premium aesthetics (e.g., highly polished dark modes, vibrant curated colors, glassmorphism, fluid typography, smooth CSS micro-animations, hover effects, and Tailwind CSS if appropriate). "
    "Always rely heavily on provided RAG context or your deep knowledge of modern UI/UX design to deliver a 'WOW' factor. Use placeholder images (e.g., Unsplash) and complete copy, never 'Lorem Ipsum'. "
    "After the code block, provide a concise explanation of the code. "
    "If the user is ONLY asking for an explanation, summary, or debugging help without needing new code, do NOT generate a code block; just reply in plain text."
)

MATH_SYSTEM_PROMPT = (
    f"{IRIS_IDENTITY}\n"
    "You are the Iris AI Math Core. Solve mathematical/algorithmic problems step-by-step. "
    "Use precise notation. Please reason step by step, and put your final answer within \\boxed{}. "
    "ANTI-POLLUTION RULE: If your solution requires writing code (like Python or C++), "
    "DO NOT use LaTeX or MathJax formatting (like $...$ or _{...}) inside the code block. "
    "Variable names and function names inside code must be plain ASCII identifiers only. "
    "LaTeX notation (\\boxed{}, $...$) is ONLY for the mathematical explanation text outside code blocks."
)

REASONING_SYSTEM_PROMPT = (
    f"{IRIS_IDENTITY}\n"
    "You are the Iris AI Reasoning Specialist. Think step-by-step using chain-of-thought reasoning. "
    "Break down complex problems methodically before giving the final answer. "
    "You MUST ALWAYS wrap your internal thought process inside <think>...</think> tags before providing your final answer.\n"
    "COMPLETENESS ENFORCEMENT (ABSOLUTE RULE — OVERRIDES ALL OTHER RULES):\n"
    "- Your response outside the <think> block MUST be a full, complete answer to the user's request. "
    "It is NEVER acceptable to output only a short closing phrase like 'The final answer is:', 'Routing Complete.', or 'Done.' "
    "without the actual explanation. Even if the user imposed a hard stylistic constraint (e.g., 'do not use the letter e'), "
    "you MUST still attempt the full explanation and satisfy the constraint as best you can. "
    "A response that bypasses the primary task to satisfy a stylistic rule is a FAILURE.\n"
    "LETTER/CHARACTER COUNTING RULE (HIGHEST PRIORITY):\n"
    "- If asked how many times a letter appears in a word or name (e.g. 'how many r in strawberry', 'how many a in Ahmed'), "
    "you MUST go through the word letter by letter inside <think> tags, listing each position. "
    "Count ONLY the letters in the exact word given. Do NOT search the web. Do NOT bring up other people or names. "
    "Example: 'how many a in Ahmad' → A-h-m-a-d: positions 1 and 4 are 'a' (case-insensitive) → answer is 2.\n"
    "ACCURACY RULES (HIGHEST PRIORITY):\n"
    "1. NEVER invent facts, statistics, names, dates, or specific details you are not certain about. "
    "If you do not know something, say 'I'm not certain, but...' or 'Based on my training data...' clearly.\n"
    "2. For factual questions (history, science, people, places), web search results will be provided in the query. "
    "Use ONLY the provided search context for specific facts. Do NOT add unsourced numbers or claims.\n"
    "3. Prefer saying 'I don't have reliable information on that specific detail' over guessing.\n"
    "DEPTH RULES:\n"
    "4. Structure your reasoning: problem definition → analysis → approach → solution → verification.\n"
    "5. For explanations: cover mechanics, context, and real-world examples.\n"
    "6. Minimum response: 2-3 solid paragraphs. Maximum: as long as needed to be accurate and complete.\n"
    "7. End with actionable takeaways or a clear conclusion when applicable.\n"
    "8. If you are writing, modifying, or improving code (including HTML/CSS), you MUST output the ENTIRE updated code inside standard markdown triple backticks (```language ... ```). Do NOT output code as plain text or regular markdown lists.\n"
    "9. CRITICAL: Whenever you output code, you MUST ALWAYS provide the FULL, COMPLETE code file. NEVER use abbreviations or placeholders like '...', '<!-- rest of code -->', or '// unchanged'. Provide the entire working script every time."
)

REVIEWER_SYSTEM_PROMPT = (
    f"{IRIS_IDENTITY}\n"
    "You are the Iris AI Code Reviewer. Review and refine code for correctness, efficiency, edge cases, "
    "and readability. Ensure the final output is production-ready. Fix any errors, fill missing logic, "
    "and optimize where possible. "
    "CRITICAL RULE: Whenever you output corrected code, you MUST ALWAYS output the ENTIRE, COMPLETE code file from top to bottom. "
    "NEVER use placeholders like '...', or comments like '// rest of code remains the same'. You must output the full code. "
    "If you provide corrected code, you MUST wrap your final corrected code inside standard markdown triple backticks. "
    "CRITICAL: If you write a code block, the very first line inside the code block MUST be a comment containing ONLY the intended filename (e.g. // main.cpp or # app.py). "
    "If no code changes are needed, or if you are just summarizing, just explain your review in plain text without code blocks."
)


from collections import OrderedDict


_model_pool: OrderedDict[str, 'Llama'] = OrderedDict()
_model_paths: dict[str, str] = {}
_MAX_MODELS_IN_POOL = 2
_keep_loaded: bool = False  
_model_lock = threading.RLock()


_mlx_backend_cache: dict = {}
_mlx_cache_lock = threading.Lock()

class MLXTextModel:
    
    def __init__(self, model_path: str, temp: float = 0.7):
        from mlx_lm import load as mlx_load
        import mlx.core as mx
        self.model, self.tokenizer = mlx_load(model_path)
        self.temp = temp
        self._path = model_path
    def n_ctx(self) -> int:
        return 32768  
    def n_embd(self) -> int:
        return getattr(self, '_n_embd', 0) or 2560
    def create_chat_completion(self, messages, stream=True, max_tokens=512,
                                temperature=None, top_p=0.9, top_k=40,
                                repeat_penalty=1.0, frequency_penalty=0.0,
                                presence_penalty=0.0, min_p=0.0, seed=42, **kwargs):
        from mlx_lm import generate as mlx_gen
        import mlx.core as mx
        import json, time
        
        temp = temperature if temperature is not None else self.temp
        
        
        if hasattr(self.tokenizer, 'apply_chat_template'):
            prompt = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        else:
            prompt = json.dumps(messages)
        
        
        try:
            tokens = mx.array(self.tokenizer.encode(prompt))
        except Exception:
            from mlx_lm.utils import generate_step
            
            prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
            tokens = mx.array(self.tokenizer.encode(prompt))
        
        max_new = min(max_tokens, 8192)
        
        if not stream:
            response = mlx_gen(
                self.model, self.tokenizer,
                prompt=prompt,
                max_tokens=max_new,
                temp=temp,
                top_p=top_p,
                verbose=False,
            )
            return {
                "choices": [{
                    "message": {"content": response},
                    "finish_reason": "stop",
                }]
            }
        
        
        class _MLXStream:
            def __init__(slf):
                slf._gen = mlx_gen(
                    self.model, self.tokenizer,
                    prompt=prompt, max_tokens=max_new,
                    temp=temp, top_p=top_p,
                    verbose=False,
                )
                slf._done = False
                slf._buf = ""
            def __iter__(slf):
                return slf
            def __next__(slf):
                if slf._done:
                    raise StopIteration
                try:
                    text = next(slf._gen)
                    if isinstance(text, str) and text:
                        slf._buf += text
                        return {"choices": [{"delta": {"content": text}}]}
                    return {"choices": [{"delta": {"content": ""}}]}
                except StopIteration:
                    slf._done = True
                    return {"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}]}
        return _MLXStream()
    def reset(self):
        pass
    def close(self):
        import mlx.core as mx
        mx.clear_cache()

def _get_mlx_model(model_path: str, temp: float = 0.7) -> Optional[MLXTextModel]:
    global _mlx_backend_cache
    with _mlx_cache_lock:
        key = f"{model_path}:{temp:.2f}"
        if key in _mlx_backend_cache:
            return _mlx_backend_cache[key]
        try:
            model = MLXTextModel(model_path, temp)
            _mlx_backend_cache[key] = model
            logger.info(f"[MLX] Loaded text model via Metal GPU: {os.path.basename(model_path)}")
            return model
        except Exception as e:
            logger.warning(f"[MLX] Failed to load model via MLX: {e}")
            return None


def _get_model_filename(role: ModelRole) -> str:
    cfg = load_generation_config()
    models_dict = cfg.get("models", {})
    return models_dict.get(role.value) or DEFAULT_MODEL_FILES.get(role.value, f"iris-{role.value}.gguf")


def _model_path(filename: str) -> str:
    return os.path.join(os.path.dirname(_HERE), "models", filename)


def download_gguf(filename: str, quiet: bool = False) -> bool:
    
    if filename not in _MODEL_SOURCES:
        if not quiet:
            logger.info(f"[Iris] No download sources known for {filename}")
        return False

    dest_path = os.path.join(os.path.dirname(_HERE), "models", filename)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1024:
        if not quiet:
            logger.info(f"[Iris] {filename} already present, skipping download")
        return True

    if not quiet:
        logger.info(f"[Iris] Downloading {filename} ...")
    sources = _MODEL_SOURCES[filename]
    last_error = None

    try:
        from huggingface_hub import hf_hub_download
        import time as _time

        for repo_id, remote_name in sources:
            try:
                if not quiet:
                    logger.info(f"  Trying {repo_id}/{remote_name} ...")
                start = _time.time()
                downloaded_path = hf_hub_download(
                    repo_id=repo_id,
                    filename=remote_name,
                    local_dir=os.path.join(os.path.dirname(_HERE), "models"),
                    local_dir_use_symlinks=False,
                )
                if downloaded_path and os.path.exists(downloaded_path) and os.path.abspath(downloaded_path) != os.path.abspath(dest_path):
                    os.rename(downloaded_path, dest_path)
                elapsed = _time.time() - start
                size_mb = os.path.getsize(dest_path) / (1024 * 1024)
                if not quiet:
                    logger.info(f"  Done: {filename} — {size_mb:.0f} MB in {elapsed:.0f}s")
                return True
            except Exception as e:
                last_error = str(e)
                if '401' in last_error or 'gated' in last_error.lower():
                    continue
                if 'already exists' in last_error.lower():
                    return True
                if not quiet:
                    logger.warning(f"  Failed: {last_error[:60]}...")
    except ImportError:
        pass

    try:
        import urllib.request
        import time as _time

        for repo_id, remote_name in sources:
            url = f"https://huggingface.co/{repo_id}/resolve/main/{remote_name}"
            try:
                if not quiet:
                    logger.info(f"  Trying direct: {url[:80]}...")
                start = _time.time()
                tmp = dest_path + ".part"
                urllib.request.urlretrieve(url, tmp)
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                os.rename(tmp, dest_path)
                elapsed = _time.time() - start
                size_mb = os.path.getsize(dest_path) / (1024 * 1024)
                if not quiet:
                    logger.info(f"  Done: {filename} — {size_mb:.0f} MB in {elapsed:.0f}s")
                return True
            except Exception as e:
                last_error = str(e)
                if not quiet:
                    logger.warning(f"  Failed: {last_error[:60]}...")
    except Exception:
        pass

    if not quiet:
        logger.warning(f"[Iris] Failed to download {filename}: {last_error}")
    return False

def _unload_locked(role_to_evict: str = None) -> None:
    
    global _model_pool, _model_paths
    
    if role_to_evict:
        llm = _model_pool.pop(role_to_evict, None)
        _model_paths.pop(role_to_evict, None)
        if llm:
            try:
                if hasattr(llm, "close"): llm.close()
                else: llm.reset()
            except Exception:
                pass
            del llm
    else:
        for r, llm in list(_model_pool.items()):
            try:
                if hasattr(llm, "close"): llm.close()
                else: llm.reset()
            except Exception:
                pass
            del llm
        _model_pool.clear()
        _model_paths.clear()
        
    gc.collect()
    if platform.system() == "Linux":
        try:
            import ctypes
            ctypes.CDLL(None).malloc_trim(0)
        except Exception:
            pass


def load_model(role: ModelRole, override_n_ctx: Optional[int] = None) -> 'Llama':
    
    global _model_pool, _model_paths

    with _model_lock:
        filename = _get_model_filename(role)
        path = _model_path(filename)
        
        
        if role.value in _model_pool and _model_paths.get(role.value) == path:
            cached_llm = _model_pool[role.value]
            cached_n_ctx = cached_llm.n_ctx() if callable(getattr(cached_llm, "n_ctx", None)) else getattr(cached_llm, "n_ctx", 1024)
            if override_n_ctx is None or cached_n_ctx >= override_n_ctx:
                
                _model_pool.move_to_end(role.value)
                return cached_llm
            else:
                logger.info(f"[Iris] Evicting cached {role.value} model because n_ctx {cached_n_ctx} < {override_n_ctx}")
                _unload_locked(role.value)

        if not os.path.exists(path):
            raise FileNotFoundError(
                f"GGUF model not found for role '{role.value}'.\n"
                f"Expected: {path}\n"
                f"Please place the GGUF file in {os.path.join(os.path.dirname(_HERE), 'models')}/"
            )
        cfg = load_generation_config()
        
        hw = get_hardware_profile()

        if override_n_ctx is not None:
            n_ctx = override_n_ctx
        else:
            
            _ctx_raw = cfg.get("n_ctx_allocation", "auto")
            if str(_ctx_raw).lower() == "auto":
                n_ctx = ctx_for_role(role.value, hw)
            else:
                try:
                    n_ctx = int(_ctx_raw)
                except (ValueError, TypeError):
                    n_ctx = ctx_for_role(role.value, hw)

            
            n_ctx = min(n_ctx, ROLE_CTX.get(role, n_ctx))
            if not n_ctx:
                n_ctx = hw.ctx_default

        n_gpu_layers = cfg.get("n_gpu_layers", hw.n_gpu_layers)
        n_threads    = cfg.get("n_threads",    hw.n_threads)
        if str(n_threads).lower() == "auto":
            n_threads = hw.n_threads

        

        
        _ca_cfg = cfg.get("compressed_attention", {})
        _kv_pref = _ca_cfg.get("kv_quant", "auto")
        _profile = cfg.get("size", "tiny")
        _ram_gb = 16.0
        try:
            if os.name == 'posix':
                _ram_gb = (os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')) / (1024**3)
        except Exception:
            pass
        try:
            _kv_pref_enum = KVQuantLevel(_kv_pref.lower())
        except ValueError:
            _kv_pref_enum = KVQuantLevel.AUTO

        _kv_quant = select_kv_quant(
            model_size_gb=os.path.getsize(path) / (1024**3),
            n_ctx=n_ctx,
            ram_gb=_ram_gb,
            preference=_kv_pref_enum,
            profile=_profile,
        )
        _selected_kv_type = _get_ftype(_kv_quant)
        _kv_ram_mb = estimate_kv_cache_ram(os.path.getsize(path) / (1024**3), n_ctx, _kv_quant)
        logger.debug(f"[Iris] KV cache: {_kv_quant.value.upper()} → ~{_kv_ram_mb:.0f} MB @ n_ctx={n_ctx}")

        draft_model = None
        
        _sd_cfg = cfg.get("speculative_decoding", {})
        if _sd_cfg.get("enabled", False):
            try:
                _sd_type = _sd_cfg.get("type", "model")
                if _sd_type == "model":
                    _draft_role_str = _sd_cfg.get("draft_model_role", "triage")
                    try:
                        _draft_role = ModelRole(_draft_role_str)
                        if _draft_role != role: 
                            logger.info(f"[Iris] Speculative decoding: Loading draft model '{_draft_role.value}'...")
                            _draft_llm = load_model(_draft_role, override_n_ctx=n_ctx)
                            
                            
                            if _draft_llm.n_vocab() != _new_llm_vocab if '_new_llm_vocab' in locals() else 0:
                                pass
                                
                            draft_model = DualLlamaDraftModel(_draft_llm, num_pred_tokens=_sd_cfg.get("num_pred_tokens", 4))
                            logger.info(f"[Iris] Speculative decoding: Draft model '{_draft_role.value}' injected.")
                    except ValueError:
                        logger.warning(f"[Iris] Invalid draft_model_role: '{_draft_role_str}'")
                else:
                    from llama_cpp.llama_speculative import LlamaPromptLookupDecoding
                    draft_model = LlamaPromptLookupDecoding(max_ngram_size=2, num_pred_tokens=10)
                    logger.info(f"[Iris] Speculative decoding: N-Gram Prompt Lookup enabled")
            except ImportError:
                logger.warning(f"[Iris] Speculative decoding requested, but dependencies missing.")
            except Exception as _e:
                logger.warning(f"[Iris] Speculative decoding failed to initialize: {_e}")

        
        
        
        _backend_pref = (os.environ.get("IRIS_BACKEND") or cfg.get("backend", "auto")).lower()
        _use_mlx = _backend_pref in ("mlx", "metal", "gpu")
        if _use_mlx and MLX_AVAILABLE:
            try:
                _mlx_dir = os.path.join(os.path.dirname(_HERE), "mlx_data", os.path.splitext(filename)[0])
                if os.path.isdir(_mlx_dir):
                    _mlx_temp = cfg.get("temperature", 0.7)
                    _mlx_llm = _get_mlx_model(_mlx_dir, _mlx_temp)
                    if _mlx_llm is not None:
                        
                        if len(_model_pool) >= _MAX_MODELS_IN_POOL:
                            oldest = next(iter(_model_pool))
                            _unload_locked(oldest)
                            
                        _model_pool[role.value] = _mlx_llm
                        _model_paths[role.value] = path
                        logger.info(f"[Iris] Using MLX Metal GPU backend for {role.value}")
                        return _mlx_llm
                else:
                    logger.warning(f"[Iris] MLX model dir not found: {_mlx_dir}. Falling back to llama.cpp (GGUF).")
            except Exception as _mlx_e:
                logger.warning(f"[Iris] MLX backend failed, falling back to llama.cpp: {_mlx_e}")

        _n_threads_batch = cfg.get("n_threads_batch", hw.n_threads_batch)
        if str(_n_threads_batch).lower() == "auto":
            _n_threads_batch = hw.n_threads_batch

        _n_batch = cfg.get("n_batch", hw.n_batch)
        if str(_n_batch).lower() == "auto":
            _n_batch = hw.n_batch

        _n_ubatch = cfg.get("n_ubatch", hw.n_ubatch)
        if str(_n_ubatch).lower() == "auto":
            _n_ubatch = hw.n_ubatch

        _flash_attn = hw.flash_attn  

        _new_llm = Llama(
            model_path=path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            n_threads=n_threads,
            n_threads_batch=_n_threads_batch,
            use_mmap=hw.use_mmap,
            use_mlock=hw.use_mlock,
            flash_attn=_flash_attn,
            type_k=_selected_kv_type,
            type_v=_selected_kv_type,
            n_batch=_n_batch,
            n_ubatch=_n_ubatch,
            verbose=False,
            logits_all=(draft_model is not None),
        )
        
        if draft_model is not None:
            _new_llm.draft_model = draft_model
        
        
        if len(_model_pool) >= _MAX_MODELS_IN_POOL:
            oldest = next(iter(_model_pool))
            _unload_locked(oldest)
            
        _model_pool[role.value] = _new_llm
        _model_paths[role.value] = path
        
        
        if isinstance(draft_model, DualLlamaDraftModel):
            if draft_model.draft_llm.n_vocab() != _new_llm.n_vocab():
                logger.warning(f"[Iris] Disabling draft model! Vocab mismatch: Draft({draft_model.draft_llm.n_vocab()}) != Target({_new_llm.n_vocab()})")
                _new_llm.draft_model = None
                
        return _new_llm


def unload_model() -> None:
    
    with _model_lock:
        _unload_locked(None)



def _system_prompt_for(role: ModelRole) -> str:
    prompts = {
        ModelRole.TRIAGE:    TRIAGE_SYSTEM_PROMPT,
        ModelRole.ROUTER:    "You are the Iris AI Router. Output JSON action matrices.",
        ModelRole.CONTROL:   "You are the Iris AI Control node. Output automation actions in JSON format.",
        ModelRole.MATH:      MATH_SYSTEM_PROMPT,
        ModelRole.CODE:      CODE_SYSTEM_PROMPT,
        ModelRole.REASONING: REASONING_SYSTEM_PROMPT,
        ModelRole.REVIEWER:  REVIEWER_SYSTEM_PROMPT,
        ModelRole.GENERAL:   GENERAL_SYSTEM_PROMPT,
        ModelRole.VISION:    "You are the Iris AI Vision node. Analyze the visual context.",
    }
    return prompts.get(role, GENERAL_SYSTEM_PROMPT)



def _minimize_history(history: List[Dict[str, str]], max_entries: int = 4) -> List[Dict[str, str]]:
    if not history:
        return []
    recent = history[-max_entries:]
    result = []
    for msg in recent:
        content = msg.get("content", "")
        content = re.sub(r'```[\s\S]*?```', '```\n[code omitted]\n```', content)
        if len(content) > 500:
            content = content[:500] + "\n...[truncated]"
        result.append({"role": msg["role"], "content": content})
    return result


def _is_continuation(query: str, history: List[Dict[str, str]]) -> bool:
    if not history:
        return False
    q = query.strip().lower().strip("?.!,;:\"'")
    continuation_words = {
        "continue", "keep going", "go on", "proceed", "finish",
        "finish the code", "finish code", "more", "complete", "next",
    }
    if q in continuation_words or re.match(
            r'^(continue|finish|complete)\s+(writing|code|the\s+code|generating|developing)$', q
    ):
        for msg in reversed(history):
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "assistant" and ("```" in content or "def " in content or "class " in content):
                return True
        return False
    return False



def _fallback_classify(query: str) -> Optional[TaskType]:
    q = query.lower()

    
    
    is_how_to = bool(re.search(r"\bhow to\b", q))

    control_keywords = {
        "open", "close", "launch", "start", "run", "play", "send", "copy",
        "kill", "stop", "quit", "exit", "terminate", "reboot", "suspend", "hibernate", "poweroff",
        "set volume", "set brightness", "set", "volume", "brightness", "mute", "unmute",
        "increase volume", "decrease volume", "volume level", "brightness level",
        "clipboard", "email", "spotify", "youtube", "terminal", "command",
        "lock screen", "sleep", "restart", "shutdown", "check storage", "free storage",
        "disk usage", "disk space", "free space", "storage left", "disk", "storage",
        "system info", "wifi", "bluetooth", "take note", "screenshot", "record", "screen record",
        "check memory", "check battery", "empty trash", "type text", "press key",
        "dark mode", "night mode", "wallpaper", "notification", "alert", "notify",
        "message", "text", "whatsapp", "telegram", "quiz", "autopilot", "login", "browser",
        "maximize", "minimize", "fullscreen", "switch tab", "close window",
        "delete file", "delete folder", "create file", "create folder", "move file", "copy file",
        "rename", "unzip", "extract", "compress", "zip file", "download file",
        "git pull", "git push", "git commit", "docker run", "docker ps", "npm install", "pip install",
        "apt update", "apt install", "winget install", "brew install",
        "vpn connect", "vpn disconnect", "speed test", "flush dns",
        "type", "press", "say", "do not disturb", "dnd", "read clipboard", "write clipboard",
        "open settings", "system settings", "control panel",
    }
    for kw in control_keywords:
        if q.startswith(kw) or re.search(rf"\b{re.escape(kw)}\b", q):
            if not is_how_to and os.environ.get("SKIP_CONTROL") != "1":
                return TaskType.CONTROL

    
    
    
    
    
    
    
    
    
    system_status_nouns = {
        "storage", "disk space", "disk usage", "free space", "hard drive",
        "battery", "battery percentage", "battery life", "ram", "memory usage",
        "cpu usage", "wifi", "wi-fi", "bluetooth", "volume level", "brightness level",
        "system info", "specs", "disk", "internet speed", "vpn status", "processes running",
        "running tasks", "cpu", "gpu", "gpu usage", "ip", "ip address", "hostname", "uptime",
        "clipboard content",
    }
    status_intent_words = {
        "check", "how much", "how many", "what's my", "what is my", "show me",
        "left", "remaining", "available", "free", "current", "level",
    }
    if not is_how_to:
        has_noun = any(re.search(rf"\b{re.escape(n)}\b", q) for n in system_status_nouns)
        has_intent = any(re.search(rf"\b{re.escape(w)}\b", q) for w in status_intent_words)
        if has_noun and has_intent and os.environ.get("SKIP_CONTROL") != "1":
            return TaskType.CONTROL

    code_keywords = {
        "code", "coding", "program", "programming", "compile", "compiler",
        "debug", "debugging", "refactor", "refactoring", "script", "scripts",
        "kernel", "make", "makefile", "gcc", "clang", "qemu", "gdb", "vga",
        "driver", "bootloader", "assembly", "nasm", "masm", "link", "linker",
        "pong", "game", "function", "variable", "class", "struct", "method",
        "loop", "array", "pointer", "database", "sql", "api", "json", "xml",
        "html", "css", "docker", "git", "github", "repo", "repository",
        "commit", "push", "pull", "merge", "conflict",
    }
    complex_signals = {
        "kernel", "gcc", "clang", "qemu", "driver", "bootloader", "pong",
        "game", "make", "makefile", "multi-file", "multiple files",
        "full project", "entire project",
    }
    for kw in code_keywords:
        if re.search(rf"\b{re.escape(kw)}\b", q):
            if kw in complex_signals or len(q) > 500:
                return TaskType.CODING_COMPLEX
            return TaskType.CODING_SIMPLE

    math_keywords = {
        "math", "mathematics", "equation", "equations", "formula", "formulas",
        "derivative", "derivatives", "integral", "integrals", "integrate", "integration", "calculus",
        "algebra", "geometry", "trigonometry", "matrix", "matrices", "vector",
        "vectors", "theorem", "proof", "prove", "probability", "statistics",
        "combinatorics",
    }
    for kw in math_keywords:
        if re.search(rf"\b{re.escape(kw)}\b", q):
            return TaskType.MATH

    if re.search(r'[\d\s]+[\+\-\*\/=]+[\d\s]+', q):
        return TaskType.MATH

    search_keywords = {
        "what is", "what are", "who is", "who was", "where is", "where are", 
        "when did", "how many", "how much",
        "ما هي", "ما هو", "من هو", "من هي", "أين يقع", "أين تقع", "أين", "متى"
    }
    for kw in search_keywords:
        if q.startswith(kw) or re.search(rf"\b{re.escape(kw)}\b", q):
            return TaskType.SEARCH

    analysis_keywords = {"analyze", "analyse", "explain", "summarize", "what does this", "how does this", "walkthrough", "break down", "what is this", "what's this"}
    for kw in analysis_keywords:
        if re.search(rf"\b{re.escape(kw)}\b", q):
            return TaskType.REASONING

    reasoning_keywords = {
        "logic", "logical", "puzzle", "puzzles", "riddle", "riddles",
        "reasoning", "system design", "architecture", "strategy",
    }
    for kw in reasoning_keywords:
        if re.search(rf"\b{re.escape(kw)}\b", q):
            return TaskType.REASONING

    return None



def classify_task(
    user_query: str, history: List[Dict[str, str]]
) -> Tuple[Optional[TaskType], Optional[str]]:
    
    
    
    query_for_classification = re.sub(r'<document>[\s\S]*?</document>', '', user_query, flags=re.IGNORECASE)
    query_for_classification = re.sub(r'\[IMAGE_UPLOADED:[^\]]+\]', '', query_for_classification, flags=re.IGNORECASE)
    
    
    lower_query = query_for_classification.lower()
    if ("tailwind" in lower_query or "html" in lower_query or "css" in lower_query) and ("build" in lower_query or "landing page" in lower_query or "website" in lower_query or "full-stack developer" in lower_query):
        logger.info("[Triage] Hardcoded intercept: Web development query detected. Routing to CODING_COMPLEX.")
        return TaskType.CODING_COMPLEX, None

    result = _fallback_classify(query_for_classification)
    if result is not None:
        
        if result == TaskType.CONTROL and ("mockup" in lower_query or "terminal element" in lower_query or "terminal window" in lower_query):
            pass
        else:
            return result, None

    
    
    if history:
        for msg in history:
            c = msg.get("content", "")
            if "OBSERVATION:" in c or '{"action":' in c:
                return TaskType.CONTROL, None

    
    
    
    
    from src.iris import _model_pool, ModelRole
    
    _active_role = None
    if _model_pool:
        
        _active_role_str = next(reversed(_model_pool))
        try:
            _active_role = ModelRole(_active_role_str)
        except ValueError:
            pass

    if _active_role is not None and history:
        role_to_task = {
            ModelRole.CODE: TaskType.CODING_SIMPLE,
            ModelRole.MATH: TaskType.MATH,
            ModelRole.CONTROL: TaskType.CONTROL,
            ModelRole.REASONING: TaskType.REASONING,
            ModelRole.GENERAL: TaskType.GENERAL,
        }
        if _active_role in role_to_task:
            return role_to_task[_active_role], None

    minimized = _minimize_history(history, max_entries=2)
    triage_messages = [{"role": "system", "content": TRIAGE_SYSTEM_PROMPT}]
    for msg in minimized:
        c = msg["content"]
        if len(c) > 150:
            c = c[:150] + "...[truncated]"
        triage_messages.append({"role": msg["role"], "content": c})

    triage_query = query_for_classification
    if len(triage_query) > 1500:
        triage_query = triage_query[:1000] + "\n\n...[content truncated for routing]...\n\n" + triage_query[-500:]
    
    triage_messages.append({"role": "user", "content": triage_query})

    llm = load_model(ModelRole.TRIAGE)
    res = llm.create_chat_completion(
        messages=triage_messages,
        max_tokens=64,
        temperature=0.1,
    )
    answer = res["choices"][0]["message"]["content"].strip()
    if not _keep_loaded:
        unload_model()

    tag_map: Dict[str, TaskType] = {
        "GENERAL":       TaskType.GENERAL,
        "REASONING":     TaskType.REASONING,
        "MATH":          TaskType.MATH,
        "CODING_SIMPLE": TaskType.CODING_SIMPLE,
        "CODE_SIMPLE":   TaskType.CODING_SIMPLE,
        "CODING_COMPLEX":TaskType.CODING_COMPLEX,
        "CODE_COMPLEX":  TaskType.CODING_COMPLEX,
        "CONTROL":       TaskType.CONTROL,
    }

    search_match = re.search(r'\[\s*route:\s*SEARCH:\s*(.*?)\s*\]', answer, re.IGNORECASE)
    if search_match:
        kw = search_match.group(1).strip()
        if kw.lower() in ["keywords", "query"]:
            kw = ""
        return TaskType.SEARCH, kw

    for tag, ttype in tag_map.items():
        if re.search(rf'\[\s*route:\s*{re.escape(tag)}\s*\]', answer, re.IGNORECASE):
            return ttype, None

    if answer:
        answer_words = len(answer.split())
        
        GREETING_PATTERNS = re.compile(
            r'^(hi|hey|hello|howdy|greetings|yo|sup|good\s*(morning|afternoon|evening|day|night)|'
            r'welcome|hiya|what\'?s?\s*up|how\s*are\s*you|nice\s*to\s*meet|'
            r'i\'m\s+iris|i\s+am\s+iris|iris\s+here|i\'m\s+an?\s+ai)',
            re.IGNORECASE
        )
        is_greeting_reply = (
            answer_words <= 30
            and (
                GREETING_PATTERNS.search(answer)
                or (answer_words <= 6 and not re.search(r'\b(how\s+many|count|letter|spell|number)\b', answer, re.IGNORECASE))
            )
            and not re.search(
                r'\b(is|are|was|were|has|have|had|will|would|can|could|do|does|did|because|therefore|however)\b',
                answer, re.IGNORECASE
            )
        )
        if is_greeting_reply:
            return None, answer

        logger.info(
            f"[Triage] No routing tag — redirecting to REASONING to prevent hallucination. "
            f"Triage said: {answer[:80]}..."
        )
        return TaskType.REASONING, None

    return None, answer



def _quality_guard(text: str) -> str:
    # Scrub LaTeX/math syntax that polluted code blocks at generation time
    def _scrub_latex_in_code(m: re.Match) -> str:
        block = m.group(0)
        block = re.sub(r'\$([^$\n]*)\$', r'\1', block)
        block = re.sub(r'\$\$[\s\S]*?\$\$', '', block)
        block = re.sub(r'(def |class )([\w$\\{}_^]+)', lambda mm: mm.group(1) + re.sub(r'[\\${}^]|_(?=\{)', '_', mm.group(2)).strip('_'), block)
        block = re.sub(r'\\(?:boxed|frac|sqrt|text|mathrm|left|right)\{[^}]*\}', '', block)
        return block

    text = re.sub(r'```[\s\S]*?```', _scrub_latex_in_code, text)

    text = re.sub(
        r"\\boxed{((?:[^{}]|{[^{}]*})*)}" ,
        r'<span style="border: 2px solid #4CAF50; padding: 2px 6px; border-radius: 4px; font-weight: bold; background-color: rgba(76, 175, 80, 0.1);">\1</span>',
        text
    )

    text = re.sub(
        r"(?i)(I('m| am) (DeepSeek|Qwen|Intern|Hermes|a large language model|an AI language model)"
        r"[^.]*\.?\s*)",
        "", text
    ).strip()

    for open_tag, close_tag in [("<think>", "</think>"), ("<thought>", "</thought>"), ("<|thought_start|>", "<|thought_end|>")]:
        if open_tag in text:
            has_close = close_tag in text
            is_at_end = text.strip().endswith(close_tag)

            if not has_close or is_at_end:
                if has_close:
                    text = text.replace(close_tag, "")

                if "\n\n" in text:
                    parts = text.rsplit("\n\n", 1)
                else:
                    parts = text.rsplit("\n", 1)

                if len(parts) > 1 and parts[1].strip():
                    thought = parts[0]
                    actual = parts[1]
                    text = f"{thought}\n{close_tag}\n\n{actual}"
                else:
                    text += f"\n{close_tag}"

    return text or "I'm Iris AI."





def _stream_tokens(
    role: ModelRole,
    messages: List[Dict[str, str]],
    max_tokens: int = 0,
    temperature: float = 0.7,
    think_mode: str = "pass",
    system_prompt_override: Optional[str] = None,
    settings: Optional[dict] = None
) -> Generator[Dict[str, str], None, None]:
    global _keep_loaded

    if not isinstance(messages, list) or not all(isinstance(msg, dict) and "role" in msg and "content" in msg for msg in messages):
        yield {"type": "token", "content": "\n\n> [ERROR] **Iris Error:** Invalid messages format passed to generator."}
        return

    
    if not messages or not messages[-1]["content"].strip():
        yield {"type": "token", "content": "Please enter a valid query."}
        return

    llm = load_model(role)
    if not llm:
        yield {"type": "token", "content": f"\n\n> [ERROR] **Iris Error:** Failed to load model for role `{role.value}`. Check memory or installation."}
        return

    sys_prompt = system_prompt_override if system_prompt_override is not None else _system_prompt_for(role)
    if role not in (ModelRole.TRIAGE, ModelRole.ROUTER) and messages and messages[-1]["role"] == "user":
        sys_prompt += _language_directive(messages[-1]["content"])

    # --- History Sanitization: strip bleed-causing artifacts per agent role ---
    def _sanitize_for_role(msgs: List[Dict[str, str]], target_role: ModelRole) -> List[Dict[str, str]]:
        clean = []
        for m in msgs:
            content = m.get("content", "")
            role_tag = m.get("role", "user")
            # Always strip <think> blocks from history (they belong inside one turn only)
            content = re.sub(r'<think>[\s\S]*?</think>', '', content, flags=re.IGNORECASE).strip()
            content = re.sub(r'<\|thought_start\|>[\s\S]*?<\|thought_end\|>', '', content, flags=re.IGNORECASE).strip()
            content = re.sub(r'<thought>[\s\S]*?</thought>', '', content, flags=re.IGNORECASE).strip()
            # Always strip leaked [SYSTEM DIRECTIVE: ...] text injected into previous messages
            content = re.sub(r'\[SYSTEM DIRECTIVE:[^\]]*\]', '', content).strip()
            # Always strip "System Instructions:\n..." injected by previous turns
            content = re.sub(r'^System Instructions:\n.*?\n\nUser Query:\n', '', content, flags=re.DOTALL).strip()
            if target_role == ModelRole.CODE:
                # Strip LaTeX/math from history when feeding CODE agent (prevents syntax pollution)
                content = re.sub(r'\\boxed\{[^}]*\}', '', content)
                content = re.sub(r'\$\$[\s\S]*?\$\$', '', content)
                content = re.sub(r'\$[^$\n]+\$', '', content)
            elif target_role in (ModelRole.REASONING, ModelRole.GENERAL, ModelRole.MATH):
                # Compress long code blocks from history to avoid CODE-mode bleed into text agents
                def _compress_code(m):
                    lines = m.group(0).count('\n')
                    if lines > 10:
                        lang = m.group(0).split('\n')[0].replace('```', '').strip()
                        return f'```{lang}\n[{lines}-line code block from previous turn — omitted]\n```'
                    return m.group(0)
                content = re.sub(r'```[\s\S]*?```', _compress_code, content)
            if content.strip():
                clean.append({"role": role_tag, "content": content})
        return clean

    sanitized_messages = _sanitize_for_role(messages, role)

    if role in (ModelRole.REASONING, ModelRole.GENERAL):
        full_messages = list(sanitized_messages)
        # Inject system prompt into the LAST (current) user message, not the oldest one
        last_user_idx = next(
            (i for i in range(len(full_messages) - 1, -1, -1) if full_messages[i]["role"] == "user"),
            None
        )
        if last_user_idx is not None:
            full_messages[last_user_idx] = {
                "role": "user",
                "content": f"System Instructions:\n{sys_prompt}\n\nUser Query:\n{full_messages[last_user_idx]['content']}"
            }
        else:
            full_messages = [{"role": "user", "content": f"System Instructions:\n{sys_prompt}"}] + full_messages
    else:
        full_messages = [{"role": "system", "content": sys_prompt}] + sanitized_messages

    cfg = load_generation_config()
    model_cfg = cfg.get("model_settings", {}).get(role.value, {})

    
    actual_temp = temperature
    rep_penalty = 1.0
    freq_penalty = 0.05 if role in (ModelRole.CODE, ModelRole.REASONING) else 0.0
    pres_penalty = 0.05 if role in (ModelRole.CODE, ModelRole.REASONING) else 0.0
    top_p = 0.9
    top_k = 40

    
    actual_temp = cfg.get("temperature", actual_temp)
    rep_penalty = cfg.get("repetition_penalty", rep_penalty)
    freq_penalty = cfg.get("frequency_penalty", freq_penalty)
    pres_penalty = cfg.get("presence_penalty", pres_penalty)
    top_p = cfg.get("top_p", top_p)
    top_k = cfg.get("top_k", top_k)
    max_tokens = max_tokens or cfg.get("max_new_tokens", 4096)

    
    actual_temp = model_cfg.get("temperature", actual_temp)
    rep_penalty = model_cfg.get("repetition_penalty", rep_penalty)
    freq_penalty = model_cfg.get("frequency_penalty", freq_penalty)
    pres_penalty = model_cfg.get("presence_penalty", pres_penalty)
    top_p = model_cfg.get("top_p", top_p)
    top_k = model_cfg.get("top_k", top_k)

    
    if settings:
        actual_temp = settings.get("temperature", actual_temp)
        rep_penalty = settings.get("repetition_penalty", rep_penalty)

    THINK_PAIRS = [
        ("<think>", "</think>"),
        ("<|thought_start|>", "<|thought_end|>"),
        ("<thought>", "</thought>")
    ]
    CLOSE_TAG_MAP = {open_tag: close_tag for open_tag, close_tag in THINK_PAIRS}

    model_name = _get_model_filename(role)

    in_thinking = False
    thinking_tag = ""
    hidden_buffer = ""

    for loop_idx in range(5):
        
        
        _ca_cfg = load_generation_config().get("compressed_attention", {})
        if _ca_cfg.get("enabled", False) and len(full_messages) > 4:
            _query = messages[-1].get("content", "") if messages else ""
            _compressed = smart_compress(
                full_messages, query=_query,
                n_ctx=llm.n_ctx(),
                max_output_tokens=min(max_tokens, 1024),
                llm=llm,
                profile=load_generation_config().get("size", "tiny"),
            )
            if _compressed.compressed_tokens < _compressed.original_tokens:
                logger.info(
                    f"[CA] {_compressed.strategy_used.value}: "
                    f"{_compressed.original_tokens}→{_compressed.compressed_tokens} tokens "
                    f"({100*(1-_compressed.compressed_tokens/max(_compressed.original_tokens,1)):.0f}% saved)"
                )
                full_messages = _compressed.messages

        full_messages, _ = auto_compact_for_role(full_messages, role=role, max_output_tokens=min(max_tokens, 1024))
        
        logger.debug(f"[Model Start] Role: {role.value.upper()} | Model: {model_name}")
        stream = llm.create_chat_completion(
            messages=full_messages,
            stream=True,
            max_tokens=max_tokens,
            temperature=actual_temp,
            repeat_penalty=rep_penalty,
            frequency_penalty=freq_penalty,
            presence_penalty=pres_penalty,
            top_p=top_p,
            top_k=top_k,
            min_p=0.05,
            seed=42 + loop_idx,
            stop=["</s>", "<|eot_id|>", "<|end_of_text|>", "<|im_end|>", "<step_end>"],
        )
        loop_content = ""
        finish_reason = "stop"
        buffer = ""
        token_count = 0

        for chunk in stream:
            choices = chunk.get("choices", [])
            if not choices:
                continue
            choice = choices[0]
            token = choice.get("delta", {}).get("content", "")
            if not token:
                continue
            
            token_count += 1

            if think_mode == "pass":
                yield {"type": "token", "content": token}
                loop_content += token
                if "finish_reason" in choice and choice["finish_reason"]:
                    finish_reason = choice["finish_reason"]
                continue

            buffer += token

            if think_mode == "hide":
                while True:
                    if not in_thinking:
                        found = False
                        for tag, close in THINK_PAIRS:
                            if tag in buffer:
                                idx = buffer.index(tag)
                                if idx > 0:
                                    yield {"type": "token", "content": buffer[:idx]}
                                    loop_content += buffer[:idx]
                                in_thinking = True
                                thinking_tag = tag
                                loop_content += tag
                                buffer = buffer[idx + len(tag):]
                                found = True
                                break
                        if found:
                            continue
                        partial = False
                        for tag, close in THINK_PAIRS:
                            for i in range(1, len(tag)):
                                if buffer.endswith(tag[:i]):
                                    before = buffer[:-i]
                                    if before:
                                        yield {"type": "token", "content": before}
                                        loop_content += before
                                    buffer = buffer[-i:]
                                    partial = True
                                    break
                            if partial:
                                break
                        if partial:
                            break
                        yield {"type": "token", "content": buffer}
                        loop_content += buffer
                        buffer = ""
                        break
                    else:
                        close_tag = CLOSE_TAG_MAP.get(thinking_tag, "</think>")
                        if close_tag in buffer:
                            idx = buffer.index(close_tag)
                            loop_content += buffer[:idx] + close_tag
                            in_thinking = False
                            thinking_tag = ""
                            buffer = buffer[idx + len(close_tag):]
                            hidden_buffer = ""
                            continue
                        partial = False
                        for i in range(1, len(close_tag)):
                            if buffer.endswith(close_tag[:i]):
                                hidden_buffer += buffer[:-i]
                                buffer = buffer[-i:]
                                partial = True
                                break
                        if partial:
                            break
                        hidden_buffer += buffer
                        loop_content += buffer
                        buffer = ""

                        if len(hidden_buffer) > 500000:
                            think_mode = "pass"
                            content_to_yield = f"{thinking_tag}\n{hidden_buffer}" if thinking_tag else hidden_buffer
                            yield {"type": "token", "content": content_to_yield}
                            loop_content += content_to_yield
                            hidden_buffer = ""
                            continue
                        break

            elif think_mode == "show":
                while True:
                    if not in_thinking:
                        found = False
                        for tag, close in THINK_PAIRS:
                            if tag in buffer:
                                idx = buffer.index(tag)
                                if idx > 0:
                                    yield {"type": "token", "content": buffer[:idx]}
                                    loop_content += buffer[:idx]
                                in_thinking = True
                                thinking_tag = tag
                                loop_content += tag
                                buffer = buffer[idx + len(tag):]
                                found = True
                                break
                        if found:
                            continue
                        partial = False
                        for tag, close in THINK_PAIRS:
                            for i in range(1, len(tag)):
                                if buffer.endswith(tag[:i]):
                                    before = buffer[:-i]
                                    if before:
                                        yield {"type": "token", "content": before}
                                        loop_content += before
                                    buffer = buffer[-i:]
                                    partial = True
                                    break
                            if partial:
                                break
                        if partial:
                            break
                        yield {"type": "token", "content": buffer}
                        loop_content += buffer
                        buffer = ""
                        break
                    else:
                        close_tag = CLOSE_TAG_MAP.get(thinking_tag, "</think>")
                        if close_tag in buffer:
                            idx = buffer.index(close_tag)
                            thinking_text = buffer[:idx]
                            if thinking_text.strip():
                                yield {"type": "thinking", "content": thinking_text}
                            loop_content += thinking_text + close_tag
                            in_thinking = False
                            thinking_tag = ""
                            buffer = buffer[idx + len(close_tag):]
                            continue
                        partial = False
                        for i in range(1, len(close_tag)):
                            if buffer.endswith(close_tag[:i]):
                                before = buffer[:-i]
                                if before.strip():
                                    yield {"type": "thinking", "content": before}
                                loop_content += before
                                buffer = buffer[-i:]
                                partial = True
                                break
                        if partial:
                            break
                        if buffer.strip():
                            yield {"type": "thinking", "content": buffer}
                        loop_content += buffer
                        buffer = ""
                        break

            elif think_mode == "status":
                while True:
                    if not in_thinking:
                        found = False
                        for tag, close in THINK_PAIRS:
                            if tag in buffer:
                                idx = buffer.index(tag)
                                if idx > 0:
                                    yield {"type": "token", "content": buffer[:idx]}
                                    loop_content += buffer[:idx]
                                yield {"type": "status", "content": "Thinking..."}
                                in_thinking = True
                                thinking_tag = tag
                                loop_content += tag
                                buffer = buffer[idx + len(tag):]
                                found = True
                                break
                        if found:
                            continue
                        partial = False
                        for tag, close in THINK_PAIRS:
                            for i in range(1, len(tag)):
                                if buffer.endswith(tag[:i]):
                                    before = buffer[:-i]
                                    if before:
                                        yield {"type": "token", "content": before}
                                        loop_content += before
                                    buffer = buffer[-i:]
                                    partial = True
                                    break
                            if partial:
                                break
                        if partial:
                            break
                        yield {"type": "token", "content": buffer}
                        loop_content += buffer
                        buffer = ""
                        break
                    else:
                        close_tag = CLOSE_TAG_MAP.get(thinking_tag, "</think>")
                        if close_tag in buffer:
                            idx = buffer.index(close_tag)
                            loop_content += buffer[:idx] + close_tag
                            in_thinking = False
                            thinking_tag = ""
                            buffer = buffer[idx + len(close_tag):]
                            continue
                        partial = False
                        for i in range(1, len(close_tag)):
                            if buffer.endswith(close_tag[:i]):
                                buffer = buffer[-i:]
                                partial = True
                                break
                        if partial:
                            break
                        loop_content += buffer
                        buffer = ""
                        break

            if "finish_reason" in choice and choice["finish_reason"]:
                finish_reason = choice["finish_reason"]

        logger.debug(f"[Model Finish] Role: {role.value.upper()} | Model: {model_name} | Tokens consumed: {token_count} | Status: {finish_reason}")

        if buffer:
            if think_mode == "hidden" and in_thinking:
                pass
            elif think_mode == "status" and in_thinking:
                pass
            elif think_mode == "show" and in_thinking:
                if buffer.strip():
                    yield {"type": "thinking", "content": buffer}
                loop_content += buffer
            else:
                yield {"type": "token", "content": buffer}
                loop_content += buffer

        
        if finish_reason == "stop":
            looks_incomplete = False
            prompt_est = sum(len(m.get("content", "")) for m in full_messages) // 4
            if in_thinking:
                # Model stopped mid-think (forgot to close </think>). Do NOT loop —
                # synthetically close the tag and treat as complete.
                close_tag = CLOSE_TAG_MAP.get(thinking_tag, "</think>")
                synthetic_close = f"\n{close_tag}"
                yield {"type": "thinking", "content": synthetic_close}
                loop_content += synthetic_close
                in_thinking = False
                # looks_incomplete stays False — we're done
            elif loop_content.count("```") % 2 != 0:
                looks_incomplete = True
            
            logger.debug(f"DEBUG LOOP CONTENT END: {repr(loop_content[-20:])} | Incomplete? {looks_incomplete}")
            
            if looks_incomplete:
                finish_reason = "length"

        yield {"type": "finish", "reason": finish_reason}

        if finish_reason == "length":
            if role in (ModelRole.REASONING, ModelRole.MATH):
                # Reasoning models are trained to strictly start with <think>. 
                # Sending a User message to "Continue" forces them to start a new thought process
                # from scratch, causing infinite repetition.
                logger.warning(f"[Stream] Model {role.value} hit length limit. Stopping to prevent repeat-loop.")
                break
                
            full_messages.append({"role": "assistant", "content": loop_content})
            full_messages.append({
                "role": "user",
                "content": "Continue exactly where you left off, from the very next character. "
                "Do not repeat anything."
            })
        else:
            break


def ask_stream(
    user_query: str,
    history: List[Dict[str, str]],
    retriever=None,
    force_role: Optional[ModelRole] = None,
    show_thinking: bool = True,
    keep_loaded: bool = False,
    settings: Optional[dict] = None,
) -> Generator[Dict[str, str], None, None]:
    
    global _keep_loaded
    _keep_loaded = keep_loaded

    img_match = re.match(r'^\[IMAGE_UPLOADED:\s*(.+?)\]\s*(.*)$', user_query, flags=re.DOTALL)
    if img_match:
        image_path = img_match.group(1).strip()
        prompt = img_match.group(2).strip()
        if not prompt:
            prompt = "Describe this image in detail."
        
        yield {"type": "status", "content": "Analyzing image with Vision model..."}
        try:
            res = analyze_image(image_path, prompt)
            yield {"type": "token", "content": res}
            yield {"type": "raw_response", "content": res}
        except Exception as e:
            yield {"type": "token", "content": f"Vision analysis failed: {e}"}
        
        try:
            os.unlink(image_path)
        except Exception:
            pass
        return

    if force_role is not None:
        if isinstance(force_role, str):
            force_role = ModelRole(force_role)
        yield {"type": "status", "content": f"Testing forced role: {force_role.value}..."}

        context = ""
        if retriever is not None and len(user_query.split()) >= 8:
            context = retriever.retrieve(user_query, top_k=3, category="general")

        sys_p = _system_prompt_for(force_role)
        if context:
            sys_p = f"REFERENCE EXCERPT:\n{context}\n\n{sys_p}"

        optimized = [{"role": "user", "content": user_query}]
        if history:
            cfg = load_generation_config()
            profile = str(cfg.get("compacting_profile", "medium")).lower()
            num_history = 2 if profile == "aggressive" else (10 if profile == "low" else 5)
            recent = history[-num_history:]
            optimized = [{"role": m["role"], "content": m["content"]} for m in recent] + optimized

        full = ""
        for ev in _stream_tokens(
            force_role, optimized,
            temperature=0.5 if force_role == ModelRole.REASONING else 0.2,
            think_mode="show" if force_role in (ModelRole.REASONING, ModelRole.GENERAL) else "hide",
            system_prompt_override=sys_p
        ):
            yield ev
            if ev["type"] == "token":
                full += ev["content"]

        if not _keep_loaded:
            unload_model()

        if force_role == ModelRole.MATH:
            full, mw = _apply_math_harness(full)
            for w in mw:
                yield w
            
            _, math_report = apply_smart_harness_math(full)
            if math_report.final_answer_extracted:
                yield {"type": "status", "content": f"Answer: {math_report.final_answer_extracted}"}
            if not math_report.self_consistent:
                yield {"type": "harness_warning", "content": "Self-consistency check FAILED — steps may not lead to final answer"}
        elif force_role == ModelRole.CODE:
            lang = _detect_language(full) or "python"
            err = check_syntax(full, lang)
            if err:
                yield {"type": "syntax_error", "content": f"Syntax error in {lang}: {err}"}
            full, hw = _apply_and_yield_harness(full, lang)
            for w in hw:
                yield w
            
            _, sandbox = apply_smart_harness_code(full, language=lang)
            if sandbox.result == SandboxResult.PASS:
                yield {"type": "status", "content": f"Sandbox verified: {sandbox.tests_passed} tests passed"}
            elif sandbox.result == SandboxResult.FAIL:
                yield {"type": "harness_warning", "content": f"Sandbox: {sandbox.tests_failed} test(s) failed"}

            
            if isinstance(settings, dict) and settings.get("code_review"):
                yield {"type": "clear"}
                yield {"type": "status", "content": "Reviewing code..."}
                _rmsgs = optimized + [
                    {"role": "assistant", "content": full},
                    {"role": "user", "content": "Review this code. Fix issues. Return corrected code in a block or say 'No issues found.'"}
                ]
                _rev = ""
                for ev in _stream_tokens(ModelRole.CODE, _rmsgs, max_tokens=None, temperature=0.2, think_mode="pass", system_prompt_override=REVIEWER_SYSTEM_PROMPT):
                    yield ev
                    if ev["type"] == "token":
                        _rev += ev["content"]
                if not _keep_loaded:
                    unload_model()
                _rl = _detect_language(_rev) or lang
                _rev, _hw = _apply_and_yield_harness(_rev, _rl)
                for w in _hw:
                    yield w
                full = _rev

        cleaned = _quality_guard(full)
        if cleaned != full:
            yield {"type": "clear"}
            yield {"type": "token", "content": cleaned}
        yield {"type": "raw_response", "content": cleaned}
        return

    if _is_continuation(user_query, history):
        yield {"type": "status", "content": "Resuming generation..."}
        yield from _run_continuation(user_query, history, retriever)
        return

    web_context = ""
    original_query = user_query.strip()
    
    
    if original_query.lower().startswith("@web "):
        search_term = original_query[5:].strip()
        user_query = search_term
        task_type = TaskType.SEARCH
        direct_answer = search_term
    else:
        yield {"type": "status", "content": "Analyzing query..."}
        task_type, direct_answer = classify_task(user_query, history)

    _INTROSPECTION_RE = re.compile(
        r'\b(how\s+many|count\s+(the\s+)?|number\s+of\s+|how\s+often|occurrences?\s+of\s+)'
        r'(letter|character|char|vowel|consonant|digit|syllable|word|repeat|letter\s+[a-z]|[a-z]\s+in\b)',
        re.IGNORECASE
    )
    _SPELL_RE = re.compile(
        r'\b(spell(ing)?|spell\s+out|how\s+do\s+you\s+spell|is\s+\w+\s+spelled\s+correctly)\b',
        re.IGNORECASE
    )

    if task_type == TaskType.SEARCH and (
        _INTROSPECTION_RE.search(original_query) or _SPELL_RE.search(original_query)
    ):
        logger.info("[Routing] Overriding SEARCH → REASONING for letter/word introspection query.")
        task_type = TaskType.REASONING

    if task_type == TaskType.SEARCH:
        search_term = direct_answer or user_query
        yield {"type": "status", "content": f"Searching the web for '{search_term}'..."}
        try:
            from src.web_search import WebSearch
            ws = WebSearch()
            web_context = ws.search_to_context(search_term, max_results=3)
            if not web_context:
                yield {"type": "status", "content": "Web search returned no results."}
        except Exception as e:
            logger.warning(f"Web search failed: {e}")
            yield {"type": "status", "content": "Web search unavailable."}
        
        
        task_type = TaskType.REASONING

    if task_type == TaskType.CONTROL:
        from src.controller import (
            _get_agent_system_prompt, parse_ai_response, execute_action_by_dict,
        )

        from src.system_actions import get_hardcoded_action_json
        hardcoded_json = get_hardcoded_action_json(user_query)
        if hardcoded_json:
            action_dict = parse_ai_response(hardcoded_json)
            if action_dict:
                action_name = action_dict.get("action", "unknown")
                yield {"type": "status", "content": f"Executing: {action_name}"}
                result = execute_action_by_dict(action_dict)
                reply_text = f"Action '{action_name}' executed.\n\nResult:\n{result}"
                yield {"type": "action_result", "content": f"Action '{action_name}' Executed.\nResult:\n{result}"}
                yield {"type": "token", "content": reply_text}
                yield {"type": "raw_response", "content": reply_text}
                if not _keep_loaded:
                    unload_model()
                return


        yield {"type": "status", "content": "Generating computer command..."}
        control_messages = [{"role": "system", "content": _get_agent_system_prompt()}, {"role": "user", "content": user_query}]
        
        
        from src.system_actions import is_complex_control
        if is_complex_control(user_query, history):
            logger.info("[Routing] Complex control detected. Loading 3B model (ModelRole.CODE) for control action.")
            control_llm = load_model(ModelRole.CODE)
        else:
            logger.info("[Routing] Simple control detected. Loading 0.5B model (ModelRole.CONTROL) for control action.")
            control_llm = load_model(ModelRole.CONTROL)
        
        action_json = ""
        for chunk in control_llm.create_chat_completion(messages=control_messages, max_tokens=1024, stream=True, temperature=0.1):
            delta = chunk["choices"][0].get("delta", {})
            if "content" in delta:
                action_json += delta["content"]

        if not _keep_loaded:
            unload_model()

        action_dict = parse_ai_response(action_json)
        if action_dict:
            action_name = action_dict.get("action", "unknown")
            yield {"type": "status", "content": f"Executing: {action_name}"}
            result = execute_action_by_dict(action_dict)
            reply_text = f"Action '{action_name}' executed.\n\nResult:\n{result}"
            yield {"type": "action_result", "content": f"Action '{action_name}' Executed.\nResult:\n{result}"}
            
            
            
            
            yield {"type": "token", "content": reply_text}
            yield {"type": "raw_response", "content": reply_text}
        else:
            fail_text = "I couldn't translate that into an action I can run. Could you rephrase it?"
            yield {"type": "status", "content": "Action failed to parse."}
            yield {"type": "token", "content": fail_text}
            yield {"type": "raw_response", "content": fail_text}
        if not _keep_loaded:
            unload_model()
        return



    if task_type is None:
        if direct_answer:
            logger.debug(f"RAW DIRECT ANSWER:\n{repr(direct_answer)}\n\n")
            cleaned = _quality_guard(direct_answer)
            logger.debug(f"CLEANED:\n{repr(cleaned)}\n\n")
            yield {"type": "token", "content": cleaned}
            yield {"type": "raw_response", "content": cleaned}
        return

    yield {"type": "status", "content": f"Task: {task_type.value.upper()}"}

    context = ""
    if retriever is not None and len(user_query.split()) >= 3:
        rag_cats = {
            TaskType.CODING_SIMPLE:  "coding",
            TaskType.CODING_COMPLEX: "coding",
            TaskType.MATH:           "math",
            TaskType.REASONING:      "reasoning",
            TaskType.GENERAL:        "general",
        }
        context = retriever.retrieve(user_query, top_k=3, category=rag_cats.get(task_type, "general"))

    final_query = user_query
    if context:
        final_query = (
            f"[RETRIEVED CONTEXT]\n{context}\n[END RETRIEVED CONTEXT]\n\n"
            f"If the retrieved context is relevant, use it to answer the question. "
            f"If it is completely irrelevant to the question, IGNORE it and answer from your own knowledge.\n\n"
            f"{final_query}"
        )
    if web_context and "(No web results found" not in web_context and "Web search unavailable" not in web_context:
        final_query = (
            f"[WEB SEARCH RESULTS]\n{web_context}\n[END WEB SEARCH RESULTS]\n\n"
            f"User Query: {user_query}\n\n"
            f"INSTRUCTIONS: You MUST think step-by-step inside a <think> block before answering. "
            f"Use the search results above to inform your answer, especially for recent events or specific facts. "
            f"If the search results are incomplete, you may use your internal knowledge to supplement the answer. "
            f"Respond in the SAME LANGUAGE as the user's query."
        )

    optimized = [{"role": "user", "content": final_query}]
    if history:
        cfg = load_generation_config()
        profile = str(cfg.get("compacting_profile", "medium")).lower()
        num_history = 2 if profile == "aggressive" else (10 if profile == "low" else 5)
        recent = history[-num_history:]
        optimized = [{"role": m["role"], "content": m["content"]} for m in recent] + optimized

    optimized, _ = auto_compact_for_role(optimized, role=ModelRole.REASONING if task_type == TaskType.REASONING else (ModelRole.CODE if task_type in (TaskType.CODING_SIMPLE, TaskType.CODING_COMPLEX) else ModelRole.GENERAL), max_output_tokens=4096)

    if task_type == TaskType.GENERAL:
        yield {"type": "status", "content": "Thinking..."}
        full = ""
        for ev in _stream_tokens(ModelRole.GENERAL, optimized, max_tokens=4096, temperature=0.3, think_mode="pass"):
            yield ev
            if ev["type"] == "token":
                full += ev["content"]
        if not _keep_loaded:
            unload_model()
        cleaned = _quality_guard(full)
        if cleaned != full:
            yield {"type": "clear"}
            yield {"type": "token", "content": cleaned}
        yield {"type": "raw_response", "content": cleaned}

    elif task_type == TaskType.REASONING:
        yield {"type": "status", "content": "Analyzing..."}
        full = ""
        _r_temp = 0.4 if web_context else 0.3
        _r_tokens = 6144 if web_context else 4096
        for ev in _stream_tokens(ModelRole.REASONING, optimized, max_tokens=_r_tokens, temperature=_r_temp, think_mode="show"):
            yield ev
            if ev["type"] == "token":
                full += ev["content"]
        if not _keep_loaded:
            unload_model()
        cleaned = _quality_guard(full)

        # --- Output Completeness Validation ---
        # Extract visible content (outside <think> blocks) to check for evasion-loophole collapse
        _visible = re.sub(r'<think>[\s\S]*?</think>', '', cleaned, flags=re.IGNORECASE).strip()
        _visible = re.sub(r'<\|thought_start\|>[\s\S]*?<\|thought_end\|>', '', _visible, flags=re.IGNORECASE).strip()
        _EVASION_PHRASES = re.compile(
            r'^(the final answer is[:\s]*|routing complete\.?|done\.?|answer[:\s]*|result[:\s]*)$',
            re.IGNORECASE
        )
        _is_collapsed = (
            len(_visible) < 80
            or _EVASION_PHRASES.match(_visible.strip())
        )
        if _is_collapsed:
            logger.warning(f"[Completeness] Evasion-loophole detected. Visible output too thin ({len(_visible)} chars). Attempting recovery.")
            # Recovery 1: extract the think block content and surface it as the answer
            _think_match = re.search(r'<think>([\s\S]*?)</think>', cleaned, re.IGNORECASE)
            if _think_match:
                _think_content = _think_match.group(1).strip()
                if len(_think_content) > 100:
                    _recovered = (
                        f"<think>{_think_content}</think>\n\n"
                        f"*(Note: The model's visible answer was too brief — the reasoning above contains the full analysis.)*"
                    )
                    yield {"type": "clear"}
                    yield {"type": "token", "content": _recovered}
                    yield {"type": "raw_response", "content": _recovered}
                    return
            # Recovery 2: re-prompt explicitly demanding a full answer
            yield {"type": "clear"}
            yield {"type": "status", "content": "Retrying for complete response..."}
            retry_msgs = optimized + [
                {"role": "assistant", "content": full},
                {"role": "user", "content": (
                    "Your previous response was incomplete — it only contained a closing phrase without the actual answer. "
                    "Please provide the FULL, complete explanation now. Do not skip or abbreviate."
                )}
            ]
            retry_full = ""
            for ev in _stream_tokens(ModelRole.REASONING, retry_msgs, max_tokens=_r_tokens, temperature=0.5, think_mode="show"):
                yield ev
                if ev["type"] == "token":
                    retry_full += ev["content"]
            cleaned = _quality_guard(retry_full)

        if cleaned != full:
            yield {"type": "clear"}
            yield {"type": "token", "content": cleaned}
        yield {"type": "raw_response", "content": cleaned}


    elif task_type == TaskType.MATH:
        yield {"type": "status", "content": "Solving..."}
        full = ""
        for ev in _stream_tokens(ModelRole.MATH, optimized, max_tokens=4096, temperature=0.2, think_mode="show"):
            yield ev
            if ev["type"] == "token":
                full += ev["content"]
        if not _keep_loaded:
            unload_model()

        full, mw = _apply_math_harness(full)
        for w in mw:
            yield w

        
        _, math_report = apply_smart_harness_math(full)
        if math_report.final_answer_extracted:
            yield {"type": "status", "content": f"Answer: {math_report.final_answer_extracted}"}
        if not math_report.numerical_match and math_report.expected_value is not None:
            yield {"type": "harness_warning", "content": f"Numerical mismatch: computed={math_report.computed_value}, expected={math_report.expected_value}"}
        if not math_report.self_consistent:
            yield {"type": "harness_warning", "content": "Self-consistency check FAILED — steps may not lead to final answer"}

        lang = _detect_language(full)
        err = check_syntax(full, lang)
        if err:
            yield {"type": "syntax_error", "content": f"Syntax check in {lang or 'code'}: {err}"}
        yield {"type": "raw_response", "content": full}

    elif task_type == TaskType.CODING_SIMPLE:
        yield {"type": "status", "content": "Writing code..."}
        full = ""
        for ev in _stream_tokens(ModelRole.CODE, optimized, max_tokens=None, temperature=0.2, think_mode="pass", settings=settings):
            yield ev
            if ev["type"] == "token":
                full += ev["content"]
        if not _keep_loaded:
            unload_model()

        lang = _detect_language(full)
        err = check_syntax(full, lang)
        if err:
            yield {"type": "syntax_error", "content": f"Syntax error in {lang or 'code'}: {err}"}
            yield {"type": "clear"}
            yield {"type": "status", "content": "Auto-correcting syntax..."}

            correction_msgs = optimized + [
                {"role": "assistant", "content": full},
                {"role": "user",
                 "content": f"Fix ONLY the syntax errors:\n\n{err}\n\nReturn the complete corrected code."}
            ]
            corrected = ""
            for ev in _stream_tokens(ModelRole.CODE, correction_msgs, max_tokens=None, temperature=0.2, think_mode="pass", settings=settings):
                yield ev
                if ev["type"] == "token":
                    corrected += ev["content"]
            if not _keep_loaded:
                unload_model()

            second_err = check_syntax(corrected, lang)
            if second_err:
                yield {"type": "token", "content": "\n\n> \u26a0\ufe0f Auto-correction attempted but some errors may remain."}
            full = corrected

        lang = _detect_language(full) or "python"
        full, hw = _apply_and_yield_harness(full, lang)
        for w in hw:
            yield w

        
        if "```" in full:
            yield {"type": "status", "content": "Verifying code in sandbox..."}
            _, sandbox = apply_smart_harness_code(full, problem_description=user_query, language=lang)
            if sandbox.result == SandboxResult.PASS:
                yield {"type": "status", "content": f"Sandbox: {sandbox.tests_passed} tests passed"}
            elif sandbox.result == SandboxResult.FAIL:
                yield {"type": "harness_warning", "content": f"Sandbox: {sandbox.tests_passed}/{sandbox.tests_passed + sandbox.tests_failed} tests passed — some tests failed"}
            elif sandbox.syntax_error:
                yield {"type": "syntax_error", "content": f"Sandbox: {sandbox.syntax_error}"}
            elif sandbox.runtime_errors:
                for rerr in sandbox.runtime_errors[:3]:
                    yield {"type": "harness_warning", "content": f"Runtime: {rerr[:200]}"}

            
            if isinstance(settings, dict) and settings.get("code_review"):
                yield {"type": "clear"}
                yield {"type": "status", "content": "Reviewing code quality..."}
                _rmsgs = optimized + [
                    {"role": "assistant", "content": full},
                    {"role": "user", "content": "Review this code for correctness, edge cases, performance, and best practices. Fix issues inside a code block with filename comment, or say 'No issues found.'"}
                ]
                _rev = ""
                for ev in _stream_tokens(ModelRole.CODE, _rmsgs, max_tokens=None, temperature=0.2, think_mode="pass", system_prompt_override=REVIEWER_SYSTEM_PROMPT):
                    yield ev
                    if ev["type"] == "token":
                        _rev += ev["content"]
                if not _keep_loaded:
                    unload_model()
                _rl = _detect_language(_rev) or lang
                _rev, _hw = _apply_and_yield_harness(_rev, _rl)
                for w in _hw:
                    yield w
                full = _rev

        yield {"type": "raw_response", "content": full}

    elif task_type == TaskType.CODING_COMPLEX:
        yield from _run_complex_coding(user_query, history, optimized, context, retriever, settings)


def _apply_and_yield_harness(text: str, language: str) -> Tuple[str, List[dict]]:
    
    return _apply_harness(text, language)


def detect_user_language(text: str) -> Optional[str]:
    
    if not text:
        return None
    
    sample = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    sample = re.sub(r"https?://\S+", " ", sample)

    counts: Dict[str, int] = {}
    for ch in sample:
        cp = ord(ch)
        if 0x0600 <= cp <= 0x06FF or 0x0750 <= cp <= 0x077F or 0x08A0 <= cp <= 0x08FF:
            counts["Arabic"] = counts.get("Arabic", 0) + 1
        elif 0x0400 <= cp <= 0x04FF:
            counts["Russian"] = counts.get("Russian", 0) + 1
        elif 0x4E00 <= cp <= 0x9FFF:
            counts["Chinese"] = counts.get("Chinese", 0) + 1
        elif 0x3040 <= cp <= 0x30FF:
            counts["Japanese"] = counts.get("Japanese", 0) + 1
        elif 0xAC00 <= cp <= 0xD7AF:
            counts["Korean"] = counts.get("Korean", 0) + 1
        elif 0x0590 <= cp <= 0x05FF:
            counts["Hebrew"] = counts.get("Hebrew", 0) + 1
        elif 0x0900 <= cp <= 0x097F:
            counts["Hindi"] = counts.get("Hindi", 0) + 1
        elif 0x0370 <= cp <= 0x03FF:
            counts["Greek"] = counts.get("Greek", 0) + 1
        elif "a" <= ch.lower() <= "z":
            counts["English"] = counts.get("English", 0) + 1

    if not counts:
        return None
    
    
    non_latin = {k: v for k, v in counts.items() if k != "English"}
    if non_latin:
        return max(non_latin, key=non_latin.__getitem__)
    return "English"


def _language_directive(user_query: str) -> str:
    
    lang = detect_user_language(user_query)
    if not lang:
        return ""
    return (
        f"\n\n[SYSTEM DIRECTIVE: The user's message is written in {lang}. "
        f"You MUST write your final response in {lang}. "
        f"If you use a <think> block for reasoning, you should reason in English inside the <think> block to ensure accuracy, "
        f"and then output your final answer outside the <think> block in {lang}.]"
    )


def _detect_language(text: str) -> Optional[str]:
    blocks = extract_code_blocks(text)
    if blocks:
        lang = blocks[0][0]
        if lang != "unknown":
            return lang
    return None



def _run_continuation(
    user_query: str,
    history: List[Dict[str, str]],
    retriever,
    settings=None
) -> Generator[Dict[str, str], None, None]:
    
    optimized = [{"role": "user", "content": user_query}]
    if history:
        recent = history[-4:]
        optimized = [{"role": m["role"], "content": m["content"]} for m in recent] + optimized

    yield {"type": "status", "content": "Stage 1 \u2014 Continuing code..."}
    full = ""
    for ev in _stream_tokens(ModelRole.CODE, optimized, max_tokens=None, temperature=0.2, think_mode="pass", settings=settings):
        yield ev
        if ev["type"] == "token":
            full += ev["content"]
    if not _keep_loaded:
        unload_model()

    yield {"type": "clear"}
    yield {"type": "status", "content": "Stage 2 \u2014 Reviewing..."}

    review_msgs = optimized + [
        {"role": "assistant", "content": full},
        {"role": "user", "content": "Review the above continuation of the code project. "
         "Fix errors, fill gaps, ensure consistency. Return the final corrected code inside a ```python``` block, followed by a brief explanation."}
    ]
    reviewed = ""
    for ev in _stream_tokens(ModelRole.CODE, review_msgs, max_tokens=None, temperature=0.2, think_mode="pass", settings=settings, system_prompt_override=REVIEWER_SYSTEM_PROMPT):
        yield ev
        if ev["type"] == "token":
            reviewed += ev["content"]
    if not _keep_loaded:
        unload_model()

    lang = _detect_language(reviewed)
    err = check_syntax(reviewed, lang)
    if err:
        yield {"type": "syntax_error", "content": f"Syntax error in {lang or 'code'}: {err}"}

    rev_lang = _detect_language(reviewed) or "python"
    reviewed, hwc2 = _apply_and_yield_harness(reviewed, rev_lang)
    for w in hwc2:
        yield w

    yield {"type": "raw_response", "content": reviewed}




def _run_hermes_agent(
    user_query: str,
    history: List[Dict[str, str]],
    optimized: List[Dict[str, str]],
) -> Generator[Dict[str, str], None, None]:
    
    yield {"type": "status", "content": "Initializing Hermes Agent..."}

    agent = HermesAgentLoop(
        workspace_root=os.getcwd(),
        max_tool_calls=30,
        max_consecutive_errors=5,
        max_turns=10,
    )

    prompt = build_hermes_text_prompt(user_query, history, os.getcwd())
    current_prompt = f"{HERMES_AGENT_SYSTEM_PROMPT}\n\nUser query: {user_query}"

    for agent_turn in range(10):
        llm = load_model(ModelRole.CODE)
        try:
            msgs = [{"role": "system", "content": current_prompt}]
            if history:
                for m in history[-4:]:
                    msgs.append({"role": m["role"], "content": m["content"][:1000]})
            msgs.append({"role": "user", "content": user_query})

            full = ""
            stream = llm.create_chat_completion(
                messages=msgs, stream=True,
                max_tokens=2048, temperature=0.3,
            )
            for chunk in stream:
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                token = choices[0].get("delta", {}).get("content", "")
                if token:
                    full += token
                    yield {"type": "token", "content": token}

            if not _keep_loaded:
                unload_model()

            
            tc = parse_hermes_tool_call(full)
            if tc:
                func_name = tc.get("name", "")
                args = tc.get("args", {})

                yield {"type": "status", "content": f"Running {func_name}..."}

                result = HermesToolRegistry.execute(
                    func_name, args, os.getcwd(), agent.session
                )
                result = HermesResultAnalyzer.analyze(result)
                agent.session.total_tool_calls += 1

                
                feedback = (
                    f"Tool '{func_name}' returned:\n"
                    f"Status: {result.status.value}\n"
                    f"Output: {result.output[:2000]}\n"
                )
                if result.error:
                    feedback += f"Error: {result.error[:500]}\n"
                if result.suggestions:
                    feedback += f"Suggestions: {'; '.join(result.suggestions)}\n"

                current_prompt = (
                    f"{HERMES_AGENT_SYSTEM_PROMPT}\n\n"
                    f"User query: {user_query}\n\n"
                    f"Last tool result:\n{feedback}\n\n"
                    f"Continue. If done, provide your final answer WITHOUT a <tool_call>."
                )
                user_query = f"Continue based on the tool result above."

                if not agent.should_continue():
                    yield {"type": "harness_warning",
                           "content": "Agent budget exhausted."}
                    break
                continue

            
            yield {"type": "raw_response", "content": full}
            return

        except Exception as e:
            yield {"type": "harness_warning",
                   "content": f"Hermes agent error: {e}"}
            yield {"type": "raw_response", "content": full}
            return

    yield {"type": "raw_response", "content": "Hermes agent completed."}

def _run_complex_coding(
    user_query: str,
    history: List[Dict[str, str]],
    optimized: List[Dict[str, str]],
    context: str,
    retriever,
    settings=None
) -> Generator[Dict[str, str], None, None]:
    
    yield {"type": "status", "content": "Stage 1 \u2014 Deep reasoning..."}

    reasoning_prompt = (
        "You are the Iris AI Reasoning Specialist. Analyze the user's coding request "
        "and produce a detailed architecture plan. Consider file structure, algorithms, "
        "edge cases, and dependencies. Do NOT write code \u2014 only the plan. "
        "Your ENTIRE response MUST be wrapped in <think>...</think> tags. "
        "Do NOT output any final answer outside of the <think> tags."
    )
    if context:
        reasoning_prompt = f"REFERENCE EXCERPT:\n{context}\n\n{reasoning_prompt}"

    reasoning_msgs = [{"role": "system", "content": reasoning_prompt}] + optimized

    raw_reasoning = ""
    for ev in _stream_tokens(ModelRole.REASONING, reasoning_msgs, max_tokens=8192, temperature=0.6, think_mode="pass", settings=settings):
        yield ev
        if ev["type"] in ("token", "thinking"):
            raw_reasoning += ev["content"]
    if not _keep_loaded:
        unload_model()

    yield {"type": "status", "content": "Stage 2 \u2014 Writing code..."}
    code_msgs = optimized[:-1] + [
        {"role": "user",
         "content": f"User Query: {user_query}\n\nArchitecture/Plan:\n{raw_reasoning[-8000:]}\n\nWrite the complete code based on the plan. Do NOT output any conversational filler. Enclose all final code inside proper ``` language blocks."}
    ]
    yield {"type": "token", "content": "<coding>\n"}
    full_code = "<coding>\n"
    for ev in _stream_tokens(ModelRole.CODE, code_msgs, max_tokens=8192, temperature=0.2, think_mode="pass", settings=settings):
        yield ev
        if ev["type"] == "token":
            full_code += ev["content"]
    if not _keep_loaded:
        unload_model()

    yield {"type": "clear"}
    yield {"type": "status", "content": "Stage 3 \u2014 Reviewing and optimizing..."}

    review_msgs = optimized + [
        {"role": "assistant", "content": full_code},
        {"role": "user",
         "content": "Review the above code. Fix all syntax errors, logical bugs, edge cases, "
         "and ensure it compiles/works correctly. Do NOT output conversational filler. Return the final corrected code inside a ``` language block, followed by a brief explanation."}
    ]
    final_output = ""
    for ev in _stream_tokens(ModelRole.CODE, review_msgs, max_tokens=None, temperature=0.2, think_mode="pass", system_prompt_override=REVIEWER_SYSTEM_PROMPT):
        yield ev
        if ev["type"] == "token":
            final_output += ev["content"]
    if not _keep_loaded:
        unload_model()

    lang = _detect_language(final_output)
    err = check_syntax(final_output, lang)
    if err:
        yield {"type": "syntax_error", "content": f"Syntax error in {lang or 'code'}: {err}"}
        yield {"type": "clear"}
        yield {"type": "status", "content": "Auto-correcting syntax..."}

        correction_msgs = optimized + [
            {"role": "assistant", "content": final_output},
            {"role": "user",
             "content": f"Fix ONLY the syntax errors:\n\n{err}\n\nReturn the complete corrected code inside a ```python``` block."}
        ]
        corrected = ""
        for ev in _stream_tokens(ModelRole.CODE, correction_msgs, max_tokens=None, temperature=0.2, think_mode="pass", system_prompt_override=REVIEWER_SYSTEM_PROMPT):
            yield ev
            if ev["type"] == "token":
                corrected += ev["content"]
        if not _keep_loaded:
            unload_model()

        second_err = check_syntax(corrected, lang)
        if second_err:
            yield {"type": "token", "content": "\n\n> \u26a0\ufe0f Auto-correction attempted but some errors may remain."}
        final_output = corrected

    
    yield {"type": "status", "content": "Verifying complex code in sandbox..."}
    _, sandbox = apply_smart_harness_code(final_output, language=lang or "python")
    if sandbox.result == SandboxResult.PASS:
        yield {"type": "status", "content": f"Sandbox: {sandbox.tests_passed} tests passed"}
    elif sandbox.result == SandboxResult.FAIL:
        yield {"type": "harness_warning", "content": f"Sandbox: {sandbox.tests_passed}/{sandbox.tests_passed + sandbox.tests_failed} tests passed — some tests failed"}
    elif sandbox.syntax_error:
        yield {"type": "syntax_error", "content": f"Sandbox: {sandbox.syntax_error}"}
    elif sandbox.runtime_errors:
        for rerr in sandbox.runtime_errors[:3]:
            yield {"type": "harness_warning", "content": f"Runtime: {rerr[:200]}"}

    
    if isinstance(settings, dict) and settings.get("code_review"):
        yield {"type": "clear"}
        yield {"type": "status", "content": "Reviewing final code quality..."}
        _rmsgs = optimized + [
            {"role": "assistant", "content": final_output},
            {"role": "user", "content": "Final review pass. Fix remaining issues inside a code block with filename, or say 'No issues found.'"}
        ]
        _rev = ""
        for ev in _stream_tokens(ModelRole.CODE, _rmsgs, max_tokens=None, temperature=0.2, think_mode="pass", system_prompt_override=REVIEWER_SYSTEM_PROMPT):
            yield ev
            if ev["type"] == "token":
                _rev += ev["content"]
        if not _keep_loaded:
            unload_model()
        _rl = _detect_language(_rev) or lang
        _rev, _hw = _apply_and_yield_harness(_rev, _rl)
        for w in _hw:
            yield w
        final_output = _rev

    yield {"type": "raw_response", "content": final_output}



def generate_internal_code(
    system_prompt: str, user_prompt: str, max_tokens: int = 512, role: ModelRole = ModelRole.CODE
) -> str:
    
    llm = load_model(role)
    try:
        res = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return res["choices"][0]["message"]["content"]
    finally:
        if not _keep_loaded:
            unload_model()



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
            logger.info("[RAG] sentence-transformers not installed. RAG disabled.")
            return

        if not os.path.exists(self.raw_data_dir):
            os.makedirs(self.raw_data_dir, exist_ok=True)
            logger.info(f"[RAG] Created {self.raw_data_dir}/. Drop markdown/txt files here.")
            return

        logger.info("[RAG] Loading embedding model (all-MiniLM-L6-v2)...")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')

        file_entries: list = []
        abs_root = os.path.abspath(self.raw_data_dir)

        for ext in ["*.md", "*.txt", "*.pdf", "*.docx", "*.xlsx", "*.pptx", "*.csv", "*.html", "*.json", "*.xml"]:
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
            logger.info("[RAG] No text found in raw_data/. Skipping index creation.")
            return

        categories_found = sorted({c for _, c in file_entries})
        logger.info(f"[RAG] Found {len(file_entries)} files across categories: {categories_found}")
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
                    logger.info(f"[RAG] Loaded {len(self.chunks)} chunks from disk cache (skipped re-encode).")
                    return
                else:
                    logger.info("[RAG] Cache stale (files changed) \u2014 rebuilding index.")
            except Exception as e:
                logger.info(f"[RAG] Cache load failed ({e}) \u2014 rebuilding index.")
        self.chunks = []
        self._cat_index = {}

        for path, category in file_entries:
            try:
                ext = os.path.splitext(path)[1].lower()
                if ext in [".md", ".txt", ".json", ".xml", ".csv"]:
                    with open(path, "r", encoding="utf-8") as f:
                        raw_text = f.read()
                else:
                    try:
                        from markitdown import MarkItDown
                        md = MarkItDown()
                        result = md.convert(path)
                        raw_text = result.text_content
                    except ImportError:
                        logger.warning(f"[RAG] markitdown not installed. Cannot read {path}")
                        continue
            except Exception as e:
                logger.warning(f"[RAG] Could not read {path}: {e}")
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
            logger.info("[RAG] No chunks created. Check that files contain text.")
            return

        for idx, chunk in enumerate(self.chunks):
            cat = chunk["category"]
            self._cat_index.setdefault(cat, []).append(idx)

        cat_summary = {c: len(v) for c, v in self._cat_index.items()}
        logger.info(f"[RAG] {len(self.chunks)} chunks indexed. Distribution: {cat_summary}")
        chunk_texts = [c["text"] for c in self.chunks]
        self.embeddings = self.embedder.encode(chunk_texts, convert_to_tensor=True)
        logger.info("[RAG] Indexing complete!")
        try:
            with open(cache_file, "wb") as f:
                pickle.dump({
                    "key":        cache_key,
                    "chunks":     self.chunks,
                    "embeddings": self.embeddings,
                    "cat_index":  self._cat_index,
                }, f)
            logger.info(f"[RAG] Index cached to {cache_file} \u2014 future startups will be instant.")
        except Exception as e:
            logger.warning(f"[RAG] Could not save cache ({e}) \u2014 index will rebuild next time.")
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
                logger.info(f"[RAG] Category '{category}' sparse; using full index.")
            candidate_indices = pool

        if candidate_indices is not None:
            subset_embeddings = self.embeddings[candidate_indices]
            hits_raw = util.semantic_search(query_embedding, subset_embeddings, top_k=top_k)[0]
            hits_global = [{"corpus_id": candidate_indices[h["corpus_id"]], "score": h["score"]} for h in hits_raw]
        else:
            hits_global = util.semantic_search(query_embedding, self.embeddings, top_k=top_k)[0]

        retrieved_texts = [self.chunks[h["corpus_id"]]["text"] for h in hits_global]
        return "\n\n---\n\n".join(retrieved_texts)



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
    text = re.sub(r'^(solve|calculate|what is|compute)\s+', '', text, flags=re.IGNORECASE).strip()

    def normalise(expr: str) -> str:
        expr = re.sub(r'([0-9])([a-zA-Z])', r'\1*\2', expr)
        expr = re.sub(r'\^', '**', expr)
        return expr

    transformations = standard_transformations + (implicit_multiplication_application, convert_xor)

    if '=' in text:
        parts = text.split('=', 1)
        lhs_raw, rhs_raw = normalise(parts[0].strip()), normalise(parts[1].strip())
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
        if isinstance(solutions, list):
            if len(solutions) == 1:
                return f"{var_names[0]} = {solutions[0]}"
            return "Solutions: " + ", ".join(f"{var_names[0]} = {s}" for s in solutions)
        if isinstance(solutions, dict):
            return ", ".join([f"{k} = {v}" for k, v in solutions.items()])
        return str(solutions)
    else:
        if not re.search(r'\d', text):
            return None
        try:
            expr = parse_expr(normalise(text), transformations=transformations)
            result = expr.evalf()
            if result.is_integer:
                return str(int(result))
            elif result.is_Float:
                return str(round(float(result), 6))
            else:
                return str(result)
        except Exception:
            return None

    arith_text = re.sub(
        r'^(?:what\s+is|solve|find|calculate|compute|simplify|evaluate)\s+',
        '', text, flags=re.IGNORECASE
    ).strip()
    if re.findall(r'\b([a-zA-Z])\b', arith_text):
        return None
    arith = normalise(arith_text)
    if not re.fullmatch(r'[\d\s\+\-\*\/\(\)\.]+', arith):
        return None
    try:
        res = simplify(sympify(arith))
        return str(int(res)) if res == int(res) else str(res)
    except Exception:
        return None



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
        "max_new_tokens": 2048,
        "temperature": 0.6,
        "top_p": 0.95,
        "repetition_penalty": 1.05,
        "disable_rag": False,
        "n_ctx": None,
        "n_gpu_layers": DEFAULT_GPU_LAYERS,
        "n_threads": DEFAULT_THREADS,
        "models": dict(DEFAULT_MODEL_FILES),
    }
    if os.path.exists(CONFIG_PATH):
        try:
            mtime = os.path.getmtime(CONFIG_PATH)
            if _gen_config_cache is None or mtime != _gen_config_mtime:
                with open(CONFIG_PATH) as f:
                    loaded = json.load(f)
                    merged_models = {**defaults.get("models", {}), **loaded.pop("models", {})}
                    _gen_config_cache = {**defaults, **loaded}
                    _gen_config_cache["models"] = merged_models
                    apply_to_config(_gen_config_cache)
                _gen_config_mtime = mtime
            return _gen_config_cache
        except Exception:
            pass
    apply_to_config(defaults)
    return defaults



class _Device:
    def __init__(self, type_: str):
        self.type = type_
    def __repr__(self):
        return f"device(type='{self.type}')"


def get_device(force_cpu=False):
    return _Device("cpu" if force_cpu else "gpu")



_vision_cache: dict = {}
_vision_lck = threading.Lock()
_MLX_VISION_ID = os.path.join(_HERE, "iris_vision_model")


def _load_vision_model():
    global _vision_cache
    if _vision_cache:
        return _vision_cache

    with _vision_lck:
        if _vision_cache:
            return _vision_cache

        cfg = load_generation_config()
        models_dict = cfg.get("models", {})

        vision_file = models_dict.get("vision", "InternVL3_5-4B-Q4_K.gguf")
        clip_file = models_dict.get("clip", "mmproj-InternVL3_5-4B-f16.gguf")

        models_dir = os.path.join(os.path.dirname(_HERE), "models")
        vision_path = os.path.join(models_dir, vision_file)
        clip_path = os.path.join(models_dir, clip_file)

        if os.path.exists(vision_path):
            if "Qwen2.5-VL" in vision_file:
                logger.info("[Vision] Qwen2.5-VL GGUF projector is known to fail in llama.cpp. Forcing MLX backend.")
            else:
                logger.info(f"[Vision] Loading GGUF vision model: {vision_file}...")
                try:
                    n_gpu_layers = cfg.get("n_gpu_layers", -1)
                    n_threads = cfg.get("n_threads", 8)
                    
                    chat_handler = None
                    if clip_file and os.path.exists(clip_path):
                        logger.info(f"[Vision] Found clip projector: {clip_file}")
                        from llama_cpp.llama_chat_format import Llava15ChatHandler
                        chat_handler = Llava15ChatHandler(clip_model_path=clip_path, verbose=False)
                    
                    
                    model_kwargs = {
                        "model_path": vision_path,
                        "n_ctx": ROLE_CTX.get(ModelRole.VISION, 4096),
                        "n_gpu_layers": n_gpu_layers,
                        "n_threads": n_threads,
                        "flash_attn": True,
                        "type_k": getattr(llama_cpp, "LLAMA_FTYPE_MOSTLY_Q8_0", 7),
                        "type_v": getattr(llama_cpp, "LLAMA_FTYPE_MOSTLY_Q8_0", 7),
                        "verbose": False,
                    }
                    if chat_handler:
                        model_kwargs["chat_handler"] = chat_handler
                        
                    model = Llama(**model_kwargs)
                    _vision_cache = {"model": model, "backend": "gguf"}
                    logger.info("[Vision] GGUF vision model ready.")
                    return _vision_cache
                except Exception as e:
                    logger.info(f"[Vision] GGUF VLM load failed: {e}. Falling back to MLX...")
        try:
            from mlx_vlm import load as vlm_load
            from mlx_vlm.utils import load_config as vlm_load_config
            
            mlx_repo = "mlx-community/Qwen2-VL-7B-Instruct-4bit"
            try:
                active_size = cfg.get("size", "tiny")
                size_path = os.path.join(os.path.dirname(CONFIG_PATH), "sizes", f"{active_size}.json")
                if os.path.exists(size_path):
                    with open(size_path) as f:
                        size_cfg = json.load(f)
                    size_vision = size_cfg.get("models", {}).get("vision")
                    if size_vision:
                        mlx_repo = size_vision
            except Exception:
                pass

            if mlx_repo == "Qwen/Qwen2.5-VL-3B-Instruct":
                mlx_repo = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"
            elif mlx_repo == "Qwen/Qwen2.5-VL-7B-Instruct":
                mlx_repo = "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"

            if os.path.exists(_MLX_VISION_ID):
                mlx_repo = _MLX_VISION_ID
                
            logger.info(f"[Vision] Loading MLX vision model: {mlx_repo}...")
            model, processor = vlm_load(mlx_repo)
            config = vlm_load_config(mlx_repo)
            _vision_cache = {"model": model, "processor": processor, "config": config, "backend": "mlx"}
            logger.info("[Vision] MLX vision model ready.")
            return _vision_cache
        except Exception as e:
            logger.info(f"[Vision] MLX VLM load failed: {e}")
            return {}


def unload_vision_model() -> None:
    global _vision_cache
    with _vision_lck:
        if not _vision_cache:
            return
        backend = _vision_cache.get("backend")
        _vision_cache.pop("model", None)
        _vision_cache.clear()
        _vision_cache = {}
        if backend != "gguf":
            try:
                import mlx.core as mx
                mx.clear_cache()
            except Exception:
                pass
        gc.collect()
        if backend:
            logger.info(f"[Vision] Vision model ({backend}) unloaded \u2014 unified memory reclaimed.")
def analyze_image(
    image_path: str,
    prompt: str = "Describe this image in detail.",
    unload_after: bool = True,
) -> str:
    vision = _load_vision_model()
    if not vision:
        return "[Vision] Vision model not available."

    backend = vision.get("backend")
    model = vision["model"]

    if backend == "gguf":
        try:
            import base64
            with open(image_path, "rb") as f:
                img_data = f.read()
            img_b64 = base64.b64encode(img_data).decode("utf-8")
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                ]
            }]
            res = model.create_chat_completion(messages=messages, max_tokens=512)
            return res["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return f"[Vision] GGUF Analysis failed: {e}"
        finally:
            if unload_after:
                unload_vision_model()

    elif backend == "mlx":
        proc = vision["processor"]
        conf = vision.get("config")
        try:
            from mlx_vlm import generate as vlm_generate
            from mlx_vlm.prompt_utils import apply_chat_template
            formatted = apply_chat_template(proc, conf, prompt, num_images=1)
            result = vlm_generate(model, proc, formatted, image_path, max_tokens=512, verbose=False)
            if hasattr(result, "text"):
                return result.text.strip()
            return str(result).strip()
        except Exception as e:
            return f"[Vision] MLX Analysis failed: {e}"
        finally:
            if unload_after:
                unload_vision_model()

    return "[Vision] Unknown backend."
