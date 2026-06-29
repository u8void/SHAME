import logging
from typing import Generator, Dict, Any
from src.iris_engine import ModelRole, load_model, unload_model, _keep_loaded

logger = logging.getLogger('iris')

def get_control_prompt(identity: str = "") -> str:
    return "You are the Iris AI Control node."

def run_stream(user_query: str, history: list, retriever: Any, settings: dict) -> Generator[Dict[str, str], None, None]:
    from src.controller import _oi, OI_AVAILABLE, _prime_oi_with_3b

    if not OI_AVAILABLE:
        err_msg = "Open Interpreter is not available. Please install it with `pip install open-interpreter`."
        yield {"type": "token", "content": err_msg}
        yield {"type": "raw_response", "content": err_msg}
        return

    # Initialize the Open Interpreter model wrapper
    yield {"type": "status", "content": "Initializing Open Interpreter..."}
    _prime_oi_with_3b()

    _oi.messages = []
    
    # 1. RAG
    context = ""
    if retriever is not None and len(user_query.split()) >= 6:
        context = retriever.retrieve(user_query, top_k=1, category="control")

    task = user_query
    if context:
        task = f"<retrieved_context>\n{context}\n</retrieved_context>\n\nTask: {user_query}"

    # 2. History injection
    if history:
        recent = "\n".join([f"{m['role']}: {m['content']}" for m in history[-2:]])
        task = f"Recent context:\n{recent}\n\nTask: {task}"

    full_response = ""
    yield {"type": "status", "content": "Executing via Open Interpreter..."}

    try:
        for chunk in _oi.chat(task, display=True, stream=True, blocking=True):
            if not isinstance(chunk, dict):
                continue
                
            chunk_type = chunk.get("type", "")
            role = chunk.get("role", "")
            content = chunk.get("content", "")
            
            text_to_yield = ""
            
            if chunk_type == "message" and role == "assistant":
                if isinstance(content, str) and content:
                    text_to_yield = content
            elif chunk_type == "console" and chunk.get("format") == "output" and content:
                text_to_yield = f"\n```\n{content}\n```\n"
            elif role == "computer" and content:
                if isinstance(content, list):
                    for item in content:
                        out = item.get("output", item.get("content", "")) if isinstance(item, dict) else ""
                        if out:
                            text_to_yield += f"\n```\n{out}\n```\n"
                elif isinstance(content, str) and content:
                    text_to_yield = f"\n```\n{content}\n```\n"
                    
            if text_to_yield:
                full_response += text_to_yield
                yield {"type": "token", "content": text_to_yield}

    except Exception as e:
        logger.error(f"[OI Control] Error: {e}")
        yield {"type": "token", "content": f"\nExecution Error: {e}\n"}
        full_response += f"\nError: {e}"

    if not _keep_loaded:
        unload_model()

    if not full_response.strip():
        full_response = "Task completed."
        yield {"type": "token", "content": full_response}

    yield {"type": "raw_response", "content": full_response}
