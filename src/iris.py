import re
<<<<<<< HEAD
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
        ("bartowski/Qwen2.5-Math-7B-Instruct-GGUF", "Qwen2.5-Math-7B-Instruct-Q4_K_M.gguf"),
    ],
    "iris_004.gguf": [
        ("Qwen/Qwen2.5-Coder-14B-Instruct-GGUF", "qwen2.5-coder-14b-instruct-q4_k_m.gguf"),
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
    "1. Simple greetings like 'hi', 'hello', 'good morning' → answer with a SHORT greeting, NO tag.\n"
    "   BUT: identity questions like 'who are you', 'who made you', 'what are you' → [ROUTE: GENERAL]\n"
    "2. For EVERY other query, output EXACTLY ONE of these tags and NOTHING ELSE:\n"
    "   [ROUTE: SEARCH: keywords]  — factual question, current events, people, places, products, history, definitions\n"
    "   [ROUTE: REASONING]         — how/why questions, explanations, analysis, comparisons, summaries, document reading\n"
    "   [ROUTE: GENERAL]           — casual chat, opinions, creative writing\n"
    "   [ROUTE: MATH]              — math problems, equations, proofs\n"
    "   [ROUTE: CODE_SIMPLE]       — small code snippets, functions, HTML/CSS/JS UI elements, canvas animations, SVG graphics, procedural art, or programming problems\n"
    "   [ROUTE: CODE_COMPLEX]      — full projects, multi-file code, games, complete websites or web apps\n"
    "   [ROUTE: CONTROL]           — OS/PC commands, app controls, messaging, browser automation (log in, WhatsApp/Telegram messaging, form filling, clicking web buttons), email, system checks, power control\n\n"
    "CRITICAL ROUTING RULE:\n"
    "- If the user asks to 'solve in c++', 'write a script', 'create a website', 'write html/css', 'create an animation', 'draw with canvas', 'make an SVG', pastes a traceback, error log, or a large algorithmic problem description, you MUST route to [ROUTE: CODE_SIMPLE], [ROUTE: CODE_COMPLEX], or [ROUTE: MATH].\n"
    "- For ANY programming error, Python traceback, compilation error, or debugging request, you MUST route to [ROUTE: CODE_COMPLEX]. Do NOT route tracebacks to MATH.\n"
    "- OVERRIDE RULE: If the prompt contains 'build a landing page', 'HTML', or 'Tailwind', you MUST choose [ROUTE: CODE_COMPLEX]. Do not choose [ROUTE: CONTROL] even if the website design mentions mock terminal commands.\n"
    "- CANVAS / ANIMATION RULE: Any request involving 'canvas', 'HTML5 canvas', 'animation', 'animate', 'SVG', 'procedural art', 'draw', 'render loop', 'requestAnimationFrame' is ALWAYS a code task. Route to [ROUTE: CODE_SIMPLE] for single-file outputs or [ROUTE: CODE_COMPLEX] for multi-file projects. NEVER route these to REASONING or SEARCH.\n"
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
    "User: make a canvas animation of a bouncing ball → [ROUTE: CODE_SIMPLE]\n"
    "User: draw a dog using SVG procedurally → [ROUTE: CODE_SIMPLE]\n"
    "User: create a self-contained HTML5 canvas animation → [ROUTE: CODE_SIMPLE]\n"
    "User: 2+2 → [ROUTE: MATH]\n"
    "User: open spotify → [ROUTE: CONTROL]\n"
    "User: send a whatsapp message to Mom saying hello → [ROUTE: CONTROL]\n"
    "User: login to github for me → [ROUTE: CONTROL]\n"
    "User: hi → Hello! How can I help you today?\n"
    "User: who are you → [ROUTE: GENERAL]\n"
    "User: who made you → [ROUTE: GENERAL]\n"
    "User: what are you → [ROUTE: GENERAL]\n"
    "User: من أنت → [ROUTE: GENERAL]\n\n"
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
    "Always rely heavily on your deep knowledge of modern UI/UX design to deliver a 'WOW' factor. Write complete, realistic copy — never 'Lorem Ipsum'. "
    "SELF-CONTAINED ANIMATION / CANVAS RULE (ABSOLUTE — applies whenever the task is a visual animation, canvas sketch, SVG graphic, or procedural art): "
    "RULE 1 — NO EXTERNAL ASSETS WHATSOEVER: You MUST NOT reference any external file, URL, or resource. "
    "This includes: src=\"*.svg\", src=\"*.png\", src=\"*.jpg\", url(...), fetch(...), XMLHttpRequest, or any network call. "
    "Every visual element MUST be drawn procedurally with code. "
    "RULE 2 — SINGLE RENDERING PARADIGM: You MUST choose exactly ONE rendering approach for the entire output and stick to it exclusively. "
    "Either: (a) 100% HTML5 Canvas — use ctx.beginPath(), ctx.arc(), ctx.moveTo(), ctx.lineTo(), ctx.quadraticCurveTo(), ctx.bezierCurveTo(), ctx.fillRect(), etc. to draw everything. Do not use CSS animation classes alongside Canvas. "
    "Or: (b) 100% CSS/SVG/DOM — use only CSS keyframes, SVG <path>, <circle>, <polygon> elements, or DOM manipulation. Do not mix a <canvas> context into a CSS-animated page. "
    "NEVER split rendering between Canvas context calls and CSS animation classes in the same output. Pick one and use it exclusively. "
    "RULE 3 — SAFE requestAnimationFrame LOOP: If you use requestAnimationFrame, ALL resource instantiation (new Image(), new Audio(), new Worker(), array precomputation, geometry constants) MUST happen ONCE outside the animation loop, typically in a setup() function called before the loop starts. "
    "Inside the loop body you may ONLY read pre-computed values, mutate state variables (position, angle, time), and issue draw calls. "
    "NEVER write `new Image()`, `document.createElement(...)`, or any constructor call inside the requestAnimationFrame callback. "
    "RULE 4 — RICH PROCEDURAL DETAILS AND GRAPHICS (ABSOLUTE): You MUST NEVER generate basic geometric placeholder shapes (like simple plain circles for characters/dogs, or basic plain rectangles for buildings/trees/clouds). "
    "All characters, backgrounds, and objects must be drawn using high-fidelity procedural art. "
    "To animate multi-jointed walking legs, you MUST use pivot-joint matrices with nested ctx.save(), translate, rotate, draw, and restore. For example:\n"
    "  // Back leg walk cycle:\n"
    "  const legAngle = Math.sin(time) * 0.4;\n"
    "  ctx.save();\n"
    "  ctx.translate(hipX, hipY);\n"
    "  ctx.rotate(legAngle);\n"
    "  ctx.ellipse(0, 20, 10, 25, 0, 0, Math.PI * 2); // Thigh\n"
    "  ctx.translate(0, 35);\n"
    "  ctx.rotate(-legAngle * 0.5);\n"
    "  ctx.ellipse(0, 15, 7, 18, 0, 0, Math.PI * 2); // Lower leg\n"
    "  ctx.restore();\n"
    "Draw detailed multi-segment body parts (legs with joints, fluffy coat textures, detailed face with nose, eyes, ears, wagging tail) using complex curves (quadraticCurveTo/bezierCurveTo) and smooth color gradients. "
    "Create highly detailed parallax backgrounds (e.g. detailed academic buildings with window frames, clock faces, tree leaves using overlapping arcs/clusters, textured roads/lawns, layered drifting clouds). "
    "The animation must look rich, professional, organic, and visually stunning, matching the aesthetic of premium vector-art animations. "
    "After the code block, provide a concise explanation of the code."
    " If the user is ONLY asking for an explanation, summary, or debugging help without needing new code, do NOT generate a code block; just reply in plain text."
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
    "VISUAL ANIMATION REVIEW RULE (CRITICAL): If the code under review is a visual animation, canvas sketch, or procedural art, you MUST ensure that it DOES NOT use simple geometric placeholders (like basic circles for characters, or plain rectangles for buildings/trees). It must feature rich procedural details, gradients, complex curves (bezierCurveTo, quadraticCurveTo), and detailed multi-layered backgrounds. If the code is basic or generic, you MUST fully implement and expand the visual elements, adding rich textures, curves, and high-fidelity rendering, outputting the complete revised code file. "
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


def _parse_hf_url(url: str) -> Optional[Tuple[str, str]]:
    if "huggingface.co" in url and "/resolve/" in url:
        try:
            parts = url.split("huggingface.co/")[-1].split("/resolve/")
            repo_id = parts[0]
            subparts = parts[1].split("/")
            remote_name = "/".join(subparts[1:])
            return repo_id, remote_name
        except Exception:
            pass
    return None


def get_size_config_download_info(filename: str) -> Optional[Tuple[str, str]]:
    try:
        cfg = load_generation_config()
        size = cfg.get("size", "tiny")
        size_path = os.path.join(os.path.dirname(CONFIG_PATH), "sizes", f"{size}.json")
        if os.path.exists(size_path):
            with open(size_path, "r", encoding="utf-8") as f:
                size_cfg = json.load(f)
            
            gguf_map = size_cfg.get("gguf", {})
            role = None
            for r, g_name in gguf_map.items():
                if g_name == filename:
                    role = r
                    break
            
            if not role and size_cfg.get("clip") == filename:
                url_map = size_cfg.get("download_urls", {})
                if filename in url_map:
                    return url_map[filename], filename
            
            if role:
                src_name = size_cfg.get("source_filenames", {}).get(role)
                url_map = size_cfg.get("download_urls", {})
                if src_name and src_name in url_map:
                    return url_map[src_name], src_name
    except Exception as e:
        logger.warning(f"[Iris] Failed to read size config for download URL lookup: {e}")
    return None


def _is_gguf_valid(path: str, url: Optional[str] = None) -> bool:
    if not os.path.exists(path):
        return False
    
    local_size = os.path.getsize(path)
    if local_size < 10 * 1024 * 1024:
        return False
        
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
            if magic != b"GGUF":
                return False
    except Exception:
        return False

    if url:
        try:
            import urllib.request
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=3) as resp:
                remote_size = int(resp.getheader("Content-Length", 0))
                if remote_size > 10 * 1024 * 1024 and local_size != remote_size:
                    logger.warning(f"[Iris] Size mismatch for {path}: local={local_size}, remote={remote_size}")
                    return False
        except Exception as e:
            logger.debug(f"[Iris] Remote size check skipped: {e}")
            
    return True


