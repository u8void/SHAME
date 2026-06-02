"""
src/__init__.py
Public API surface for the Iris AI source package.
Import everything consumers need from the src/ submodules.
"""

from .iris import (
    ask_stream,
    load_model,
    unload_model,
    generate_reply,
    solve_math,
    analyze_image,
    BookRetriever,
    ModelRole,
    TaskType,
    get_device,
    load_generation_config,
)
from .syntax_checker import check_syntax, extract_code_blocks
from .iris_pro import IrisPro  # noqa: F401 — re-exported for convenience
