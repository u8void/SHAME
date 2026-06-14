"""
compare.py — Smart Answer Matcher for Iris AI Benchmarks
==========================================================
Multi-strategy answer comparison that dramatically reduces false negatives
in benchmark scoring. Handles numerical, symbolic, LaTeX, and structured
answers with normalization, epsilon matching, and sympy equivalence.

Strategies (tried in order):
  1. Exact match after normalization
  2. Numeric floating-point comparison (with tolerance)
  3. Fraction equivalence (cross-multiply, decimal)
  4. Sympy structural equivalence (for algebraic answers)
  5. Variable-isolation extraction (x=5 → 5)
  6. LaTeX/nested-brace normalization
  7. Whitespace/symbol canonicalization
"""

from __future__ import annotations

import math
import re
from typing import Optional, Tuple


# ── Normalization pipeline ──────────────────────────────────────

def normalize_answer(text: str | None) -> str:
    """Canonicalize an answer string for comparison."""
    if text is None:
        return ""

    s = text.strip()

    # Strip outer $...$ or $$...$$
    s = re.sub(r'^\$\$?(.*?)\$\$?$', r'\1', s)

    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()

    # Normalize LaTeX: remove \text{...}, \text{...}
    s = re.sub(r'\\text\s*\{([^}]*)\}', r'\1', s)
    s = re.sub(r'\\mathrm\s*\{([^}]*)\}', r'\1', s)
    s = re.sub(r'\\mathbf\s*\{([^}]*)\}', r'\1', s)

    # Normalize braces around subscripts: _{8} → _8, $_{5}$ → _5
    s = re.sub(r'_\s*\{([^}]+)\}', r'_\1', s)

    # Strip curly quotes, smart punctuation
    s = s.replace('\u201c', '"').replace('\u201d', '"')
    s = s.replace('\u2018', "'").replace('\u2019', "'")

    # Remove degree symbol spaces: 55^\circ → 55^\circ (already fine)
    # Remove trailing dots
    s = s.rstrip('.')

    return s.strip()


def extract_numeric(text: str | None) -> Optional[float]:
    """Extract a numeric value from an answer string.
    
    Only extracts if the entire string (after cleanup) is numeric.
    Does NOT extract from compound expressions like intervals or equations.
    """
    if text is None:
        return None

    cleaned = text.strip().replace(',', '').replace(' ', '')
    
    # Guard: if it looks like an interval, set, or compound expression, don't try
    if re.search(r'[\[\]\(\)\{\}|&<>]|\\in|\\cup|\\cap|\\subseteq', cleaned):
        return None
    
    # Guard: if it looks like an equation with variables
    if re.search(r'[a-zA-Z]', cleaned) and not cleaned.replace('.', '').replace('-', '').isdigit():
        return None
    
    # Guard: too many operators suggests a compound expression
    op_count = sum(1 for c in cleaned if c in '+-*/')
    if op_count > 3:
        return None

    # Try direct float parse
    try:
        return float(cleaned)
    except ValueError:
        pass

    # Try evaluating simple expressions
    cleaned_expr = cleaned.replace('^', '**').replace('×', '*').replace('÷', '/')
    safe = ''.join(c for c in cleaned_expr if c in '0123456789.+-*/()eE')
    if safe and safe != cleaned_expr:
        return None  # rejected characters — not purely numeric
    if safe and any(c.isdigit() for c in safe):
        try:
            val = float(eval(safe, {"__builtins__": {}}, {}))
            return val
        except Exception:
            pass

    return None


def extract_fraction(text: str | None) -> Optional[Tuple[float, float]]:
    """Extract numerator/denominator from \frac{num}{den} or num/den."""
    if text is None:
        return None

    # \frac{num}{den}
    m = re.search(r'\\frac\s*\{([^}]+)\}\s*\{([^}]+)\}', text)
    if m:
        n = extract_numeric(m.group(1))
        d = extract_numeric(m.group(2))
        if n is not None and d is not None and d != 0:
            return (n, d)

    # num / den
    m = re.search(r'([\d.\-]+)\s*/\s*([\d.\-]+)', text)
    if m:
        n = extract_numeric(m.group(1))
        d = extract_numeric(m.group(2))
        if n is not None and d is not None and d != 0:
            return (n, d)

    return None


