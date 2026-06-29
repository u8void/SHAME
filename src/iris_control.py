import logging
from typing import Generator, Dict, Any
from src.iris_engine import unload_model, _keep_loaded

logger = logging.getLogger('iris')

def get_control_prompt(identity: str = "") -> str:
    return "You are the Iris AI Control node."

def run_stream(user_query: str, history: list, retriever: Any, settings: dict) -> Generator[Dict[str, str], None, None]:
    from src.controller import _prime_oi_with_control, _oi, OI_AVAILABLE

    if not OI_AVAILABLE:
        yield {"type": "status", "content": "Open Interpreter is unavailable."}
        yield {"type": "token", "content": "Open Interpreter is not installed or available."}
        return

    # 1. RAG (Optional for control, but included for completeness)
    context = ""
    if retriever is not None and len(user_query.split()) >= 3:
        if len(user_query.split()) >= 6:
            context = retriever.retrieve(user_query, top_k=1, category="control")
            
    final_query = user_query
    if context:
        final_query = (
            f"<retrieved_context>\n{context}\n</retrieved_context>\n\n"
            f"If the retrieved context is relevant, use it. Otherwise, ignore it.\n\n"
            f"{final_query}"
        )
        
    yield {"type": "status", "content": "Routing task to Open Interpreter..."}
    _prime_oi_with_control()
    
    _oi.messages = []
    if history:
        # We inject the last 2 interactions so it has context for actions like "close it"
        recent = history[-2:]
        for m in recent:
            _oi.messages.append({"role": m["role"], "type": "message", "content": m["content"]})
    
    yield {"type": "status", "content": "Executing command..."}
    
    output_text = ""
    try:
        for chunk in _oi.chat(final_query, display=True, stream=True, blocking=True):
            if not isinstance(chunk, dict):
                continue
            chunk_type = chunk.get("type", "")
            role = chunk.get("role", "")
            content = chunk.get("content", "")
            
            if chunk_type == "message" and role == "assistant":
                if isinstance(content, str) and content:
                    yield {"type": "token", "content": content}
                    output_text += content
            elif chunk_type == "console" and role == "computer":
                if chunk.get("format") == "output" and content:
                    out_str = str(content)
                    out_display = f"\n```\n{out_str}\n```\n"
                    yield {"type": "token", "content": out_display}
                    output_text += out_display
            elif role == "computer" and chunk_type == "code":
                code_str = str(content)
                code_display = f"\n```python\n{code_str}\n```\n"
                yield {"type": "token", "content": code_display}
                output_text += code_display
    except Exception as e:
        logger.error(f"[OI] chat error: {e}")
        err_msg = f"\nError: {e}"
        yield {"type": "token", "content": err_msg}
        output_text += err_msg

    if not _keep_loaded:
        unload_model()

    yield {"type": "action_result", "content": f"Task Executed via Open Interpreter.\nResult:\n{output_text}"}
    yield {"type": "raw_response", "content": output_text}
