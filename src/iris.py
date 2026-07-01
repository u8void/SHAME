import re
import logging
from typing import Generator, Dict

logger = logging.getLogger('iris')

def ask_stream(
    user_query: str,
    history: list = None,
    stream: bool = True,
    retriever=None,
    settings: dict = None,
    force_role=None,
    keep_loaded: bool = False,
    **kwargs
) -> Generator[Dict[str, str], None, None]:
    if history is None:
        history = []
    
    # Asynchronously warm the OS page cache for the most common specialist models
    try:
        import threading
        from src.iris_engine import prefetch_model_file, _get_model_filename, ModelRole
        def _bg_prefetch():
            for r in [ModelRole.GENERAL, ModelRole.CODE]:
                try:
                    prefetch_model_file(_get_model_filename(r))
                except Exception:
                    pass
        threading.Thread(target=_bg_prefetch, daemon=True).start()
    except Exception:
        pass


    # Image checking and formatting
    original_query = user_query
    img_match = re.match(r'^\[IMAGE_UPLOADED:\s*(.+?)\]\s*(.*)$', user_query, flags=re.DOTALL)
    if img_match:
        image_path = img_match.group(1).strip()
        prompt = img_match.group(2).strip()
        if not prompt:
            prompt = "Describe this image in detail."
        yield {"type": "status", "content": "Analyzing image with Vision model..."}
        from src.iris_vision import analyze_image
        res = analyze_image(image_path, prompt, unload_after=not keep_loaded)
        
        try:
            import os
            os.unlink(image_path)
        except Exception:
            pass
            
        yield {"type": "token", "content": res}
        yield {"type": "raw_response", "content": res}
        return
    direct_answer = ""

    from src.iris_engine import TaskType, ModelRole, _keep_loaded, detect_user_language, translate_text
    import src.iris_engine
    src.iris_engine._keep_loaded = keep_loaded

    user_lang = detect_user_language(user_query)
    is_translated = False

    if user_lang and user_lang != "English":
        translated_query = translate_text(user_query, "English")
        if translated_query and translated_query != user_query:
            user_query = translated_query
            is_translated = True

        if history:
            translated_history = []
            for msg in history:
                role = msg.get("role")
                content = msg.get("content", "")
                if detect_user_language(content) != "English":
                    translated_content = translate_text(content, "English")
                else:
                    translated_content = content
                translated_history.append({"role": role, "content": translated_content})
            history = translated_history

    if force_role:
        if isinstance(force_role, str):
            try:
                force_role = ModelRole(force_role)
            except ValueError:
                pass
        
        # Map ModelRole to TaskType
        role_map = {
            ModelRole.CODE: TaskType.CODING_COMPLEX,
            ModelRole.MATH: TaskType.MATH,
            ModelRole.REASONING: TaskType.REASONING,
            ModelRole.GENERAL: TaskType.GENERAL,
            ModelRole.CONTROL: TaskType.CONTROL
        }
        task_type = role_map.get(force_role, None)
        if task_type is None:
            from src.iris_triage import classify_task
            task_type, direct_answer = classify_task(user_query, history)
    else:
        from src.iris_triage import classify_task
        task_type, direct_answer = classify_task(user_query, history)
    
    gen = None
    if task_type == TaskType.CONTROL:
        from src.iris_control import run_stream
        gen = run_stream(user_query, history, retriever, settings)
        
    elif task_type == TaskType.SEARCH:
        from src.iris_reasoning import run_stream
        gen = run_stream(user_query, history, retriever, settings, do_search=True, direct_answer=direct_answer)

    elif task_type is None:
        if direct_answer:
            from src.iris_engine import _quality_guard
            cleaned = _quality_guard(direct_answer)
            if is_translated:
                cleaned = translate_text(cleaned, user_lang)
            yield {"type": "token", "content": cleaned}
            yield {"type": "raw_response", "content": cleaned}
        return
    else:
        yield {"type": "status", "content": f"Task: {task_type.value.upper()}"}
        if task_type == TaskType.GENERAL:
            from src.iris_general import run_stream
            gen = run_stream(user_query, history, retriever, settings)
        elif task_type == TaskType.REASONING:
            from src.iris_reasoning import run_stream
            gen = run_stream(user_query, history, retriever, settings, do_search=False)
        elif task_type == TaskType.MATH:
            from src.iris_math import run_stream
            gen = run_stream(user_query, history, retriever, settings)
        elif task_type == TaskType.CODING_SIMPLE:
            from src.iris_coding import run_stream
            gen = run_stream(user_query, history, retriever, settings, is_complex=False)
        elif task_type == TaskType.CODING_COMPLEX:
            from src.iris_coding import run_stream
            gen = run_stream(user_query, history, retriever, settings, is_complex=True)

    if gen is not None:
        if not is_translated:
            yield from gen
        else:
            accumulated_response = ""
            for event in gen:
                ev_type = event.get("type")
                if ev_type == "token":
                    accumulated_response += event.get("content", "")
                elif ev_type == "raw_response":
                    pass
                else:
                    yield event
            
            if accumulated_response:
                yield {"type": "status", "content": f"Translating to {user_lang}..."}
                translated = translate_text(accumulated_response, user_lang)
                yield {"type": "clear"}
                yield {"type": "token", "content": translated}
                yield {"type": "raw_response", "content": translated}
