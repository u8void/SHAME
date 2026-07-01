def get_reasoning_prompt(identity: str) -> str:
    return (
        f"{identity}\n"
        "You are the Iris AI Reasoning Specialist. You MUST use chain-of-thought reasoning for every query. "
        "RESPONSE FORMAT (MANDATORY):\n"
        "1. ALWAYS start your response with <think> and put ALL of your reasoning, analysis, step-by-step breakdown, "
        "explanations of your thought process, intermediate steps, and any internal deliberation inside <think>...</think> tags.\n"
        "2. After closing </think>, output a DETAILED, COMPREHENSIVE response for the user. "
        "Do NOT be brief or concise. Provide thorough explanations with context, background, examples, "
        "and supporting details. Structure your response with paragraphs, bullet points, or sections as needed.\n"
        "3. NEVER output reasoning, analysis steps, or thought process outside of <think> tags. "
        "Everything outside </think> is shown directly to the user as the response.\n\n"
        "LETTER/CHARACTER COUNTING RULE (HIGHEST PRIORITY):\n"
        "- If asked how many times a letter appears in a word or name (e.g. 'how many r in strawberry', 'how many a in Ahmed'), "
        "you MUST go through the word letter by letter inside <think> tags, listing each position. "
        "Count ONLY the letters in the exact word given. Do NOT search the web. Do NOT bring up other people or names. "
        "Example: 'how many a in Ahmad' → A-h-m-a-d: positions 1 and 4 are 'a' (case-insensitive) → answer is 2.\n"
        "ACCURACY RULES (HIGHEST PRIORITY):\n"
        "1. NEVER invent facts, statistics, names, dates, or specific details you are not certain about.\n"
        "2. For factual questions, web search results will be provided in the query. "
        "You MUST base your entire answer EXCLUSIVELY on the provided <search_results>. "
        "DO NOT add unsourced claims, foreign language translations, or unrelated trivia that was not in the search results. "
        "Answer EXACTLY what the user asked.\n"
        "3. Prefer saying 'I don't have reliable information on that' over guessing.\n"
        "DEPTH RULES:\n"
        "4. Structure your reasoning inside <think>: problem definition → analysis → approach → solution → verification.\n"
        "5. For explanations: cover mechanics, context, history, significance, and real-world examples.\n"
        "6. After </think>, provide a THOROUGH response. Include multiple paragraphs, detailed explanations, "
        "background context, key facts, dates, names, and any relevant supporting information.\n"
        "7. End with actionable takeaways or a clear conclusion when applicable.\n"
        "8. If you are writing, modifying, or improving code (including HTML/CSS), you MUST output the ENTIRE updated code inside standard markdown triple backticks (```language ... ```). Do NOT output code as plain text or regular markdown lists.\n"
        "9. CRITICAL: Whenever you output code, you MUST ALWAYS provide the FULL, COMPLETE code file. NEVER use abbreviations or placeholders like '...', '<!-- rest of code -->', or '// unchanged'. Provide the entire working script every time."
    )


import re
import logging
from typing import Generator, Dict, Optional, Any
from src.iris_engine import ModelRole, load_model, unload_model, _keep_loaded, _stream_tokens, load_generation_config, _quality_guard

from src.iris_engine import detect_user_language, _language_directive

logger = logging.getLogger('iris')

