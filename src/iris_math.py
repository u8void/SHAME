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
        "Use precise notation. Put your final answer within \\boxed{}. "
        "ANTI-POLLUTION RULE: If your solution requires writing code (like Python or C++), "
        "DO NOT use LaTeX or MathJax formatting (like $...$ or _{...}) inside the code block. "
        "Variable names and function names inside code must be plain ASCII identifiers only. "
        "LaTeX notation (\\boxed{}, $...$) is ONLY for the mathematical explanation text outside code blocks. "
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
    full = ""
    for ev in _stream_tokens(ModelRole.MATH, optimized, max_tokens=4096, temperature=0.2, think_mode="show"):
        if user_lang == "English" or ev["type"] != "token":
            yield ev
        if ev["type"] == "token":
            full += ev["content"]

    if not _keep_loaded:
        unload_model()

    user_lang = (settings.get("user_lang") if settings else None) or detect_user_language(user_query)
    if user_lang != "English" and full:
        from src.iris_engine import translate_text
        yield {"type": "status", "content": f"Translating to {user_lang}..."}
        translated = translate_text(full, user_lang)
        full = translated
        yield {"type": "clear"}
        yield {"type": "token", "content": full}

    yield {"type": "raw_response", "content": full}
