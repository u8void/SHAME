"""
harness.py - Code Output Quality Harness for Iris AI
=====================================================
Post-generation passes that clean, normalize, and repair model code output.

Every pass returns (text, warnings). Warnings are human-readable notes
yielded as {"type": "harness_warning", "content": "..."}.
"""

import re
import os
from typing import Tuple, List, Optional



def normalize_fences(text: str, language: str = "python") -> Tuple[str, List[str]]:
    """Fix broken markdown code fences."""
    warnings: List[str] = []
    original = text

    text = re.sub(r'````+', '```', text)

    text = re.sub(r'(?<![`\n])``([^`\n]+)``(?![`\n])', r'`\1`', text)

    opening = [m for m in re.finditer(r'^```', text, re.MULTILINE)]
    closing = [m for m in re.finditer(r'\n```\s*$', text, re.MULTILINE)]
    if len(opening) > len(closing):
        text = text.rstrip() + '\n```'
        warnings.append("Fence: added missing closing ```")

    if text != original and not warnings:
        warnings.append("Fence: normalized malformed code fence(s)")

    return text, warnings



def strip_comments(text: str, language: str = "python") -> Tuple[str, List[str]]:
    """Strip inline and block comments per language.

    Uses simple per-line regex + string-awareness heuristics.
    """
    warnings: List[str] = []
    original = text.strip()
    lang = language.lower()

    if lang in ("python", "py"):
        lines = text.split("\n")
        result = []
        for line in lines:
            line_stripped = _strip_py_line(line)
            result.append(line_stripped)
        stripped = "\n".join(result)
        if stripped != text:
            text = stripped
            warnings.append("Comment: stripped Python inline comments")

    elif lang in ("javascript", "js", "typescript", "ts", "c", "cpp", "c++",
                  "go", "rust", "rs", "java"):
        if re.search(r'//|/\*', text):
            text = re.sub(r'/\*[^*]*\*+(?:[^/*][^*]*\*+)*/', '', text)
            lines = text.split("\n")
            result = []
            for line in lines:
                idx = line.find("//")
                if idx < 0:
                    result.append(line)
                else:
                    before = line[:idx]
                    if before.rstrip().endswith("http:") or before.rstrip().endswith("https:"):
                        result.append(line)
                    else:
                        result.append(line[:idx])
            text = "\n".join(result)
            warnings.append("Comment: stripped C-style comments")

    elif lang in ("bash", "sh"):
        text = re.sub(r'(\s*)#[^\n]*', '', text)
        warnings.append("Comment: stripped shell comments")

    text = re.sub(r'\n{3,}', '\n\n', text)

    if text.strip() != original and not warnings:
        warnings.append("Comment: removed developer comments")

    return text, warnings


def _strip_py_line(line: str) -> str:
    """Remove Python inline comment from a line if # is not inside a string."""
    in_string = False
    string_char = ""
    hash_idx = -1

    i = 0
    while i < len(line):
        ch = line[i]

        if not in_string:
            if ch in ('"', "'"):
                if line[i:i+3] == ch * 3:
                    in_string = True
                    string_char = ch * 3
                    i += 3
                    continue
                else:
                    in_string = True
                    string_char = ch
            elif ch == '#':
                hash_idx = i
                break
        else:
            if line[i:i+len(string_char)] == string_char:
                in_string = False
                i += len(string_char)
                continue
            elif ch == '\\' and i + 1 < len(line):
                i += 2
                continue

        i += 1

    if hash_idx >= 0:
        return line[:hash_idx].rstrip()
    return line



def repair_truncation(text: str, language: str = "python") -> Tuple[str, List[str]]:
    """Detect and repair truncated code (unclosed braces, strings)."""
    warnings: List[str] = []
    original = text

    pairs = {"{": "}", "(": ")", "[": "]"}
    stack = []
    in_string = False
    string_char = ""
    prev = ""

    for i, ch in enumerate(text):
        if in_string:
            if ch == string_char and prev != "\\":
                in_string = False
            prev = ch
            continue
        if ch in ('"', "'"):
            if text[i:i+3] == ch * 3:
                continue
            in_string = True
            string_char = ch
            prev = ch
            continue
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in pairs.values():
            if stack and stack[-1] == ch:
                stack.pop()
        prev = ch

    if stack:
        closing = "".join(reversed(stack))
        text = text.rstrip() + "\n" + closing
        warnings.append(f"Truncation: added missing closing: {closing}")

    if in_string:
        text = text.rstrip() + string_char
        warnings.append("Truncation: closed unterminated string literal")

    return text, warnings