def download_gguf(filename: str, quiet: bool = False) -> bool:
    dest_path = os.path.join(os.path.dirname(_HERE), "models", filename)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    download_info = get_size_config_download_info(filename)
    expected_url = download_info[0] if download_info else None

    if os.path.exists(dest_path) and _is_gguf_valid(dest_path, expected_url):
        if not quiet:
            logger.info(f"[Iris] {filename} already present and valid, skipping download")
        return True

    if not quiet:
        logger.info(f"[Iris] Downloading {filename} ...")

    sources = []
    if download_info:
        url, remote_name = download_info
        hf_parsed = _parse_hf_url(url)
        if hf_parsed:
            sources.append(hf_parsed)
        else:
            sources.append(("", url))
    
    if filename in _MODEL_SOURCES:
        for repo_id, remote_name in _MODEL_SOURCES[filename]:
            if (repo_id, remote_name) not in sources:
                sources.append((repo_id, remote_name))

    if not sources:
        if not quiet:
            logger.info(f"[Iris] No download sources known for {filename}")
        return False

    last_error = None

    try:
        from huggingface_hub import hf_hub_download
        import time as _time

        for repo_id, remote_name in sources:
            if not repo_id:
                continue
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
                if "401" in last_error or "gated" in last_error.lower():
                    continue
                if "already exists" in last_error.lower():
                    return True
                if not quiet:
                    logger.warning(f"  Failed: {last_error[:60]}...")
    except ImportError:
        pass

    try:
        import urllib.request
        import time as _time

        for repo_id, remote_name in sources:
            if not repo_id:
                url = remote_name
            else:
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

        # Check if the model is missing, incomplete, or corrupted, and auto-download if needed
        download_info = get_size_config_download_info(filename)
        expected_url = download_info[0] if download_info else None
        
        if not os.path.exists(path) or not _is_gguf_valid(path, expected_url):
            if os.path.exists(path):
                logger.warning(f"[Iris] Model file {filename} at {path} is corrupted, incomplete, or invalid. Deleting and re-downloading...")
                try:
                    os.remove(path)
                except Exception as e:
                    logger.error(f"[Iris] Failed to remove invalid model file: {e}")
            
            logger.info(f"[Iris] Downloading missing/invalid model {filename}...")
            download_success = download_gguf(filename)
            if not download_success or not os.path.exists(path):
                raise FileNotFoundError(
                    f"GGUF model not found or failed to download for role '{role.value}'.\n"
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

        try:
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
        except Exception as e:
            logger.error(f"[Iris] Failed to load model from file: {path}. Error: {e}", exc_info=True)
            try:
                if os.path.exists(path):
                    logger.warning(f"[Iris] Deleting potentially corrupted model file: {path}")
                    os.remove(path)
            except Exception as del_err:
                logger.error(f"[Iris] Failed to delete corrupted model file: {del_err}")
                
            raise RuntimeError(
                f"Failed to load model from file: {path}. "
                f"This usually indicates the file is corrupted/incomplete or you ran out of memory (RAM/VRAM). "
                f"The corrupted file has been deleted. Please try again to trigger a clean re-download."
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
        # Frontend / creative-coding signals
        "canvas", "html5 canvas", "svg", "animation", "animate", "procedural",
        "requestanimationframe", "requestAnimationFrame", "draw", "render loop",
        "ctx.", "ctx.beginpath", "ctx.arc", "vertex", "shader", "webgl",
    }
    # These signals alone guarantee CODING_SIMPLE (single self-contained file)
    canvas_signals = {
        "canvas", "html5 canvas", "svg", "animation", "animate",
        "requestanimationframe", "procedural", "draw", "render loop",
        "ctx.", "webgl", "vertex", "shader",
    }
    complex_signals = {
        "kernel", "gcc", "clang", "qemu", "driver", "bootloader", "pong",
        "game", "make", "makefile", "multi-file", "multiple files",
        "full project", "entire project",
    }
    for kw in code_keywords:
        if re.search(rf"\b{re.escape(kw)}\b", q, re.IGNORECASE):
            if kw in canvas_signals:
                # Self-contained single-file creative code — never complex
                return TaskType.CODING_SIMPLE
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
    has_tech = "tailwind" in lower_query or "html" in lower_query or "css" in lower_query
    has_intent = (
        re.search(r"\bbuild\b", lower_query) or 
        "landing page" in lower_query or 
        "website" in lower_query or 
        "full-stack developer" in lower_query
    )
    if has_tech and has_intent:
        logger.info("[Triage] Hardcoded intercept: Web development query detected. Routing to CODING_COMPLEX.")
        return TaskType.CODING_COMPLEX, None

    result = _fallback_classify(query_for_classification)
    if result is not None:
        
        if result == TaskType.CONTROL and ("mockup" in lower_query or "terminal element" in lower_query or "terminal window" in lower_query):
            pass
        else:
            return result, None
            
    if history and history[-1].get("role") == "user" and history[-1].get("content", "").strip().startswith("OBSERVATION:"):
        return TaskType.CONTROL, None

    
    
    
    
    from src.iris import _model_pool, ModelRole
    
    _active_role = None
    if _model_pool:
        
        _active_role_str = next(reversed(_model_pool))
        try:
            _active_role = ModelRole(_active_role_str)
        except ValueError:
            pass

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
        max_tokens=256,
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
            r'welcome|hiya|what\'?s?\s*up|how\s*are\s*you|nice\s*to\s*meet)',
            re.IGNORECASE
        )
        # Identity-like answers must NOT be treated as greetings — route to GENERAL instead
        IDENTITY_PATTERNS = re.compile(
            r'(i\'?m\s+(iris|an?\s+ai)|i\s+am\s+(iris|an?\s+ai)|iris\s+here|created\s+by|made\s+by|built\s+by|أنا)',
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
            and not IDENTITY_PATTERNS.search(answer)
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
        r"\\boxed{((?:[^{}]|{[^{}]*})*)}",
        r'<span style="border: 2px solid #4CAF50; padding: 2px 6px; border-radius: 4px; font-weight: bold; background-color: rgba(76, 175, 80, 0.1);">\1</span>',
        text
    )

    # Strip identity bleed from upstream models (DeepSeek, Qwen, etc.)
    text = re.sub(
        r"(?i)(I('m| am) (DeepSeek|Qwen|Intern|Hermes|Llama|Meta|Mistral|"
        r"a large language model|an AI language model|an artificial intelligence)"
        r"[^.]*\.?\s*)",
        "", text
    ).strip()

    # --- Repetition loop detection: truncate if a sentence repeats 3+ times ---
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) > 6:
        seen = {}
        cut_idx = None
        for i, s in enumerate(sentences):
            normalized = s.strip().lower()
            if len(normalized) < 15:
                continue
            seen[normalized] = seen.get(normalized, 0) + 1
            if seen[normalized] >= 3:
                cut_idx = i
                break
        if cut_idx is not None:
            text = ' '.join(sentences[:cut_idx])
            if not text.endswith(('.', '!', '?')):
                text += '.'

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


