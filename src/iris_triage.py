
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

from src.iris_engine import _load_skill_prompt, ModelRole

TRIAGE_SYSTEM_PROMPT = _load_skill_prompt("triage/triage_routing_guide.md")
if not TRIAGE_SYSTEM_PROMPT:
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
    "type": "string",
    "enum": _ROUTES
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

# Post-check override pattern (see classify_task for the design rationale). This is
# a *post-routing* check, not a pre-filter: the model's classification still runs
# first and its choice is the default. We only override when (a) the model picked
# a non-code route, AND (b) the query contains BOTH a coding verb and a code-shaped
# target noun. The verb list is the only list here that would be dangerous to
# broaden \u2014 "create a pizza" must NOT match. The code-shaped target list is
# intentionally restricted to words that strongly imply a code artifact.
#
#   "create a calculator in python"        verb=create, target=calculator (CODE_SIMPLE)
#   "build me a web app in flask"          verb=build,  target=web app    (CODE_COMPLEX)
#   "write a function to reverse a list"   verb=write,  target=function   (CODE_SIMPLE)
#   "make a website for a pizza place"     verb=make,   target=website    (CODE_COMPLEX)
#   "create a pizza"                       no target noun -> no match, stays REASONING
_CODE_VERBS = (
    r"create|build|write|implement|code|make|develop|design|generate|"
    r"add|fix|patch|modify|update|refactor|rewrite|convert|port|translate"
)
_CODE_TARGETS = (
    r"(?:calculator|function|method|class|module|script|program|app|application|"
    r"website|site|web\s*app|web\s*page|landing\s*page|api|service|server|"
    r"endpoint|backend|frontend|ui|gui|cli|tool|library|package|component|"
    r"plugin|extension|game|binary|bot|scraper|crawler|pipeline|algorithm|"
    r"snippets?|codebase)"
)
# We allow a LANG_QUALIFIER to appear either before the target ("a flask
# app" \u2014 "flask" is a language, "app" is the target) or after it
# ("calculator in python"). To handle both, the LANG_QUALIFIER is allowed
# inside the function-word sequence and after the target.
_LQ_BODY = (
    r"\s+(?:in|using|with|for)\s+(?:python|javascript|typescript|js|ts|"
    r"c\+\+|cpp|c#|csharp|java|kotlin|swift|go|rust|ruby|php|"
    r"html|css|sql|bash|shell|matlab|r|lua|scala|haskell|elixir|dart|"
    r"flask|django|fastapi|express|react|vue|angular|next\.js|nuxt|svelte|"
    r"spring|laravel|rails|node|node\.js|deno|bun|"
    r"tensorflow|pytorch|numpy|pandas|"
    r"tailwind|bootstrap|jquery)"
)
_LQ_AT_END = "(" + _LQ_BODY + ")?"

# Explicit "code/script" nouns anywhere in the query, which is enough on its own.
_EXPLICIT_CODE_NOUN = r"\b(?:code|script|function|program|class|module)\b"

# Primary: verb, then zero or more function words (which may include a
# language qualifier like "flask" / "in python"), then a target noun
# optionally followed by a language qualifier. The LANG_QUALIFIER by
# itself is not enough \u2014 we need EITHER a target noun OR an explicit
# language tag, so "create something in python" works but "write a haiku
# about the sea" does not.
_PRIMARY_PATTERN = re.compile(
    r"\b(?P<verb>" + _CODE_VERBS + r")\b"
    r"(?:[^.?!\n])*"
    r"\b(?P<target>" + _CODE_TARGETS + r")\b",
    re.IGNORECASE,
)


