import re
from typing import Generator, Dict, Optional, Any
from src.iris_engine import ModelRole, load_model, unload_model, _keep_loaded, _stream_tokens, load_generation_config, _quality_guard

from src.iris_engine import detect_user_language, _language_directive

def get_general_prompt(identity: str) -> str:
    return (
        f"{identity}\n"
        "You are the Iris AI General node. You are a versatile, highly intelligent conversational assistant. "
        "You should be helpful, friendly, and thorough. Always provide detailed, comprehensive explanations. "
        "Do not give short or brief answers - take the time to fully explain concepts, provide context, "
        "examples, and background information. The user appreciates depth and completeness.\n"
        "RESPONSE FORMAT:\n"
        "- If you need to reason or think through a problem, put ALL reasoning inside <think>...</think> tags.\n"
        "- After </think>, output a well-structured, detailed response. Use paragraphs, bullet points, "
        "or numbered lists as appropriate to organize your explanation.\n"
        "- Everything outside </think> is displayed directly to the user.\n"
        "IMPORTANT: Always end your response naturally. Never append meta-comments like 'Done.' or 'I hope this helps.' "
        "If you don't know the answer, just say so."
    )

def run_stream(user_query: str, history: list, retriever: Any, settings: dict) -> Generator[Dict[str, str], None, None]:
    import logging
    logger = logging.getLogger('iris')

    web_context = ""

    yield {"type": "status", "content": "Thinking..."}
    
    # 1. RAG
    context = ""
    if retriever is not None and len(user_query.split()) >= 3:
        # Avoid RAG for short contextual queries like "what about him?"
        is_contextual = False
        if history:
            pronouns = re.compile(r'\b(he|him|his|she|her|it|its|they|them|this|that)\b', re.IGNORECASE)
            if len(user_query.split()) < 6 or pronouns.search(user_query):
                is_contextual = True
        
        if not is_contextual:
            context = retriever.retrieve(user_query, top_k=3, category="general")
            
    final_query = user_query
    if context:
        final_query = (
            f"<retrieved_context>\n{context}\n</retrieved_context>\n\n"
            f"If the retrieved context is relevant, use it. Otherwise, ignore it.\n\n"
            f"{final_query}"
        )
        
    if web_context and "(No web results found" not in web_context and "Web search unavailable" not in web_context:
        final_query = (
            f"<search_results>\n{web_context}\n</search_results>\n\n"
            f"User Query:\n{final_query}\n\n"
            f"INSTRUCTIONS: Use the search results above to inform your answer, especially for recent events or specific facts. "
            f"If the search results are incomplete, you may use your internal knowledge to supplement the answer."
        )

    final_query += _language_directive(user_query, role=ModelRole.GENERAL)
    
    # 2. History & Compaction
    optimized = [{"role": "user", "content": final_query}]
    if history:
        optimized = [{"role": m["role"], "content": m["content"]} for m in history] + optimized
    # 3. Generation
    user_lang = (settings.get("user_lang") if settings else None) or detect_user_language(user_query)
    full = ""
    thought_process = ""
    try:
        for ev in _stream_tokens(ModelRole.GENERAL, optimized, max_tokens=8192, temperature=0.6, think_mode="show"):
            if user_lang == "English" or ev["type"] != "token":
                yield ev
            if ev["type"] == "token":
                full += ev["content"]
            elif ev["type"] == "thinking":
                thought_process += ev["content"]
    finally:
        if not _keep_loaded:
            unload_model()

    # Strip any leaked <think>/<\/think> tags from thought_process since _stream_tokens
    # may yield a synthetic "</think>" as a thinking event when the model stops mid-think.
    thought_clean = thought_process.strip()
    thought_clean = re.sub(r'</?think>', '', thought_clean, flags=re.IGNORECASE).strip()
    thought_clean = re.sub(r'<\|?/?thought(?:_(?:start|end))?\|?>', '', thought_clean, flags=re.IGNORECASE).strip()

    # Strip any leaked think tags from the visible answer
    visible_answer = full.strip()
    visible_answer = re.sub(r'</?think>', '', visible_answer, flags=re.IGNORECASE).strip()
    
    cleaned = _quality_guard(visible_answer) if visible_answer else ""
    
    # Translate only the visible answer (not think blocks)
    user_lang = (settings.get("user_lang") if settings else None) or detect_user_language(user_query)
    if user_lang != "English" and cleaned:
        from src.iris_engine import translate_text
        yield {"type": "status", "content": f"Translating to {user_lang}..."}
        cleaned = translate_text(cleaned, user_lang)

    # Build final display: think block (always English) + translated answer
    display_content = ""
    if thought_clean:
        display_content = f"<think>\n{thought_clean}\n</think>\n\n{cleaned}"
    else:
        display_content = cleaned
    
    if display_content:
        yield {"type": "clear"}
        yield {"type": "token", "content": display_content}
    elif not thought_clean:
        yield {"type": "token", "content": "I'm Iris AI."}
        display_content = "I'm Iris AI."
        
    yield {"type": "raw_response", "content": display_content}
