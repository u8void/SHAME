import logging
from typing import Generator, Dict, Any
from src.iris_engine import ModelRole, load_model, unload_model, _keep_loaded

logger = logging.getLogger('iris')

def get_control_prompt(identity: str = "") -> str:
    return "You are the Iris AI Control node."

def run_stream(user_query: str, history: list, retriever: Any, settings: dict) -> Generator[Dict[str, str], None, None]:
    from src.controller import (
        _get_agent_system_prompt, parse_ai_response, execute_action_by_dict,
    )
    from src.system_actions import is_complex_control

    # 1. RAG (Optional for control, but included for completeness)
    context = ""
    if retriever is not None and len(user_query.split()) >= 3:
        # Avoid RAG for short commands like "open it"
        if len(user_query.split()) >= 6:
            context = retriever.retrieve(user_query, top_k=1, category="control")
            
    final_query = user_query
    if context:
        final_query = (
            f"<retrieved_context>\n{context}\n</retrieved_context>\n\n"
            f"If the retrieved context is relevant, use it. Otherwise, ignore it.\n\n"
            f"{final_query}"
        )
        
    yield {"type": "status", "content": "Generating computer command..."}
    control_messages = [{"role": "system", "content": _get_agent_system_prompt()}]
    
    # 2. History injection (if applicable for control tasks)
    if history:
        # We inject the last 2 interactions so it has context for actions like "close it"
        recent = history[-2:]
        control_messages += [{"role": m["role"], "content": m["content"]} for m in recent]
        
    enforcement_prompt = final_query + "\n\n[SYSTEM REMINDER: You MUST output a valid JSON object for the action. Do not reply in plain text.]"
    control_messages.append({"role": "user", "content": enforcement_prompt})
    
    if is_complex_control(user_query, history):
        logger.info("[Routing] Complex control detected. Loading 3B model (ModelRole.CODE) for control action.")
        control_llm = load_model(ModelRole.CODE)
    else:
        logger.info("[Routing] Simple control detected. Loading 0.5B model (ModelRole.CONTROL) for control action.")
        control_llm = load_model(ModelRole.CONTROL)
    
    action_json = ""
    for chunk in control_llm.create_chat_completion(messages=control_messages, max_tokens=1024, stream=True, temperature=0.1):
        delta = chunk["choices"][0].get("delta", {})
        if "content" in delta:
            action_json += delta["content"]

    if not _keep_loaded:
        unload_model()

    action_dict = parse_ai_response(action_json)
    if action_dict:
        action_name = action_dict.get("action", "unknown")
        yield {"type": "status", "content": f"Executing: {action_name}"}
        result = execute_action_by_dict(action_dict)
        reply_text = f"Action '{action_name}' executed.\n\nResult:\n{result}"
        yield {"type": "action_result", "content": f"Action '{action_name}' Executed.\nResult:\n{result}"}
        yield {"type": "token", "content": reply_text}
        yield {"type": "raw_response", "content": reply_text}
    else:
        fail_text = "I couldn't translate that into an action I can run. Could you rephrase it?"
        yield {"type": "status", "content": "Action failed to parse."}
        yield {"type": "token", "content": fail_text}
        yield {"type": "raw_response", "content": fail_text}
