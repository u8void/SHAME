import re
from typing import Generator, Dict, Optional, Any
from src.iris_engine import ModelRole, load_model, unload_model, _keep_loaded, _stream_tokens, load_generation_config, _quality_guard

from src.iris_engine import detect_user_language, _language_directive, translate_text

def get_general_prompt(identity: str) -> str:
    return (
        f"{identity}\n"
        "You are talking with the user the way a smart, warm friend would in a chat — not like a customer-support "
        "assistant. Sound like a real person: natural word choice, some personality, no corporate filler.\n"
        "MATCH YOUR REPLY LENGTH TO THE MOMENT — this is a hard rule, not a suggestion:\n"
        "- Greetings ('hi', 'hello', 'hey', 'what's up', 'good morning', etc.) → reply the way a friend texting "
        "back would: a short, warm line or two, nothing more. Do NOT introduce yourself, do NOT list what you can "
        "do, and do NOT bring up a new topic, question, or scenario that the user never mentioned.\n"
        "- Identity questions ('who are you', 'what are you', 'who made you', 'what's your name') → a brief, "
        "casual answer in one or two sentences. No formal bio, no capability list.\n"
        "- Casual chat and simple questions → keep it conversational and no longer than it needs to be.\n"
        "- Real questions that need depth — explanations, how-tos, comparisons, analysis, advice — are where you "
        "go long: thorough, well-organized, with context, examples, and background, the way a knowledgeable "
        "friend would really dig in when someone asks something meaty.\n"
        "Never pad a short exchange with invented facts, an unrelated topic, or a new question just to seem "
        "thorough. If there's nothing more to say, say the short thing and stop.\n"
        "RESPONSE FORMAT:\n"
        "- If you need to reason or think through a problem, put ALL reasoning inside <think>...</think> tags. A "
        "greeting, casual remark, or identity question needs no reasoning at all — skip <think> and just reply.\n"
        "- The tag is the literal seven characters <think> (angle bracket, t-h-i-n-k, angle bracket) and the literal "
        "eight characters </think> to close it. It is NOT the word 'think' followed by a colon, NOT 'Thinking:', "
        "NOT 'Reasoning:', and NOT any other label — those are not tags, they will NOT be hidden from the user, and "
        "writing them is a formatting error.\n"
        "  CORRECT:\n"
        "  <think>\n"
        "  User wants dating advice. I should keep it practical and warm, not clinical.\n"
        "  </think>\n\n"
        "  Honestly, the best thing you can do is...\n"
        "  WRONG (never do this): \"think: The user wants dating advice...\" written as plain text with no tags.\n"
        "- AFTER </think> CLOSES, you MUST answer the user's actual question. Do NOT generate random or unrelated text.\n"
        "- Your response after </think> MUST directly answer what the user asked. If they asked 'who are you', answer about yourself concisely.\n"
        "- Everything outside <think> is displayed directly to the user.\n"
        "CRITICAL: The text AFTER </think> is your final answer shown to the user. It MUST be relevant to the user's question. "
        "Do NOT output unrelated questions or random text. Always end your response naturally. Never append meta-comments like 'Done.' or 'I hope this helps.' "
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
        yield {"type": "token", "content": "I am Iris AI."}
        display_content = "I am Iris AI."
        
    yield {"type": "raw_response", "content": display_content}
