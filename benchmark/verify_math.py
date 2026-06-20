

import re
import math
import time
from typing import Tuple, Optional




def sandbox_compute_arithmetic(problem: str) -> Optional[float]:
    
    
    
    m = re.search(
        r'(?:what is|calculate|compute|find|evaluate|how many|how much)\s+'
        r'([^?]+?)\s*\??$',
        problem, re.IGNORECASE
    )
    if not m:
        return None

    expr = m.group(1).strip()
    
    
    
    cleaned = re.sub(r'[a-zA-Z]', '', expr)
    
    safe = ''.join(c for c in cleaned if c in '0123456789.+-*/() ')
    safe = safe.strip()
    
    if not safe or not any(c.isdigit() for c in safe):
        return None
    
    
    if len(safe) > 60:  
        return None
    
    try:
        safe = safe.replace(' ', '')
        result = eval(safe, {"__builtins__": {}}, {})
        if isinstance(result, (int, float)) and math.isfinite(result):
            return float(result)
    except Exception:
        pass
    
    return None




VERIFY_PROMPT = """You are a math grader. Review the solution below and determine if the final answer is correct.

PROBLEM:
{problem}

SOLUTION:
{solution}

INSTRUCTIONS:
1. Re-derive the answer independently from the problem (do not just re-read the solution)
2. If the answer in the solution is correct, output: CORRECT
3. If the answer is wrong, output: WRONG: <the correct answer> inside \\boxed{{}}
4. If you cannot determine, output: UNCERTAIN

Your response:"""


def verify_with_model(solution: str, problem: str,
                      model_callable) -> Tuple[str, bool]:
    
    prompt = VERIFY_PROMPT.format(problem=problem, solution=solution)
    
    try:
        verification = model_callable(prompt)
        
        
        if verification.startswith("CORRECT") or "CORRECT" in verification[:20]:
            return solution, False
        
        
        boxed = _extract_boxed(verification)
        if boxed:
            
            corrected = f"{solution}\n\n[Self-Verification: original answer was incorrect.]\nCorrected answer: \\boxed{ {boxed}} "
            return corrected, True
            
    except Exception:
        pass
    
    return solution, False




def detect_off_by_factor(expected: Optional[float],
                          actual: Optional[float]) -> Optional[float]:
    
    if expected is None or actual is None:
        return None
    if expected == 0:
        return None

    ratio = actual / expected
    
    
    for factor in [0.001, 0.01, 0.1, 10, 100, 1000]:
        if math.isclose(ratio, factor, rel_tol=0.05):
            return expected
    
    
    
    if math.isclose(ratio, 10, rel_tol=0.05):
        return expected
    if math.isclose(ratio, 0.1, rel_tol=0.05):
        return expected
    
    return None




def clean_answer(text: str) -> str:
    
    text = text.strip()
    
    
    if re.match(r'^\d+\.$', text):
        text = text[:-1]
    
    
    text = text.strip()
    
    
    try:
        val = float(text.replace(',', ''))
        if val == int(val) and '.' in text:
            text = str(int(val))
    except ValueError:
        pass
    
    return text




def _extract_boxed(text: str) -> Optional[str]:
    
    idx = text.rfind(r"\boxed{")
    if idx == -1:
        return None
    start = idx + 7
    braces = 1
    content = []
    for char in text[start:]:
        if char == "{":
            braces += 1
        elif char == "}":
            braces -= 1
        if braces == 0:
            break
        content.append(char)
    if braces == 0:
        return "".join(content).strip()
    return None




def verify_and_refine(solution: str, problem: str,
                       sandbox_first: bool = True,
                       keep_loaded: bool = False) -> Tuple[str, bool]:
    
    original = solution
    was_corrected = False
    
    
    if sandbox_first:
        ground = sandbox_compute_arithmetic(problem)
        if ground is not None:
            boxed = _extract_boxed(solution)
            if boxed:
                try:
                    boxed_val = float(boxed.replace(',', ''))
                    if math.isclose(boxed_val, ground, rel_tol=1e-6, abs_tol=1e-9):
                        
                        pass
                    else:
                        ground_int = int(ground) if (math.isfinite(ground) and math.isclose(ground, round(ground), abs_tol=1e-9)) else ground
                        corrected = solution.replace(boxed, str(ground_int), 1)
                        return corrected, True
                except ValueError:
                    pass

    
    boxed = _extract_boxed(solution)
    if boxed:
        cleaned = clean_answer(boxed)
        if cleaned != boxed:
            solution = solution.replace(boxed, cleaned, 1)
            was_corrected = True
    
    
    
    
    
    
    solution = re.sub(r'(\d+)\.(\s|$)', r'\1\2', solution)
    
    return solution, (solution != original)


__all__ = [
    "verify_and_refine",
    "sandbox_compute_arithmetic",
    "clean_answer",
    "detect_off_by_factor",
]
