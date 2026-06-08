"""
iris.py — Iris AI Base Model with MRA (Multi-Role Architecture)
===============================================================
"""

total_time_spent = 248 #hours (update after working)

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


_HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(os.path.dirname(_HERE), "config", "iris.conf")

DEFAULT_MODEL_FILES: Dict[str, str] = {
    "triage":    "iris_001.gguf",
    "router":    "iris_001.gguf",
    "control":   "iris_002.gguf",
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
    "iris_002.gguf": [
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
    ModelRole.TRIAGE:    2048,
    ModelRole.ROUTER:    2048,
    ModelRole.CONTROL:   2048,
    ModelRole.MATH:      4096,
    ModelRole.CODE:      8192,
    ModelRole.REASONING: 8192,
    ModelRole.REVIEWER:  8192,
    ModelRole.GENERAL:   4096,
    ModelRole.VISION:    4096,
}

DEFAULT_CTX = 4096
DEFAULT_GPU_LAYERS = -1
DEFAULT_THREADS = 8


IRIS_IDENTITY = (
    "You are Iris AI. Answer directly without introducing yourself or saying 'I am Iris AI' at the start. "
    "Never mention underlying model names or pipeline architecture. "
    "If asked who you are, identify as Iris AI."
)

TRIAGE_SYSTEM_PROMPT = (
    "You are the Iris AI Triage node.\n"
    "Rules:\n"
    "1. If the user is just greeting, saying hi/hello, asking simple conversational or factual questions, "
    "answer them directly. Do NOT output any routing tags.\n"
    "2. If the query needs a specialist model, output EXACTLY ONE routing tag "
    "and NOTHING ELSE (do not answer the query yourself):\n"
    "   [ROUTE: GENERAL]     — general knowledge, explanations, broad topics\n"
    "   [ROUTE: REASONING]   — complex logic, system design, strategy, architecture\n"
    "   [ROUTE: MATH]        — math, equations, proofs, algorithmic problems\n"
    "   [ROUTE: CODE_SIMPLE]  — simple single-file code, small functions, snippets\n"
    "   [ROUTE: CODE_COMPLEX] — large projects, games, multi-file, kernels, bootloaders\n\n"
    "Be precise. If unsure, default to [ROUTE: GENERAL]."
)

GENERAL_SYSTEM_PROMPT = (
    f"{IRIS_IDENTITY}\nProvide a helpful, direct response. "
    "Use chain-of-thought reasoning when appropriate."
)

CODE_SYSTEM_PROMPT = (
    "You are the Iris AI Coding Specialist. Generate clean, fully working, production-quality code. "
    "Ensure correctness, edge-case handling, and error-free syntax. "
    "Do NOT include comments in your code. "
    "After the code block, provide a concise explanation of the code, its key features, "
    "and clear instructions on how to compile/run it."
)

MATH_SYSTEM_PROMPT = (
    "You are the Iris AI Math Core. Solve mathematical/algorithmic problems step-by-step. "
    "Use precise notation. Please reason step by step, and put your final answer within \\boxed{}."
)

REASONING_SYSTEM_PROMPT = (
    "You are the Iris AI Reasoning Specialist. Think step-by-step using chain-of-thought reasoning. "
    "Break down complex problems methodically before giving the final answer."
)

REVIEWER_SYSTEM_PROMPT = (
    "You are the Iris AI Code Reviewer. Review and refine code for correctness, efficiency, edge cases, "
    "and readability. Ensure the final output is production-ready. Fix any errors, fill missing logic, "
    "and optimize where possible. Return the final code and explanation."
)


_active_role: Optional[ModelRole] = None
_active_llm: Optional[Llama] = None
_keep_loaded: bool = False  # Set True during benchmarks to skip unload
_model_lock = threading.Lock()


def _get_model_filename(role: ModelRole) -> str:
    cfg = load_generation_config()
    models_dict = cfg.get("models", {})
    return models_dict.get(role.value) or DEFAULT_MODEL_FILES.get(role.value, f"iris-{role.value}.gguf")


def _model_path(filename: str) -> str:
    return os.path.join(os.path.dirname(_HERE), "models", filename)


def download_gguf(filename: str, quiet: bool = False) -> bool:
    """Download a single GGUF model file from HuggingFace using hf_hub_download.

    Tries multiple repos in priority order. Handles auth-gated repos gracefully.
    Returns True on success.
    """
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


def _unload_locked() -> None:
    """Internal: unload without acquiring lock (caller holds _model_lock)."""
    global _active_role, _active_llm
    if _active_llm is not None:
        role_val = _active_role.value if _active_role else "unknown"
        #print(f"[Iris] Unloaded {role_val}.")
        try:
            _active_llm.reset()
        except Exception:
            pass
        llm = _active_llm
        _active_llm = None
        _active_role = None
        del llm
        gc.collect()
        if platform.system() == "Linux":
            try:
                import ctypes
                ctypes.CDLL(None).malloc_trim(0)
            except Exception:
                pass


def load_model(role: ModelRole) -> Llama:
    """Load a model by role. Unloads any currently active model first. Only one in RAM."""
    global _active_role, _active_llm

    with _model_lock:
        if _active_role == role and _active_llm is not None:
            return _active_llm

        _unload_locked()

        filename = _get_model_filename(role)
        path = _model_path(filename)

        if not os.path.exists(path):
            raise FileNotFoundError(
                f"GGUF model not found for role '{role.value}'.\n"
                f"Expected: {path}\n"
                f"Please place the GGUF file in {os.path.join(os.path.dirname(_HERE), 'models')}/"
            )
        cfg = load_generation_config()
        
        n_ctx_allocation = cfg.get("n_ctx_allocation", "auto")
        if str(n_ctx_allocation).lower() == "auto":
            try:
                # Basic cross-platform RAM calc using os.sysconf if posix
                if os.name == 'posix':
                    ram_bytes = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
                    ram_gb = ram_bytes / (1024**3)
                    if ram_gb < 16:
                        n_ctx = 4096
                    elif ram_gb < 32:
                        n_ctx = 8192
                    elif ram_gb < 64:
                        n_ctx = 16384
                    else:
                        n_ctx = 32768
                else:
                    n_ctx = 8192
            except Exception:
                n_ctx = 4096
        else:
            try:
                n_ctx = int(n_ctx_allocation)
            except ValueError:
                n_ctx = 4096

        if not n_ctx:
            n_ctx = ROLE_CTX.get(role, DEFAULT_CTX)

        n_gpu_layers = cfg.get("n_gpu_layers", DEFAULT_GPU_LAYERS)
        n_threads = cfg.get("n_threads", DEFAULT_THREADS)

        #print(f"[Iris] Loading {role.value} ({filename}) [ctx={n_ctx}]...")

        _active_llm = Llama(
            model_path=path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            n_threads=n_threads,
            use_mmap=True,
            use_mlock=False,
            flash_attn=True,
            type_k=getattr(llama_cpp, "LLAMA_FTYPE_MOSTLY_Q8_0", 7),
            type_v=getattr(llama_cpp, "LLAMA_FTYPE_MOSTLY_Q8_0", 7),
            n_batch=1024,
            verbose=False,
        )
        _active_role = role
        return _active_llm


def unload_model() -> None:
    """Fully unload the currently active model and free RAM."""
    with _model_lock:
        _unload_locked()



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
        "derivative", "derivatives", "integral", "integrals", "calculus",
        "algebra", "geometry", "trigonometry", "matrix", "matrices", "vector",
        "vectors", "theorem", "proof", "prove", "probability", "statistics",
        "combinatorics",
    }
    for kw in math_keywords:
        if re.search(rf"\b{re.escape(kw)}\b", q):
            return TaskType.MATH

    if re.search(r'[\d\s]+[\+\-\*\/=]+[\d\s]+', q):
        return TaskType.MATH

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
    """Triage: classify the query or answer it directly."""
    result = _fallback_classify(user_query)
    if result is not None:
        return result, None

    minimized = _minimize_history(history, max_entries=2)
    triage_messages = [{"role": "system", "content": TRIAGE_SYSTEM_PROMPT}]
    for msg in minimized:
        triage_messages.append({"role": msg["role"], "content": msg["content"]})
    triage_messages.append({"role": "user", "content": user_query})

    llm = load_model(ModelRole.TRIAGE)
    res = llm.create_chat_completion(
        messages=triage_messages,
        max_tokens=512,
        temperature=0.2,
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
    }
    for tag, ttype in tag_map.items():
        if re.search(rf'\[\s*route:\s*{re.escape(tag)}\s*\]', answer, re.IGNORECASE):
            return ttype, None

    return None, answer



