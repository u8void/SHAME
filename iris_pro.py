from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator

import httpx
 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("iris_ai")

OCENZA_BASE_URL = "https://ocenza.com/v1"
SITE_URL: str       = os.getenv("OCENZA_SITE_URL", "https://iris-ai.app")
APP_TITLE: str      = os.getenv("OCENZA_APP_TITLE", "Iris AI")
REQUEST_TIMEOUT_S   = float(os.getenv("IRIS_REQUEST_TIMEOUT", "600"))

IRIS_IDENTITY = (
    "Your name is Iris AI. You are a powerful, multi-agent AI assistant built to handle "
    "software engineering, mathematics, deep reasoning, and general technical questions. "
    "Whenever someone asks who you are, what your name is, or what you do, you must identify "
    "yourself as Iris AI — never reveal the underlying models or pipeline architecture. "
    "If you generate code that includes an author or attribution header, ALWAYS use 'Iris AI (Iris Team)' as the author. Never use MiMo, Xiaomi, or any other underlying model names. "
    "CRITICAL: Do NOT introduce yourself or say 'I am Iris AI' at the start of your responses unless the user explicitly asked for your name."
)

class Model(str, Enum):
    ORCHESTRATOR  = "openai/gpt-oss-120b"
    CODE          = "openai/gpt-oss-120b"
    REASONING     = "openai/gpt-oss-120b"
    MATH          = "openai/gpt-oss-120b"
    CODE_REVIEWER = "qwen/qwen3-32b"

class TaskType(str, Enum):
    MATH      = "math"
    CODING    = "coding"
    REASONING = "reasoning"
    GENERAL   = "general"
    SEARCH    = "search"


TASK_TO_MODEL: dict[TaskType, Model] = {
    TaskType.MATH:      Model.MATH,
    TaskType.CODING:    Model.CODE,
    TaskType.REASONING: Model.REASONING,
    TaskType.GENERAL:   Model.ORCHESTRATOR,
    TaskType.SEARCH:    Model.ORCHESTRATOR,
}


@dataclass
class TokenUsage:
    prompt_tokens:     int = 0
    completion_tokens: int = 0
    total_tokens:      int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
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


ORCHESTRATOR_SYSTEM_PROMPT = (
    f"{IRIS_IDENTITY}\n\n"
    "You are also the Iris AI Orchestrator. Analyse the incoming query and classify it "
    "into exactly ONE of the following task types:\n\n"
    "  • math      — mathematical modelling, algorithm complexity, numerical optimisation, proofs.\n"
    "  • coding    — writing, refactoring, debugging, or reviewing source code; build/CI tooling.\n"
    "  • reasoning — architecture decisions, long-context analysis, logic design, system design.\n"
    "  • search    — questions requiring real-time facts, current events, or internet lookup.\n"
    "  • general   — anything that does not fit the above categories.\n\n"
    "Respond with a single minified JSON object — no markdown fences, no prose outside the JSON.\n"
    "Schema: {\"task_type\": \"<math|coding|reasoning|search|general>\", "
    "\"rationale\": \"<one sentence>\", \"subtasks\": [\"<optional>\"]}"
)

REVIEWER_SYSTEM_PROMPT = (
    f"{IRIS_IDENTITY}\n\n"
    "You are the Iris AI Verification Reviewer. A specialist has produced a draft answer. "
    "Your job is to verify correctness and completeness against the user's original query, "
    "fix any errors or omissions, and return a polished final response. "
    "Preserve all correct code blocks and mathematical notation. "
    "If the draft is already perfect, return it as-is. DO NOT prepend any quality notes, meta-commentary, or conversational filler. "
    "Always respond directly to the user as Iris AI — never expose model names, reviewer roles, or pipeline internals."
)

MATH_SYSTEM_PROMPT = (
    f"{IRIS_IDENTITY}\n\n"
    "You are the Iris AI Math & Algorithm Core. Solve mathematical modelling problems, "
    "derive algorithms, analyse complexity, and apply optimisation constraints rigorously. "
    "Use precise notation and show all significant derivation steps."
)

