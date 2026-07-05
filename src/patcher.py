import re
import logging

logger = logging.getLogger(__name__)

def apply_patch(original_code: str, patch_text: str) -> str:
    """
    Applies an Aider-style SEARCH/REPLACE block to the original_code.
    Uses fuzzy whitespace-agnostic matching to ensure stability even if the model
    messes up indentation or newlines.
    """
    import re
    
    # Aggressively strip any number of carets, equal signs, or whitespace from boundaries
    patch_text = patch_text.strip()
    patch_text = patch_text.strip("<").strip(">").strip()
        
    # Split on 3 or more equal signs
    parts = re.split(r'={3,}', patch_text, maxsplit=1)
    if len(parts) < 2:
        logger.warning("[Patcher] '===' separator not found in patch.")
        return original_code
        
    search_block = parts[0].strip("\n")
    replace_block = parts[1].strip("\n")
    
    def strip_fences(text):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines.pop(0)
        if lines and lines[-1].strip().startswith("```"):
            lines.pop()
        return "\n".join(lines)
        
    search_block = strip_fences(search_block)
    replace_block = strip_fences(replace_block)
    
    # 1. Exact Match
    if search_block and search_block in original_code:
        return original_code.replace(search_block, replace_block, 1)
        
    # 2. Fuzzy Match (line-by-line whitespace-agnostic)
    orig_lines = original_code.splitlines()
    search_lines = search_block.splitlines()
    
    while search_lines and not search_lines[0].strip():
        search_lines.pop(0)
    while search_lines and not search_lines[-1].strip():
        search_lines.pop()
        
    if not search_lines:
        return original_code
        
    def normalize(s):
        return " ".join(s.split())
        
    norm_search = [normalize(l) for l in search_lines]
    
    for i in range(len(orig_lines) - len(search_lines) + 1):
        match = True
        for j in range(len(search_lines)):
            if normalize(orig_lines[i+j]) != norm_search[j]:
                match = False
                break
        if match:
            # Found fuzzy match! Replace the matched lines.
            new_lines = orig_lines[:i] + replace_block.splitlines() + orig_lines[i+len(search_lines):]
            return "\n".join(new_lines)
            
    logger.warning("[Patcher] Match failed entirely. Original code returned.")
    return original_code
