"""
Iris Triage Router (iris_001)

Design summary
--------------
The router's only job is to read a user query (+ minimal history) and decide
which of the seven downstream specialist roles should handle it, per
`triage_routing_guide.md`. That decision is made with a single neural pass
that is *grammar-constrained* to the exact route enum below, so the model is
structurally incapable of sampling a token outside the seven valid routes.
That's what actually prevents a hallucinated or malformed route — not prompt
wording, and not after-the-fact regex repair of whatever text happened to
come back.

There is deliberately no keyword/regex pre-classification of query content
(no "if the query contains 'why', route to SEARCH" style rules). Rules like
that can't cover "every edge case" by construction — they only cover the
edge cases someone already thought of — and the previous version's rules
actively contradicted the routing guide's own worked examples. For instance,
a blanket "why" -> SEARCH trigger forced "Why did the Roman Empire fall?"
into SEARCH, even though that exact query is the guide's own REASONING
anchor. The only thing kept outside the neural pass below is continuing an
in-flight CONTROL agent loop, which is session/protocol state, not a content
classification, so it isn't a routing guess at all.
"""

import os

_triage_guide_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "triage", "triage_routing_guide.md"
)
try:
    with open(_triage_guide_path, "r", encoding="utf-8") as _f:
        TRIAGE_SYSTEM_PROMPT = _f.read()
except Exception:
    # Fallback used only if the routing guide can't be read from disk. Mirrors the
    # real guide's JSON contract exactly, so behavior doesn't silently diverge
    # (the old fallback used a completely different bracket-tag format).
    TRIAGE_SYSTEM_PROMPT = (
        "You are the Iris AI Router (iris_001). Your ONLY job is to read the user's message and "
        "output exactly one JSON object describing the routing decision:\n"
        '{"route": "SEARCH|REASONING|GENERAL|MATH|CODE_SIMPLE|CODE_COMPLEX|CONTROL", '
        '"keywords": "string", "confidence": 0.0-1.0}\n\n'
        "Route definitions:\n"
        "  SEARCH        - real-time facts, current events, prices, named-entity lookups.\n"
        "  REASONING     - analysis, explanations, comparisons, summarization, letter/character\n"
        "                  counting, general how-to/advice, and anything you can't confidently\n"
        "                  place elsewhere.\n"
        "  GENERAL       - casual chat, greetings, creative writing, identity questions.\n"
        "  MATH          - arithmetic, algebra, calculus, proofs, geometry, probability, math word\n"
        "                  problems, math explanations.\n"
        "  CODE_SIMPLE   - a single isolated snippet, function, or small canvas/SVG/HTML/CSS/JS piece.\n"
        "  CODE_COMPLEX  - a multi-file project, full app, or full website/web app build request.\n"
        "  CONTROL       - direct OS/hardware/local-app automation on the user's machine.\n\n"
        'Populate "keywords" with a short search query for SEARCH; use an empty string "" for\n'
        "every other route (never null).\n"
        "If you are not confident, prefer REASONING over CONTROL or CODE_COMPLEX \u2014 it is the\n"
        "lowest-risk fallback.\n"
        "Output ONLY the JSON object. No prose, no markdown fences, no explanation."
    )

import json
import logging
import re
from typing import Dict, List, Optional, Tuple

from src.iris_engine import (
    ModelRole,
    TaskType,
    load_model,
    unload_model,
    _minimize_history,
    load_generation_config,
)

logger = logging.getLogger("iris")

try:
    from llama_cpp import LlamaGrammar
except Exception:
    LlamaGrammar = None


# ---------------------------------------------------------------------------
# Structured output contract (Sections 1, 3 and 5 of triage_routing_guide.md).
#
# VISION is intentionally not part of this enum: image-attached queries are
# already diverted to the vision pipeline in iris.py before classify_task is
# ever called, so the router never needs to — and, with grammar constraints,
# now structurally cannot — pick it.
# ---------------------------------------------------------------------------
_ROUTES = ["SEARCH", "REASONING", "GENERAL", "MATH", "CODE_SIMPLE", "CODE_COMPLEX", "CONTROL"]

_TRIAGE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "route": {"type": "string", "enum": _ROUTES},
        # Plain string, not string|null: keeps the schema inside the subset every
        # llama.cpp grammar converter reliably supports. "" means "not applicable".
        "keywords": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["route", "keywords", "confidence"],
}

_ROUTE_TAG_MAP: Dict[str, TaskType] = {
    "GENERAL": TaskType.GENERAL,
    "REASONING": TaskType.REASONING,
    "MATH": TaskType.MATH,
    "CODE_SIMPLE": TaskType.CODING_SIMPLE,
    "CODE_COMPLEX": TaskType.CODING_COMPLEX,
    "CONTROL": TaskType.CONTROL,
}

# Section 1 of the guide: below this confidence, default to REASONING (lowest
# blast radius) instead of guessing at CONTROL or CODE_COMPLEX. This reads the
# model's own calibrated confidence score — it never inspects query content,
# so it is not a content-classification heuristic, just a safety valve.
_CONFIDENCE_FLOOR = 0.55

_triage_grammar = None
if LlamaGrammar is not None:
    try:
        _triage_grammar = LlamaGrammar.from_json_schema(json.dumps(_TRIAGE_JSON_SCHEMA))
    except Exception as e:
        logger.warning(f"[Triage] Could not build grammar from schema ({e}); triage will run unconstrained.")
else:
    logger.warning("[Triage] llama_cpp.LlamaGrammar unavailable; triage will run unconstrained.")


