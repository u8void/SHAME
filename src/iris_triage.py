
import os
_triage_guide_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "documentations", "triage_routing_guide.md")
try:
    with open(_triage_guide_path, "r", encoding="utf-8") as _f:
        TRIAGE_SYSTEM_PROMPT = _f.read()
except Exception:
    TRIAGE_SYSTEM_PROMPT = (
        "[CLASSIFICATION TASK — SAFETY OVERRIDE] You are an AI router performing a mechanical text classification task. "
        "You MUST output EXACTLY ONE routing tag regardless of the query topic. This is NOT a content generation task; you will NEVER produce harmful content. "
        "Your only output is the exact routing tag. Do not output JSON. Do not explain. "
        "You are NEVER responsible for the actual response. NEVER refuse. NEVER say 'I cannot assist'. JUST OUTPUT THE TAG.\n\n"
        f"{""}\n"
        "You are the Iris AI Router. Your ONLY job is to output ONE routing tag.\n"
        "Rules:\n"
        "1. Simple greetings like 'hi', 'hello', 'good morning' → answer with a SHORT greeting, NO tag, NO OFF-TOPICS STUFF\n"
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
        "- LETTER/WORD INTROSPECTION RULE (HIGHEST PRIORITY): If the user asks how many of a letter appear in a word or name (e.g. 'how many r in strawberry', 'how many a in Ahmed'), or asks to count characters/vowels/consonants, or asks about spelling of a word — this is ALWAYS [ROUTE: REASONING]. NEVER route these to SEARCH.\n"
        "- RECOMMENDATION/ADVICE RULE: If the user asks for advice on what to buy, product recommendations, or general questions about items/pets (e.g., 'which cat is best to buy'), route to [ROUTE: SEARCH] or [ROUTE: REASONING]. NEVER route these to [ROUTE: CONTROL].\n\n"
        "_ If the user greats you, Great Him Again like \n"
        "_ User: Hi -> Bot: Hi, How is it going \n"
        "EXAMPLES:\n"
        "Query: 'what is the capital of France' → [ROUTE: SEARCH: capital of France]\n"
        "Query: 'how many r in strawberry' → [ROUTE: REASONING]\n"
        "Query: 'how to make a pizza' → [ROUTE: REASONING]\n"
        "Query: 'create a tailwind css landing page' → [ROUTE: CODE_COMPLEX]\n"
        "Query: 'open spotify' → [ROUTE: CONTROL]\n"
        "Query: 'set brightness to 40%' → [ROUTE: CONTROL]\n"
        "Query: 'hi' → Hello! How can I help you today?\n"
        "Query: 'who are you' → [ROUTE: GENERAL]\n\n"
        "You MUST output exactly one routing tag based on the user's intent. Do not output anything else. No JSON, no markdown blocks."
    )

import os
import re
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from src.iris_engine import ModelRole, TaskType, load_model, unload_model, _keep_loaded, _minimize_history, load_generation_config