def _quality_guard(text: str) -> str:
    text = re.sub(
        r"(?i)(I('m| am) (DeepSeek|Qwen|Intern|Hermes|a large language model|an AI language model)"
        r"[^.]*\.?\s*)",
        "", text
    ).strip()
    return text or "I'm Iris AI."



def _stream_tokens(
    role: ModelRole,
    messages: List[Dict[str, str]],
    max_tokens: int = 4096,
    temperature: float = 0.2,
    think_mode: str = "hide",
    system_prompt_override: Optional[str] = None,
) -> Generator[Dict[str, str], None, None]:
    """Stream tokens from a model with DeepSeek R1-style thinking.

    think_mode: "show" = thinking events  "hide" = strip  "status" = spinner  "pass" = through
    Supports <think>/</think> (Qwen distill and DeepSeek R1).
    """
    llm = load_model(role)
    sys_prompt = system_prompt_override if system_prompt_override is not None else _system_prompt_for(role)
    full_messages = [{"role": "system", "content": sys_prompt}] + messages

    THINK_PAIRS = [
        ("<think>", "</think>"),
        ("<|thought_start|>", "<|thought_end|>"),
        ("<thought>", "</thought>")
    ]
    CLOSE_TAG_MAP = {open_tag: close_tag for open_tag, close_tag in THINK_PAIRS}

    for loop_idx in range(5):
        stream = llm.create_chat_completion(
            messages=full_messages, stream=True, max_tokens=max_tokens, temperature=temperature, repeat_penalty=load_generation_config().get("repetition_penalty", 1.0),
        )
        loop_content = ""
        finish_reason = "stop"
        in_thinking = False
        thinking_tag = ""
        buffer = ""
        hidden_buffer = ""

        for chunk in stream:
            choices = chunk.get("choices", [])
            if not choices:
                continue
            choice = choices[0]
            token = choice.get("delta", {}).get("content", "")
            if not token:
                continue

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
                        buffer = ""

                        if len(hidden_buffer) > 500:
                            think_mode = "pass"
                            yield {"type": "token", "content": hidden_buffer}
                            loop_content += hidden_buffer
                            hidden_buffer = ""
                            in_thinking = False
                            thinking_tag = ""
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
                        buffer = ""
                        break

            if "finish_reason" in choice and choice["finish_reason"]:
                finish_reason = choice["finish_reason"]

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

        yield {"type": "finish", "reason": finish_reason}

        if finish_reason == "length":
            full_messages.append({"role": "assistant", "content": loop_content})
            full_messages.append({
                "role": "user",
                "content": "Continue exactly where you left off, from the very next character. "
                "Do not repeat anything, do not write intro text or markdown blocks, just the raw continuation."
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
) -> Generator[Dict[str, str], None, None]:
    """Generate a response using the multi-model routing pipeline.

    Args:
        show_thinking: When True, DeepSeek R1 thinking tokens stream as
            {"type": "thinking", "content": "..."} events. Set False to strip.
    """
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
            think_mode="show" if force_role in (ModelRole.REASONING, ModelRole.GENERAL) else "hide"
        ):
            yield ev
            if ev["type"] == "token":
                full += ev["content"]

        if not _keep_loaded:
            if not _keep_loaded:
                unload_model()

        if force_role == ModelRole.MATH:
            full, mw = _apply_math_harness(full)
            for w in mw:
                yield w
            # SmartHarness: verify math solution
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
            # SmartHarness: sandbox-verify force-routed code
            _, sandbox = apply_smart_harness_code(full, language=lang)
            if sandbox.result == SandboxResult.PASS:
                yield {"type": "status", "content": f"Sandbox verified: {sandbox.tests_passed} tests passed"}
            elif sandbox.result == SandboxResult.FAIL:
                yield {"type": "harness_warning", "content": f"Sandbox: {sandbox.tests_failed} test(s) failed"}

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

    yield {"type": "status", "content": "Analyzing query..."}
    task_type, direct_answer = classify_task(user_query, history)

    if task_type is None:
        if direct_answer:
            yield {"type": "token", "content": direct_answer}
            yield {"type": "raw_response", "content": direct_answer}
        return

    yield {"type": "status", "content": f"Task: {task_type.value.upper()}"}

    context = ""
    if retriever is not None and len(user_query.split()) >= 8:
        rag_cats = {
            TaskType.CODING_SIMPLE:  "coding",
            TaskType.CODING_COMPLEX: "coding",
            TaskType.MATH:           "math",
            TaskType.REASONING:      "reasoning",
            TaskType.GENERAL:        "general",
        }
        context = retriever.retrieve(user_query, top_k=3, category=rag_cats.get(task_type, "general"))

    optimized = [{"role": "user", "content": user_query}]
    if history:
        cfg = load_generation_config()
        profile = str(cfg.get("compacting_profile", "medium")).lower()
        num_history = 2 if profile == "aggressive" else (10 if profile == "low" else 5)
        recent = history[-num_history:]
        optimized = [{"role": m["role"], "content": m["content"]} for m in recent] + optimized

    if task_type == TaskType.GENERAL:
        yield {"type": "status", "content": "Thinking deeply..."}
        full = ""
        for ev in _stream_tokens(ModelRole.GENERAL, optimized, max_tokens=4096, temperature=0.4, think_mode="show"):
            yield ev
            if ev["type"] == "token":
                full += ev["content"]
        if not _keep_loaded:
            if not _keep_loaded:
                unload_model()
        cleaned = _quality_guard(full)
        if cleaned != full:
            yield {"type": "clear"}
            yield {"type": "token", "content": cleaned}
        yield {"type": "raw_response", "content": cleaned}

    elif task_type == TaskType.REASONING:
        yield {"type": "status", "content": "Reasoning step-by-step..."}
        full = ""
        for ev in _stream_tokens(ModelRole.REASONING, optimized, max_tokens=4096, temperature=0.5, think_mode="show"):
            yield ev
            if ev["type"] == "token":
                full += ev["content"]
        if not _keep_loaded:
            if not _keep_loaded:
                unload_model()
        yield {"type": "raw_response", "content": full}

    elif task_type == TaskType.MATH:
        yield {"type": "status", "content": "Solving..."}
        full = ""
        for ev in _stream_tokens(ModelRole.MATH, optimized, max_tokens=4096, temperature=0.2, think_mode="show"):
            yield ev
            if ev["type"] == "token":
                full += ev["content"]
        if not _keep_loaded:
            if not _keep_loaded:
                unload_model()

        full, mw = _apply_math_harness(full)
        for w in mw:
            yield w

        # SmartHarness: verify math numerically & symbolically
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
        for ev in _stream_tokens(ModelRole.CODE, optimized, max_tokens=3072, temperature=0.2, think_mode="hide"):
            yield ev
            if ev["type"] == "token":
                full += ev["content"]
        if not _keep_loaded:
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
            for ev in _stream_tokens(ModelRole.CODE, correction_msgs, max_tokens=3072, temperature=0.2, think_mode="hide"):
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

        # SmartHarness: sandbox-verify generated code
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

        yield {"type": "raw_response", "content": full}

    elif task_type == TaskType.CODING_COMPLEX:
        yield from _run_complex_coding(user_query, history, optimized, context, retriever)

    if not _keep_loaded:
        unload_model()


