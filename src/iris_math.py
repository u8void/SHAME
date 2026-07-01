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
        "- After </think>, output ONLY the clean final solution and answer. Do NOT include 'Step-by-Step:' or "
        "reasoning headers outside of think tags. Everything outside </think> is shown directly to the user.\n"
        "Use precise notation. Always wrap your final answer and mathematical expressions in LaTeX delimiters (e.g., $$ answer $$ or $ answer $). Everything outside </think> should be clear, elegant, and well-formatted. "
        "ANTI-POLLUTION RULE: If your solution requires writing code (like Python or C++), "
        "DO NOT use LaTeX or MathJax formatting (like $...$ or _{...}) inside the code block. "
        "Variable names and function names inside code must be plain ASCII identifiers only. "
        "LaTeX notation ($...$) is ONLY for the mathematical explanation text outside code blocks. "
        "IMPORTANT: For display math blocks, you MUST use $$ ... $$ and NEVER use \\[ ... \\]."
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

    # 2. History & Compaction
    optimized = [{"role": "user", "content": final_query}]
    if history:
        optimized = [{"role": m["role"], "content": m["content"]} for m in history] + optimized

    # 3. Generation — model thinks and solves, no preemptive interception
    user_lang = (settings.get("user_lang") if settings else None) or detect_user_language(user_query)
    math_output = ""
    
    yield {"type": "status", "content": "Calculating math..."}
    try:
        for ev in _stream_tokens(ModelRole.MATH, optimized, max_tokens=4096, temperature=0.2, think_mode="pass"):
            if ev["type"] == "token":
                math_output += ev["content"]
    finally:
        if not _keep_loaded:
            unload_model()

    yield {"type": "status", "content": "Explaining solution..."}
    explanation_prompt = (
        f"The user asked the following math problem: {user_query}\n\n"
        f"The math core calculated the following step-by-step solution:\n{math_output}\n\n"
        f"Please explain this solution to the user clearly and in a friendly way. "
        f"Do NOT use bounding boxes (like \\boxed{{}}) as they cause formatting conflicts. "
        f"Use clean LaTeX for math. Put your reasoning inside <think>...</think> tags, and your final explanation outside."
    )
    
    gen_optimized = [{"role": "user", "content": explanation_prompt}]
    if history:
        gen_optimized = [{"role": m["role"], "content": m["content"]} for m in history] + gen_optimized

    gen_full = ""
    try:
        for ev in _stream_tokens(ModelRole.GENERAL, gen_optimized, max_tokens=4096, temperature=0.4, think_mode="show"):
            if user_lang == "English" or ev["type"] != "token":
                yield ev
            if ev["type"] == "token":
                gen_full += ev["content"]
    finally:
        if not _keep_loaded:
            unload_model()

    if user_lang != "English" and gen_full:
        from src.iris_engine import translate_text
        yield {"type": "status", "content": f"Translating to {user_lang}..."}
        translated = translate_text(gen_full, user_lang)
        gen_full = translated
        yield {"type": "clear"}
        yield {"type": "token", "content": gen_full}

    yield {"type": "raw_response", "content": gen_full}