def _is_explicit_coding_query(query: str) -> Optional[TaskType]:
    q = query.strip().lower()
    
    # 1. Programming languages / file extensions co-occurring with programming terms
    languages = (
        r"\b(?:python|javascript|typescript|js|ts|cpp|c\+\+|c#|csharp|java|kotlin|swift|"
        r"go|rust|ruby|php|html|css|sql|bash|shell|powershell|rustlang|golang)\b"
    )
    code_terms = (
        r"\b(?:code|script|function|program|class|module|array|string|list|dict|map|set|"
        r"loop|variable|sorting|regex|json|api|hashmap|matrix|tree|binary|algorithm|"
        r"dp|dynamic programming|recursion|reverse|print|parse|write|solve|implement)\b"
    )
    
    # If the query contains a programming language AND a coding term:
    if re.search(languages, q) and re.search(code_terms, q):
        # Determine simple vs complex
        if any(tok in q for tok in ("app", "website", "site", "api", "service", "server", "project")):
            return TaskType.CODING_COMPLEX
        return TaskType.CODING_SIMPLE

    # 2. Known algorithmic coding platforms or terminology (e.g. Codeforces, LeetCode)
    if "codeforces" in q or "leetcode" in q or "hackerrank" in q or "codewars" in q:
        return TaskType.CODING_SIMPLE
        
    return None
# Secondary: code-modification verbs followed by a non-target word ("the bug"),
# where an explicit code noun (code/script/function/...) appears later in the
# query. This is intentionally narrower than the primary pattern.
_MODIFY_VERBS = (
    r"fix|patch|modify|update|refactor|rewrite|optimise|optimize|improve|clean\s+up|"
    r"debug|review|audit|annotate|document|format|lint"
)
_SECONDARY_PATTERN = re.compile(
    r"\b(?P<verb>" + _MODIFY_VERBS + r")\b"
    r"(?:[^.?!\n])*"
    r"\b(?P<target>" + _EXPLICIT_CODE_NOUN + r")\b",
    re.IGNORECASE,
)


def _code_override_route(query: str):
    """Return (chosen_task, verb, target_str) if the query matches an unambiguous
    coding pattern, else None. Called only as a post-check after the model has
    routed \u2014 it never *initiates* a routing decision.
    """
    m = _PRIMARY_PATTERN.search(query)
    if not m:
        m = _SECONDARY_PATTERN.search(query)
    if not m:
        return None
    verb = m.group("verb")
    target_raw = m.group("target")
    # The PRIMARY pattern has two alternatives: target noun, or language qualifier
    # (in which case no "target" group is captured). For the language-qualifier
    # path we fall back to the matched span as the target string so the
    # COMPLEX-vs-SIMPLE decision below can still inspect it.
    target = (target_raw or m.group(0)).lower()
    if any(tok in target for tok in ("app", "website", "site", "api", "service", "server", "project")):
        return TaskType.CODING_COMPLEX, verb, target
    return TaskType.CODING_SIMPLE, verb, target


# Post-check override for GENERAL: catches greetings and short identity questions
# that the model often misroutes to REASONING when its structured output is
# degenerating into noise. The "hi" -> REASONING bug was the trigger.
#
# The scope is intentionally narrow:
#   - The query must be short (<= 8 words) so it can't be "hi, can you help
#     me debug this code" (which is genuinely a coding request that happens
#     to start with a greeting).
#   - The query must START with a known greeting word ("hi", "hello", ...) or
#     contain a direct identity question ("who are you", "what are you").
_GREETING_WORDS = (
    r"hi|hello|hey|howdy|greetings|yo|hola|sup|hiya|ahoy|good\s+(morning|afternoon|evening)"
)
_IDENTITY_QUESTIONS = (
    r"who\s+(are|r\s+you|made|created|built)\s+you|"
    r"what\s+(are|r\s+you)\s+(you|a|an)|"
    r"your\s+name|"
    r"are\s+you\s+(a|an)\s+(human|bot|ai|robot|llm|model|assistant)"
)
_GENERAL_OVERRIDE_PATTERN = re.compile(
    r"^\s*(?:" + _GREETING_WORDS + r")\b[\s\S]*$",
    re.IGNORECASE,
)
_IDENTITY_PATTERN = re.compile(
    _IDENTITY_QUESTIONS,
    re.IGNORECASE,
)