CODE_SYSTEM_PROMPT = (
    f"{IRIS_IDENTITY}\n\n"
    "You are the Iris AI Code Execution & Synthesis Specialist. Generate, refactor, debug, "
    "and document source code across all languages. Produce production-quality code with "
    "clean formatting and correct dependency management.\n"
    "CRITICAL INSTRUCTION: DO NOT INCLUDE ANY COMMENTS IN YOUR CODE. You must not type a single code comment."
)

CODE_REVIEWER_SYSTEM_PROMPT = (
    f"{IRIS_IDENTITY}\n\n"
    "You are the Iris AI Lead Engineering Reviewer, powered by a massive 120-billion parameter architecture. "
    "A specialist has produced a draft code answer. Your job is to review this code, heavily optimize its "
    "time and space complexity, enforce robust error handling, align it with the latest best practices, "
    "and rigorously fix any bugs or edge cases. "
    "Return the fully optimized and polished final code. DO NOT prepend any quality notes or conversational filler. "
    "Always respond directly to the user as Iris AI — never expose model names, reviewer roles, or pipeline internals.\n"
    "CRITICAL INSTRUCTION: DO NOT INCLUDE ANY COMMENTS IN YOUR CODE. You must not type a single code comment."
)

REASONING_SYSTEM_PROMPT = (
    f"{IRIS_IDENTITY}\n\n"
    "You are the Iris AI Context & Reasoning Specialist. Think step by step using deep "
    "chain-of-thought reasoning. Tackle long-context analysis, multi-turn architecture "
    "mapping, and complex logic design. Show your reasoning process before giving your final answer."
)

GENERAL_SYSTEM_PROMPT = (
    f"{IRIS_IDENTITY}\n\n"
    "You are the Iris AI General Assistant. Provide a helpful, direct, and conversational "
    "response to the user's query.\n"
    "CRITICAL INSTRUCTION: If you provide code, DO NOT INCLUDE ANY COMMENTS IN YOUR CODE. You must not type a single code comment."
)

SEARCH_SYSTEM_PROMPT = (
    f"{IRIS_IDENTITY}\n\n"
    "You are the Iris AI Web Research Specialist. You have been provided with real-time "
    "search results from the internet. Use these search results to answer the user's query "
    "accurately and comprehensively. Always cite your sources using the URLs provided."
)

SPECIALIST_SYSTEM_PROMPTS: dict[TaskType, str] = {
    TaskType.MATH:      MATH_SYSTEM_PROMPT,
    TaskType.CODING:    CODE_SYSTEM_PROMPT,
    TaskType.REASONING: REASONING_SYSTEM_PROMPT,
    TaskType.GENERAL:   GENERAL_SYSTEM_PROMPT,
    TaskType.SEARCH:    SEARCH_SYSTEM_PROMPT,
}


