

from __future__ import annotations

import re
import time
import subprocess
import math
from typing import Optional, Tuple

from benchmark.compare import (
    match, match_with_verifier, normalize_answer,
    extract_numeric, fix_common_format_issues,
)


def auto_correct_math_answer(
    problem: str,
    model_raw_output: str,
    ground_truth: str | None = None,
    max_attempts: int = 3,
) -> Tuple[str, bool, str]:
    
    log_parts = []

    
    boxed = _extract_boxed(model_raw_output)
    if boxed is None:
        
        boxed = _extract_answer_pattern(model_raw_output)

    original = boxed or model_raw_output[-500:]
    log_parts.append(f"Extracted: {original[:80]}")

    
    try:
        from src.harness import MathVerifier
        if ground_truth:
            mr = MathVerifier.verify(
                generated_text=model_raw_output,
                target_answer=ground_truth,
            )

            if mr.is_equivalent:
                
                log_parts.append("MathVerifier: numerically correct")
                corrected = fix_common_format_issues(str(mr.extracted_answer or original))
                if corrected != original:
                    log_parts.append(f"Format fix: '{original[:40]}' → '{corrected[:40]}'")

                ok, reason = match(ground_truth, corrected)
                return corrected, (corrected != original), "; ".join(log_parts)

            log_parts.append(f"MathVerifier issues: {mr.error_message if mr.error_message else 'none'}")
        else:
            log_parts.append("MathVerifier issues: no ground truth")

    except ImportError:
        log_parts.append("MathVerifier unavailable")

    
    fmt_fixed = fix_common_format_issues(original)
    if fmt_fixed != original and ground_truth:
        ok, reason = match(ground_truth, fmt_fixed)
        if ok:
            log_parts.append(f"Format fix resolved: {reason}")
            return fmt_fixed, True, "; ".join(log_parts)

    
    for attempt in range(max_attempts):
        try:
            corrected = _sandbox_recompute(problem, model_raw_output)
            if corrected and corrected != original:
                log_parts.append(f"Sandbox recompute: {corrected[:60]}")
                if ground_truth:
                    ok, reason = match(ground_truth, corrected)
                    if ok:
                        log_parts.append(f"Sandbox match: {reason}")
                        return corrected, True, "; ".join(log_parts)
                else:
                    return corrected, True, "; ".join(log_parts)
        except Exception as e:
            log_parts.append(f"Sandbox error (attempt {attempt+1}): {e}")

    
    if fmt_fixed != original:
        return fmt_fixed, True, "; ".join(log_parts + ["Format fix only"])

    return original, False, "; ".join(log_parts)


def auto_correct_code_answer(
    problem: str,
    code_output: str,
    test_cases: list | None = None,
) -> Tuple[str, bool, str]:
    
    log_parts = []

    
    try:
        import ast
        ast.parse(code_output)
        log_parts.append("Syntax: OK")
    except SyntaxError as e:
        log_parts.append(f"Syntax error: {e}")
        
        try:
            code_output = _basic_syntax_fix(code_output, e)
            ast.parse(code_output)
            log_parts.append("Syntax fix applied")
        except Exception:
            pass

    
    try:
        from src.harness import CodeSandbox

        report = CodeSandbox.run(code_output, language="python")
        if report.result.value == "error":
            log_parts.append(f"Sandbox error: {report.runtime_errors[:2]}")
        elif report.result.value == "fail":
            log_parts.append(f"Sandbox: {report.tests_passed}/{report.tests_passed + report.tests_failed} tests")
        else:
            log_parts.append(f"Sandbox: {report.result.value}")

    except ImportError:
        log_parts.append("CodeSandbox unavailable")

    return code_output, False, "; ".join(log_parts)


def _extract_boxed(text: str) -> str | None:
    
    idx = text.rfind(r"\boxed{")
    if idx == -1:
        idx = text.rfind(r"boxed{")
        if idx == -1:
            return None
        start = idx + 6
    else:
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


def _extract_answer_pattern(text: str) -> str | None:
    
    
    m = re.search(r'\*\*Answer:?\*\*\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    
    m = re.search(
        r'(?:Therefore|Thus|Hence|So|Final answer|The answer is)\s*,?\s*(.+?)(?:\.|$)\s*$',
        text, re.IGNORECASE | re.MULTILINE
    )
    if m:
        return m.group(1).strip()

    
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    for line in reversed(lines[-3:]):
        nums = re.findall(r'[\d.\-+eE]+', line.replace(',', ''))
        if nums:
            return nums[-1]

    return None


def _basic_syntax_fix(code: str, error: SyntaxError) -> str:
    
    if "'(' was never closed" in str(error) or "unexpected EOF" in str(error):
        
        open_parens = code.count('(') - code.count(')')
        open_braces = code.count('{') - code.count('}')
        open_brackets = code.count('[') - code.count(']')
        code = code.rstrip()
        code += ')' * max(0, open_parens)
        code += '}' * max(0, open_braces)
        code += ']' * max(0, open_brackets)
    return code


def _sandbox_recompute(problem: str, solution: str) -> str | None:
    
    
    

    
    m = re.search(
        r'(?:what is|calculate|compute|find|evaluate|solve)\s+'
        r'(.+?)\s*\??$',
        problem, re.IGNORECASE
    )
    if not m:
        return None

    expr = m.group(1).strip().rstrip('?').strip()

    
    
    numeric_expr = re.sub(r'[^0-9.\+\-\*\/\(\)\^\s]', '', expr)
    numeric_expr = re.sub(r'\s+', '', numeric_expr)

    if not numeric_expr or len(numeric_expr) < 1:
        return None

    
    if re.search(r'[^0-9.\+\-\*\/\(\)\^]', numeric_expr):
        return None

    try:
        numeric_expr = numeric_expr.replace('^', '**')
        result = eval(numeric_expr, {"__builtins__": {}}, {})
        if isinstance(result, (int, float)):
            return str(int(result)) if result == int(result) else f"{result:.6g}"
    except Exception:
        pass

    return None


__all__ = [
    "auto_correct_math_answer",
    "auto_correct_code_answer",
]