def normalize_latex(text: str | None) -> str:
    """Aggressively normalize LaTeX for comparison."""
    if text is None:
        return ""

    s = text.strip()
    # Remove $ signs anywhere
    s = s.replace('$', '')
    # Remove \left, \right
    s = s.replace('\\left', '').replace('\\right', '')
    # Collapse whitespace aggressively
    s = re.sub(r'\s+', '', s)
    # Remove braces around single characters
    s = re.sub(r'\{([^{}]{1,3})\}', r'\1', s)
    # Backslash normalization
    s = s.replace('\\', '')
    return s.strip()


# ── Core comparison strategies ─────────────────────────────────

def compare_numeric(a_str: str, b_str: str,
                    rel_tol: float = 1e-6,
                    abs_tol: float = 1e-9) -> Tuple[bool, str]:
    """Compare two answer strings as numeric values."""
    a = extract_numeric(a_str)
    b = extract_numeric(b_str)
    if a is not None and b is not None:
        if math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol):
            return True, f"numeric_match({a} ≈ {b})"
    return False, "numeric_mismatch"


def compare_fraction(a_str: str, b_str: str,
                     rel_tol: float = 1e-6) -> Tuple[bool, str]:
    """Compare two answer strings as fractions."""
    fa = extract_fraction(a_str)
    fb = extract_fraction(b_str)
    if fa and fb:
        val_a = fa[0] / fa[1]
        val_b = fb[0] / fb[1]
        if math.isclose(val_a, val_b, rel_tol=rel_tol):
            return True, f"fraction_match({fa[0]:.3f}/{fa[1]:.3f})"
    return False, "fraction_mismatch"


def compare_fraction_vs_numeric(frac_str: str, num_str: str,
                                 rel_tol: float = 1e-6) -> Tuple[bool, str]:
    """Compare a fraction against a numeric value."""
    fa = extract_fraction(frac_str)
    if fa:
        val = fa[0] / fa[1]
        num = extract_numeric(num_str)
        if num is not None:
            if math.isclose(val, num, rel_tol=rel_tol):
                return True, f"frac_vs_num({val:.6f} ≈ {num})"
    return False, "frac_vs_num_mismatch"


def compare_sympy(a_str: str, b_str: str) -> Tuple[bool, str]:
    """Compare using sympy structural equivalence."""
    try:
        import sympy as sp

        a_norm = normalize_answer(a_str)
        b_norm = normalize_answer(b_str)

        # Try parsing both as sympy expressions
        a_expr = sp.sympify(a_norm, evaluate=False)
        b_expr = sp.sympify(b_norm, evaluate=False)

        # Simplify difference
        diff = sp.simplify(a_expr - b_expr)
        if diff == 0:
            return True, f"sympy_equiv({a_expr} ≡ {b_expr})"

        # Try numeric evaluation
        try:
            a_val = float(sp.N(a_expr))
            b_val = float(sp.N(b_expr))
            if math.isclose(a_val, b_val, rel_tol=1e-6):
                return True, f"sympy_numeric({a_val:.6g} ≈ {b_val:.6g})"
        except Exception:
            pass

    except ImportError:
        pass
    except Exception:
        pass

    return False, "sympy_mismatch"


def extract_variable_value(text: str | None) -> Optional[str]:
    """Extract value after variable= (e.g., 'x=5' → '5')."""
    if text is None:
        return None

    # x = 5 or x=5
    m = re.search(r'[a-zA-Z]\s*[=≈]\s*(.+?)(?:,|$|\s|\.)', text)
    if m:
        val = m.group(1).strip()
        if val:
            return val
    return None