def run_stream(user_query: str, history: list, retriever: Any, settings: dict, do_search: bool = False, direct_answer: str = "") -> Generator[Dict[str, str], None, None]:
    web_context = ""
    if do_search:
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

    # 1. RAG
    context = ""
    if retriever is not None and len(user_query.split()) >= 3:
        is_contextual = False
        if history:
            pronouns = re.compile(r'\b(he|him|his|she|her|it|its|they|them|this|that)\b', re.IGNORECASE)
            if len(user_query.split()) < 6 or pronouns.search(user_query):
                is_contextual = True
        
        if not is_contextual:
            context = retriever.retrieve(user_query, top_k=3, category="reasoning")
            
    final_query = user_query
    if context:
        final_query = (
            f"<retrieved_context>\n{context}\n</retrieved_context>\n\n"
            f"If the retrieved context is relevant, use it. Otherwise, ignore it.\n\n"
            f"{final_query}"
        )
        
    if web_context and "(No web results found" not in web_context and "Web search unavailable" not in web_context:
        final_query = (
            f"--- SEARCH RESULTS ---\n{web_context}\n--- END SEARCH RESULTS ---\n\n"
            f"User Query:\n{final_query}\n\n"
            f"INSTRUCTIONS:\nYou MUST think step-by-step before answering. You MUST enclose ALL step-by-step reasoning strictly inside <think> and </think> tags.\n"
            f"Start your response immediately with <think>. Do not add any introductory text or meta-commentary.\n"
            f"DO NOT pretend to search the web inside your thought process. The search results have ALREADY been provided to you in the SEARCH RESULTS block above. Read the provided results directly.\n"
            f"Use the search results above to inform your answer. If the search results are incomplete, you may use your internal knowledge to supplement the answer.\n"
            f"CRITICAL: After you output </think>, write ONLY the clean final answer. Do NOT include 'Final Answer:', 'Step-by-Step Explanation:', or numbered analysis steps outside of <think> tags. The text after </think> is shown directly to the user.\n"
            f"Respond in the SAME LANGUAGE as the user's query."
        )
        
    final_query += _language_directive(user_query, role=ModelRole.REASONING)
    
    # 2. History & Compaction
    optimized = [{"role": "user", "content": final_query}]
    if history:
        optimized = [{"role": m["role"], "content": m["content"]} for m in history] + optimized    
    # 3. Generation
    yield {"type": "status", "content": "Analyzing..."}
    full = ""
    thought_process = ""
    _r_temp = 0.4 if web_context else 0.3
    _r_tokens = 8192 if web_context else 6144
    
    user_lang = detect_user_language(user_query)
    for ev in _stream_tokens(ModelRole.REASONING, optimized, max_tokens=_r_tokens, temperature=_r_temp, think_mode="show"):
        if user_lang == "English" or ev["type"] != "token":
            yield ev
        if ev["type"] == "token":
            full += ev["content"]
        elif ev["type"] == "thinking":
            thought_process += ev["content"]
            
    if not _keep_loaded:
        unload_model()
        
    combined = ""
    if thought_process:
        combined += f"<think>\n{thought_process.strip()}"
        if full:
            combined += f"\n</think>\n{full}"
        else:
            combined += "\n</think>"
    else:
        combined = full
        
    cleaned = _quality_guard(combined)

    # --- Output Completeness Validation ---
    _visible = cleaned.strip()
    _visible_no_think = re.sub(r'<think>[\s\S]*?</think>', '', _visible).strip()
    
    _EVASION_PHRASES = re.compile(
        r'^(the final answer is[:\s]*|\[?routing complete\]?\.?|done\.?|answer[:\s]*|result[:\s]*)$',
        re.IGNORECASE
    )
    _is_collapsed = (
        len(_visible_no_think) < 5
        or _EVASION_PHRASES.match(_visible_no_think)
    ) and len(thought_process.strip()) < 50
    
    if _is_collapsed:
        logger.warning(f"[Completeness] Evasion-loophole detected. Visible output too thin ({len(_visible)} chars). Attempting recovery.")
        if len(thought_process) > 100:
            _recovered = (
                f"*(Note: The model's visible answer was evaded due to constraints — surfacing internal thought process instead.)*\n\n"
                f"{thought_process.strip()}\n\n"
                f"**Final Answer emitted**: {_visible}"
            )
            yield {"type": "clear"}
            yield {"type": "token", "content": _recovered}
            yield {"type": "raw_response", "content": _recovered}
            return
            
        yield {"type": "clear"}
        yield {"type": "status", "content": "Retrying for complete response..."}
        
        _assistant_context = full
        if thought_process.strip():
            _assistant_context = f"<think>{thought_process}</think>\n{full}"
            
        retry_msgs = optimized + [
            {"role": "assistant", "content": _assistant_context},
            {"role": "user", "content": (
                "Your previous response was incomplete — it only contained a closing phrase without the actual answer. "
                "Please provide the FULL, complete explanation now. Do not skip or abbreviate."
            )}
        ]
        retry_full = ""
        for ev in _stream_tokens(ModelRole.REASONING, retry_msgs, max_tokens=_r_tokens, temperature=0.5, think_mode="show"):
            if user_lang == "English" or ev["type"] != "token":
                yield ev
            if ev["type"] == "token":
                retry_full += ev["content"]
        cleaned = _quality_guard(retry_full)

    if combined and cleaned and cleaned != combined:
        yield {"type": "clear"}
        yield {"type": "token", "content": cleaned}
        
    user_lang = detect_user_language(user_query)
    if user_lang != "English" and cleaned:
        from src.iris_engine import translate_text
        yield {"type": "status", "content": f"Translating to {user_lang}..."}
        translated = translate_text(cleaned, user_lang)
        if translated != cleaned:
            cleaned = translated
            yield {"type": "clear"}
            yield {"type": "token", "content": cleaned}
        
    if web_context:
        sources = re.findall(r'\[source\]\((.*?)\)', web_context)
        if sources:
            unique_sources = []
            for s in list(dict.fromkeys(sources)):
                domain = s.split('://')[-1].split('/')[0]
                if domain.startswith("www."):
                    domain = domain[4:]
                unique_sources.append({"url": s, "domain": domain})
            yield {"type": "sources", "sources": unique_sources}
                
    yield {"type": "raw_response", "content": cleaned}
