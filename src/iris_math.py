import re
from typing import Generator, Dict, Any
from src.iris_engine import ModelRole, load_model, unload_model, _keep_loaded, _stream_tokens, load_generation_config
from src.iris_engine import detect_user_language, _language_directive
from src.iris_engine import _quality_guard, translate_text, _load_skill_prompt, ModelRole


def get_math_prompt(identity: str) -> str:
    prompt = _load_skill_prompt("math/math_prompt.txt", role=ModelRole.MATH)
    return f"{identity}\n{prompt}"


def run_stream(user_query: str, history: list, retriever: Any, settings: dict) -> Generator[Dict[str, str], None, None]:
    yield {"type": "status", "content": "Solving..."}

    # 1. RAG
    context = ""
    if retriever is not None and len(user_query.split()) >= 12:
        is_contextual = False
        if history:
            pronouns = re.compile(r'\b(he|him|his|she|her|it|its|they|them|this|that)\b', re.IGNORECASE)
            if len(user_query.split()) < 6 or pronouns.search(user_query):
                is_contextual = True

        if not is_contextual:
            context = retriever.retrieve(user_query, top_k=3, category="math")

    final_query = user_query
    
    if context:
        final_query = (
            f"<retrieved_context>\n{context}\n</retrieved_context>\n\n"
            f"If the retrieved context is relevant, use it. Otherwise, ignore it.\n\n"
            f"{final_query}"
        )

    final_query += _language_directive(user_query, role=ModelRole.MATH)
    final_query += "\n\nCRITICAL INSTRUCTION: You MUST solve this problem purely analytically. DO NOT write any Python code, sympy scripts, or code blocks. DO NOT use HTML tags like <span>, CSS styling, or \\boxed{}. Just write your final answer in clean plain LaTeX (e.g. $x = 5$ or $$x = 5$$)."

    # 2. History & Compaction
    optimized = [{"role": "user", "content": final_query}]
    if history:
        optimized = [{"role": m["role"], "content": m["content"]} for m in history] + optimized

    # 3. Silent Generation from Math Model (003)
    import logging
    logger = logging.getLogger('iris')
    
    math_tokens = []
    try:
        for ev in _stream_tokens(ModelRole.MATH, optimized, max_tokens=4096, temperature=0.2, think_mode="show"):
            if ev["type"] in ("token", "thinking"):
                math_tokens.append(ev["content"])
    except Exception as e:
        logger.warning(f"Math core (003) calculation failed: {e}")
    finally:
        if not _keep_loaded:
            unload_model()

    math_solution = "".join(math_tokens).strip()

    # 4. Fallback if Math model returned nothing
    if not math_solution:
        math_solution = "[No mathematical solution calculated by 003]"

    # 5. Explaining with General Model (005)
    yield {"type": "status", "content": "Explaining solution..."}

    general_query = (
        f"The math core model (003) solved the following mathematical problem:\n"
        f"User Query: {user_query}\n\n"
        f"Here are the verified calculations and reasoning from 003:\n"
        f"--- START CALCULATIONS ---\n"
        f"{math_solution}\n"
        f"--- END CALCULATIONS ---\n\n"
        f"Your job is to present and explain this solution clearly to the user. "
        f"CRITICAL: Do NOT re-derive the problem yourself. Do NOT second-guess or redo the math model's calculations. "
        f"Trust the work above as correct and focus entirely on explaining it in a clear, structured, and elegant way. "
        f"Use flawless LaTeX for all mathematical expressions."
    )

    general_messages = []
    if history:
        general_messages = [{"role": m["role"], "content": m["content"]} for m in history]
    general_messages.append({"role": "user", "content": general_query})

    user_lang = (settings.get("user_lang") if settings else None) or detect_user_language(user_query)
    full = ""
    thought_process = ""
    try:
        for ev in _stream_tokens(ModelRole.GENERAL, general_messages, max_tokens=8192, temperature=0.5, think_mode="show"):
            if user_lang == "English" or ev["type"] != "token":
                yield ev
            if ev["type"] == "token":
                full += ev["content"]
            elif ev["type"] == "thinking":
                thought_process += ev["content"]
    finally:
        if not _keep_loaded:
            unload_model()

    thought_clean = thought_process.strip()
    thought_clean = re.sub(r'</?think>', '', thought_clean, flags=re.IGNORECASE).strip()
    thought_clean = re.sub(r'<\|?/?thought(?:_(?:start|end))?\|?>', '', thought_clean, flags=re.IGNORECASE).strip()

    visible_answer = full.strip()
    visible_answer = re.sub(r'</?think>', '', visible_answer, flags=re.IGNORECASE).strip()
    
    # Strip any rogue markdown code blocks (to prevent file card rendering), even if unclosed
    visible_answer = re.sub(r'```[\s\S]*?(?:```|$)', '', visible_answer, flags=re.IGNORECASE)
    # Strip any HTML tags with their content (span, div, etc.) - aggressive cleanup
    visible_answer = re.sub(r'<(?:span|div|section|article)[^>]*>[\s\S]*?</(?:span|div|section|article)>', '', visible_answer, flags=re.IGNORECASE)
    # Also strip any remaining orphaned HTML tags
    visible_answer = re.sub(r'</?(?:span|div|section|article|style|script)[^>]*>', '', visible_answer, flags=re.IGNORECASE)
    # Strip HTML-encoded angle brackets
    visible_answer = re.sub(r'&lt;/?[\w]+[^&]*?&gt;', '', visible_answer, flags=re.IGNORECASE).strip()
    # Strip any remaining HTML tags
    visible_answer = re.sub(r'<[^>]+>', '', visible_answer).strip()

    cleaned = _quality_guard(visible_answer) if visible_answer else ""

    if user_lang != "English" and cleaned:
        yield {"type": "status", "content": f"Translating to {user_lang}..."}
        cleaned = translate_text(cleaned, user_lang)

    display_content = ""
    if thought_clean:
        display_content = f"<think>\n{thought_clean}\n</think>\n\n{cleaned}"
    else:
        display_content = cleaned

    if display_content:
        yield {"type": "clear"}
        yield {"type": "token", "content": display_content}

    yield {"type": "raw_response", "content": display_content}