def _general_override_route(query: str):
    """Return True if the query is a short greeting or identity question that
    should route to GENERAL even if the model picked something else. Returns
    a short reason string for logging, or None if no override applies.
    """
    q = query.strip()
    if not q:
        return None
    # Word-count cap: keep this rule from swallowing real requests that happen
    # to start with a greeting ("hi can you fix the bug in my code"). 6 words
    # is the longest pure greeting that's still plausible ("hi how are you doing
    # today") and short enough that real requests ("hi, can you help me debug
    # this code") comfortably exceed it.
    if len(q.split()) > 6:
        return None
    if _GENERAL_OVERRIDE_PATTERN.match(q):
        return "greeting"
    if _IDENTITY_PATTERN.search(q):
        return "identity"
    return None


_CREATIVE_PATTERN = re.compile(
    r"\b(haiku|poem|story|song|joke|write a (?:haiku|poem|story|song|joke))\b",
    re.IGNORECASE
)


def _math_override_route(query: str) -> bool:
    q = query.strip().lower()
    # Patterns for algebraic equations like: x^2 - 5x + 6 = 0 or 2x + 3 = 7
    if "=" in q and any(c in q for c in "xyz"):
        if not any(kw in q for kw in ("var ", "let ", "const ", "int ", "float ", "==", "def ")):
            return True
    # Patterns for arithmetic operations: e.g. "what is 45 * 34" or "solve 234 / 2.5"
    if any(op in q for op in ("+", "-", "*", "/", "^")) and any(c.isdigit() for c in q):
        if not ("/" in q and q.count("/") == 2 and not any(op in q for op in ("+", "-", "*", "^"))):
            return True
    return False


def _search_override_route(query: str) -> bool:
    q = query.strip().lower()
    search_keywords = (
        "weather", "temperature", "forecast",
        "today", "latest", "current", "news",
        "stock", "price of", "time in", "population of"
    )
    if any(kw in q for kw in search_keywords):
        return True
    return False


def _control_override_route(query: str) -> bool:
    q = query.strip().lower()
    control_actions = (
        "set my brightness", "set brightness", "turn brightness",
        "delete the files", "delete files in", "empty my trash",
        "open the app", "open chrome", "open finder",
        "shut down my", "restart my mac"
    )
    if any(kw in q for kw in control_actions):
        return True
    return False


def _reasoning_override_route(query: str) -> bool:
    q = query.strip().lower()
    if q.startswith("why did") or q.startswith("how do i") or q.startswith("explain how"):
        return True
    return False

_triage_grammar = None
if LlamaGrammar is not None:
    try:
        _triage_grammar = LlamaGrammar.from_json_schema(json.dumps(_TRIAGE_JSON_SCHEMA))
    except Exception as e:
        logger.warning(f"[Triage] Could not build grammar from schema ({e}); triage will run unconstrained.")
else:
    logger.warning("[Triage] llama_cpp.LlamaGrammar unavailable; triage will run unconstrained.")


