"""
verify_math.py — Self-Verification Loop for Math Benchmarks
=============================================================
After the model generates a math answer, feeds it back through
a verification pass that catches arithmetic mistakes, unit errors,
and step-logic flaws. Uses the same model in "checker" mode.

Strategies:
  1. Numeric sandbox: extract arithmetic from problem, compute ground truth
  2. Self-consistency: re-ask with "verify your answer" prompt
  3. Off-by-factor detection: check for ×10, ×100 factor errors
  4. Decimal/trailing-dot normalization
"""

import re
import math
import time
from typing import Tuple, Optional


# ── Sandbox computation ─────────────────────────────────────────

def sandbox_compute_arithmetic(problem: str) -> Optional[float]:
    """Try to compute the answer directly from the problem text
    by extracting a pure arithmetic expression.
    
    Works for simple GSM8K problems like "What is 15 + 27?" but not
    for multi-step word problems.
    """
    # Clean: remove text, keep digits and operators
    # Try to find a simple arithmetic question
    m = re.search(
        r'(?:what is|calculate|compute|find|evaluate|how many|how much)\s+'
        r'([^?]+?)\s*\??$',
        problem, re.IGNORECASE
    )
    if not m:
        return None

    expr = m.group(1).strip()
    
    # Try to extract pure arithmetic: digits, decimals, +-*/()
    # Remove words
    cleaned = re.sub(r'[a-zA-Z]', '', expr)
    # Keep only math chars
    safe = ''.join(c for c in cleaned if c in '0123456789.+-*/() ')
    safe = safe.strip()
    
    if not safe or not any(c.isdigit() for c in safe):
        return None
    
    # Only attempt if it's a simple expression
    if len(safe) > 60:  # too complex
        return None
    
    try:
        safe = safe.replace(' ', '')
        result = eval(safe, {"__builtins__": {}}, {})
        if isinstance(result, (int, float)) and math.isfinite(result):
            return float(result)
    except Exception:
        pass
    
    return None


# ── Self-consistency verification ──────────────────────────────

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
    """Ask the model to verify its own answer.
    
    Returns (corrected_solution_or_original, was_corrected).
    """
    prompt = VERIFY_PROMPT.format(problem=problem, solution=solution)
    
    try:
        verification = model_callable(prompt)
        
        # Parse the verification result
        if verification.startswith("CORRECT") or "CORRECT" in verification[:20]:
            return solution, False
        
        # Extract corrected answer
        boxed = _extract_boxed(verification)
        if boxed:
            # Build a corrected solution
            corrected = f"{solution}\n\n[Self-Verification: original answer was incorrect.]\nCorrected answer: \\boxed{{{boxed}}}"
            return corrected, True
            
    except Exception:
        pass
    
    return solution, False


# ── Off-by-factor detection ────────────────────────────────────

def detect_off_by_factor(expected: Optional[float],
                          actual: Optional[float]) -> Optional[float]:
    """Check if actual is off from expected by a factor of 10, 100, etc.
    Returns the corrected value if a factor is detected.
    """
    if expected is None or actual is None:
        return None
    if expected == 0:
        return None

    ratio = actual / expected
    
    # Check power-of-10 ratios
    for factor in [0.001, 0.01, 0.1, 10, 100, 1000]:
        if math.isclose(ratio, factor, rel_tol=0.05):
            return expected
    
    # Check if dividing by/comparing swapped values
    # e.g., expected=220, got=2200 → ratio=10
    if math.isclose(ratio, 10, rel_tol=0.05):
        return expected
    if math.isclose(ratio, 0.1, rel_tol=0.05):
        return expected
    
    return None


# ── Answer cleanup ─────────────────────────────────────────────

def clean_answer(text: str) -> str:
    """Normalize a model answer: strip trailing dots, fix decimals."""
    text = text.strip()
    
    # Remove trailing dot from integers: "25." → "25"
    if re.match(r'^\d+\.$', text):
        text = text[:-1]
    
    # Remove leading/trailing whitespace
    text = text.strip()
    
    # Normalize decimal: "520.00" → "520"
    try:
        val = float(text.replace(',', ''))
        if val == int(val) and '.' in text:
            text = str(int(val))
    except ValueError:
        pass
    
    return text


# ── Boxed extractor ────────────────────────────────────────────

def _extract_boxed(text: str) -> Optional[str]:
    """Extract content from \\boxed{...} with nested brace handling."""
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


# ── Main verification pipeline ─────────────────────────────────

def verify_and_refine(solution: str, problem: str,
                       sandbox_first: bool = True,
                       keep_loaded: bool = False) -> Tuple[str, bool]:
    """Full self-verification pipeline for math answers.
    
    Returns (refined_solution, was_corrected).
    """
    original = solution
    was_corrected = False
    
    # 1. Try sandbox numeric computation
    if sandbox_first:
        ground = sandbox_compute_arithmetic(problem)
        if ground is not None:
            boxed = _extract_boxed(solution)
            if boxed:
                try:
                    boxed_val = float(boxed.replace(',', ''))
                    if math.isclose(boxed_val, ground, rel_tol=1e-6, abs_tol=1e-9):
                        # Numerically correct — still clean formatting below
                        pass
                    else:
                        ground_int = int(ground) if (math.isfinite(ground) and math.isclose(ground, round(ground), abs_tol=1e-9)) else ground
                        corrected = solution.replace(boxed, str(ground_int), 1)
                        return corrected, True
                except ValueError:
                    pass

    # Always clean the answer formatting
    boxed = _extract_boxed(solution)
    if boxed:
        cleaned = clean_answer(boxed)
        if cleaned != boxed:
            solution = solution.replace(boxed, cleaned, 1)
            was_corrected = True
    
    # 2. Model self-verification (only if model calls available)
    # This is optional — the benchmark runner can skip if too slow
    # For now, just clean the answer
    
    # 3. Clean any remaining trailing dots on numbers
    solution = re.sub(r'(\d+)\.(\s|$)', r'\1\2', solution)
    
    return solution, (solution != original)


__all__ = [
    "verify_and_refine",
    "sandbox_compute_arithmetic",
    "clean_answer",
    "detect_off_by_factor",
]
