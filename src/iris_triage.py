
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


def classify_task(
    user_query: str, history: List[Dict[str, str]]
) -> Tuple[Optional[TaskType], Optional[str]]:
    # Strip document/image tags from the query before routing
    query_for_classification = re.sub(r'<document>[\s\S]*?</document>', '', user_query, flags=re.IGNORECASE)
    query_for_classification = re.sub(r'\[IMAGE_UPLOADED:[^\]]+\]', '', query_for_classification, flags=re.IGNORECASE)
    query_for_classification = query_for_classification.strip()

    # If previous message was an OBSERVATION (agent loop), continue as CONTROL
    if history and history[-1].get("role") == "user" and history[-1].get("content", "").strip().startswith("OBSERVATION:"):
        return TaskType.CONTROL, None

    minimized = _minimize_history(history, max_entries=2)
    triage_prompt = TRIAGE_SYSTEM_PROMPT

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

    triage_messages = [{"role": "system", "content": triage_prompt}]
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
    try:
        json_str = answer.strip()
        if "```" in json_str:
            match = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', json_str)
            if match:
                json_str = match.group(1).strip()
        data = json.loads(json_str)
        if isinstance(data, dict):
            route_val = str(data.get("route", "")).strip().upper()
            kw = data.get("keywords")
            if route_val == "SEARCH":
                return TaskType.SEARCH, kw or ""
            if route_val in tag_map:
                return tag_map[route_val], None
    except Exception:
        pass

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
        if answer.strip().upper() == tag:
            return ttype, None

    # Default fallback — let REASONING handle anything unclear
    logger.info(f"[Triage] No tag matched — defaulting to REASONING. Answer was: {answer[:80]!r}")
    return TaskType.REASONING, None