def compare_isolated_variable(a_str: str, b_str: str) -> Tuple[bool, str]:
    """Try comparing after stripping variable= prefix."""
    a_val = extract_variable_value(a_str)
    b_val = extract_variable_value(b_str)

    # One has variable, other doesn't
    if a_val and b_val:
        return match(a_val, b_val)
    elif a_val:
        return match(a_val, b_str)
    elif b_val:
        return match(a_str, b_val)

    return False, "no_variable_isolation"


def compare_latex_deep(a_str: str, b_str: str) -> Tuple[bool, str]:
    """Deep LaTeX normalization then exact match."""
    a = normalize_latex(a_str)
    b = normalize_latex(b_str)
    if a and b and a == b:
        return True, f"latex_deep_match({a[:50]})"
    return False, "latex_mismatch"


# ── Master matcher ─────────────────────────────────────────────

def _compare_intervals(a_str: str, b_str: str) -> Tuple[bool, str]:
    """Compare interval notation: [-2,7] vs x∈[-2,7] etc."""
    def _extract_interval(text: str) -> Optional[Tuple[str, str, str, str]]:
        # Match [a,b] or (a,b) with optional variable prefix
        m = re.search(
            r'(?:[a-zA-Z]\s*[=∈≈]\s*)?'
            r'([\[\(])\s*([^,\]]+)\s*,\s*([^\]\)]+)\s*([\]\)])',
            text
        )
        if m:
            return (m.group(1), m.group(2).strip(), m.group(3).strip(), m.group(4))
        return None
    
    a_int = _extract_interval(a_str)
    b_int = _extract_interval(b_str)
    if a_int and b_int:
        if a_int == b_int:
            return True, f"interval_exact({a_str})"
        # Compare numeric bounds
        a_lo = extract_numeric(a_int[1])
        a_hi = extract_numeric(a_int[2])
        b_lo = extract_numeric(b_int[1])
        b_hi = extract_numeric(b_int[2])
        if all(v is not None for v in (a_lo, a_hi, b_lo, b_hi)):
            if (math.isclose(a_lo, b_lo, rel_tol=1e-6) and
                math.isclose(a_hi, b_hi, rel_tol=1e-6)):
                return True, f"interval_numeric([{a_lo},{a_hi}])"
    return False, "interval_mismatch"

def compare_degree(a_str: str, b_str: str) -> Tuple[bool, str]:
    """Compare degree values: 36^\circ vs 36"""
    a_match = re.match(r'^([\d.]+)\s*\\?\s*circ\s*$', a_str)
    b_match = re.match(r'^([\d.]+)\s*\\?\s*circ\s*$', b_str)
    if a_match and b_match:
        return compare_numeric(a_match.group(1), b_match.group(1))
    if a_match:
        num = extract_numeric(a_match.group(1))
        other = extract_numeric(b_str)
        if num is not None and other is not None:
            return math.isclose(num, other, rel_tol=1e-6), "degree_vs_num"
    if b_match:
        num = extract_numeric(b_match.group(1))
        other = extract_numeric(a_str)
        if num is not None and other is not None:
            return math.isclose(num, other, rel_tol=1e-6), "degree_vs_num"
    return False, "degree_mismatch"

def compare_plain_name(a_str: str, b_str: str) -> Tuple[bool, str]:
    """Compare text answers: \text{Navin} vs Navin"""
    a_clean = re.sub(r'\\text\s*\{([^}]*)\}', r'\1', a_str).strip()
    b_clean = re.sub(r'\\text\s*\{([^}]*)\}', r'\1', b_str).strip()
    if a_clean.lower() == b_clean.lower():
        return True, f"text_name_match({a_clean})"
    return False, "name_mismatch"

