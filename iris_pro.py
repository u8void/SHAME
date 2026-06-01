from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import time
import warnings
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator

import openai
from openai import AsyncOpenAI

warnings.filterwarnings("ignore", category=RuntimeWarning, message="coroutine method 'aclose'")
 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("iris_ai")

# OCENZA_BASE_URL was removed because the OpenRouterClient must point to the local
# OpenRouter proxy server running at http://localhost:20128/v1 for this workspace environment.
SITE_URL: str       = os.getenv("OCENZA_SITE_URL", "https://iris-ai.app")
APP_TITLE: str      = os.getenv("OCENZA_APP_TITLE", "Iris AI")
REQUEST_TIMEOUT_S   = float(os.getenv("IRIS_REQUEST_TIMEOUT", "600"))

# Configuration Constants
MAX_TOKENS = 8196
MAX_TOKENS_GENERAL = 4096
MAX_TOKENS_TRIAGE = 1024
MAX_REASONING_CHARS = 150000
MAX_HISTORY_CONTENT_CHARS = 1000
MAX_TRIAGE_CONTENT_CHARS = 500
MAX_HISTORY_MESSAGES = 40
MAX_RETRIES = 6
RETRY_BASE_WAIT_S = 3.0
MAX_STAGE_INPUT_CHARS = 8000
MAX_CONTINUATION_LOOPS = 5

IRIS_IDENTITY = (
    "You are Iris AI. Answer directly without introducing yourself or saying 'I am Iris AI' at the start. "
    "Never mention underlying model names (e.g., MiMo, Xiaomi, DeepSeek) or pipeline architecture. "
    "If asked who you are, identify as Iris AI."
)

class Model(str, Enum):
    ORCHESTRATOR  = "cmc/deepseek/deepseek-v4-flash"
    CODE          = "cmc/xiaomi/mimo-v2.5-pro"
    REASONING     = "cmc/deepseek/deepseek-v4-pro"
    MATH          = "cmc/deepseek/deepseek-v4-flash"
    CODE_REVIEWER = "cmc/xiaomi/mimo-v2.5-pro"

class TaskType(str, Enum):
    MATH           = "math"
    CODING_SIMPLE  = "coding_simple"
    CODING_COMPLEX = "coding_complex"
    REASONING      = "reasoning"
    GENERAL        = "general"
    SEARCH         = "search"


TASK_TO_MODEL: dict[TaskType, Model] = {
    TaskType.MATH:           Model.MATH,
    TaskType.CODING_SIMPLE:  Model.CODE,
    TaskType.CODING_COMPLEX: Model.CODE,
    TaskType.REASONING:      Model.REASONING,
    TaskType.GENERAL:        Model.ORCHESTRATOR,
    TaskType.SEARCH:         Model.ORCHESTRATOR,
}


@dataclass
class TokenUsage:
    prompt_tokens:     int = 0
    completion_tokens: int = 0
    total_tokens:      int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        if not isinstance(other, TokenUsage):
            raise TypeError("Operand must be an instance of TokenUsage")
        return TokenUsage(
            self.prompt_tokens     + other.prompt_tokens,
            self.completion_tokens + other.completion_tokens,
            self.total_tokens      + other.total_tokens,
        )

    def __str__(self) -> str:
        return (
            f"prompt={self.prompt_tokens}, "
            f"completion={self.completion_tokens}, "
            f"total={self.total_tokens}"
        )


@dataclass
class HopResult:
    hop_name:     str
    model:        str
    content:      str
    usage:        TokenUsage
    latency_ms:   float
    raw_response: dict[str, Any] = field(default_factory=dict, repr=False)

    def log_summary(self) -> None:
        log.info(
            "HOP %-30s | model=%-40s | tokens=[%s] | %.0fms",
            self.hop_name, self.model, self.usage, self.latency_ms,
        )


@dataclass
class RoutingDecision:
    task_type: TaskType
    rationale: str
    subtasks:  list[str]        = field(default_factory=list)
    raw_json:  dict[str, Any]   = field(default_factory=dict)


@dataclass
class PipelineResult:
    user_query:        str
    routing_decision:  RoutingDecision
    specialist_output: str
    final_answer:      str
    hops:              list[HopResult] = field(default_factory=list)
    aggregate_usage:   TokenUsage      = field(default_factory=TokenUsage)


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

SPECIALIST_SYSTEM_PROMPTS: dict[TaskType, str] = {
    TaskType.MATH:           MATH_SYSTEM_PROMPT,
    TaskType.CODING_SIMPLE:  CODE_SYSTEM_PROMPT,
    TaskType.CODING_COMPLEX: CODE_SYSTEM_PROMPT,
    TaskType.REASONING:      REASONING_SYSTEM_PROMPT,
    TaskType.GENERAL:        GENERAL_SYSTEM_PROMPT,
    TaskType.SEARCH:         GENERAL_SYSTEM_PROMPT,
}