_PY_IMPORT_PATTERNS = {
    "sys":         r'\bsys\.(argv|exit|stdout|stderr|stdin|path|version|platform)\b',
    "os":          r'\bos\.(path|environ|getenv|listdir|makedirs?|remove|rename|chdir|getcwd|walk|stat|urandom|system)\b',
    "json":        r'\bjson\.(dumps?|loads?)\b',
    "re":          r'\bre\.(compile|match|search|findall|sub|split|escape|fullmatch)\b',
    "time":        r'\btime\.(time|sleep|perf_counter|monotonic|strftime|gmtime|localtime)\b',
    "datetime":    r'\bdatetime\.(datetime|date|time|timedelta|timezone|now|utcnow)\b',
    "collections": r'\b(collections\.(defaultdict|Counter|OrderedDict|deque|namedtuple)|from collections import)\b',
    "itertools":   r'\bitertools\.(cycle|islice|chain|product|permutations|combinations|groupby)\b',
    "functools":   r'\bfunctools\.(lru_cache|partial|reduce|wraps|cache)\b',
    "random":      r'\brandom\.(random|randint|choice|shuffle|seed|uniform|sample|choices)\b',
    "math":        r'\bmath\.(sqrt|sin|cos|tan|log|log10|log2|exp|floor|ceil|pi|e|factorial|gcd|pow)\b',
    "pathlib":     r'\b(Path\s*\(|pathlib\.)\b',
    "subprocess":  r'\b(subprocess\.(run|call|Popen|check_output|check_call|PIPE|STDOUT|DEVNULL)|from subprocess import)\b',
    "typing":      r'\b(typing\.(List|Dict|Tuple|Set|Optional|Union|Any|Callable|Iterator|Generator)|from typing import)\b',
    "argparse":    r'\b(argparse\.(ArgumentParser|Namespace)|from argparse import)\b',
    "threading":   r'\b(threading\.(Thread|Lock|RLock|Event|Condition|Semaphore|Timer)|from threading import)\b',
    "dataclasses": r'\b(dataclasses\.(dataclass|field)|from dataclasses import|@dataclass)\b',
    "hashlib":     r'\bhashlib\.(md5|sha1|sha256|sha512|new)\b',
    "base64":      r'\bbase64\.(b64encode|b64decode|standard_b64encode|urlsafe_b64encode)\b',
    "uuid":        r'\buuid\.(uuid4|uuid1|uuid3|uuid5|UUID)\b',
    "tempfile":    r'\btempfile\.(NamedTemporaryFile|TemporaryFile|TemporaryDirectory|mkstemp|mkdtemp|gettempdir)\b',
    "shutil":      r'\bshutil\.(copy|copy2|copytree|rmtree|move|make_archive|disk_usage|which)\b',
    "logging":     r'\blogging\.(getLogger|basicConfig|info|debug|warning|error|critical|exception|log)\b',
    "warnings":    r'\bwarnings\.(warn|filterwarnings|simplefilter|catch_warnings)\b',
    "struct":      r'\bstruct\.(pack|unpack|calcsize|iter_unpack)\b',
    "pickle":      r'\bpickle\.(dump|dumps|load|loads|HIGHEST_PROTOCOL)\b',
    "csv":         r'\bcsv\.(reader|writer|DictReader|DictWriter|writerow|writerows)\b',
    "io":          r'\bio\.(BytesIO|StringIO|open|BufferedWriter|BufferedReader|TextIOWrapper)\b',
    "enum":        r'\benum\.(Enum|IntEnum|StrEnum|auto|unique)\b',
    "abc":         r'\b(abc\.(ABC|abstractmethod|abstractclassmethod|abstractproperty)|from abc import)\b',
    "socket":      r'\bsocket\.(socket|AF_INET|AF_INET6|SOCK_STREAM|SOCK_DGRAM|gethostname|gethostbyname|getaddrinfo|create_connection)\b',
    "html":        r'\bhtml\.(escape|unescape)\b',
    "urllib":      r'\b(urllib\.(request|parse|error|robotparser)|urllib\.parse\.(urlencode|quote|unquote|urlparse|urljoin))\b',
    "zipfile":     r'\bzipfile\.(ZipFile|is_zipfile|ZIP_DEFLATED|ZIP_STORED)\b',
    "tarfile":     r'\btarfile\.(open|is_tarfile|TarFile|TarInfo)\b',
    "gzip":        r'\bgzip\.(open|compress|decompress|GzipFile)\b',
    "glob":        r'\bglob\.(glob|iglob|escape)\b',
    "textwrap":    r'\btextwrap\.(fill|wrap|shorten|dedent|indent)\b',
    "pprint":      r'\bpprint\.(pprint|pformat|PrettyPrinter)\b',
    "copy":        r'\bcopy\.(copy|deepcopy)\b',
}