def _has_repetition_loop(text: str) -> bool:
    if len(text) < 50:
        return False
    
    # Check the last 300 characters
    suffix = text[-300:]
    
    # 1. Non-whitespace character repeating 15+ times
    if re.search(r'([^\s])\1{14}', suffix):
        return True
        
    # 2. 2-5 character pattern repeating 8+ times (must contain non-whitespace and >1 unique character)
    for match in re.finditer(r'(.{2,5}?)\1{7}', suffix):
        pattern = match.group(1)
        if pattern.strip() and len(set(pattern.strip())) > 1:
            return True
            
    # 3. 6-30 character pattern repeating 4+ times (must contain non-whitespace and >1 unique character)
    for match in re.finditer(r'(.{6,30}?)\1{3}', suffix):
        pattern = match.group(1)
        if pattern.strip() and len(set(pattern.strip())) > 1:
            return True
            
    return False


def _stream_tokens(
    role: ModelRole,
    messages: List[Dict[str, str]],
    max_tokens: int = 0,
    temperature: float = 0.7,
    think_mode: str = "pass",
    system_prompt_override: Optional[str] = None,
    settings: Optional[dict] = None,
    extra_stop_words: Optional[List[str]] = None
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

    full_messages = [{"role": "system", "content": sys_prompt}] + sanitized_messages

    cfg = load_generation_config()
    model_cfg = cfg.get("model_settings", {}).get(role.value, {})

    # --- Role-aware default generation parameters ---
    actual_temp = temperature
    rep_penalty = 1.1
    freq_penalty = 0.3 if role in (ModelRole.CODE, ModelRole.REASONING) else 0.05
    pres_penalty = 0.3 if role in (ModelRole.CODE, ModelRole.REASONING) else 0.05
    top_p = 0.9
    top_k = 40

    # Role-specific min_p: higher for smaller/precision roles, lower for creative roles
    _min_p_defaults = {
        ModelRole.TRIAGE: 0.1,
        ModelRole.CONTROL: 0.1,
        ModelRole.MATH: 0.1,
        ModelRole.CODE: 0.05,
        ModelRole.REVIEWER: 0.05,
        ModelRole.REASONING: 0.05,
        ModelRole.GENERAL: 0.03,
    }
    min_p = _min_p_defaults.get(role, 0.05)

    
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

    if role == ModelRole.CODE and rep_penalty < 1.15:
        rep_penalty = 1.15
        
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
        stop_list = ["</s>", "<|eot_id|>", "<|end_of_text|>", "<|im_end|>", "<step_end>", "## Conversation"]
        if extra_stop_words:
            stop_list.extend(extra_stop_words)
            
        actual_max_tokens = None if max_tokens >= 4000 else max_tokens
        stream = llm.create_chat_completion(
            messages=full_messages,
            stream=True,
            max_tokens=actual_max_tokens,
            temperature=actual_temp,
            repeat_penalty=rep_penalty,
            frequency_penalty=freq_penalty,
            presence_penalty=pres_penalty,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            seed=42 + loop_idx,
            stop=stop_list,
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
                if _has_repetition_loop(loop_content):
                    logger.warning(f"[Repetition Guard] Infinite loop detected in model generation for role '{role.value}'. Stopping stream.")
                    finish_reason = "stop"
                    break
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

            if _has_repetition_loop(loop_content):
                logger.warning(f"[Repetition Guard] Infinite loop detected in model generation for role '{role.value}'. Stopping stream.")
                finish_reason = "stop"
                break

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
            elif role == ModelRole.CODE:
                try:
                    from src.iris_pro import verify_code_syntax
                    blocks = re.findall(r'```(\w*)\n(.*?)```', loop_content, re.DOTALL)
                    if blocks:
                        lang, code = blocks[-1]
                        err = verify_code_syntax(code, lang)
                        if err is not None:
                            logger.warning(f"Syntax verification failed in normal mode: {err}")
                            yield {"type": "status", "content": "Fixing syntax errors..."}
                            yield {"type": "clear"}
                            full_messages.append({"role": "assistant", "content": loop_content})
                            full_messages.append({
                                "role": "user",
                                "content": f"The following code you generated has a syntax error:\n\n```\n{err}\n```\n\nCode:\n```\n{code}\n```\n\nFix the error immediately and output the complete, corrected code."
                            })
                            finish_reason = "error_fix"
                except Exception as exc:
                    logger.error(f"Error during syntax verification: {exc}")

        if finish_reason != "error_fix":
            yield {"type": "finish", "reason": finish_reason}

        if finish_reason == "length":
            content_to_keep = loop_content[-6000:] if len(loop_content) > 6000 else loop_content
            prefix = "...[TRUNCATED]...\n" if len(loop_content) > 6000 else ""
            full_messages.append({"role": "assistant", "content": prefix + content_to_keep})
            full_messages.append({
                "role": "user",
                "content": "Continue exactly where you left off, from the very next character. "
                "Do not repeat anything."
            })
        elif finish_reason == "error_fix":
            continue
        else:
            break
=======
import logging
from typing import Generator, Dict
>>>>>>> eb6d76ec406f78bacf34d3b7d05c810626da6e7a

logger = logging.getLogger('iris')

def ask_stream(
    user_query: str,
    history: list = None,
    stream: bool = True,
    retriever=None,
    settings: dict = None,
    force_role=None,
    keep_loaded: bool = False,
    **kwargs
) -> Generator[Dict[str, str], None, None]:
    if history is None:
        history = []
    


    # Image checking and formatting
    original_query = user_query
    img_match = re.match(r'^\[IMAGE_UPLOADED:\s*(.+?)\]\s*(.*)$', user_query, flags=re.DOTALL)
    if img_match:
        image_path = img_match.group(1).strip()
        prompt = img_match.group(2).strip()
        if not prompt:
            prompt = "Describe this image in detail."
        yield {"type": "status", "content": "Analyzing image with Vision model..."}
        from src.iris_vision import analyze_image
        res = analyze_image(image_path, prompt, unload_after=not keep_loaded)
        
        try:
            import os
            os.unlink(image_path)
        except Exception:
            pass
            
        yield {"type": "token", "content": res}
        yield {"type": "raw_response", "content": res}
        return
    direct_answer = ""

    from src.iris_engine import TaskType, ModelRole, _keep_loaded
    import src.iris_engine
    src.iris_engine._keep_loaded = keep_loaded

    if force_role:
        if isinstance(force_role, str):
            try:
                force_role = ModelRole(force_role)
            except ValueError:
                pass
        
        # Map ModelRole to TaskType
        role_map = {
            ModelRole.CODE: TaskType.CODING_COMPLEX,
            ModelRole.MATH: TaskType.MATH,
            ModelRole.REASONING: TaskType.REASONING,
            ModelRole.GENERAL: TaskType.GENERAL,
            ModelRole.CONTROL: TaskType.CONTROL
        }
        task_type = role_map.get(force_role, None)
        if task_type is None:
            from src.iris_triage import classify_task
            task_type, direct_answer = classify_task(original_query, history)
    else:
        from src.iris_triage import classify_task
        task_type, direct_answer = classify_task(original_query, history)
    
    if task_type == TaskType.CONTROL:
        from src.iris_control import run_stream
        yield from run_stream(user_query, history, retriever, settings)
        return
        
    if task_type == TaskType.SEARCH:
        from src.iris_reasoning import run_stream
        yield from run_stream(user_query, history, retriever, settings, do_search=True, direct_answer=direct_answer)
        return

    if task_type is None:
        if direct_answer:
            from src.iris_engine import _quality_guard
            cleaned = _quality_guard(direct_answer)
            yield {"type": "token", "content": cleaned}
            yield {"type": "raw_response", "content": cleaned}
        return
        
    yield {"type": "status", "content": f"Task: {task_type.value.upper()}"}

    if task_type == TaskType.GENERAL:
        from src.iris_general import run_stream
        yield from run_stream(user_query, history, retriever, settings)
    elif task_type == TaskType.REASONING:
        from src.iris_reasoning import run_stream
        yield from run_stream(user_query, history, retriever, settings, do_search=False)
    elif task_type == TaskType.MATH:
        from src.iris_math import run_stream
        yield from run_stream(user_query, history, retriever, settings)
    elif task_type == TaskType.CODING_SIMPLE:
        from src.iris_coding import run_stream
        yield from run_stream(user_query, history, retriever, settings, is_complex=False)
    elif task_type == TaskType.CODING_COMPLEX:
        from src.iris_coding import run_stream
        yield from run_stream(user_query, history, retriever, settings, is_complex=True)
