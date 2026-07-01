
import os
_triage_guide_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "triage", "triage_routing_guide.md")
try:
    with open(_triage_guide_path, "r", encoding="utf-8") as _f:
        TRIAGE_SYSTEM_PROMPT = _f.read()
except Exception:
    TRIAGE_SYSTEM_PROMPT = (
        "You are the Iris AI Router. Your ONLY job is to read the user's message and output EXACTLY ONE routing tag.\n"
        "Available routes:\n"
        "  [ROUTE: SEARCH: keywords]  — factual questions, current events, news, people, places, prices, definitions\n"
        "  [ROUTE: REASONING]         — how/why questions, step-by-step explanations, analysis, comparisons, counting letters/characters, summaries\n"
        "  [ROUTE: GENERAL]           — casual chat, greetings, opinions, creative writing, identity questions\n"
        "  [ROUTE: MATH]              — math problems, equations, proofs, calculations\n"
        "  [ROUTE: CODE_SIMPLE]       — small code snippets, functions, HTML/CSS/JS elements, canvas animations, SVG graphics\n"
        "  [ROUTE: CODE_COMPLEX]      — full projects, multi-file code, games, complete websites or web apps\n"
        "  [ROUTE: CONTROL]           — OS/PC commands, opening/closing apps, browser automation, email, power control, system settings\n\n"
        "Output ONLY the tag. Nothing else. No explanation. No JSON. Just the tag.\n"
        "For SEARCH routes, include keywords: [ROUTE: SEARCH: <keywords>]\n"
        "For greetings and casual chat output: [ROUTE: GENERAL]"
    )

import os
import re
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from src.iris_engine import ModelRole, TaskType, load_model, unload_model, _keep_loaded, _minimize_history, load_generation_config

logger = logging.getLogger('iris')