def inject_imports(text: str, language: str = "python") -> Tuple[str, List[str]]:
    """Detect missing stdlib imports and inject them at the top of Python code."""
    warnings: List[str] = []

    if language.lower() not in ("python", "py"):
        return text, warnings

    lines = text.split("\n")
    existing_imports = set()
    import_line = -1
    shebang_line = -1

    for i, line in enumerate(lines):
        s = line.strip()
        if i == 0 and (s.startswith("#!") or s.startswith("# -*-")):
            shebang_line = i
            continue
        m = re.match(r'^(?:from\s+(\w+)|import\s+(\w+))', s)
        if m:
            pkg = m.group(1) or m.group(2)
            existing_imports.add(pkg)
            import_line = i
        elif import_line >= 0 and (not s or s.startswith("#")):
            continue
        elif import_line >= 0:
            break

    insert_at = max(shebang_line, import_line, -1) + 1
    if insert_at > len(lines):
        insert_at = len(lines)

    new_imports = []
    for pkg, pattern in _PY_IMPORT_PATTERNS.items():
        if pkg in existing_imports:
            continue
        if re.search(pattern, text):
            new_imports.append(f"import {pkg}")
            existing_imports.add(pkg)

    if new_imports:
        insert_line = lines[insert_at] if insert_at < len(lines) else ""
        if insert_line.strip():
            lines.insert(insert_at, "")
            insert_at += 1
        for imp in sorted(new_imports):
            lines.insert(insert_at, imp)
            insert_at += 1
        if insert_at < len(lines) and lines[insert_at].strip():
            lines.insert(insert_at, "")
        text = "\n".join(lines)
        warnings.append(f"Imports: injected missing: {', '.join(sorted(new_imports))}")

    return text, warnings




def deduplicate_blocks(text: str, language: str = "") -> Tuple[str, List[str]]:
    """Detect repeated code blocks (common with continuation models)."""
    warnings: List[str] = []

    blocks = re.split(r'\n\n+', text)
    if len(blocks) < 2:
        return text, warnings

    seen = {}
    result = []
    for i, block in enumerate(blocks):
        key = re.sub(r'\s+', ' ', block.strip().lower())
        if len(key) < 20:
            result.append(block)
            continue
        if key in seen:
            warnings.append(f"Duplicate: block {i + 1} repeats block {seen[key] + 1}")
            continue
        seen[key] = i
        result.append(block)

    if len(result) != len(blocks):
        text = "\n\n".join(result)
        text = re.sub(r'\n{3,}', '\n\n', text)

    return text, warnings