def classify_task(
    user_query: str, history: List[Dict[str, str]]
) -> Tuple[Optional[TaskType], Optional[str]]:
    # Strip document/image tags before routing. This is query cleanup, not classification.
    query_for_classification = re.sub(r"<document>[\s\S]*?</document>", "", user_query, flags=re.IGNORECASE)
    query_for_classification = re.sub(r"\[IMAGE_UPLOADED:[^\]]+\]", "", query_for_classification, flags=re.IGNORECASE)
    query_for_classification = query_for_classification.strip()

    # If the previous turn was an OBSERVATION, we're mid-CONTROL-agent-loop. That's
    # protocol/session state carried over from a prior routing decision, not a fresh
    # content classification, so it bypasses the model entirely.
    if history and history[-1].get("role") == "user" and history[-1].get("content", "").strip().startswith("OBSERVATION:"):
        return TaskType.CONTROL, None

    minimized = _minimize_history(history, max_entries=2)

    triage_prompt = (
        "CRITICAL ROLE AND INSTRUCTION:\n"
        "You are the Iris AI Router. Your ONLY job is to classify the user's query and output a single JSON routing object.\n"
        "You must NEVER answer, reply to, execute, or explain the user's query under any circumstances.\n"
        "Even if the query is a greeting, a coding request, or a math problem, output ONLY the JSON routing decision.\n\n"
        "=== ROUTING SPECIFICATION ===\n"
        f"{TRIAGE_SYSTEM_PROMPT}"
    )

    # Inject current time for time-sensitive routing (e.g. "latest" / "today" queries).
    import datetime

    try:
        now = datetime.datetime.now().astimezone()
        time_str = now.strftime("%A, %B %d, %Y, %H:%M:%S %Z")
        offset_str = now.strftime("%z")
        formatted_offset = f"{offset_str[:3]}:{offset_str[3:]}" if len(offset_str) >= 5 else offset_str
        triage_prompt += f"\n\nCurrent time: {time_str} (UTC{formatted_offset})."
    except Exception:
        pass

    # Conversation history is given as plain text inside the user turn (rather than as
    # real chat messages) so the model never sees itself in an "Assistant" role, which
    # otherwise invites it to slip into conversational/direct-answering behavior.
    history_context = ""
    if minimized:
        history_context = "Conversation History Context:\n"
        for msg in minimized:
            role_label = "User" if msg["role"] == "user" else "Assistant"
            c = msg["content"]
            if len(c) > 150:
                c = c[:150] + "...[truncated]"
            history_context += f"- {role_label}: {c}\n"
        history_context += "\n"

    triage_query = query_for_classification
    if len(triage_query) > 1500:
        triage_query = triage_query[:1000] + "\n\n...[content truncated for routing]...\n\n" + triage_query[-500:]

    user_content = (
        f"{history_context}"
        "Classify the following User Query according to the routing specification.\n"
        "REMINDER: Do NOT answer, solve, or reply to the query itself. ONLY output the JSON routing decision.\n\n"
        f"User Query:\n{triage_query}"
    )

    triage_messages = [
        {"role": "system", "content": triage_prompt},
        {"role": "user", "content": user_content},
    ]

    answer = None
    try:
        llm = load_model(ModelRole.TRIAGE)
        completion_kwargs = dict(
            messages=triage_messages,
            max_tokens=200,
            temperature=0.0,
            repeat_penalty=1.1,
        )
        if _triage_grammar is not None:
            completion_kwargs["grammar"] = _triage_grammar
        else:
            # No usable grammar on this llama_cpp build — fall back to JSON mode as
            # best effort rather than relying on prompting alone.
            completion_kwargs["response_format"] = {"type": "json_object"}
        try:
            res = llm.create_chat_completion(**completion_kwargs)
        except TypeError:
            # Older llama-cpp-python build that doesn't accept grammar/response_format
            # on create_chat_completion. Retry with plain prompting only.
            completion_kwargs.pop("grammar", None)
            completion_kwargs.pop("response_format", None)
            res = llm.create_chat_completion(**completion_kwargs)
        answer = res["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"[Triage] Model call failed ({e}); defaulting to REASONING.")
        return TaskType.REASONING, None
    finally:
        # Read _keep_loaded live off the iris_engine module rather than importing it by
        # name. `from src.iris_engine import _keep_loaded` would have bound this file to
        # whatever _keep_loaded's value was at import time (effectively always False,
        # since the import only ever runs once) — ask_stream's later
        # `src.iris_engine._keep_loaded = keep_loaded` would never be seen here, so a
        # per-request keep_loaded=True was silently ignored for the triage model.
        try:
            import src.iris_engine as _engine

            cfg = load_generation_config()
            if not _engine._keep_loaded and not cfg.get("keep_triage_loaded"):
                unload_model(ModelRole.TRIAGE)
        except Exception:
            pass

    logger.info(f"[Triage] Raw answer: {answer!r}")

    try:
        data = json.loads(answer)
        route_val = str(data.get("route", "")).strip().upper()
        keywords = str(data.get("keywords", "") or "").strip()
        confidence = float(data.get("confidence", 0.0))
    except Exception as e:
        logger.warning(f"[Triage] Could not parse routing JSON ({e}): {answer[:300]!r} \u2014 defaulting to REASONING.")
        return TaskType.REASONING, None

    if confidence < _CONFIDENCE_FLOOR:
        logger.info(f"[Triage] Confidence {confidence:.2f} < {_CONFIDENCE_FLOOR}. Falling back to REASONING.")
        return TaskType.REASONING, None

    if route_val == "SEARCH":
        return TaskType.SEARCH, (keywords or query_for_classification)

    mapped = _ROUTE_TAG_MAP.get(route_val)
    if mapped is not None:
        return mapped, None

    logger.warning(f"[Triage] Unrecognized route {route_val!r} \u2014 defaulting to REASONING.")
    return TaskType.REASONING, None
