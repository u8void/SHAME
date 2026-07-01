import re
from typing import Generator, Dict, Any
from src.iris_engine import ModelRole, load_model, unload_model, _keep_loaded, _stream_tokens, load_generation_config
from src.iris_engine import detect_user_language, _language_directive


def get_math_prompt(identity: str) -> str:
    return (
        f"{identity}\n"
        "You are the Iris AI Math Core. Solve mathematical and algorithmic problems with precision. "
        "RESPONSE FORMAT:\n"
        "- Put ALL your step-by-step reasoning, work, and derivations inside <think>...</think> tags.\n"
        "- After </think>, output ONLY the clean final solution and answer. Everything outside </think> is shown directly to the user.\n"
        "LATEX FORMATTING RULES:\n"
        "1. You MUST use FULL, flawless LaTeX for all mathematics.\n"
        "2. For inline math, ALWAYS use $...$ (never \\( ... \\)). Do NOT put spaces inside the delimiters (e.g., $x$ not $ x $).\n"
        "3. For display math, ALWAYS use $$...$$ on their own separate lines (never \\[ ... \\]).\n"
        "4. If using environments like \\begin{align} or \\begin{cases}, they MUST be wrapped inside $$...$$ blocks.\n"
        "5. Keep the explanation outside the <think> tags clean, elegant, and highly professional.\n"
        "6. Use standard LaTeX \\boxed{} to highlight your final answer. DO NOT use HTML, CSS, or markdown formatting hacks.\n"
        "STRICT NO-CODE RULE:\n"
        "You MUST solve the problem purely using mathematical reasoning and analytical derivations. DO NOT write any Python code, scripts, HTML, or programmatic verifications. Code blocks (```) are STRICTLY FORBIDDEN."
    )


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
    final_query += "\n\nCRITICAL INSTRUCTION: You MUST solve this problem purely analytically. DO NOT write any Python code, sympy scripts, or code blocks. DO NOT use HTML/CSS styling or any HTML tags (like <span>). Use standard LaTeX \\boxed{} for your final answer."


    # 2. History & Compaction
    optimized = [{"role": "user", "content": final_query}]
    if history:
        optimized = [{"role": m["role"], "content": m["content"]} for m in history] + optimized

    # 3. Generation — model thinks and solves, no preemptive interception
    user_lang = (settings.get("user_lang") if settings else None) or detect_user_language(user_query)
    full = ""
    thought_process = ""
    try:
        for ev in _stream_tokens(ModelRole.MATH, optimized, max_tokens=8192, temperature=0.2, think_mode="show"):
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
    # Strip any rogue HTML span tags (both raw and HTML-encoded), handling typos
    visible_answer = re.sub(r'</?span[\s\S]*?(?:>|&gt;|$)', '', visible_answer, flags=re.IGNORECASE)
    visible_answer = re.sub(r'&lt;/?span[\s\S]*?(?:>|&gt;|$)', '', visible_answer, flags=re.IGNORECASE).strip()

    from src.iris_engine import _quality_guard
    cleaned = _quality_guard(visible_answer) if visible_answer else ""

    if user_lang != "English" and cleaned:
        from src.iris_engine import translate_text
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