_SECRET_PATTERNS = [
    (r'(sk-[a-zA-Z0-9_-]{20,}T3BlbkFJ[a-zA-Z0-9_-]{20,})', '[OPENAI_KEY_REDACTED]'),
    (r'(sk-[a-zA-Z0-9_-]{30,})', '[API_KEY_REDACTED]'),
    (r'(sk-ant-[a-zA-Z0-9_-]{20,})', '[ANTHROPIC_KEY_REDACTED]'),
    (r'(AIza[0-9A-Za-z\-_]{35})', '[GOOGLE_KEY_REDACTED]'),
    (r'(hf_[a-zA-Z0-9]{34})', '[HF_KEY_REDACTED]'),
    (r'(api[_-]?key\s*[:=]\s*["\'])([^"\'\s]{16,})(["\'])', r'\1[REDACTED]\3'),
    (r'(secret\s*[:=]\s*["\'])([^"\'\s]{16,})(["\'])', r'\1[REDACTED]\3'),
    (r'(token\s*[:=]\s*["\'])([^"\'\s]{16,})(["\'])', r'\1[REDACTED]\3'),
    (r'(password\s*[:=]\s*["\'])([^"\'\s]{8,})(["\'])', r'\1[REDACTED]\3'),
    (r'(AKIA[0-9A-Z]{16})', '[AWS_KEY_REDACTED]'),
    (r'(ASIA[0-9A-Z]{16})', '[AWS_KEY_REDACTED]'),
    (r'(gh[pousr]_[a-zA-Z0-9]{36,})', '[GITHUB_TOKEN_REDACTED]'),
    (r'(github_pat_[a-zA-Z0-9_]{20,})', '[GITHUB_TOKEN_REDACTED]'),
    (r'(eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,})', '[JWT_REDACTED]'),
]

def redact_secrets(text: str, language: str = "") -> Tuple[str, List[str]]:
    """Detect and redact hallucinated API keys / secrets from model output."""
    warnings: List[str] = []

    for pattern, replacement in _SECRET_PATTERNS:
        if re.search(pattern, text):
            count = len(re.findall(pattern, text))
            text = re.sub(pattern, replacement, text)
            warnings.append(f"Secret: redacted {count} potential secret(s)")

    return text, warnings



def clean_whitespace(text: str, language: str = "") -> Tuple[str, List[str]]:
    """Strip trailing whitespace and collapse excessive blank lines."""
    warnings: List[str] = []
    original = text

    lines = text.split("\n")
    lines = [l.rstrip() for l in lines]

    cleaned = []
    blank_count = 0
    for line in lines:
        if not line.strip():
            blank_count += 1
            if blank_count <= 2:
                cleaned.append(line)
        else:
            blank_count = 0
            cleaned.append(line)

    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()

    text = "\n".join(cleaned)

    if text != original:
        warnings.append("Whitespace: stripped trailing spaces and excess blank lines")

    return text, warnings



def normalize_header(text: str, language: str = "python") -> Tuple[str, List[str]]:
    """Ensure proper shebang and encoding header for scripts."""
    warnings: List[str] = []

    if language.lower() not in ("python", "py", "bash", "sh"):
        return text, warnings

    lines = text.split("\n")
    has_shebang = lines[0].strip().startswith("#!") if lines else False

    is_script = bool(re.search(r'if\s+__name__\s*==\s*["\']__main__["\']', text))
    is_cli = bool(re.search(r'argparse\.|sys\.argv|click\.|typer\.|fire\.', text))

    if language == "python" and (is_script or is_cli) and not has_shebang:
        lines.insert(0, "#!/usr/bin/env python3")
        warnings.append("Header: added #!/usr/bin/env python3")

    elif language in ("bash", "sh") and not has_shebang:
        lines.insert(0, "#!/usr/bin/env bash")
        warnings.append("Header: added #!/usr/bin/env bash")

    return "\n".join(lines), warnings



_PASSES = [
    ("normalize_fences",   normalize_fences),
    ("redact_secrets",     redact_secrets),
    ("repair_truncation",  repair_truncation),
    ("strip_comments",     strip_comments),
    ("inject_imports",     inject_imports),
    ("normalize_header",   normalize_header),
    ("deduplicate_blocks", deduplicate_blocks),
    ("clean_whitespace",   clean_whitespace),
]


def apply_all(text: str, language: str = "python",
              enabled: Optional[List[str]] = None) -> Tuple[str, List[dict]]:
    """Run all harness passes on code output.

    Returns (cleaned_text, [{"type": "harness_warning", "content": "..."}])
    """
    all_warnings: List[dict] = []

    for name, func in _PASSES:
        if enabled and name not in enabled:
            continue
        try:
            text, warns = func(text, language)
            for w in warns:
                all_warnings.append({"type": "harness_warning", "content": w})
        except Exception:
            pass

    return text, all_warnings


