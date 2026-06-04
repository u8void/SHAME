"""
syntax_checker.py — Lightweight, language-aware syntax checker for Iris AI.
==========================================================================
 Catches syntax errors in generated code blocks before delivery.
 Uses stdlib parsers (AST for Python) and system CLI tools as available.
 Catches errors for: Python, JS/TS, C/C++, Bash, Go, Rust.

Contract:
---------
When a syntax error is found during coding tasks, the router will yield a syntax error event:
    yield {"type": "syntax_error", "content": f"Syntax error detected in {language}: {error_msg}"}
The frontend must handle "syntax_error" events (e.g. by showing a warning banner).
"""

import os
import re
import ast
import shutil
import subprocess
import tempfile
from typing import Optional, List, Tuple

def guess_language_from_content(code: str) -> str:
    """Guess the programming language of a code block based on common syntax markers."""
    if re.search(r'\bdef\s+\w+\s*\(|import\s+\w+|\bif\s+__name__\s*==', code):
        return "python"
    if re.search(r'#include\s+<[^>]+>|#include\s+"[^"]+"|\bint\s+main\s*\(', code):
        return "c"
    if re.search(r'\bpackage\s+main\b|\bimport\s+\([^)]*\)|import\s+"fmt"', code):
        return "go"
    if re.search(r'\bfn\s+main\s*\(\s*\)|use\s+std::\w+', code):
        return "rust"
    if re.search(r'\bconsole\.log\s*\(|const\s+\w+\s*=|let\s+\w+\s*=|function\s+\w+\s*\(', code):
        return "javascript"
    if re.search(r'^#!\s*/(bin|usr)/env\s+(bash|sh)|\becho\s+["\']|if\s+\[.*\]\s*;\s*then|\bfi\b', code, re.MULTILINE):
        return "bash"
    return "unknown"

def extract_code_blocks(text: str) -> List[Tuple[str, str]]:
    """Extract language tags and code content for all fenced code blocks."""
    pattern = re.compile(r'```(\w*)\n([\s\S]*?)```', re.MULTILINE)
    blocks = []
    for m in pattern.finditer(text):
        lang = m.group(1).lower()
        code = m.group(2)
        if not lang or lang == "unknown":
            lang = guess_language_from_content(code)
        blocks.append((lang, code))
    return blocks


def _check_python(code: str) -> Optional[str]:
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return f"Python SyntaxError at line {e.lineno}: {e.msg}"

def _check_javascript(code: str, lang: str = "javascript") -> Optional[str]:
    if not shutil.which("node"):
        return None
    suffix = ".ts" if lang == "typescript" else ".js"
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        result = subprocess.run(
            ["node", "--check", tmp],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return result.stderr.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

def _check_c(code: str, lang: str = "c") -> Optional[str]:
    compiler = shutil.which("clang") or shutil.which("gcc")
    if not compiler:
        return None
    suffix = ".cpp" if lang in ("cpp", "c++") else ".c"
    std_flag = "-std=c++17" if lang in ("cpp", "c++") else "-std=c11"
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        result = subprocess.run(
            [compiler, "-fsyntax-only", std_flag, tmp],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            lines = [line for line in result.stderr.splitlines() if "error:" in line.lower()]
            return "\n".join(lines[:10]) if lines else result.stderr[:500]
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

def _check_bash(code: str) -> Optional[str]:
    if not shutil.which("bash"):
        return None
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        result = subprocess.run(
            ["bash", "-n", tmp],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return result.stderr.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

def _check_go(code: str) -> Optional[str]:
    if not shutil.which("gofmt"):
        return None
    with tempfile.NamedTemporaryFile(mode="w", suffix=".go", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        result = subprocess.run(
            ["gofmt", "-e", tmp],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return result.stderr.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

def _check_rust(code: str) -> Optional[str]:
    if not shutil.which("rustc"):
        return None
    with tempfile.NamedTemporaryFile(mode="w", suffix=".rs", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        result = subprocess.run(
            ["rustc", "--edition", "2021", "--crate-type", "lib", "--emit=metadata", "-o", os.devnull, tmp],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            lines = [line for line in result.stderr.splitlines() if "error" in line.lower()]
            return "\n".join(lines[:10]) if lines else result.stderr[:500]
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

CHECKERS = {
    "python":     _check_python,
    "py":         _check_python,
    "javascript": lambda c: _check_javascript(c, "javascript"),
    "js":         lambda c: _check_javascript(c, "javascript"),
    "typescript": lambda c: _check_javascript(c, "typescript"),
    "ts":         lambda c: _check_javascript(c, "typescript"),
    "c":          lambda c: _check_c(c, "c"),
    "cpp":        lambda c: _check_c(c, "cpp"),
    "c++":        lambda c: _check_c(c, "cpp"),
    "bash":       _check_bash,
    "sh":         _check_bash,
    "go":         _check_go,
    "rust":       _check_rust,
    "rs":         _check_rust,
}

def check_syntax(code_output: str, language: Optional[str] = None) -> Optional[str]:
    """Check code blocks for syntax errors. Dispatches to matching CHECKERS.

    Returns the first error found, or None if clean.
    """
    blocks = extract_code_blocks(code_output)
    if not blocks:
        return None

    for lang, code in blocks:
        effective_lang = language or lang
        checker = CHECKERS.get(effective_lang)
        if checker:
            err = checker(code)
            if err:
                return err
    return None
