def get_reasoning_prompt(identity: str) -> str:
    return (
        f"{identity}\n"
        "You are the Iris AI Reasoning Specialist. You MUST use chain-of-thought reasoning for every substantive query. "
        "EXCEPTION: If the message is just a greeting, casual small talk, or an identity question ('who are you', "
        "'what are you', 'who made you', etc.), skip the chain-of-thought and the heavy structure entirely — reply "
        "briefly and casually in one or two sentences, like a friend would, with no capability list and no formal bio.\n"
        "RESPONSE FORMAT (MANDATORY):\n"
        "1. ALWAYS start your response with the literal tag <think> — the seven characters angle-bracket, t-h-i-n-k, "
        "angle-bracket — and put ALL of your reasoning, analysis, step-by-step breakdown, explanations of your "
        "thought process, intermediate steps, and any internal deliberation inside <think>...</think> tags. "
        "This must be the actual tag, NOT the word 'think' followed by a colon, NOT 'Thinking:', NOT 'Reasoning:', "
        "and NOT any other plain-text label — those are not tags and will be shown to the user as broken, unhidden "
        "text, which is a formatting error. Example of the only acceptable format:\n"
        "   <think>\n   [reasoning goes here]\n   </think>\n\n   [final answer goes here]\n"
        "2. After closing </think>, output a DETAILED, COMPREHENSIVE response for the user. "
        "Do NOT be brief or concise (except for identity questions). Provide thorough explanations with context, background, examples, "
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
    
    try:
        user_lang = (settings.get("user_lang") if settings else None) or detect_user_language(user_query)
        for ev in _stream_tokens(ModelRole.REASONING, optimized, max_tokens=_r_tokens, temperature=_r_temp, think_mode="show"):
            if user_lang == "English" or ev["type"] != "token":
                yield ev
            if ev["type"] == "token":
                full += ev["content"]
            elif ev["type"] == "thinking":
                thought_process += ev["content"]

        # Strip any leaked <think>/<\/think> tags from thought_process since _stream_tokens
        # may yield a synthetic "</think>" as a thinking event when the model stops mid-think.
        # We re-wrap the thought_process cleanly below to avoid double tags.
        thought_clean = thought_process.strip()
        thought_clean = re.sub(r'</?think>', '', thought_clean, flags=re.IGNORECASE).strip()
        # Also strip other think tag variants
        thought_clean = re.sub(r'<\|?/?thought(?:_(?:start|end))?\|?>', '', thought_clean, flags=re.IGNORECASE).strip()
        
        # Build the visible answer (without think tags) for quality checks and translation
        visible_answer = full.strip()
        # Strip any leaked think tags from visible answer too
        visible_answer = re.sub(r'</?think>', '', visible_answer, flags=re.IGNORECASE).strip()
        visible_answer = re.sub(r'<\|?/?thought(?:_(?:start|end))?\|?>', '', visible_answer, flags=re.IGNORECASE).strip()

        # Strip any rogue markdown code blocks (to prevent file card rendering)
        visible_answer = re.sub(r'```[\s\S]*?(?:```|$)', '', visible_answer, flags=re.IGNORECASE)
        # Strip any rogue HTML span tags (both raw and HTML-encoded), handling typos
        visible_answer = re.sub(r'</?span[\s\S]*?(?:>|&gt;|$)', '', visible_answer, flags=re.IGNORECASE)
        visible_answer = re.sub(r'&lt;/?span[\s\S]*?(?:>|&gt;|$)', '', visible_answer, flags=re.IGNORECASE).strip()
            
        cleaned_answer = _quality_guard(visible_answer) if visible_answer else ""

        # --- Output Completeness Validation ---
        _EVASION_PHRASES = re.compile(
            r'^(the final answer is[:\s]*|\[?routing complete\]?\.?|done\.?|answer[:\s]*|result[:\s]*)$',
            re.IGNORECASE
        )
        # Generic conversational refusals ("I'm sorry, but I can't assist with that request.")
        # were previously invisible to this check — _EVASION_PHRASES only matches specific
        # short evasive closers, not an apology/refusal sentence. That meant a refusal from
        # the model (spontaneous, or from a query that landed here after a routing misclassification)
        # was passed straight through to the user as the entire response. Kept narrow (anchored at
        # the start, capped length, no code fence) so a long legitimate answer that happens to
        # contain "sorry" in passing is never mistaken for a refusal.
        _REFUSAL_PHRASES = re.compile(
            r"^(i'?m sorry,?\s*but\s*i\s*(?:can'?t|cannot|won'?t|am unable to)|"
            r"i\s*(?:can'?t|cannot|won'?t|am unable to)\s*(?:assist|help|comply|continue|do that|fulfill)|"
            r"as an ai(?:\s*language model)?,?\s*i\s*(?:can'?t|cannot)|"
            r"i\s*apologi[sz]e,?\s*but)",
            re.IGNORECASE
        )
        _is_refusal = len(cleaned_answer) < 300 and "```" not in cleaned_answer and bool(_REFUSAL_PHRASES.match(cleaned_answer))
        _is_collapsed = (
            len(cleaned_answer) < 5
            or bool(_EVASION_PHRASES.match(cleaned_answer))
            or _is_refusal
        )
        
        if _is_collapsed:
            logger.warning(f"[Completeness] {'Refusal' if _is_refusal else 'Evasion-loophole'} detected. Visible output too thin ({len(cleaned_answer)} chars). Attempting recovery.")
            yield {"type": "clear"}
            yield {"type": "status", "content": "Retrying for complete response..."}
            
            _assistant_context = visible_answer
            if thought_clean:
                _assistant_context = f"<think>{thought_clean}</think>\n{cleaned_answer}"
                
            _retry_nudge = (
                "Your previous reply was a refusal, but this is an ordinary, benign request with "
                "nothing sensitive about it. Please provide the actual, complete answer now outside "
                "of any <think> tags. Do not skip or abbreviate."
                if _is_refusal else
                "Your previous response was incomplete — it only contained a thought process or closing phrase without the actual answer. "
                "Please provide the FULL, complete explanation now outside of any <think> tags. Do not skip or abbreviate."
            )
            retry_msgs = optimized + [
                {"role": "assistant", "content": _assistant_context},
                {"role": "user", "content": _retry_nudge}
            ]
            retry_full = ""
            retry_thought = ""
            for ev in _stream_tokens(ModelRole.REASONING, retry_msgs, max_tokens=_r_tokens, temperature=0.5, think_mode="show"):
                if user_lang == "English" or ev["type"] != "token":
                    yield ev
                if ev["type"] == "token":
                    retry_full += ev["content"]
                elif ev["type"] == "thinking":
                    retry_thought += ev["content"]
                    
            # Use the retry answer; combine think from both rounds
            retry_answer = retry_full.strip()
            retry_answer = re.sub(r'</?think>', '', retry_answer, flags=re.IGNORECASE).strip()
            
            retry_answer = re.sub(r'```[\s\S]*?(?:```|$)', '', retry_answer, flags=re.IGNORECASE)
            retry_answer = re.sub(r'</?span[\s\S]*?(?:>|&gt;|$)', '', retry_answer, flags=re.IGNORECASE)
            retry_answer = re.sub(r'&lt;/?span[\s\S]*?(?:>|&gt;|$)', '', retry_answer, flags=re.IGNORECASE).strip()
            
            if retry_answer:
                cleaned_answer = _quality_guard(retry_answer)
            # Merge retry thought into thought_clean for the final raw_response
            if retry_thought.strip():
                retry_thought_clean = re.sub(r'</?think>', '', retry_thought, flags=re.IGNORECASE).strip()
                thought_clean = (thought_clean + "\n\n[Retry]\n" + retry_thought_clean).strip()
    finally:
        if not _keep_loaded:
            unload_model()

    # --- Translation (only translate the visible answer, not think blocks) ---
    user_lang = (settings.get("user_lang") if settings else None) or detect_user_language(user_query)
    if user_lang != "English" and cleaned_answer:
        from src.iris_engine import translate_text
        yield {"type": "status", "content": f"Translating to {user_lang}..."}
        cleaned_answer = translate_text(cleaned_answer, user_lang)

    # --- Build final combined output for display ---
    # Re-assemble: think block (always English) + translated visible answer
    display_content = ""
    if thought_clean:
        display_content = f"<think>\n{thought_clean}\n</think>\n\n{cleaned_answer}"
    else:
        display_content = cleaned_answer

    if display_content:
        yield {"type": "clear"}
        yield {"type": "token", "content": display_content}
        
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
                
    yield {"type": "raw_response", "content": display_content}