class OpenRouterClient:
    def __init__(self) -> None:
        self.api_key = "sk-1c489e5544334f97-p50fxh-ec2cb811"
        self.base_url = "http://localhost:20128/v1"
        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=REQUEST_TIMEOUT_S,
        )

    async def _handle_api_error(self, exc: Exception, attempt: int) -> None:
        """Log a retryable API error and sleep for the backoff duration.

        Raises RuntimeError on the final attempt instead of sleeping.
        """
        wait_s = RETRY_BASE_WAIT_S * (2 ** attempt)
        if attempt < MAX_RETRIES - 1:
            log.warning(
                "API error (%s): %s. Retrying in %.1fs (attempt %d/%d)...",
                type(exc).__name__, exc, wait_s, attempt + 1, MAX_RETRIES,
            )
            await asyncio.sleep(wait_s)
        else:
            raise RuntimeError("API is currently overloaded or down. Please try again.") from exc

    async def chat(
        self,
        *,
        model:           str,
        messages:        list[dict[str, str]],
        temperature:     float                  = 0.2,
        max_tokens:      int                    = MAX_TOKENS,
        response_format: dict[str, str] | None  = None,
        extra_body:      dict[str, Any] | None  = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model":       model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format
        if extra_body:
            kwargs["extra_body"] = extra_body

        for attempt in range(MAX_RETRIES):
            try:
                response = await self._client.chat.completions.create(**kwargs)
                return response.model_dump()
            except (openai.APIStatusError, openai.APIConnectionError, openai.APITimeoutError) as exc:
                await self._handle_api_error(exc, attempt)

    async def stream_chat(
        self,
        *,
        model:           str,
        messages:        list[dict[str, str]],
        temperature:     float                  = 0.2,
        max_tokens:      int                    = MAX_TOKENS,
        response_format: dict[str, str] | None  = None,
        extra_body:      dict[str, Any] | None  = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        kwargs: dict[str, Any] = {
            "model":       model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
            "stream":      True,
        }
        if response_format:
            kwargs["response_format"] = response_format
        if extra_body:
            kwargs["extra_body"] = extra_body

        for attempt in range(MAX_RETRIES):
            try:
                stream = await self._client.chat.completions.create(**kwargs)
                iterator = stream.__aiter__()
                pending_task = None
                
                try:
                    while True:
                        if pending_task is None:
                            pending_task = asyncio.create_task(iterator.__anext__())
                        
                        done, pending = await asyncio.wait([pending_task], timeout=2.0)
                        
                        if pending_task in done:
                            try:
                                chunk = pending_task.result()
                                yield chunk.model_dump()
                                pending_task = None
                            except StopAsyncIteration:
                                break
                        else:
                            yield {"keepalive": True}
                finally:
                    if pending_task and not pending_task.done():
                        pending_task.cancel()
                    if hasattr(stream, '_iterator') and stream._iterator is not None:
                        try:
                            await stream._iterator.aclose()
                        except Exception:
                            pass
                    if hasattr(iterator, 'aclose'):
                        try:
                            await iterator.aclose()
                        except Exception:
                            pass
                    await stream.close()
                return
            except (openai.APIStatusError, openai.APIConnectionError, openai.APITimeoutError) as exc:
                await self._handle_api_error(exc, attempt)

    async def aclose(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> "OpenRouterClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()


def _extract_usage(raw: dict[str, Any]) -> TokenUsage:
    usage = raw.get("usage") or {}
    return TokenUsage(
        prompt_tokens     = usage.get("prompt_tokens",     0),
        completion_tokens = usage.get("completion_tokens", 0),
        total_tokens      = usage.get("total_tokens",      0),
    )


def _extract_content(raw: dict[str, Any]) -> str:
    try:
        choices = raw.get("choices", [])
        if not choices:
            return ""
        content = choices[0].get("message", {}).get("content")
        if content is None:
            return ""
        if isinstance(content, list):
            return "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        return str(content)
    except Exception:
        return ""


def _timed_hop(name: str, model: str, raw: dict[str, Any], elapsed_s: float) -> HopResult:
    return HopResult(
        hop_name     = name,
        model        = model,
        content      = _extract_content(raw),
        usage        = _extract_usage(raw),
        latency_ms   = elapsed_s * 1000,
        raw_response = raw,
    )


def _extract_reasoning_content(raw: dict[str, Any]) -> str:
    try:
        message = raw["choices"][0]["message"]
        if message.get("reasoning_content"):
            return message["reasoning_content"]
        content: str = message.get("content") or ""
        if "<think>" in content and "</think>" in content:
            start = content.index("<think>") + len("<think>")
            end   = content.index("</think>")
            return content[start:end].strip()
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return ""


# ---------------------------------------------------------------------------
# Non-streaming pipeline helpers
# These two functions implement a blocking (non-streaming) two-hop pipeline:
#   stage_reasoning → stage_talking
# They are NOT called by ask_stream (which handles its own streaming stages)
# and are intended for direct use by callers that don't require streaming output.
# ---------------------------------------------------------------------------

async def stage_reasoning(
    client: OpenRouterClient,
    user_query: str,
    history: list[dict[str, str]] | None = None,
) -> tuple[str, HopResult]:
    log.info("Stage 1 — Reasoning model thinking...")
    messages = []
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_query})

    t0 = time.perf_counter()
    raw = await client.chat(
        model=Model.REASONING.value,
        messages=messages,
        temperature=0.6,
        max_tokens=MAX_TOKENS,
        extra_body={"include_reasoning": True}
    )
    elapsed = time.perf_counter() - t0
    hop = _timed_hop("1:reasoning", Model.REASONING.value, raw, elapsed)
    hop.log_summary()

    reasoning_content = _extract_reasoning_content(raw)
    output = hop.content
    if reasoning_content:
        output = f"<thinking>\n{reasoning_content}\n</thinking>\n\n{hop.content}"
    
    return output, hop


async def stage_talking(
    client: OpenRouterClient,
    user_query: str,
    reasoning_output: str,
) -> tuple[str, HopResult]:
    log.info("Stage 2 — Orchestrator formulating final response...")
    
    talk_prompt = (
        f"{IRIS_IDENTITY}\n\n"
        "You are the Iris AI Orchestrator. You have been provided with the user's query and the "
        "raw reasoning process from our internal deep-thinking engine. "
        "Your task is to read the reasoning, synthesize it, and present the final answer to the user "
        "in a clear, professional, and well-formatted manner. "
        "CRITICAL INSTRUCTION: If the user asks for code, or the reasoning contains code, you MUST output the complete, full code without ANY truncation, abbreviation, or placeholders (like 'rest of the code goes here' or '...'). Never be lazy. Always provide the full, ready-to-run code.\n"
        "DO NOT expose the `<thinking>` tags or mention the internal reasoning engine. Just give the final answer."
    )
    
    truncated_reasoning = reasoning_output
    if len(truncated_reasoning) > MAX_REASONING_CHARS:
        log.warning("Truncating reasoning_output from %d to %d chars.", len(truncated_reasoning), MAX_REASONING_CHARS)
        truncated_reasoning = truncated_reasoning[:MAX_REASONING_CHARS] + "\n...[truncated for length]"

    messages = [
        {"role": "system", "content": talk_prompt},
        {"role": "user", "content": f"User Query: {user_query}\n\nInternal Reasoning:\n{truncated_reasoning}"}
    ]

    t0 = time.perf_counter()
    
    full_content = ""
    last_raw = None
    
    for i in range(MAX_CONTINUATION_LOOPS):
        raw = await client.chat(
            model=Model.ORCHESTRATOR.value,
            messages=messages,
            temperature=0.3,
            max_tokens=MAX_TOKENS,
        )
        last_raw = raw
        chunk_content = _extract_content(raw)
        full_content += chunk_content
        
        finish_reason = "stop"
        try:
            finish_reason = raw["choices"][0].get("finish_reason", "stop")
        except (KeyError, IndexError):
            pass
            
        if finish_reason == "length":
            log.warning("Orchestrator hit max_tokens length. Auto-continuing (loop %d)...", i+1)
            messages.append({"role": "assistant", "content": chunk_content})
            messages.append({"role": "user", "content": "Continue exactly where you left off, from the very next character. Do not repeat anything, do not write intro text or markdown blocks, just the raw continuation."})
        else:
            break
            
    elapsed = time.perf_counter() - t0
    synthetic_raw = {}
    if last_raw:
        synthetic_raw = {
            "choices": [{"message": {"content": full_content, "role": "assistant"}}],
            "usage": last_raw.get("usage", {})
        }
    hop = _timed_hop("2:talking", Model.ORCHESTRATOR.value, synthetic_raw, elapsed)
    hop.log_summary()
    return hop.content, hop


def optimize_messages(history_messages: list[dict[str, str]] | None, user_query: str) -> list[dict[str, str]]:
    if not history_messages:
        return [{"role": "user", "content": user_query}]
    
    recent = history_messages[-6:]
    optimized = []
    
    for i, msg in enumerate(recent):
        role = msg.get("role")
        content = msg.get("content", "")
        
        if i < len(recent) - 1:
            content = re.sub(r'```[\s\S]*?```', '```\n[Code block omitted to save tokens]\n```', content)
            if len(content) > MAX_HISTORY_CONTENT_CHARS:
                content = content[:MAX_HISTORY_CONTENT_CHARS] + "\n...[truncated]"
                
        optimized.append({"role": role, "content": content})
        
    optimized.append({"role": "user", "content": user_query})
    return optimized


def fallback_classify(query: str) -> TaskType | None:
    q = query.lower()
    
    # 1. Coding check
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
            if kw in complex_keywords or len(q) > 300:
                return TaskType.CODING_COMPLEX
            else:
                return TaskType.CODING_SIMPLE

    # 2. Math check
    math_keywords = {
        "math", "mathematics", "equation", "equations", "formula", "formulas",
        "derivative", "derivatives", "integral", "integrals", "calculus",
        "algebra", "geometry", "trigonometry", "matrix", "matrices", "vector", "vectors",
        "theorem", "proof", "prove", "probability", "statistics", "combinatorics"
    }
    for kw in math_keywords:
        if re.search(rf"\b{re.escape(kw)}\b", q):
            return TaskType.MATH
            
    # Math symbols check
    if re.search(r'[\d\s]+[\+\-\*\/=]+[\d\s]+', q):
        return TaskType.MATH

    # 3. Reasoning check
    reasoning_keywords = {
        "logic", "logical", "puzzle", "puzzles", "riddle", "riddles",
        "reasoning", "system design", "architecture"
    }
    for kw in reasoning_keywords:
        if re.search(rf"\b{re.escape(kw)}\b", q):
            return TaskType.REASONING

    return None


def is_continuation_query(query: str, history: list[dict[str, str]] | None) -> bool:
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
            if "```" in content or "<file_card" in content or "<thinking" in content:
                has_code = True
                break
    return has_code


async def ask_stream(
    user_query: str,
    history:    list[dict[str, str]] | None = None,
    mode:       str = "smart"
) -> AsyncGenerator[dict[str, Any], None]:
    hops: list[HopResult] = []
    is_continuation = is_continuation_query(user_query, history)
    
    async with OpenRouterClient() as client:
        if mode == "smart":
            # Optimize history for all subsequent specialist stages
            messages = optimize_messages(history, user_query)

            if is_continuation:
                task_type = TaskType.CODING_COMPLEX
                yield {"type": "status", "content": "Resuming code generation..."}
            else:
                # Minimize history for Triage stage to save prompt tokens
                minimized_history = []
                if history:
                    last_msg = history[-1]
                    content = last_msg.get("content", "")
                    content_clean = re.sub(r'```[\s\S]*?```', '```\n[Code block omitted]\n```', content)
                    if len(content_clean) > MAX_TRIAGE_CONTENT_CHARS:
                        content_clean = content_clean[:MAX_TRIAGE_CONTENT_CHARS] + "\n...[truncated]"
                    minimized_history.append({"role": last_msg.get("role"), "content": content_clean})
                triage_query = user_query
                if "I have attached a file named" in triage_query and "User Prompt:\n" in triage_query:
                    parts = triage_query.split("User Prompt:\n")
                    if len(parts) > 1:
                        triage_query = parts[-1]
                minimized_history.append({"role": "user", "content": triage_query})

                # Stage 0: Triage
                yield {"type": "status", "content": "Analyzing query complexity..."}
                triage_prompt = (
                    "You are the Iris AI query router.\n"
                    "If the user asks a conversational/general knowledge question, do NOT output any tags; answer directly.\n\n"
                    "Otherwise, output EXACTLY ONE tag and NOTHING ELSE. DO NOT answer the query yourself:\n"
                    "- [TASK_TYPE: coding_simple] (for simple coding questions, explaining code, syntax, basic functions, single script edits)\n"
                    "- [TASK_TYPE: coding_complex] (for large projects, writing games, custom emulators/drivers, multi-file codebases, or complex logic coding)\n"
                    "- [TASK_TYPE: math] (for equations, proofs, algorithmic derivations)\n"
                    "- [TASK_TYPE: reasoning] (for deep logic puzzles, architecture design, long analysis)\n\n"
                    "CRITICAL: If the query mentions writing a complete game (e.g. Pong), building compilers, operating system bootloaders, or complex hardware simulation, output [TASK_TYPE: coding_complex]."
                )
                triage_messages = [
                    {"role": "system", "content": triage_prompt},
                    *minimized_history
                ]

                t0_triage = time.perf_counter()
                triage_answer = ""
                triage_usage = {}
                try:
                    async for chunk in client.stream_chat(
                        model=Model.ORCHESTRATOR.value,
                        messages=triage_messages,
                        temperature=0.2,
                        max_tokens=MAX_TOKENS_TRIAGE,
                    ):
                        if chunk.get("usage"):
                            triage_usage = chunk["usage"]
                        token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if token:
                            triage_answer += token
                        if chunk.get("keepalive"):
                            yield {"type": "status", "content": "Analyzing..."}
                except (openai.APIStatusError, openai.APIConnectionError, openai.APITimeoutError) as exc:
                    log.exception("Unexpected error in Triage stage: %s", exc)
                    triage_answer = "[TASK_TYPE: general]"

                task_type = None
                if re.search(r'\[\s*task_type:\s*coding_complex\s*\]', triage_answer, re.IGNORECASE): task_type = TaskType.CODING_COMPLEX
                elif re.search(r'\[\s*task_type:\s*coding_simple\s*\]', triage_answer, re.IGNORECASE): task_type = TaskType.CODING_SIMPLE
                elif re.search(r'\[\s*task_type:\s*coding\s*\]', triage_answer, re.IGNORECASE): task_type = TaskType.CODING_SIMPLE
                elif re.search(r'\[\s*task_type:\s*math\s*\]', triage_answer, re.IGNORECASE): task_type = TaskType.MATH
                elif re.search(r'\[\s*task_type:\s*reasoning\s*\]', triage_answer, re.IGNORECASE): task_type = TaskType.REASONING
                elif re.search(r'\[\s*task_type:\s*general\s*\]', triage_answer, re.IGNORECASE): task_type = TaskType.GENERAL

                if task_type is None and "task_type" not in triage_answer.lower():
                    # Direct answer from Triage
                    task_type = fallback_classify(user_query)

                if task_type is None:
                    # Direct answer from Triage
                    triage_clean = triage_answer.strip()
                    if not triage_clean:
                        triage_clean = "Hello! How can I help you today?"
                    
                    # Yield the Triage model's answer directly
                    yield {"type": "token", "content": triage_clean}
                    elapsed = time.perf_counter() - t0_triage
                    synthetic_raw = {
                        "choices": [{"message": {"content": triage_clean}}],
                        "usage": triage_usage
                    }
                    hop = _timed_hop("0:triage_answer", Model.ORCHESTRATOR.value, synthetic_raw, elapsed)
                    hop.content = triage_clean
                    hops.append(hop)
                    return

                yield {"type": "status", "content": f"Task categorized as {task_type.value.upper()}..."}

            if task_type in (TaskType.GENERAL, TaskType.SEARCH):
                t0 = time.perf_counter()
                log.info("Starting general response with %s...", Model.ORCHESTRATOR.value)
                general_messages = [
                    {"role": "system", "content": GENERAL_SYSTEM_PROMPT},
                    *messages
                ]
                try:
                    full_content = ""
                    last_usage = {}
                    for i in range(MAX_CONTINUATION_LOOPS):
                        finish_reason = "stop"
                        loop_content = ""
                        async for chunk in client.stream_chat(
                            model=Model.ORCHESTRATOR.value,
                            messages=general_messages,
                            temperature=0.3,
                            max_tokens=MAX_TOKENS_GENERAL,
                        ):
                            try:
                                choice = chunk.get("choices", [{}])[0]
                                if chunk.get("usage"):
                                    last_usage = chunk["usage"]
                                delta = choice.get("delta", {})
                                token = delta.get("content", "")
                                if token:
                                    loop_content += token
                                    full_content += token
                                    yield {"type": "token", "content": token}
                                if "finish_reason" in choice and choice["finish_reason"]:
                                    finish_reason = choice["finish_reason"]
                            except (KeyError, IndexError):
                                pass
                        if finish_reason == "length":
                            log.warning("Orchestrator hit max_tokens length in GENERAL. Auto-continuing (loop %d)...", i+1)
                            general_messages.append({"role": "assistant", "content": loop_content})
                            general_messages.append({"role": "user", "content": "Continue exactly where you left off, from the very next character. Do not repeat anything."})
                        else:
                            break

                    elapsed = time.perf_counter() - t0
                    synthetic_raw = {
                        "choices": [{"message": {"content": full_content}}],
                        "usage": last_usage
                    }
                    hop = _timed_hop("1:general", Model.ORCHESTRATOR.value, synthetic_raw, elapsed)
                    hops.append(hop)
                except Exception as exc:
                    log.exception("Error in General stage: %s", exc)
                    raise

            elif task_type == TaskType.MATH:
                t0 = time.perf_counter()
                log.info("Starting math solver with %s...", Model.MATH.value)
                math_messages = [
                    {"role": "system", "content": MATH_SYSTEM_PROMPT},
                    *messages
                ]
                try:
                    full_content = ""
                    last_usage = {}
                    for i in range(MAX_CONTINUATION_LOOPS):
                        finish_reason = "stop"
                        loop_content = ""
                        async for chunk in client.stream_chat(
                            model=Model.MATH.value,
                            messages=math_messages,
                            temperature=0.2,
                            max_tokens=MAX_TOKENS,
                        ):
                            try:
                                choice = chunk.get("choices", [{}])[0]
                                if chunk.get("usage"):
                                    last_usage = chunk["usage"]
                                delta = choice.get("delta", {})
                                token = delta.get("content", "")
                                if token:
                                    loop_content += token
                                    full_content += token
                                    yield {"type": "token", "content": token}
                                if "finish_reason" in choice and choice["finish_reason"]:
                                    finish_reason = choice["finish_reason"]
                            except (KeyError, IndexError):
                                pass
                        if finish_reason == "length":
                            log.warning("Model.MATH hit max_tokens length in MATH. Auto-continuing (loop %d)...", i+1)
                            math_messages.append({"role": "assistant", "content": loop_content})
                            math_messages.append({"role": "user", "content": "Continue exactly where you left off, from the very next character. Do not repeat anything."})
                        else:
                            break

                    elapsed = time.perf_counter() - t0
                    synthetic_raw = {
                        "choices": [{"message": {"content": full_content}}],
                        "usage": last_usage
                    }
                    hop = _timed_hop("1:math", Model.MATH.value, synthetic_raw, elapsed)
                    hops.append(hop)
                except Exception as exc:
                    log.exception("Error in Math stage: %s", exc)
                    raise

            elif task_type == TaskType.REASONING:
                t0 = time.perf_counter()
                log.info("Starting deep reasoning with %s...", Model.REASONING.value)
                reasoning_messages = [
                    {"role": "system", "content": REASONING_SYSTEM_PROMPT},
                    *messages
                ]
                try:
                    full_content = ""
                    last_usage = {}
                    in_thinking = False
                    for i in range(MAX_CONTINUATION_LOOPS):
                        finish_reason = "stop"
                        loop_content = ""
                        async for chunk in client.stream_chat(
                            model=Model.REASONING.value,
                            messages=reasoning_messages,
                            temperature=0.5,
                            max_tokens=MAX_TOKENS,
                            extra_body={"include_reasoning": True}
                        ):
                            try:
                                choice = chunk.get("choices", [{}])[0]
                                if chunk.get("usage"):
                                    last_usage = chunk["usage"]
                                delta = choice.get("delta", {})
                                
                                if "reasoning_content" in delta and delta["reasoning_content"]:
                                    if not in_thinking:
                                        yield {"type": "token", "content": "<think>\n"}
                                        in_thinking = True
                                    yield {"type": "token", "content": delta["reasoning_content"]}
                                else:
                                    if in_thinking:
                                        yield {"type": "token", "content": "\n</think>\n\n"}
                                        in_thinking = False
                                        
                                token = delta.get("content", "")
                                if token:
                                    loop_content += token
                                    full_content += token
                                    yield {"type": "token", "content": token}
                                if "finish_reason" in choice and choice["finish_reason"]:
                                    finish_reason = choice["finish_reason"]
                            except (KeyError, IndexError):
                                pass
                        if finish_reason == "length":
                            log.warning("Model.REASONING hit max_tokens length in REASONING. Auto-continuing (loop %d)...", i+1)
                            reasoning_messages.append({"role": "assistant", "content": loop_content})
                            reasoning_messages.append({"role": "user", "content": "Continue exactly where you left off, from the very next character. Do not repeat anything."})
                        else:
                            break

                    if in_thinking:
                        yield {"type": "token", "content": "\n</think>\n\n"}
                    elapsed = time.perf_counter() - t0
                    synthetic_raw = {
                        "choices": [{"message": {"content": full_content}}],
                        "usage": last_usage
                    }
                    hop = _timed_hop("1:reasoning", Model.REASONING.value, synthetic_raw, elapsed)
                    hops.append(hop)
                except Exception as exc:
                    log.exception("Error in Reasoning stage: %s", exc)
                    raise

            elif task_type == TaskType.CODING_SIMPLE:
                t0 = time.perf_counter()
                log.info("Starting simple coding response with %s...", Model.CODE.value)
                code_messages = [
                    {"role": "system", "content": CODE_SYSTEM_PROMPT},
                    *messages
                ]
                try:
                    full_content = ""
                    last_usage = {}
                    for i in range(MAX_CONTINUATION_LOOPS):
                        finish_reason = "stop"
                        loop_content = ""
                        async for chunk in client.stream_chat(
                            model=Model.CODE.value,
                            messages=code_messages,
                            temperature=0.2,
                            max_tokens=MAX_TOKENS,
                        ):
                            try:
                                choice = chunk.get("choices", [{}])[0]
                                if chunk.get("usage"):
                                    last_usage = chunk["usage"]
                                delta = choice.get("delta", {})
                                token = delta.get("content", "")
                                if token:
                                    loop_content += token
                                    full_content += token
                                    yield {"type": "token", "content": token}
                                if "finish_reason" in choice and choice["finish_reason"]:
                                    finish_reason = choice["finish_reason"]
                            except (KeyError, IndexError):
                                pass
                        if finish_reason == "length":
                            log.warning("Model.CODE hit max_tokens length in CODING_SIMPLE. Auto-continuing (loop %d)...", i+1)
                            code_messages.append({"role": "assistant", "content": loop_content})
                            code_messages.append({"role": "user", "content": "Continue exactly where you left off, from the very next character. Do not repeat anything, do not write intro text or markdown blocks, just the raw continuation."})
                        else:
                            break

                    elapsed = time.perf_counter() - t0
                    synthetic_raw = {
                        "choices": [{"message": {"content": full_content}}],
                        "usage": last_usage
                    }
                    hop = _timed_hop("1:coding_simple", Model.CODE.value, synthetic_raw, elapsed)
                    hops.append(hop)
                except Exception as exc:
                    log.exception("Error in Simple Coding stage: %s", exc)
                    raise

            elif task_type == TaskType.CODING_COMPLEX:
                raw_reasoning = ""
                raw_code = ""
                raw_review = ""

                # Stage 1: Deep reasoning
                if is_continuation:
                    raw_reasoning = "Continuation requested. Continuing from the previous truncated code."
                    hop1 = HopResult("1:reasoning", Model.REASONING.value, raw_reasoning, TokenUsage(), 0.0)
                    hops.append(hop1)
                else:
                    t0_reasoning = time.perf_counter()
                    yield {"type": "status", "content": "Stage 1 — Deep reasoning..."}
                    log.info("Starting reasoning stage with %s...", Model.REASONING.value)
                    last_yield_time = time.time()
                    try:
                        async for chunk in client.stream_chat(
                            model=Model.REASONING.value,
                            messages=messages,
                            temperature=0.6,
                            max_tokens=MAX_TOKENS,
                            extra_body={"include_reasoning": True}
                        ):
                            token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if token:
                                raw_reasoning += token
                            if time.time() - last_yield_time > 2.0:
                                yield {"type": "status", "content": "Deep reasoning..."}
                                last_yield_time = time.time()
                                
                        elapsed = time.perf_counter() - t0_reasoning
                        hop1 = _timed_hop("1:reasoning", Model.REASONING.value, {"content": raw_reasoning}, elapsed)
                        hop1.log_summary()
                        hops.append(hop1)
                    except Exception as exc:
                        log.exception("Error in Reasoning stage: %s", exc)
                        raise

                # Stage 2: Code generation — streamed live so the user sees output immediately
                t0_code = time.perf_counter()
                yield {"type": "status", "content": "Stage 2 — Writing code..."}
                log.info("Starting code generation with %s...", Model.CODE.value)

                code_sys_prompt = CODE_SYSTEM_PROMPT
                if is_continuation:
                    code_sys_prompt += (
                        "\n\nIMPORTANT: The previous code was truncated. Please continue writing the code exactly "
                        "from where it cut off in the previous turn. Do NOT rewrite the entire file from the beginning. "
                        "Start writing immediately from the next character/line, without introducing it, and do not wrap it "
                        "in new markdown code blocks unless you are continuing inside one."
                    )

                code_messages = [
                    {"role": "system", "content": code_sys_prompt},
                    *messages[:-1],
                    {"role": "user", "content": f"User Query: {user_query}\n\nArchitecture/Plan:\n{raw_reasoning[-MAX_STAGE_INPUT_CHARS:]}"}
                ]
                try:
                    async for chunk in client.stream_chat(
                        model=Model.CODE.value,
                        messages=code_messages,
                        temperature=0.2,
                        max_tokens=MAX_TOKENS,
                    ):
                        choice = chunk.get("choices", [{}])[0]
                        token = choice.get("delta", {}).get("content", "")
                        if token:
                            raw_code += token
                            yield {"type": "token", "content": token}
                        if chunk.get("keepalive"):
                            yield {"type": "status", "content": "Writing code..."}

                    elapsed = time.perf_counter() - t0_code
                    hop_code = _timed_hop("2:coding", Model.CODE.value, {"content": raw_code}, elapsed)
                    hop_code.log_summary()
                    hops.append(hop_code)
                except Exception as exc:
                    log.exception("Error in Coding stage: %s", exc)
                    raise

                # Clear Stage 2 draft from the UI before Stage 3 streams its reviewed version
                yield {"type": "clear"}

                # Stage 3: Code Review — streams the final, reviewed output
                t0_review = time.perf_counter()
                yield {"type": "status", "content": "Stage 3 — Reviewing and optimizing..."}
                log.info("Starting code review with %s...", Model.CODE_REVIEWER.value)
                
                reviewer_sys_prompt = CODE_REVIEWER_SYSTEM_PROMPT
                if is_continuation:
                    reviewer_sys_prompt += (
                        "\n\nIMPORTANT: The previous code was truncated. Please only review and output the final code continuation, "
                        "beginning exactly from where the previous code cut off. Do NOT rewrite the entire file from the beginning. "
                        "Start writing the code immediately from the next character/line without introductory text."
                    )
                
                review_messages = [
                    {"role": "system", "content": reviewer_sys_prompt},
                    *messages[:-1],
                    {"role": "user", "content": f"User Query: {user_query}\n\nDraft Code:\n{raw_code[-MAX_STAGE_INPUT_CHARS:]}"}
                ]
                try:
                    last_review_usage = {}
                    for i in range(MAX_CONTINUATION_LOOPS):
                        finish_reason = "stop"
                        loop_content = ""
                        async for chunk in client.stream_chat(
                            model=Model.CODE_REVIEWER.value,
                            messages=review_messages,
                            temperature=0.2,
                            max_tokens=MAX_TOKENS,
                        ):
                            try:
                                choice = chunk.get("choices", [{}])[0]
                                if chunk.get("usage"):
                                    last_review_usage = chunk["usage"]
                                delta = choice.get("delta", {})
                                token = delta.get("content", "")
                                if token:
                                    raw_review += token
                                    loop_content += token
                                    yield {"type": "token", "content": token}
                                    
                                if "finish_reason" in choice and choice["finish_reason"]:
                                    finish_reason = choice["finish_reason"]
                                    
                                if chunk.get("keepalive"):
                                    yield {"type": "status", "content": "Reviewing code..."}
                            except (KeyError, IndexError):
                                pass
                                
                        if finish_reason == "length":
                            log.warning("MiMo hit max_tokens length. Auto-continuing (loop %d)...", i+1)
                            review_messages.append({"role": "assistant", "content": loop_content})
                            review_messages.append({"role": "user", "content": "Continue exactly where you left off, from the very next character. Do not repeat anything, do not write intro text or markdown blocks, just the raw continuation."})
                        else:
                            break
                            
                    elapsed = time.perf_counter() - t0_review
                    synthetic_raw = {
                        "choices": [{"message": {"content": raw_review}}],
                        "usage": last_review_usage
                    }
                    hop_rev = _timed_hop("3:code_review", Model.CODE_REVIEWER.value, synthetic_raw, elapsed)
                    hop_rev.log_summary()
                    hops.append(hop_rev)
                except Exception as exc:
                    log.exception("Error in Code Review stage: %s", exc)
                    raise

        elif mode == "fast":
            yield {"type": "status", "content": "Fast mode enabled..."}
            t0 = time.perf_counter()
            messages = optimize_messages(history, user_query)
            
            full_content = ""
            last_fast_usage = {}
            
            for i in range(MAX_CONTINUATION_LOOPS):
                finish_reason = "stop"
                loop_content = ""
                async for chunk in client.stream_chat(
                    model=Model.MATH.value,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=MAX_TOKENS,
                ):
                    try:
                        choice = chunk.get("choices", [{}])[0]
                        if chunk.get("usage"):
                            last_fast_usage = chunk["usage"]
                        delta = choice.get("delta", {})
                        if "content" in delta and delta["content"]:
                            text = delta["content"]
                            loop_content += text
                            full_content += text
                            yield {"type": "token", "content": text}
                        if "finish_reason" in choice and choice["finish_reason"]:
                            finish_reason = choice["finish_reason"]
                    except (KeyError, IndexError):
                        pass
                        
                if finish_reason == "length":
                    log.warning("Fast mode hit max_tokens length. Auto-continuing (loop %d)...", i+1)
                    messages.append({"role": "assistant", "content": loop_content})
                    messages.append({"role": "user", "content": "Continue exactly where you left off, from the very next character. Do not repeat anything."})
                else:
                    break
                    
            elapsed = time.perf_counter() - t0
            synthetic_raw = {
                "choices": [{"message": {"content": full_content}}],
                "usage": last_fast_usage
            }
            hop = _timed_hop("1:fast", Model.MATH.value, synthetic_raw, elapsed)
            hop.content = full_content
            hops.append(hop)

    aggregate_usage = TokenUsage()
    for h in hops:
        aggregate_usage = aggregate_usage + h.usage

    log.info("Pipeline complete — aggregate tokens: [%s]", aggregate_usage)

async def chat_loop() -> None:
    print("\nIris AI  —  How can I help you today?")
    print("Type 'exit' to quit.\n")
    history: list[dict[str, str]] = []

    while True:
        try:
            user_input = (await asyncio.to_thread(input, "You: ")).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nIris AI: Goodbye!")
            break
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "bye"}:
            print("Iris AI: Goodbye!")
            break

        print("Iris AI: ", end="", flush=True)

        full_response = ""
        try:
            async for event in ask_stream(user_input, history=history or None, mode="smart"):
                if event["type"] == "token":
                    text = event["content"]
                    print(text, end="", flush=True)
                    full_response += text
                elif event["type"] == "status":
                    print(f"[{event['content']}]", end=" ", flush=True)
        except Exception:
            print("Something went wrong. Please try again.\n")
            continue

        print()
        history.append({"role": "user",      "content": user_input})
        history.append({"role": "assistant", "content": full_response})
        if len(history) > MAX_HISTORY_MESSAGES:
            history = history[-MAX_HISTORY_MESSAGES:]

if __name__ == "__main__":
    if len(sys.argv) > 1:
        single_query = " ".join(sys.argv[1:])
        async def _run() -> None:
            full_response = ""
            async for event in ask_stream(single_query, mode="smart"):
                if event["type"] == "token":
                    full_response += event["content"]
            print(f"\nIris AI: {full_response}\n")
        asyncio.run(_run())
    else:
        asyncio.run(chat_loop())