def apply_code_specific(text: str, language: str = "python") -> Tuple[str, List[dict]]:
    """Full harness pass — all 8 stages."""
    return apply_all(text, language)


def _is_math_output(text: str) -> bool:
    """Detect if text is primarily a math solution (not general code)."""
    math_signals = [
        r'\$\$.*\$\$', r'\$[^$]+\$', r'\\frac\{', r'\\sum_', r'\\int_',
        r'\\lim_', r'\\sqrt\{', r'\\cdot\b', r'\\times\b', r'\\alpha\b',
        r'\\beta\b', r'\\theta\b', r'\\pi\b', r'\\infty\b', r'\\partial\b',
        r'\\nabla\b', r'\\forall\b', r'\\exists\b', r'\\implies?\b',
        r'\\mathbb\{', r'\\mathcal\{', r'\\mathbf\{', r'\\longrightarrow\b',
        r'd/d[xX]\b', r'∫', r'∂', r'∑', r'∏', r'√', r'∞',
    ]
    return any(re.search(sig, text) for sig in math_signals)



def normalize_math_fences(text: str, language: str = "") -> Tuple[str, List[str]]:
    """Fix common LaTeX rendering issues in math model output.

    Problems models commonly produce:
    - Unescaped underscores in non-LaTeX context
    - Double-dollar fences with whitespace gaps: $$ text $$ -> $$text$$
    - Single $ used for display math when $$ needed
    - Stray backslashes from LLM tokenization
    """
    warnings: List[str] = []
    original = text

    text = re.sub(r'\$\$\s+', '$$', text)
    text = re.sub(r'\s+\$\$', '$$', text)

    text = re.sub(r'\$\s+([^$]+?)\s+\$', r'$\1$', text)

    text = re.sub(r'\\\\([^\\a-zA-Z{])', r'\\\1', text)

    if '$' not in text:
        text = re.sub(r'(?<!\\)_(?!_)(\w+)', r'$_{\1}$', text)

    text = re.sub(r'\\frac(\d)(\d)', r'\\frac{\1}{\2}', text)
    text = re.sub(r'\\frac(\w)(\w)', r'\\frac{\1}{\2}', text)

    if text != original:
        warnings.append("Math: normalized LaTeX formatting")

    return text, warnings



def normalize_math_steps(text: str, language: str = "") -> Tuple[str, List[str]]:
    """Ensure step-by-step solutions have consistent numbering."""
    warnings: List[str] = []

    step_indicators = re.findall(
        r'(?:^|\n)\s*(?:Step|step)\s*(\d+|[ivxlcdm]+)[\s:.\-)]',
        text, re.IGNORECASE
    )
    if len(step_indicators) <= 1:
        return text, warnings

    for i, match in enumerate(re.finditer(
        r'(^|\n)(\s*)(Step|step)\s*(\d+|[ivxlcdm]+)([\s:.\-)]+)',
        text, re.IGNORECASE
    ), 1):
        text = text[:match.start()] + match.group(1) + match.group(2) + \
               f"**Step {i}:** " + text[match.end():]
        if i != int(match.group(4)) if match.group(4).isdigit() else True:
            warnings.append("Math: normalized step numbering")

    return text, warnings



def extract_math_answer(text: str, language: str = "") -> Tuple[str, List[str]]:
    """Ensure a clear final answer is present and highlighted.

    If the model buried the answer in a paragraph, pull it out with a box/emphasis.
    """
    warnings: List[str] = []

    if re.search(r'\*\*Answer:?\*\*|\\boxed\{|\\therefore\b|Therefore,|Thus,|Hence,|Final answer:',
                 text, re.IGNORECASE):
        return text, warnings

    lines = text.strip().split('\n')
    candidate = None
    for line in reversed(lines):
        s = line.strip()
        if not s:
            continue
        if re.search(r'[=≈]\s*[\d\-.]+', s) and len(s) < 120:
            candidate = s
            break
        if re.search(r'\\boxed\{', s):
            candidate = s
            break
        if re.search(r'\b[xXyYzZnNtT]\s*[=≈]\s*[\d\-.a-zA-Z√π]+', s) and len(s) < 120:
            candidate = s
            break

    if candidate:
        text = text[:text.rfind(candidate)] + f"\n\n**Answer:** {candidate}\n" \
               + text[text.rfind(candidate) + len(candidate):]
        warnings.append("Math: extracted final answer for clarity")

    return text, warnings