def match(expected: str | None, actual: str | None,
          verbose: bool = False) -> Tuple[bool, str]:
    """Master answer comparator. Returns (matched, reason).

    Tries strategies in order of specificity, falling through.
    """
    if expected is None or actual is None:
        return False, "null_input"

    e = normalize_answer(expected)
    a = normalize_answer(actual)

    if not e or not a:
        return False, "empty_after_normalization"

    # 0. Exact match after basic normalization
    if e == a:
        return True, "exact_match"
    
    # 0.5 Interval comparison (before numeric, so [-2,7] ≠ "extract -27")
    ok, reason = _compare_intervals(e, a)
    if ok:
        return True, reason
    
    # 0.6 Degree comparison  
    ok, reason = compare_degree(e, a)
    if ok:
        return True, reason
    
    # 0.7 Plain text name comparison
    ok, reason = compare_plain_name(e, a)
    if ok:
        return True, reason

    # 1. Deep LaTeX normalization match
    ok, reason = compare_latex_deep(expected, actual)
    if ok:
        return (True, reason) if not verbose else (True, f"latex→exact: {reason}")

    # 2. Numeric comparison
    ok, reason = compare_numeric(expected, actual)
    if ok:
        return True, reason

    # 3. Fraction equivalence
    ok, reason = compare_fraction(expected, actual)
    if ok:
        return True, reason

    # 4. Fraction vs numeric
    ok, reason = compare_fraction_vs_numeric(expected, actual)
    if ok:
        return True, reason
    ok, reason = compare_fraction_vs_numeric(actual, expected)  # swap
    if ok:
        return True, reason

    # 5. Sympy structural equivalence
    ok, reason = compare_sympy(expected, actual)
    if ok:
        return True, reason

    # 6. Variable isolation
    ok, reason = compare_isolated_variable(expected, actual)
    if ok:
        return True, reason

    # 7. Fallback: case-insensitive exact
    if e.lower() == a.lower():
        return True, "case_insensitive_match"

    return False, f"all_strategies_failed | expected='{e[:60]}' got='{a[:60]}'"


def match_with_verifier(expected: str | None, actual: str | None,
                        problem: str = "",
                        verbose: bool = False) -> Tuple[bool, str]:
    """Match with MathVerifier integration for math answers.

    First tries all comparison strategies, then falls back
    to MathVerifier.numerical_match for computational verification.
    """
    ok, reason = match(expected, actual, verbose=verbose)
    if ok:
        return True, reason

    # Fallback to MathVerifier from harness
    try:
        from src.harness import MathVerifier

        # Extract expected numeric value
        expected_num = extract_numeric(expected)
        if expected_num is not None and actual:
            mr = MathVerifier.verify(
                solution=f"Solution: {actual}\n\\boxed{{{actual}}}",
                problem=problem,
                expected_value=expected_num,
            )
            if mr.numerical_match:
                return True, f"math_verifier_numeric({mr.computed_value} ≈ {mr.expected_value})"

    except ImportError:
        pass
    except Exception:
        pass

    return False, reason


# ── Batch comparison for benchmark tables ──────────────────────

def compare_batch(pairs: list[Tuple[str | None, str | None]],
                  problems: list[str] | None = None,
                  verbose: bool = False) -> list[Tuple[bool, str, str, str]]:
    """Compare a batch of (expected, actual) pairs.

    Returns list of (passed, reason, expected_display, actual_display).
    """
    results = []
    for i, (exp, act) in enumerate(pairs):
        prob = problems[i] if problems and i < len(problems) else ""
        ok, reason = match_with_verifier(exp, act, problem=prob, verbose=verbose)
        results.append((ok, reason, str(exp or ""), str(act or "")))
    return results


# ── Format fixer: fix common LaTeX rendering differences ──────

def fix_common_format_issues(text: str) -> str:
    """Fix common formatting issues the model might produce that
    don't affect correctness."""
    s = text
    # $204_{5}$ → 204_5
    s = re.sub(r'\$\s*(\d+)\s*_\s*\{\s*(\d+)\s*\}\s*\$', r'\1_\2', s)
    # $120^\circ$ → 120^\circ
    s = re.sub(r'\$\s*(\d+)\s*\\circ\s*\$', r'\1^\\circ', s)
    # Strip stray $ at boundaries
    s = s.strip().strip('$').strip()
    return s


__all__ = [
    "match",
    "match_with_verifier",
    "normalize_answer",
    "extract_numeric",
    "extract_fraction",
    "normalize_latex",
    "compare_batch",
    "fix_common_format_issues",
]