def is_math_query(query: str) -> bool:
    # 1. First, check if this is likely a coding request to avoid misrouting it to MATH.
    # Code requests should fall through to normal triage or coding routes.
    query_lower = query.lower()
    
    # Check for code blocks or explicit code requests
    if "```" in query:
        return False
        
    code_indicators = [
        r"\b(?:write|create|implement|make|program|code|run|debug|fix)\s+(?:a\s+)?(?:python|javascript|js|c\+\+|cpp|java|rust|go|php|typescript|html|css|sql|script|function|program|class|method)\b",
        r"\b(?:python|javascript|js|c\+\+|cpp|java|rust|go|php|typescript|html|css|sql)\b.*\b(?:code|function|class|array|list|dict|loop|import|return)\b",
        r"\b(?:code|function|class|array|list|dict|loop|import|return)\b.*\b(?:python|javascript|js|c\+\+|cpp|java|rust|go|php|typescript|html|css|sql)\b"
    ]
    if any(re.search(pat, query_lower) for pat in code_indicators):
        return False

    # Avoid routing historical/biographical/factual queries to MATH
    search_override_indicators = [
        r"\bwho\s+(?:is|was|were|wrote|created|discovered|invented|proved)\b",
        r"\bwhere\s+(?:is|was|were|did)\b",
        r"\bwhen\s+(?:did|was|were|is)\b",
        r"\bwhy\s+(?:did|was|were|is)\b",
        r"\bhistory\s+of\b",
        r"\btell\s+me\s+about\b"
    ]
    if any(re.search(pat, query_lower) for pat in search_override_indicators):
        return False

    # 2. Check for LaTeX mathematical syntax
    latex_patterns = [
        r"\$\$",
        r"\\\[",
        r"\\\]",
        r"\\\(",
        r"\\\)",
        r"\\begin\{[a-zA-Z]+[*]?\}",
        r"\\end\{[a-zA-Z]+[*]?\}",
        r"\\(?:frac|sum|int|lim|sqrt|alpha|beta|gamma|delta|pi|theta|infty|times|div|pm|le|ge|neq|approx|in|subset|cup|cap|nabla|partial|forall|exists|rightarrow|implies|iff|mathbb|mathcal|mathbf|mathrm|boxed|cdot|log|sin|cos|tan|ln|binom)"
    ]
    if any(re.search(pat, query) for pat in latex_patterns):
        return True

    # 3. Check for Unicode mathematical characters
    unicode_math_chars = r"[∫∑∏√∞∠△±≤≥≠≈∈∉⊆⊂∪∩¬∧∨⇒⇔∀∃]"
    if re.search(unicode_math_chars, query):
        return True

    # 4. Check for algebraic variables and equations (e.g. x^2, 2x + 3 = 7, y = mx + c)
    algebra_patterns = [
        # Variables with exponents, e.g. x^2, y^n, (x+1)^3
        r"\b[a-zA-Z]\^[-+*]?[0-9a-zA-Zn]+\b",
        r"\([a-zA-Z]\s*[-+*/^]\s*\d+\)\^[-+*]?[0-9a-zA-Zn]+\b",
        # Variables with subscripts, e.g. x_i, a_n, y_{j}
        r"\b[a-zA-Z]_[0-9a-zA-Zni_]+\b",
        r"\b[a-zA-Z]_\{[0-9a-zA-Zni_]+\}",
        # Standard algebraic equations, e.g. 2x + 3 = 7, 4y - 2 = x, x^2 - 4 = 0
        r"\b\d*[a-zA-Z]\s*[-+*/^]\s*\d*[a-zA-Z0-9]\s*[=<>]",
        r"[=<>]\s*\d*[a-zA-Z]\s*[-+*/^]\s*\d*[a-zA-Z0-9]",
        r"\b\d*[a-zA-Z]\s*[=<>]\s*\d+",
        r"\b\d+\s*[=<>]\s*\d*[a-zA-Z]\b",
        # Function definitions, e.g., f(x) = x^2, g(x,y)
        r"\b[fgh]\([a-zA-Z](?:\s*,\s*[a-zA-Z])*\)\s*="
    ]
    if any(re.search(pat, query) for pat in algebra_patterns):
        return True

    # 5. Check for pure arithmetic / numerical expressions
    arithmetic_patterns = [
        # Multiple numbers separated by basic operators, optionally with parenthesis
        r"\b\d+\s*[-+*/^%]\s*\d+\s*[-+*/^%]\s*\d+",
        r"\(\s*\d+\s*[-+*/^%]\s*\d+\s*\)",
        r"\b\d+\s*[-+*/^%]\s*\d+\s*=\s*\d+",
        # Two numbers with specific math operators (*, /, ^, %)
        r"\b\d+(?:\.\d+)?\s*[\*\/^%]\s*\d+(?:\.\d+)?\b",
        # Two numbers with addition or subtraction (guarded against dates/phone numbers)
        r"\b\d+(?:\.\d+)?\s*\+\s*\d+(?:\.\d+)?\b",
        r"(?<!\d-)\b\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\b(?!-\d)",
        # Percentage calculation: "15% of 340"
        r"\b\d+(?:\.\d+)?%\s+of\s+\d+",
        # Fraction operations: "1/2 + 3/4"
        r"\b\d+/\d+\s*[-+*/]\s*\d+/\d+",
        # Arithmetic series pattern: "1 + 2 + 3 + ... + 100" or similar
        r"\d+\s*[-+*/]\s*\d+\s*[-+*/]\s*\d+\s*[-+*/]\s*\.\.\.\s*[-+*/]\s*\d+",
        # sum/product of ...
        r"\b(?:sum|product|difference|ratio|quotient|average)\s+of\s+.*?\d+"
    ]
    if any(re.search(pat, query_lower) for pat in arithmetic_patterns):
        return True

    # 6. Specific math verbs / trigger phrases
    math_phrases = [
        r"\bsolve\s+(?:the\s+)?(?:equation|system|inequality|integral|derivative|limit|problem)\b",
        r"\bcalculate\s+(?:the\s+)?(?:value|sum|product|integral|derivative|probability|limit|mean|median|variance|std|standard\s+deviation|percentage)\b",
        r"\bcompute\s+(?:the\s+)?(?:sum|product|integral|derivative|probability|limit|mean|median|variance|std|standard\s+deviation|percentage)\b",
        r"\bevaluate\s+(?:the\s+)?(?:expression|integral|derivative|limit)\b",
        r"\bfind\s+(?:the\s+)?(?:minimum|maximum|roots|eigenvalues|eigenvectors|determinant|sum|product|limit|probability|derivative|integral)\b",
        r"\bprove\s+that\b",
        r"\bderive\s+(?:the\s+)?(?:formula|equation|derivative)\b",
        r"\bsimplify\s+(?:the\s+)?(?:expression|fraction|equation)\b",
        r"\bfactor\s+(?:the\s+)?(?:polynomial|expression|quadratic)\b",
        r"\bexpand\s+(?:the\s+)?(?:expression|polynomial)\b"
    ]
    if any(re.search(pat, query_lower) for pat in math_phrases):
        return True

    # 7. Math terms and concepts
    math_nouns = [
        # General math terminology, matrices (plural), highly specific terms
        r"\b(?:derivative|integral|matrices|polynomial|algebra|calculus|trigonometry|geometry|theorem|logarithm|sine|cosine|tangent|factorial|prime\s+number|divisors|gcd|lcm|modular\s+arithmetic|modulus|complex\s+number|eigenvalue|eigenvector|determinant|transpose|differential\s+equation|linear\s+algebra|arithmetic\s+progression|geometric\s+progression|combinatorics|permutation|combination|fibonacci|pythagorean|quadratic|cubic|standard\s+deviation|variance|normal\s+distribution|bayes\s+theorem|binomial\s+distribution|hypotenuse|right\s+triangle|irrational\s+number|rational\s+number|probability|set\s+theory|union\s+of\s+set|intersection\s+of\s+set|subset\s+of|venn\s+diagram|cardinality)\b",
        # Explicit matrix/vector operation terms
        r"\bmatrix\s+(?:multiplication|multiplied|addition|determinant|inverse|transpose|equation|space|vector)\b",
        r"\bvector\s+(?:space|addition|product|multiplication|calculus)\b"
    ]
    if any(re.search(pat, query_lower) for pat in math_nouns):
        highly_specific_math = [
            "derivative", "integral", "matrices", "calculus", "trigonometry", "theorem", "logarithm", "sine", "cosine", "tangent",
            "gcd", "lcm", "modular arithmetic", "complex number", "eigenvalue", "eigenvector", "determinant", "differential equation",
            "linear algebra", "arithmetic progression", "geometric progression", "combinatorics", "permutation", "combination",
            "pythagorean", "hypotenuse", "right triangle", "irrational number", "rational number", "bayes theorem", "set theory",
            "union of set", "intersection of set", "subset of", "venn diagram", "cardinality", "probability"
        ]
        if any(w in query_lower for w in highly_specific_math):
            return True
            
        if re.search(r"\b(?:solve|calculate|compute|find|what|how|prove|evaluate|value|sum|x|y|z|\d+)\b", query_lower):
            return True

    # 8. Prime / divisibility / gcd / lcm queries
    extra_patterns = [
        r"\bis\s+\d+\s+(?:a\s+)?prime\b",
        r"\bis\s+\d+\s+divisible\s+by\b",
        r"\b(?:gcd|lcm)\(\s*\d+\s*,\s*\d+\s*\)",
        r"\b\d+\s*mod\s*\d+\b"
    ]
    if any(re.search(pat, query_lower) for pat in extra_patterns):
        return True

    return False