def _apply_and_yield_harness(text: str, language: str) -> Tuple[str, List[dict]]:
    """Run harness passes and collect warnings. Caller should yield them."""
    return _apply_harness(text, language)


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
) -> Generator[Dict[str, str], None, None]:
    """2-stage continuation: CODE → REVIEWER."""
    optimized = [{"role": "user", "content": user_query}]
    if history:
        recent = history[-4:]
        optimized = [{"role": m["role"], "content": m["content"]} for m in recent] + optimized

    yield {"type": "status", "content": "Stage 1 \u2014 Continuing code..."}
    full = ""
    for ev in _stream_tokens(ModelRole.CODE, optimized, max_tokens=3072, temperature=0.2, think_mode="hide"):
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
    for ev in _stream_tokens(ModelRole.CODE, review_msgs, max_tokens=3072, temperature=0.2, think_mode="hide", system_prompt_override=REVIEWER_SYSTEM_PROMPT):
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
    """Hermes agent mode: text-based tool-calling loop for local models.

    Uses build_hermes_text_prompt + parse_hermes_tool_call for models
    that don't support native OpenAI function calling.
    """
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

            # Parse tool call
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

                # Feed result back
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

            # No tool call found — assume this is the final answer
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
) -> Generator[Dict[str, str], None, None]:
    """3-stage pipeline: Reasoning (silent) → Codegen (streamed) → Reviewer (streamed)."""
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
    for ev in _stream_tokens(ModelRole.REASONING, reasoning_msgs, max_tokens=8192, temperature=0.6, think_mode="pass"):
        yield ev
        if ev["type"] in ("token", "thinking"):
            raw_reasoning += ev["content"]
    if not _keep_loaded:
        unload_model()

    yield {"type": "status", "content": "Stage 2 \u2014 Writing code..."}
    code_msgs = optimized[:-1] + [
        {"role": "user",
         "content": f"User Query: {user_query}\n\nArchitecture/Plan:\n{raw_reasoning[-8000:]}\n\nWrite the complete code based on the plan. You MUST wrap your internal thought process inside <think>...</think> tags. After thinking, enclose all final code inside proper ``` language blocks."}
    ]
    yield {"type": "token", "content": "<coding>\n"}
    full_code = "<coding>\n"
    for ev in _stream_tokens(ModelRole.CODE, code_msgs, max_tokens=8192, temperature=0.2, think_mode="pass"):
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
         "and ensure it compiles/works correctly. You MUST wrap your internal code review thought process inside <think>...</think> tags. Return the final corrected code inside a ```python``` block, followed by a brief explanation."}
    ]
    final_output = ""
    for ev in _stream_tokens(ModelRole.CODE, review_msgs, max_tokens=3072, temperature=0.2, think_mode="pass", system_prompt_override=REVIEWER_SYSTEM_PROMPT):
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
        for ev in _stream_tokens(ModelRole.CODE, correction_msgs, max_tokens=3072, temperature=0.2, think_mode="pass", system_prompt_override=REVIEWER_SYSTEM_PROMPT):
            yield ev
            if ev["type"] == "token":
                corrected += ev["content"]
        if not _keep_loaded:
            if not _keep_loaded:
                unload_model()

        second_err = check_syntax(corrected, lang)
        if second_err:
            yield {"type": "token", "content": "\n\n> \u26a0\ufe0f Auto-correction attempted but some errors may remain."}
        final_output = corrected

    # SmartHarness: sandbox-verify complex code
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

    yield {"type": "raw_response", "content": final_output}



def generate_internal_code(
    system_prompt: str, user_prompt: str, max_tokens: int = 512, role: ModelRole = ModelRole.CODE
) -> str:
    """Helper for internal subsystems (e.g., browser_agent) to generate code."""
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
                with open(path, "r", encoding="utf-8") as f:
                    raw_text = f.read()
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
        return str(solutions)

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
        "max_new_tokens": 256,
        "temperature": 0.7,
        "top_p": 0.9,
        "repetition_penalty": 1.0,
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
                _gen_config_mtime = mtime
            return _gen_config_cache
        except Exception:
            pass
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
            logger.info(f"[Vision] Loading GGUF vision model: {vision_file}...")
            try:
                n_gpu_layers = cfg.get("n_gpu_layers", -1)
                n_threads = cfg.get("n_threads", 8)
                
                chat_handler = None
                if clip_file and os.path.exists(clip_path):
                    logger.info(f"[Vision] Found clip projector: {clip_file}")
                    from llama_cpp.llama_chat_format import Llava15ChatHandler
                    chat_handler = Llava15ChatHandler(clip_model_path=clip_path, verbose=False)
                
                # If no chat_handler is provided, llama.cpp handles native architectures like qwen2vl automatically
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