def deduplicate_math_steps(text: str, language: str = "") -> Tuple[str, List[str]]:
    """Remove repeated reasoning steps (common with chain-of-thought models)."""
    warnings: List[str] = []

    paragraphs = re.split(r'\n\n+', text)
    if len(paragraphs) < 2:
        return text, warnings

    seen = set()
    result = []
    removed = 0
    for para in paragraphs:
        normalized = re.sub(r'\s+', ' ', para.strip().lower())
        if len(normalized) < 8:
            result.append(para)
            continue
        if normalized in seen:
            removed += 1
            continue
        seen.add(normalized)
        result.append(para)

    if removed > 0:
        text = '\n\n'.join(result)
        warnings.append(f"Math: removed {removed} duplicate reasoning step(s)")

    return text, warnings



_HALLUCINATED_REF_PATTERNS = [
    (r'\b(?:theorem|lemma|corollary|proposition)\s+(\d+\.\d+\.\d+)\b',
     r'**Theorem \1**'),
    (r'\(([A-Z][a-z]+ et al\.,?\s*\d{4}[a-z]?)\)',
     r'(\1)'),
    (r'\\tag\{(\d+\.\d+)\}', r''),
]

def redact_hallucinated_refs(text: str, language: str = "") -> Tuple[str, List[str]]:
    """Flag hallucinated theorem/paper references models sometimes invent."""
    warnings: List[str] = []

    for pattern, replacement in _HALLUCINATED_REF_PATTERNS:
        matches = re.findall(pattern, text)
        if matches:
            warnings.append(f"Math: flagged {len(matches)} potentially hallucinated reference(s)")

    return text, warnings



def normalize_math_notation(text: str, language: str = "") -> Tuple[str, List[str]]:
    """Ensure consistent math notation throughout the solution.

    Fixes:
    - Mixed `*` and `×` for multiplication → use `×` (or `*` in code)
    - Inconsistent integral bounds formatting
    - Missing parentheses around negative numbers in substitutions
    """
    warnings: List[str] = []
    original = text

    if '\\cdot' in text or '\\times' in text:
        text = re.sub(r'(?<!\\)\*(?!\*)', r'\\cdot ', text)
    else:
        text = re.sub(r'\\cdot\b', '*', text)
        text = re.sub(r'\\times\b', '*', text)

    text = re.sub(r'(?<=\w)\s*=\s*-(\d+)', r' = (-\1)', text)

    if text != original:
        warnings.append("Math: normalized notation consistency")

    return text, warnings



def separate_math_code_blocks(text: str, language: str = "") -> Tuple[str, List[str]]:
    """If the math solution contains code blocks, ensure they're properly fenced."""
    warnings: List[str] = []

    code_indicators = re.findall(
        r'((?:import|def|lambda|for|while)\s+\w+.*?(?:\n|$))',
        text
    )
    if code_indicators and '```' not in text:
        warnings.append("Math: code snippets detected without fence blocks")

    return text, warnings



_MATH_PASSES = [
    ("normalize_math_fences",    normalize_math_fences),
    ("deduplicate_math_steps",   deduplicate_math_steps),
    ("normalize_math_notation",  normalize_math_notation),
    ("normalize_math_steps",     normalize_math_steps),
    ("redact_hallucinated_refs", redact_hallucinated_refs),
    ("separate_math_code_blocks",separate_math_code_blocks),
    ("extract_math_answer",      extract_math_answer),
    ("clean_whitespace",         clean_whitespace),
]


def apply_math(text: str, language: str = "") -> Tuple[str, List[dict]]:
    """Run math-specific harness passes on a math solution.

    Args:
        text: Raw math model output
        language: Optional language hint (unused for math)

    Returns:
        (cleaned_text, [{type: harness_warning, content: ...}])
    """
    all_warnings: List[dict] = []

    for name, func in _MATH_PASSES:
        try:
            text, warns = func(text, language)
            for w in warns:
                all_warnings.append({"type": "harness_warning", "content": w})
        except Exception:
            pass

    return text, all_warnings