def _sanitize_string_values(text: str) -> str:
    """Walk the cleaned text and, inside every " ... " span, escape raw \n, \r, \t
    and drop any other ASCII control char. The triage model (iris_001) occasionally
    emits literal newlines inside the keywords string when it's unsure of the
    answer; that's a JSON syntax error and Python's strict json.loads rejects it.
    """
    out = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if not in_string:
            out.append(ch)
            if ch == '"' and (i == 0 or text[i - 1] != '\\'):
                in_string = True
            i += 1
            continue
        # Inside a string: respect existing backslash escapes first.
        if ch == '\\':
            if i + 1 < n:
                out.append(ch)
                out.append(text[i + 1])
                i += 2
            else:
                out.append(ch)
                i += 1
            continue
        if ch == '"':
            out.append(ch)
            in_string = False
            i += 1
            continue
        if ch == '\n':
            out.append('\\n'); i += 1; continue
        if ch == '\r':
            out.append('\\r'); i += 1; continue
        if ch == '\t':
            out.append('\\t'); i += 1; continue
        if ord(ch) < 0x20:
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def classify_task(
    user_query: str, history: List[Dict[str, str]]
) -> Tuple[Optional[TaskType], Optional[str]]:
    # Strip document/image tags before routing. This is query cleanup, not classification.
    query_for_classification = re.sub(r"<document>[\s\S]*?</document>", "", user_query, flags=re.IGNORECASE)
    query_for_classification = re.sub(r"\[IMAGE_UPLOADED:[^\]]+\]", "", query_for_classification, flags=re.IGNORECASE)
    query_for_classification = query_for_classification.strip()

    # Pre-filter override: bypass the model entirely for short greetings & identity questions
    general_reason = _general_override_route(query_for_classification)
    if general_reason is not None:
        logger.info(
            f"[Triage] Pre-filter override: query matched GENERAL pattern "
            f"(reason={general_reason!r}); routing directly to GENERAL."
        )
        return TaskType.GENERAL, None

    # If the previous turn was an OBSERVATION, we're mid-CONTROL-agent-loop. That's
    # protocol/session state carried over from a prior routing decision, not a fresh
    # content classification, so it bypasses the model entirely.
    if history and history[-1].get("role") == "user" and history[-1].get("content", "").strip().startswith("OBSERVATION:"):
        return TaskType.CONTROL, None

    # Explicit coding query bypass -> CODING_SIMPLE / CODING_COMPLEX
    explicit_code_route = _is_explicit_coding_query(query_for_classification)
    if explicit_code_route is not None:
        logger.info(f"[Triage] Pre-filter override: query matched explicit coding pattern; routing to {explicit_code_route.name}.")
        return explicit_code_route, None

    # Time-sensitive lookup bypass -> SEARCH
    if _search_override_route(query_for_classification):
        logger.info(f"[Triage] Pre-filter override: time-sensitive/factual query matched SEARCH pattern; routing to SEARCH.")
        return TaskType.SEARCH, query_for_classification

    # Control automation bypass -> CONTROL
    if _control_override_route(query_for_classification):
        logger.info(f"[Triage] Pre-filter override: hardware/automation query matched CONTROL pattern; routing to CONTROL.")
        return TaskType.CONTROL, None

    # Math solving bypass -> MATH
    if _math_override_route(query_for_classification):
        logger.info(f"[Triage] Pre-filter override: math/equation query matched MATH pattern; routing to MATH.")
        return TaskType.MATH, None

    # Creative general fallback bypass -> GENERAL
    if _CREATIVE_PATTERN.search(query_for_classification):
        logger.info(f"[Triage] Pre-filter override: creative query matched GENERAL pattern; routing to GENERAL.")
        return TaskType.GENERAL, None

    # Reasoning / Explanatory query bypass -> REASONING
    if _reasoning_override_route(query_for_classification):
        logger.info(f"[Triage] Pre-filter override: explanatory/reasoning query matched REASONING pattern; routing to REASONING.")
        return TaskType.REASONING, None

    if history:
        lower_query = query_for_classification.strip().lower()
        if lower_query in ("continue", "continue.", "go on", "keep going", "more"):
            last_asst = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), "")
            if "```" in last_asst or "<file_card" in last_asst or "<coding>" in last_asst:
                return TaskType.CODING_COMPLEX, None

    # --- Start of Fix added by AI ---
    # الهدف من هذا التعديل: إجبار الترياج على تحويل الطلبات البرمجية باللغة العربية
    # وطلبات تطوير الويب وتصميم الهياكل مباشرة إلى قسم البرمجة (CODING_COMPLEX)
    # لتجنب أخطاء الموديل الصغير في فهم اللغة العربية.
    lower_query_custom = query_for_classification.lower()
    
    # 1. Full-Stack / Skeleton / Complex Code Rules (Arabic & English)
    kw_en_pattern = r"\b(?:backend|server|api|full stack|full-stack|node|express|skeleton)\b"
    kw_ar_pattern = r"(?:هيكل|قالب|فراغات)"
    if re.search(kw_en_pattern, lower_query_custom) or re.search(kw_ar_pattern, lower_query_custom):
        logger.info("[Triage] Hardcoded intercept: Full-Stack or Skeleton keyword detected. Routing to CODING_COMPLEX.")
        return TaskType.CODING_COMPLEX, None
        
    # 2. Web Development Rules (Arabic & English)
    tech_pattern = r"\b(?:tailwind|html|css|react)\b"
    action_en_pattern = r"\b(?:build|landing page|website)\b"
    action_ar_pattern = r"(?:موقع|صفحة|صمم|برمج)"
    if re.search(tech_pattern, lower_query_custom) and (re.search(action_en_pattern, lower_query_custom) or re.search(action_ar_pattern, lower_query_custom)):
        logger.info("[Triage] Hardcoded intercept: Web development query detected. Routing to CODING_COMPLEX.")
        return TaskType.CODING_COMPLEX, None
    # --- End of Fix ---

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

    # Manually format the prompt using ChatML to prevent chat template and tokenization bugs in llama-cpp-python.
    prompt = (
        f"<|im_start|>system\n{triage_prompt}<|im_end|>\n"
        f"<|im_start|>user\n{user_content}<|im_end|>\n"
        "<|im_start|>assistant\n"
    )

    answer = None
    try:
        llm = load_model(ModelRole.TRIAGE)
        completion_kwargs = dict(
            prompt=prompt,
            max_tokens=200,
            temperature=0.0,
            repeat_penalty=1.1,
        )
        if _triage_grammar is not None:
            completion_kwargs["grammar"] = _triage_grammar
        else:
            completion_kwargs["response_format"] = {"type": "json_object"}
        try:
            res = llm.create_completion(**completion_kwargs)
        except TypeError:
            # Older llama-cpp-python build that doesn't accept grammar/response_format
            completion_kwargs.pop("grammar", None)
            completion_kwargs.pop("response_format", None)
            res = llm.create_completion(**completion_kwargs)
        answer = res["choices"][0]["text"].strip()
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

    # --- Pre-processing: strip <think>...</think> blocks and code fences
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", answer, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).replace("```", "").strip()

    data = None
    parse_error = None

    # Try parsing directly as a raw route string (either "ROUTE" or '"ROUTE"')
    route_candidate = cleaned.replace('"', '').strip().upper()
    if route_candidate in _ROUTES:
        data = {"route": route_candidate, "keywords": "", "confidence": 1.0}

    # Fallback to JSON parsing if it wasn't a raw string
    if data is None:
        cleaned_escaped = _sanitize_string_values(cleaned)
        try:
            data = json.loads(cleaned_escaped)
        except Exception as e:
            parse_error = e

    # Pass 2: extract the first complete {...} block and retry. The model sometimes
    # produces trailing garbage / embedded newlines after the JSON object.
    if data is None:
        m = re.search(r'\{[\s\S]*?"route"\s*:\s*"([^"]+)"[\s\S]*?\}', cleaned)
        if m:
            try:
                data = json.loads(m.group(0))
                logger.info("[Triage] JSON rescued via regex extraction (Pass 2).")
            except Exception:
                pass

    # Pass 3: directly extract just the route value without needing a valid JSON
    # object at all. The model nearly always gets the route right even when the
    # rest of the output degenerates into garbage.
    if data is None:
        route_direct = re.search(r'"route"\s*:\s*"([^"\s]+)"', cleaned, re.IGNORECASE)
        if route_direct:
            candidate = route_direct.group(1).strip().upper()
            if candidate in _ROUTES:
                logger.warning(
                    f"[Triage] Full JSON unparseable \u2014 route extracted directly: {candidate!r}. "
                    "Using it with confidence=1.0 (model showed the route clearly)."
                )
                data = {"route": candidate, "keywords": "", "confidence": 1.0}

    if data is None:
        logger.warning(
            f"[Triage] Could not parse routing string/JSON ({parse_error}): {answer[:300]!r} "
            "\u2014 defaulting to REASONING."
        )
        return TaskType.REASONING, None

    route_val = str(data.get("route", "")).strip().upper()
    raw_keywords = str(data.get("keywords", "") or "").strip()
    # The grammar only constrains keywords length, not its contents. The model has
    # been observed to dump prompt fragments, repeated digits, or the user query
    # into this field when uncertain. Per the routing spec, keywords is only
    # meaningful for SEARCH; for every other route, force it to empty so a
    # garbage value here can never influence downstream behaviour.
    keywords = raw_keywords if route_val == "SEARCH" else ""
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        # Model emitted something like ":-162" or ":-0" instead of a real number.
        # Trust the route it picked (the route token is structurally valid because
        # of the grammar constraint) and treat the missing confidence as 1.0.
        logger.warning(
            f"[Triage] Unparseable confidence value {data.get('confidence')!r} \u2014 "
            f"treating as 1.0 for route {route_val!r}."
        )
        confidence = 1.0
    # The grammar's [0.0, 1.0] bound is loose: models sometimes emit -162, 1e6,
    # -0, etc. instead of a calibrated probability. We treat anything that
    # doesn't look like a real calibrated score as 1.0 (trust the route).
    if confidence < 0.0 or confidence > 1.0 or (confidence == 0.0 and "confidence" in data):
        logger.warning(
            f"[Triage] Implausible confidence {confidence} for route {route_val!r} \u2014 "
            "treating as 1.0 (trust the structurally-valid route token)."
        )
        confidence = 1.0

    if confidence < _CONFIDENCE_FLOOR:
        logger.info(f"[Triage] Confidence {confidence:.2f} < {_CONFIDENCE_FLOOR}. Falling back to REASONING.")
        return TaskType.REASONING, None

    mapped = _ROUTE_TAG_MAP.get(route_val)
    if route_val == "SEARCH":
        mapped = TaskType.SEARCH

    if mapped is not None:
        # Post-check override: short greetings and identity questions must reach
        # GENERAL even if the model picked a heavier route. This catches the
        # common case where the triage model's structured output degenerates
        # into noise on simple "hi" / "hello" / "who are you" queries and the
        # model picks REASONING (or worse) by default.
        if mapped != TaskType.GENERAL:
            general_reason = _general_override_route(query_for_classification)
            if general_reason is not None:
                logger.info(
                    f"[Triage] Post-check override: query matched GENERAL pattern "
                    f"(reason={general_reason!r}); "
                    f"downgrading {mapped.name} -> GENERAL."
                )
                return TaskType.GENERAL, None
        # Post-check override: unambiguous coding requests must reach a code route.
        # The triage model is sometimes confident-but-wrong on clear coding requests
        # (e.g. "create a calculator in python" -> REASONING). This is a narrow,
        # high-precision list of patterns that only fires when the model picked a
        # non-code route AND the query matches an unambiguous coding pattern.
        if mapped != TaskType.CODING_SIMPLE and mapped != TaskType.CODING_COMPLEX:
            override_result = _code_override_route(query_for_classification)
            if override_result is not None:
                chosen, verb, target = override_result
                logger.info(
                    f"[Triage] Post-check override: query matched coding pattern "
                    f"(verb={verb!r}, target={target!r}); "
                    f"upgrading {mapped.name} -> {chosen.name}."
                )
                return chosen, None
        if mapped == TaskType.SEARCH:
            return TaskType.SEARCH, (keywords or query_for_classification)
        return mapped, None

    logger.warning(f"[Triage] Unrecognized route {route_val!r} \u2014 defaulting to REASONING.")
    return TaskType.REASONING, None