class OpenRouterClient:
    def __init__(self) -> None:
        self.groq_key = os.getenv("GROQ_API_KEY", "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")
        self.ocenza_keys = [
            os.getenv("OCENZA_API_KEY", "sk-1a60c1662ca7202c76f0a32586d7305e38f6db0f5f6b32ab97672ffb7ae63272"),
            "sk-b851622346e9702ee7cc2a17df2312f0205bb38961c9ba527cbf8a3dbd28c076",
            "sk-87a1227bbf6a3851415769fe43ac4bc90484553798c321702ee747133fd87905"
        ]
        self.current_ocenza_idx = 0

        if not self.ocenza_keys[0] or not self.groq_key:
            raise ValueError("API keys for both Groq and Ocenza must be set.")

        self._groq_client = httpx.AsyncClient(
            base_url="https://api.groq.com/openai/v1",
            headers={"Authorization": f"Bearer {self.groq_key}", "Content-Type": "application/json"},
            timeout=httpx.Timeout(REQUEST_TIMEOUT_S, connect=10.0),
        )
        self._ocenza_client = httpx.AsyncClient(
            base_url="https://ocenza.com/v1",
            timeout=httpx.Timeout(REQUEST_TIMEOUT_S, connect=10.0),
        )

    async def chat(
        self,
        *,
        model:           str,
        messages:        list[dict[str, str]],
        temperature:     float                  = 0.2,
        max_tokens:      int                    = 4096,
        response_format: dict[str, str] | None  = None,
        extra_body:      dict[str, Any] | None  = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model":       model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format
        if extra_body:
            payload.update(extra_body)

        max_retries = 6
        base_wait = 3.0
        
        # Switch provider based on model
        if model in ("qwen/qwen3-32b", "llama-3.3-70b-versatile", "openai/gpt-oss-120b"):
            client = self._groq_client
            api_name = "Groq"
        else:
            client = self._ocenza_client
            api_name = "Ocenza"
        
        for attempt in range(max_retries):
            kwargs: dict[str, Any] = {"json": payload}
            if api_name == "Ocenza":
                current_key = self.ocenza_keys[self.current_ocenza_idx]
                kwargs["headers"] = {"Authorization": f"Bearer {current_key}", "Content-Type": "application/json"}
                
            response = await client.post("/chat/completions", **kwargs)
            
            if response.status_code in (429, 413) or response.status_code >= 500 or response.status_code in (401, 402):
                if api_name == "Ocenza":
                    self.current_ocenza_idx = (self.current_ocenza_idx + 1) % len(self.ocenza_keys)
                    log.warning("Ocenza API error %d. Rotating to fallback API key...", response.status_code)
                
                if attempt < max_retries - 1:
                    wait_s = base_wait * (2 ** attempt)
                    log.warning("%s HTTP %d hit. Retrying in %.1fs (attempt %d/%d)...", api_name, response.status_code, wait_s, attempt + 1, max_retries)
                    import asyncio
                    await asyncio.sleep(wait_s)
                    continue
                else:
                    raise RuntimeError(
                        f"{api_name} API is currently heavily overloaded or down. "
                        "Please try again in a few minutes."
                    )
            response.raise_for_status()
            return response.json()

    async def stream_chat(
        self,
        *,
        model:           str,
        messages:        list[dict[str, str]],
        temperature:     float                  = 0.2,
        max_tokens:      int                    = 4096,
        response_format: dict[str, str] | None  = None,
        extra_body:      dict[str, Any] | None  = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        payload: dict[str, Any] = {
            "model":       model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
            "stream":      True,
        }
        if response_format:
            payload["response_format"] = response_format
        if extra_body:
            payload.update(extra_body)

        max_retries = 6
        base_wait = 3.0
        
        # Switch provider based on model
        if model in ("qwen/qwen3-32b", "llama-3.3-70b-versatile", "openai/gpt-oss-120b"):
            client = self._groq_client
            api_name = "Groq"
        else:
            client = self._ocenza_client
            api_name = "Ocenza"
        
        for attempt in range(max_retries):
            kwargs: dict[str, Any] = {"json": payload}
            if api_name == "Ocenza":
                current_key = self.ocenza_keys[self.current_ocenza_idx]
                kwargs["headers"] = {"Authorization": f"Bearer {current_key}", "Content-Type": "application/json"}
                
            try:
                async with client.stream("POST", "/chat/completions", **kwargs) as response:
                    if response.status_code in (429, 413) or response.status_code >= 500 or response.status_code in (401, 402):
                        if api_name == "Ocenza":
                            self.current_ocenza_idx = (self.current_ocenza_idx + 1) % len(self.ocenza_keys)
                            log.warning("Ocenza API error %d. Rotating to fallback API key...", response.status_code)
                        
                        if attempt < max_retries - 1:
                            wait_s = base_wait * (2 ** attempt)
                            log.warning("%s HTTP %d hit. Retrying in %.1fs (attempt %d/%d)...", api_name, response.status_code, wait_s, attempt + 1, max_retries)
                            await asyncio.sleep(wait_s)
                            continue
                        else:
                            raise RuntimeError(
                                f"{api_name} API is currently heavily overloaded or down. "
                                "Please try again in a few minutes."
                            )
                    
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            if not data_str:
                                continue
                            try:
                                yield json.loads(data_str)
                            except json.JSONDecodeError:
                                pass
                    return  # Success
            except httpx.RequestError as exc:
                if attempt < max_retries - 1:
                    wait_s = base_wait * (2 ** attempt)
                    log.warning("%s HTTP RequestError hit. Retrying in %.1fs (attempt %d/%d)...", api_name, wait_s, attempt + 1, max_retries)
                    await asyncio.sleep(wait_s)
                    continue
                raise exc

    async def aclose(self) -> None:
        await self._groq_client.aclose()
        await self._ocenza_client.aclose()

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
        max_tokens=2048,
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
    if len(truncated_reasoning) > 150000:
        log.warning("Truncating reasoning_output from %d to 150000 chars.", len(truncated_reasoning))
        truncated_reasoning = truncated_reasoning[:150000] + "\n...[truncated for length]"

    messages = [
        {"role": "system", "content": talk_prompt},
        {"role": "user", "content": f"User Query: {user_query}\n\nInternal Reasoning:\n{truncated_reasoning}"}
    ]

    t0 = time.perf_counter()
    
    full_content = ""
    last_raw = None
    
    for i in range(5):
        raw = await client.chat(
            model=Model.ORCHESTRATOR.value,
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
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
    if last_raw:
        last_raw["choices"][0]["message"]["content"] = full_content
        
    hop = _timed_hop("2:talking", Model.ORCHESTRATOR.value, last_raw, elapsed)
    hop.log_summary()
    return hop.content, hop


def _handle_http_error(stage: str, exc: httpx.HTTPStatusError) -> None:
    status = exc.response.status_code
    body   = exc.response.text[:500]
    log.error("%s — HTTP %d\n%s", stage, status, body)
    if status == 401:
        log.error("Authentication failed. Check OCENZA_API_KEY.")
    elif status == 429:
        log.error("Rate limit hit. Add exponential back-off retry logic.")
    elif status == 402:
        log.error("Insufficient credits on Ocenza account.")
    elif status >= 500:
        log.error("Ocenza server error — likely transient, retry shortly.")



async def ask_stream(
    user_query: str,
    history:    list[dict[str, str]] | None = None,
    mode:       str = "smart"
) -> AsyncGenerator[dict[str, Any], None]:
    hops: list[HopResult] = []
    
    async with OpenRouterClient() as client:
        if mode == "smart":
            messages = []
            if history:
                messages.extend(history)
            messages.append({"role": "user", "content": user_query})

            # Stage 0: Triage
            yield {"type": "status", "content": "Analyzing query complexity..."}
            triage_prompt = (
                f"{IRIS_IDENTITY}\n\n"
                "You are the Iris AI query router.\n"
                "If the user's query is a simple greeting (e.g. 'hello', 'hi') or a basic conversational remark, answer it directly.\n"
                "HOWEVER, if the query involves ANY coding, programming, mathematics, logic, or requires generating more than a few sentences, YOU MUST OUTPUT EXACTLY 'NEEDS_REASONING' as your VERY FIRST AND ONLY text. Do not explain or output anything else."
            )
            triage_messages = [
                {"role": "system", "content": triage_prompt},
                *messages
            ]

            t0_triage = time.perf_counter()
            buffer = ""
            is_simple = False
            is_reasoning = False
            
            try:
                async for chunk in client.stream_chat(
                    model=Model.ORCHESTRATOR.value,
                    messages=triage_messages,
                    temperature=0.3,
                    max_tokens=2048,
                ):
                    try:
                        choice = chunk.get("choices", [{}])[0]
                        delta = choice.get("delta", {})
                        if "content" in delta and delta["content"]:
                            text = delta["content"]
                        else:
                            text = ""
                    except Exception:
                        text = ""
                    
                    if not text:
                        continue
                        
                    buffer += text
                    
                    if not is_simple and not is_reasoning:
                        if "NEEDS_REASONING" in buffer:
                            is_reasoning = True
                            break
                        elif len(buffer) > 20 and "NEEDS_REASONING" not in buffer:
                            is_simple = True
                            yield {"type": "token", "content": buffer}
                    elif is_simple:
                        yield {"type": "token", "content": text}
            except Exception as exc:
                log.exception("Unexpected error in Triage stage: %s", exc)
                is_reasoning = True

            if not is_reasoning and not is_simple:
                if "NEEDS_REASONING" not in buffer:
                    yield {"type": "token", "content": buffer}
                    is_simple = True
                    
            if is_simple:
                elapsed = time.perf_counter() - t0_triage
                hop = _timed_hop("0:triage_answer", Model.ORCHESTRATOR.value, {}, elapsed)
                hop.content = buffer
                hops.append(hop)
                return
            
            # Smart mode: Reasoning -> Talking
            yield {"type": "status", "content": "Stage 1 — Reasoning model thinking..."}
            
            t0 = time.perf_counter()
            full_rc = ""
            full_c = ""
            
            try:
                # We don't stream the reasoning output to the user in smart mode (orchestrator handles it)
                raw = await client.chat(
                    model=Model.REASONING.value,
                    messages=messages,
                    temperature=0.6,
                    max_tokens=2048,
                    extra_body={"include_reasoning": True}
                )
                elapsed = time.perf_counter() - t0
                hop1 = _timed_hop("1:reasoning", Model.REASONING.value, raw, elapsed)
                hop1.log_summary()
                hops.append(hop1)
                
                reasoning_output = _extract_reasoning_content(raw)
                
            except httpx.HTTPStatusError as exc:
                _handle_http_error("Reasoning", exc)
                raise
            except httpx.TimeoutException as exc:
                log.error("Reasoning stage timed out after %d seconds.", REQUEST_TIMEOUT_S)
                raise
            except Exception as exc:
                log.exception("Unexpected error in Reasoning stage: %s", exc)
                raise

            yield {"type": "status", "content": "Stage 2 — Orchestrator formulating final response..."}
            
            raw_content = _extract_content(raw)
            import re
            draft_answer = re.sub(r"<think>[\s\S]*?</think>", "", raw_content).strip()
            
            if len(reasoning_output) > 8000:
                truncated_reasoning = "...\n" + reasoning_output[-8000:]
            else:
                truncated_reasoning = reasoning_output

            talk_prompt = (
                f"{IRIS_IDENTITY}\n\n"
                "You are the Iris AI Orchestrator. You have been provided with the user's query, "
                "the conclusion of the internal deep-thinking engine, and its draft answer. "
                "Your task is to synthesize this and present the final answer to the user "
                "in a clear, professional, and beautifully-formatted manner. "
                "CRITICAL INSTRUCTION: If the user asks for code, or the draft contains code, you MUST output the complete, full code without ANY truncation, abbreviation, or placeholders.\n"
                "CRITICAL INSTRUCTION: DO NOT INCLUDE ANY COMMENTS IN YOUR CODE. You must not type a single code comment.\n"
                "DO NOT expose `<thinking>` tags or mention the internal reasoning engine."
            )

            talk_messages = [
                {"role": "system", "content": talk_prompt},
                {"role": "user", "content": f"User Query: {user_query}\n\nReasoning Conclusion:\n{truncated_reasoning}\n\nDraft Answer:\n{draft_answer}"}
            ]
            
            t0 = time.perf_counter()
            full_content = ""
            
            for i in range(5):
                finish_reason = "stop"
                loop_content = ""
                async for chunk in client.stream_chat(
                    model=Model.ORCHESTRATOR.value,
                    messages=talk_messages,
                    temperature=0.3,
                    max_tokens=2048,
                ):
                    try:
                        choice = chunk.get("choices", [{}])[0]
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
                    log.warning("Orchestrator hit max_tokens length. Auto-continuing (loop %d)...", i+1)
                    talk_messages.append({"role": "assistant", "content": loop_content})
                    talk_messages.append({"role": "user", "content": "Continue exactly where you left off, from the very next character. Do not repeat anything, do not write intro text or markdown blocks, just the raw continuation."})
                else:
                    break
            
            elapsed = time.perf_counter() - t0
            hop2 = _timed_hop("2:talking", Model.ORCHESTRATOR.value, {}, elapsed)
            hop2.content = full_content
            hop2.log_summary()
            hops.append(hop2)

        elif mode == "fast":
            yield {"type": "status", "content": "Fast mode enabled..."}
            t0 = time.perf_counter()
            messages = history or []
            messages.append({"role": "user", "content": user_query})
            
            full_content = ""
            
            for i in range(5):
                finish_reason = "stop"
                loop_content = ""
                async for chunk in client.stream_chat(
                    model=Model.MATH.value,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=2048,
                ):
                    try:
                        choice = chunk.get("choices", [{}])[0]
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
            hop = _timed_hop("1:fast", Model.MATH.value, {}, elapsed)
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
            user_input = input("You: ").strip()
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
        if len(history) > 40:
            history = history[-40:]

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