def classify_task(
    user_query: str, history: List[Dict[str, str]]
) -> Tuple[Optional[TaskType], Optional[str]]:
    # Strip document/image tags from the query before routing
    query_for_classification = re.sub(r'<document>[\s\S]*?</document>', '', user_query, flags=re.IGNORECASE)
    query_for_classification = re.sub(r'\[IMAGE_UPLOADED:[^\]]+\]', '', query_for_classification, flags=re.IGNORECASE)
    query_for_classification = query_for_classification.strip()

    # Deterministic override for math queries: check if it's math before any search intercepts
    if is_math_query(query_for_classification):
        logger.info(f"[Triage] Query triggered deterministic MATH route: {query_for_classification!r}")
        return TaskType.MATH, None

    # Deterministic overrides for SEARCH triggers
    query_lower = query_for_classification.lower()
    search_triggers = [
        r"\bwhat\s+is\b",
        r"\btell\s+me\s+about\b",
        r"\bwhy\b",
        r"\bexists\b"
    ]
    if any(re.search(pat, query_lower) for pat in search_triggers):
        clean_kw = query_for_classification
        for pat in search_triggers:
            clean_kw = re.sub(pat, "", clean_kw, flags=re.IGNORECASE).strip()
        clean_kw = clean_kw.rstrip("?").strip()
        if not clean_kw:
            clean_kw = query_for_classification
        logger.info(f"[Triage] Query triggered deterministic SEARCH route: {query_for_classification!r} -> keywords: {clean_kw!r}")
        return TaskType.SEARCH, clean_kw

    # If previous message was an OBSERVATION (agent loop), continue as CONTROL
    if history and history[-1].get("role") == "user" and history[-1].get("content", "").strip().startswith("OBSERVATION:"):
        return TaskType.CONTROL, None

    minimized = _minimize_history(history, max_entries=2)
    
    # Prepend a strong classifier system instruction to prevent the model from answering the user's query
    triage_prompt = (
        "CRITICAL ROLE AND INSTRUCTION:\n"
        "You are the Iris AI Router. Your ONLY job is to classify the user's query and output a single JSON routing block.\n"
        "You must NEVER answer, reply to, execute, or explain the user's query under any circumstances.\n"
        "Even if the query is a simple greeting, a coding request, or a math problem, you must ONLY output the JSON routing decision.\n"
        "You MUST process your reasoning in a <think> block BEFORE outputting the final JSON routing block.\n"
        "No conversational preamble, no markdown formatting outside of the JSON block, and no code execution.\n\n"
        "=== ROUTING SPECIFICATION ===\n"
        f"{TRIAGE_SYSTEM_PROMPT}"
    )

    # Inject current time for time-sensitive routing
    import datetime
    try:
        now = datetime.datetime.now().astimezone()
        time_str = now.strftime("%A, %B %d, %Y, %H:%M:%S %Z")
        offset_str = now.strftime("%z")
        formatted_offset = f"{offset_str[:3]}:{offset_str[3:]}" if len(offset_str) >= 5 else offset_str
        triage_prompt += f"\n\nCurrent time: {time_str} (UTC{formatted_offset})."
    except Exception:
        pass

    # Build the conversation history context as a text block inside the user's request
    # This prevents the model from seeing itself as the 'Assistant' role in chat messages,
    # which otherwise triggers conversational/direct-answering behaviors.
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
        {"role": "user", "content": user_content}
    ]

    llm = load_model(ModelRole.TRIAGE)
    res = llm.create_chat_completion(
        messages=triage_messages,
        max_tokens=1024,
        temperature=0.05,
        repeat_penalty=1.1,
    )
    answer = res["choices"][0]["message"]["content"].strip()
    cfg = load_generation_config()
    if not _keep_loaded and not cfg.get("keep_triage_loaded"):
        unload_model(ModelRole.TRIAGE)

    logger.info(f"[Triage] Raw answer: {answer!r}")

    tag_map: Dict[str, TaskType] = {
        "GENERAL":        TaskType.GENERAL,
        "REASONING":      TaskType.REASONING,
        "MATH":           TaskType.MATH,
        "CODING_SIMPLE":  TaskType.CODING_SIMPLE,
        "CODE_SIMPLE":    TaskType.CODING_SIMPLE,
        "CODING_COMPLEX": TaskType.CODING_COMPLEX,
        "CODE_COMPLEX":   TaskType.CODING_COMPLEX,
        "CONTROL":        TaskType.CONTROL,
    }

    # Attempt to parse JSON first
    parsed_route = answer
    confidence = 1.0
     # 1. Try parsing JSON format as defined in triage_routing_guide.md
    # Strip CoT think blocks to prevent JSON parsing errors. Supports incomplete/truncated think tags.
    json_str = re.sub(r'<think>[\s\S]*?(?:</think>|$)', '', answer, flags=re.IGNORECASE).strip()

    # 1. Try parsing JSON format as defined in triage_routing_guide.md
    try:
        clean_json = json_str
        if "```" in clean_json:
            match = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', clean_json)
            if match:
                clean_json = match.group(1).strip()
        # Fallback to extracting the first matching JSON block if thought tags or other text headers prefix the JSON
        json_match = re.search(r'(\{[\s\S]*\})', clean_json)
        if json_match:
            clean_json = json_match.group(1).strip()
        data = json.loads(clean_json)
        if isinstance(data, dict):
            route_val = str(data.get("route", "")).strip().upper()
            kw = data.get("keywords")
            if route_val == "SEARCH":
                return TaskType.SEARCH, kw or ""
            if route_val in tag_map:
                return tag_map[route_val], None
    except Exception:
        # Fallback regex extraction from malformed JSON
        if "route" in json_str.lower():
            route_match = re.search(r'"route"\s*:\s*"([^"]+)"', json_str, re.IGNORECASE)
            if route_match:
                route_val = route_match.group(1).strip().upper()
                kw = None
                kw_match = re.search(r'"keywords"\s*:\s*(?:"([^"]+)"|([^,}]+))', json_str, re.IGNORECASE)
                if kw_match:
                    kw = kw_match.group(1) or kw_match.group(2)
                    if kw:
                        kw = kw.strip().strip('"').strip("'")
                        if kw.lower() in ["null", "none"]:
                            kw = None
                if route_val == "SEARCH":
                    return TaskType.SEARCH, kw or ""
                if route_val in tag_map:
                    return tag_map[route_val], None

    if confidence < 0.70:
        logger.info(f"[Routing] Confidence {confidence:.2f} < 0.70. Falling back to REASONING.")
        return TaskType.REASONING, None

    search_match = re.search(r'\[\s*route:\s*SEARCH:\s*(.*?)\s*\]', parsed_route, re.IGNORECASE)
    if not search_match and parsed_route.upper().startswith("SEARCH"):
        kw = parsed_route[6:].replace(":", "").strip()
        if kw.lower() in ["keywords", "query"]:
            kw = ""
        return TaskType.SEARCH, kw
    elif search_match:
        kw = search_match.group(1).strip()
        if kw.lower() in ["keywords", "query"]:
            kw = ""
        return TaskType.SEARCH, kw

    plain_search = re.match(r'^SEARCH:\s*(.+)$', answer.strip(), re.IGNORECASE)
    if plain_search:
        kw = plain_search.group(1).strip()
        return TaskType.SEARCH, kw if kw.lower() not in ["keywords", "query"] else ""

    for tag, ttype in tag_map.items():
        if re.search(rf'\[\s*route:\s*{re.escape(tag)}\s*\]', answer, re.IGNORECASE):
            return ttype, None
        if re.search(r'\b' + re.escape(tag) + r'\b', json_str, re.IGNORECASE):
            return ttype, None
        if answer.strip().upper() == tag:
            return ttype, None

    # Default fallback — let REASONING handle anything unclear
    logger.info(f"[Triage] No tag matched — defaulting to REASONING. Answer was: {answer[:500]!r}")
    return TaskType.REASONING, None