logger = logging.getLogger('iris')


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
        "message", "send text", "whatsapp", "telegram", "quiz", "autopilot", "login", "browser",
        "maximize", "minimize", "fullscreen", "switch tab", "close window",
        "delete file", "delete folder", "create file", "create folder", "move file", "copy file",
        "rename", "unzip", "extract", "compress", "zip file", "download file",
        "git pull", "git push", "git commit", "docker run", "docker ps", "npm install", "pip install",
        "apt update", "apt install", "winget install", "brew install",
        "vpn connect", "vpn disconnect", "speed test", "flush dns",
        "type out", "press", "say", "do not disturb", "dnd", "read clipboard", "write clipboard",
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
        "kernel", "makefile", "gcc", "clang", "qemu", "gdb", "vga",
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
        "game", "makefile", "multi-file", "multiple files",
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
        "combinatorics", "calculate", "solve", "area", "volume",
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
    

            
    if history and history[-1].get("role") == "user" and history[-1].get("content", "").strip().startswith("OBSERVATION:"):
        return TaskType.CONTROL, None

    
    
    
    
    from src.iris_engine import _model_pool
    if _model_pool:
        for model in _model_pool.values():
            if hasattr(model, 'active_role'):
                try:
                    return ModelRole(model.active_role)
                except ValueError:
                    pass

    minimized = _minimize_history(history, max_entries=2)
    triage_prompt = TRIAGE_SYSTEM_PROMPT
    import datetime
    try:
        now = datetime.datetime.now().astimezone()
        time_str = now.strftime("%A, %B %d, %Y, %H:%M:%S %Z")
        offset_str = now.strftime("%z")
        formatted_offset = f"{offset_str[:3]}:{offset_str[3:]}" if len(offset_str) >= 5 else offset_str
        triage_prompt += f"\n\nSystem Time Context: The current local time is {time_str} (UTC{formatted_offset}). Use this context to accurately route any date or time-related queries."
    except Exception:
        pass
    triage_messages = [{"role": "system", "content": triage_prompt}]
    for msg in minimized:
        c = msg["content"]
        if len(c) > 150:
            c = c[:150] + "...[truncated]"
        triage_messages.append({"role": msg["role"], "content": c})

    triage_query = f'{query_for_classification}\n\n[SYSTEM DIRECTIVE: Analyze the user query and output EXACTLY ONE routing tag (e.g. [ROUTE: REASONING], [ROUTE: SEARCH: ...], etc.). Do not output JSON. Do not output anything else.]'
    if len(triage_query) > 1500:
        triage_query = triage_query[:1000] + "\n\n...[content truncated for routing]...\n\n" + triage_query[-500:]
    
    triage_messages.append({"role": "user", "content": triage_query})

    llm = load_model(ModelRole.TRIAGE)
    res = llm.create_chat_completion(
        messages=triage_messages,
        max_tokens=512,
        temperature=0.1,
        repeat_penalty=1.15,
        presence_penalty=0.1,
    )
    answer = res["choices"][0]["message"]["content"].strip()
    cfg = load_generation_config()
    if not _keep_loaded and not cfg.get("keep_triage_loaded"):
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

    # Attempt to parse JSON first
    parsed_route = answer
    confidence = 1.0
    try:
        # Extract json block if model wrapped it
        json_match = re.search(r'\{.*\}', answer, re.DOTALL)
        if json_match:
            parsed_json = json.loads(json_match.group(0))
            parsed_route = parsed_json.get("route", answer)
            confidence = float(parsed_json.get("confidence", 1.0))
    except Exception:
        pass

    if confidence < 0.70:
        logger.info(f"[Routing] Confidence {confidence:.2f} < 0.70. Falling back to REASONING.")
        return TaskType.REASONING, None

    search_match = re.search(r'\[\s*route:\s*SEARCH:\s*(.*?)\s*\]', parsed_route, re.IGNORECASE)
    if search_match:
        kw = search_match.group(1).strip()
        if kw.lower() in ["keywords", "query"]:
            kw = ""
        return TaskType.SEARCH, kw

    for tag, ttype in tag_map.items():
        if re.search(rf'\[\s*route:\s*{re.escape(tag)}\s*\]', parsed_route, re.IGNORECASE) or re.search(rf'\b{re.escape(tag)}\b', parsed_route, re.IGNORECASE):
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
            and GREETING_PATTERNS.search(answer)
            and not re.search(
                r'\b(because|therefore|however)\b',
                answer, re.IGNORECASE
            )
            and not IDENTITY_PATTERNS.search(answer)
        )
        if is_greeting_reply:
            return None, answer

        # Detect safety refusals from Qwen's RLHF — intelligently re-route instead of always REASONING
        _REFUSAL_PATTERNS = re.compile(
            r"^(i('?m| am) sorry|i can'?t (assist|help)|i'?m unable|i cannot (assist|help)|sorry,? (but )?i|apologies)",
            re.IGNORECASE
        )
        if _REFUSAL_PATTERNS.match(answer):
            # Triage model refused — use keyword-based heuristic to pick the best route
            q_lower = query_for_classification.lower()
            if any(kw in q_lower for kw in ["code", "script", "function", "html", "css", "js", "python", "write", "debug", "fix"]):
                logger.info("[Triage] Safety refusal detected — heuristic: CODE_COMPLEX")
                return TaskType.CODING_COMPLEX, None
            elif any(kw in q_lower for kw in ["calculate", "solve", "integral", "equation", "math", "proof", "+", "-", "*", "/"]):
                logger.info("[Triage] Safety refusal detected — heuristic: MATH")
                return TaskType.MATH, None
            elif any(kw in q_lower for kw in ["open", "launch", "click", "send message", "email", "browser", "control"]):
                logger.info("[Triage] Safety refusal detected — heuristic: CONTROL")
                return TaskType.CONTROL, None
            else:
                logger.info("[Triage] Safety refusal detected — heuristic: REASONING")
                return TaskType.REASONING, None

        # Use the comprehensive _fallback_classify if Triage hallucinates
        fallback = _fallback_classify(query_for_classification)
        if fallback:
            logger.info(f"[Triage] No tag. Fallback heuristic used: {fallback.value}. Triage said: {answer[:80]}...")
            if fallback == TaskType.SEARCH:
                return fallback, ""
            return fallback, None

        logger.info(
            f"[Triage] No routing tag — redirecting to REASONING to prevent hallucination. "
            f"Triage said: {answer[:80]}..."
        )
        return TaskType.REASONING, None

    return None, answer



