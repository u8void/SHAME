import re
from typing import Generator, Dict, Optional, Any
from src.iris_engine import ModelRole, load_model, unload_model, _keep_loaded, _stream_tokens, load_generation_config, _quality_guard

from src.iris_engine import detect_user_language, _language_directive

def get_general_prompt(identity: str) -> str:
    return (
        f"{identity}\n"
        "You are the Iris AI General node. You are a versatile, highly intelligent conversational assistant. "
        "You should be helpful, friendly, and concise unless a detailed answer is needed. "
        "IMPORTANT: Always end your response naturally. Never append meta-comments like 'Done.' or 'I hope this helps.' "
        "If you don't know the answer, just say so."
    )

def run_stream(user_query: str, history: list, retriever: Any, settings: dict) -> Generator[Dict[str, str], None, None]:
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
        
    final_query += _language_directive(user_query)
    
    # 2. History & Compaction
    optimized = [{"role": "user", "content": final_query}]
    if history:
        optimized = [{"role": m["role"], "content": m["content"]} for m in history] + optimized
    # 3. Generation
    full = ""
    thought_process = ""
    for ev in _stream_tokens(ModelRole.GENERAL, optimized, max_tokens=4096, temperature=0.6, think_mode="show"):
        yield ev
        if ev["type"] == "token":
            full += ev["content"]
        elif ev["type"] == "thinking":
            thought_process += ev["content"]
            
    if not _keep_loaded:
        unload_model()
        
    cleaned = _quality_guard(full)
    if full and cleaned and cleaned != full:
        yield {"type": "clear"}
        yield {"type": "token", "content": cleaned}
        
    final_content = ""
    if thought_process:
        final_content += f"<think>\n{thought_process.strip()}\n</think>\n"
    if cleaned:
        final_content += cleaned
    elif not thought_process:
        final_content = "I'm Iris AI."
        
    yield {"type": "raw_response", "content": final_content}
