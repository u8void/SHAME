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

    from src.iris_engine import TaskType, ModelRole, _keep_loaded
    import src.iris_engine
    src.iris_engine._keep_loaded = keep_loaded

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
            task_type, direct_answer = classify_task(original_query, history)
    else:
        from src.iris_triage import classify_task
        task_type, direct_answer = classify_task(original_query, history)
    
    if task_type == TaskType.CONTROL:
        from src.iris_control import run_stream
        yield from run_stream(user_query, history, retriever, settings)
        return
        
    if task_type == TaskType.SEARCH:
        from src.iris_reasoning import run_stream
        yield from run_stream(user_query, history, retriever, settings, do_search=True, direct_answer=direct_answer)
        return

    if task_type is None:
        if direct_answer:
            from src.iris_engine import _quality_guard
            cleaned = _quality_guard(direct_answer)
            yield {"type": "token", "content": cleaned}
            yield {"type": "raw_response", "content": cleaned}
        return
        
    yield {"type": "status", "content": f"Task: {task_type.value.upper()}"}

    if task_type == TaskType.GENERAL:
        from src.iris_general import run_stream
        yield from run_stream(user_query, history, retriever, settings)
    elif task_type == TaskType.REASONING:
        from src.iris_reasoning import run_stream
        yield from run_stream(user_query, history, retriever, settings, do_search=False)
    elif task_type == TaskType.MATH:
        from src.iris_math import run_stream
        yield from run_stream(user_query, history, retriever, settings)
    elif task_type == TaskType.CODING_SIMPLE:
        from src.iris_coding import run_stream
        yield from run_stream(user_query, history, retriever, settings, is_complex=False)
    elif task_type == TaskType.CODING_COMPLEX:
        from src.iris_coding import run_stream
        yield from run_stream(user_query, history, retriever, settings, is_complex=True)
