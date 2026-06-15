"""
controller.py — Iris AI PC Agent
======================================
Natural-language control of your computer, powered by Iris.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.logger import get_logger
logger = get_logger('controller')
import re
import sys
import json
import time
from typing import Optional
import shutil
import smtplib
import platform
import subprocess
import webbrowser
import urllib.request
import urllib.parse
import urllib.error
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.text import Text
    from rich.live import Live
    from rich.prompt import Prompt
    from rich.align import Align
    from rich.box import ROUNDED, DOUBLE
    console = Console()
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

IS_INTERACTIVE = True

ROUTER_KEYWORDS: dict = {
    "medical": [
        "symptom", "symptoms", "diagnosis", "diagnose", "treatment", "medicine",
        "medication", "doctor", "health", "disease", "pain", "hospital", "surgery",
        "patient", "clinical", "therapy", "drug", "prescription", "fever", "injury",
        "chronic", "infection", "vaccine", "anatomy", "blood", "heart", "lung",
    ],
    "coding": [
        "python", "javascript", "typescript", "function", "code", "debug", "error",
        "import", "class", "algorithm", "variable", "loop", "array", "api", "sql",
        "database", "framework", "library", "bug", "syntax", "compile", "runtime",
        "async", "thread", "git", "docker", "linux", "bash", "script", "regex",
        "html", "css", "react", "node", "flask", "django", "mlx", "pytorch",
    ],
    "finance": [
        "tax", "taxes", "budget", "expense", "expenses", "investment", "invest",
        "stock", "stocks", "money", "salary", "income", "profit", "loss", "revenue",
        "accounting", "bank", "loan", "mortgage", "interest", "rate", "crypto",
        "bitcoin", "portfolio", "dividend", "inflation", "economy", "financial",
    ],
}

def route_category(text: str) -> Optional[str]:
    lower = text.lower()
    scores: dict = {}
    for cat, keywords in ROUTER_KEYWORDS.items():
        score = sum(1 for kw in keywords if re.search(r'\b' + re.escape(kw) + r'\b', lower))
        if score:
            scores[cat] = score
    if not scores:
        return None
    best = max(scores, key=scores.__getitem__)
    logger.info(f"[Router] Category='{best}' (scores={scores})")
    return best

import html as _html

_WEB_SEARCH_TRIGGERS = re.compile(
    r"""(?xi)
    \b(
      what | who  | when | where | why  | how  | which | whose |
      latest | recent | current | today | news | update | price |
      weather | score | result | explain | define | meaning | tell\s+me |
      search | look\s+up | find\s+out | is\s+it | are\s+there |
      difference\s+between | compare | vs\.?
    )\b
    |
    \?$                         # ends with a question mark
    """,
    re.IGNORECASE,
)

_WEB_SEARCH_SKIP = re.compile(
    r"""(?xi)
    \b(
      open | launch | play | send | copy | run | set\s+volume |
      brightness | clipboard | email | spotify | youtube |
      terminal | command
    )\b
    """,
    re.IGNORECASE,
)

def should_web_search(text: str) -> bool:
    """Return True when the query looks like a factual / informational question.

    Added guard: skip web search for very short inputs (< 5 words) since
    those are almost always greetings or simple commands, not factual queries.
    A DuckDuckGo fetch adds 1-3 seconds of latency — never worth it for "hi".
    """
    if len(text.split()) < 5:
        return False
    if _WEB_SEARCH_SKIP.search(text):
        return False
    return bool(_WEB_SEARCH_TRIGGERS.search(text))

def web_search(query: str, max_results: int = 5) -> str:
    """
    Search DuckDuckGo and return the top snippet results as plain text.
    Uses only the stdlib — no extra packages needed.
    """
    try:
        q   = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={q}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode    = ssl.CERT_NONE

        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="ignore")

        titles   = re.findall(
            r'class=["\']result__a["\'][^>]*>(.*?)</a>',
            body, re.DOTALL,
        )

        snippets = re.findall(
            r'class=["\']result__snippet["\'][^>]*>(.*?)</(?:a|span)>',
            body, re.DOTALL,
        )

        def clean(s: str) -> str:
            s = re.sub(r'<[^>]+>', '', s)
            return _html.unescape(s).strip()

        results = []
        for i, (t, s) in enumerate(zip(titles[:max_results], snippets[:max_results])):
            t, s = clean(t), clean(s)
            if t or s:
                results.append(f"[Result {i+1}] {t}\n{s}")

        if not results:
            return "(No web results found for this query.)"

        return "\n\n".join(results)

    except Exception as exc:
        return f"(Web search unavailable: {exc})"

# Removed pyperclip dependency warning
CLIPBOARD_AVAILABLE = True
try:
    from src.iris import ask_stream, get_device, solve_math, BookRetriever, analyze_image
    IRIS_AVAILABLE = True
except ImportError:
    IRIS_AVAILABLE = False
    logger.warning("[WARNING] iris.py not found or dependencies missing. Running in rule-only mode.")
# Model display name — pulled from environment or iris.conf if available
MLX_MODEL_ID = os.environ.get("IRIS_MODEL_ID", "")
if not MLX_MODEL_ID:
    try:
        with open("./config/iris.conf") as f:
            cfg = json.load(f)
        MLX_MODEL_ID = cfg.get("size", "medium") + " tier"
    except:
        MLX_MODEL_ID = "Iris AI"

CONFIG_FILE  = "./config/control.conf"

_is_linux = platform.system() == "Linux"
DEFAULT_CONFIG = {
    "email": {
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "sender_address": "your_email@gmail.com",
        "sender_password": "your_app_password",
        "contacts": {
            "mom": "mom@example.com",
            "dad": "dad@example.com"
        }
    },
    "apps": {
        "notepad":      "gedit" if _is_linux else "notepad.exe",
        "calculator":   "gnome-calculator" if _is_linux else "calc.exe",
        "paint":        "drawing" if _is_linux else "mspaint.exe",
        "spotify":      "spotify",
        "vscode":       "code",
        "chrome":       "google-chrome",
        "firefox":      "firefox",
        "explorer":     "nautilus" if _is_linux else "explorer.exe",
        "terminal":     "gnome-terminal" if _is_linux else "cmd.exe",
        "settings":     "gnome-control-center" if _is_linux else "start ms-settings:",
        "system_monitor":"gnome-system-monitor" if _is_linux else "taskmgr.exe",
        "store":        "gnome-software" if _is_linux else "ms-windows-store:",
        "camera":       "cheese" if _is_linux else "microsoft.windows.camera:",
        "mail":         "thunderbird" if _is_linux else "outlook",
        "calendar":     "gnome-calendar" if _is_linux else "outlookcal:",
        "word":         "libreoffice --writer" if _is_linux else "winword.exe",
        "excel":        "libreoffice --calc" if _is_linux else "excel.exe"
    },
    "browser": "default"
}

def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        logger.info(f"[INFO] Created config template at {CONFIG_FILE}")
        logger.info("       Edit it with your email credentials and app paths before sending mail.")
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[ERROR] Failed to load {CONFIG_FILE}: {e}. Using default config.")
        return DEFAULT_CONFIG

_INTENTS = [
    (
        "youtube_channel",
        re.compile(
            r"""(?:open|go\s+to|show|find|visit|search)
                \s+
                (.+?)
                \s+(?:channel|page|account)
                (?:\s+on\s+(?:youtube|yt))?""",
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
    (
        "spotify",
        re.compile(
            r"""(?:play|open|search|listen\s+to|show)\s+
                (.+?)
                \s+(?:on\s+)?spotify""",
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
    (
        "youtube_video",
        re.compile(
            r"""(?:play|open|watch|show|find|search|look\s+up)
                \s+
                (.+?)
                \s+(?:on\s+(?:youtube|yt)|on\s+yt|youtube|yt)""",
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
    (
        "youtube_video",
        re.compile(
            r"""(?:youtube|yt)\s*[:\-]\s*(.+)""",
            re.IGNORECASE,
        ),
    ),
    (
        "email",
        re.compile(
            r"""(?:send|write|compose|draft)\s+(?:an?\s+)?
                e?mail
                (?:\s+to\s+(?P<to>[^\s,]+))?
                (?:[\s,]+(?:about|subject|re:?)\s+(?P<subject>.+?))?
                (?:\s+(?:saying|body|message|content|with)\s+(?P<body>.+))?
                $""",
            re.IGNORECASE | re.VERBOSE | re.DOTALL,
        ),
    ),
    (
        "website",
        re.compile(
            r"""(?:open|go\s+to|visit|navigate\s+to|browse\s+to|load|show)\s+
                (https?://\S+|www\.\S+|\S+\.[a-z]{2,6}(?:/\S*)?)""",
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
    (
        "open_terminal",
        re.compile(
            r"""(?:open|launch|start|show|run)\s+(?:the\s+)?(?:terminal|console|shell|iterm)""",
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
    (
        "app",
        re.compile(
            r"""(?:open|launch|start|run|execute|start\s+up)\s+
                (?:the\s+|an?\s+)?
                (.+?)
                (?:\s+app(?:lication)?)?$""",
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
]

def detect_intent(text: str):
    t = text.strip()
    for intent_name, pattern in _INTENTS:
        m = pattern.search(t)
        if m:
            return intent_name, m
    return "ai_agent", None

import os
_prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "training", "control", "control.md")
try:
    with open(_prompt_path, "r", encoding="utf-8") as f:
        _content = f.read().strip()
        # Dynamically locate the start of training data to exclude examples from prompt
        _train_idx = _content.find("# TRAINING DATA")
        if _train_idx == -1:
            _train_idx = _content.find("#  TRAINING DATA")
        if _train_idx == -1:
            _train_idx = _content.find("# ═══════════")
        if _train_idx != -1:
            _content = _content[:_train_idx].strip()
        else:
            _content = "\n".join(_content.splitlines()[:144]).strip()
            
        if _content.startswith("SYSTEM:"):
            AI_AGENT_SYSTEM_PROMPT = _content[7:].strip()
        else:
            AI_AGENT_SYSTEM_PROMPT = _content
except Exception as e:
    logger.warning(f"[WARNING] Failed to load training/control.md: {e}")
    AI_AGENT_SYSTEM_PROMPT = "You are an AI PC assistant. Please respond with JSON actions."

MAX_SYS_PROMPT_CHARS = 4096

_agent_prompt_cache = {"text": None, "mtime": 0}

def _get_agent_system_prompt() -> str:
    """
    Read training/control.md exactly once; only reloads when the file changes
    on disk (same mtime-guard pattern used by load_generation_config).

    The prompt is truncated before '# TRAINING DATA' to exclude the training examples
    and keep prefill fast (< 5 s on M2). Put the most important instructions at the TOP of
    control.md — they will always be included.
    """
    global _agent_prompt_cache
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "training", "control", "control.md")
    try:
        mtime = os.path.getmtime(path)
        if _agent_prompt_cache["text"] is None or mtime != _agent_prompt_cache["mtime"]:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            # Dynamically locate the start of training data to exclude examples from prompt
            train_idx = content.find("# TRAINING DATA")
            if train_idx == -1:
                train_idx = content.find("#  TRAINING DATA")
            if train_idx == -1:
                train_idx = content.find("# ═══════════")
            if train_idx != -1:
                content = content[:train_idx].strip()
            else:
                content = "\n".join(content.splitlines()[:144]).strip()
                
            text = content[7:].strip() if content.startswith("SYSTEM:") else content
            _agent_prompt_cache = {"text": text, "mtime": mtime}
        return _agent_prompt_cache["text"]
    except Exception as e:
        logger.warning(f"[ERROR] Failed to load or truncate system prompt: {e}")
        return AI_AGENT_SYSTEM_PROMPT

_reply_prefix_cache: dict = {"key": None, "prompt": None}

def handle_run_code(code: str) -> str:
    """Execute Python code in a sandboxed subprocess and return stdout/stderr."""
    import tempfile
    if not code or not code.strip():
        return "No code provided to execute."
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp_path = f.name
    try:
        result = subprocess.run(
            ["python3", tmp_path],
            capture_output=True, text=True, timeout=15
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if stdout and stderr:
            return f"```python\n{code}\n```\n\nOutput:\n{stdout[:1500]}\n\nErrors:\n{stderr[:500]}"
        if stdout:
            return f"```python\n{code}\n```\n\nOutput:\n{stdout[:2000]}"
        if stderr:
            return f"```python\n{code}\n```\n\nError:\n{stderr[:2000]}"
        return f"```python\n{code}\n```\n\n(No output)"
    except subprocess.TimeoutExpired:
        return "Code execution timed out (15s limit)."
    except Exception as e:
        return f"Execution failed: {e}"
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

def parse_ai_response(text: str) -> dict | None:
    """Try to extract a JSON object from Iris's output."""
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None

def ai_agent_handle(user_input: str, retriever=None, history=None, **kwargs):
    """Generator that yields events for the frontend: tokens, actions, results."""
    history = history or []

    force_role = kwargs.get("force_role") or getattr(ai_agent_handle, "force_role", None)
    settings = kwargs.get("settings", {})

    if not force_role:
        math_res = solve_math(user_input)
        if math_res is not None:
            yield {"type": "token", "content": math_res}
            return

    from src.iris import ask_stream
    keep_loaded = kwargs.get("keep_loaded", False)
    yield from ask_stream(user_input, history, retriever=retriever, force_role=force_role, settings=settings, keep_loaded=keep_loaded)

def execute_action_by_dict(action_dict: dict) -> str:
    action = action_dict.get("action", "chat")
    try:
        if action == "open_website":
            url = action_dict.get("url", "")
            import re as _re
            if _re.search(r"youtube\.com/watch\?v=", url):
                log_action("youtube", f"Warning: YouTube watch URL intercepted ({url}). Redirecting to search...")
                _open_url("https://www.youtube.com")
                return "Opened YouTube (tip: use video title next time for accurate results)."
            return handle_website_from_url(url)
        elif action == "open_app":
            app = action_dict.get("name", "")
            return handle_app_by_name(app, load_config())
        elif action == "close_app":
            app = action_dict.get("name", "")
            return handle_close_app_by_name(app, load_config())
        elif action == "open_settings":
            return handle_open_settings()
        elif action == "youtube_video":
            query = action_dict.get("query", "")
            return handle_youtube_video_from_query(query)
        elif action == "youtube_channel":
            name = action_dict.get("name", "")
            return handle_youtube_channel_from_name(name)
        elif action == "spotify_song":
            query = action_dict.get("query", "")
            return handle_spotify_song(query)
        elif action == "send_email":
            to = action_dict.get("to", "")
            subject = action_dict.get("subject", "")
            body = action_dict.get("body", "")
            return handle_email_from_parts(to, subject, body, load_config())
        elif action == "open_file":
            path = action_dict.get("path", "")
            return handle_file_from_path(path)
        elif action == "search_files":
            query = action_dict.get("query", "")
            folder = action_dict.get("folder", "")
            return handle_search_from_query(query, folder)
        elif action == "run_command":
            cmd = action_dict.get("command", "")
            return handle_run_command(cmd)
        elif action == "run_code":
            code = action_dict.get("code", "")
            return handle_run_code(code)
        elif action == "analyze_image":
            from src.iris import analyze_image
            path = action_dict.get("image_path", "")
            prompt = action_dict.get("prompt", "Describe this image in detail.")
            return analyze_image(path, prompt)
        elif action == "web_search":
            query = action_dict.get("query", "")
            import urllib.parse
            q = urllib.parse.quote(query)
            if "amazon" in query.lower() and "egypt" in query.lower():
                url = f"https://www.amazon.eg/s?k={q}"
            elif "amazon" in query.lower():
                url = f"https://www.amazon.com/s?k={q}"
            else:
                url = f"https://www.google.com/search?q={q}"
            _open_url(url)
            return f"Opened browser and searched for '{query}'."
        elif action == "search_image_web":
            path = action_dict.get("image_path", "")
            return handle_search_image_web(path)
        elif action == "fix_file":
            path = action_dict.get("path", "")
            instr = action_dict.get("instructions", "")
            return handle_fix_file(path, instr)
        elif action == "browser_login":
            from src.browser_agent import browser_login
            url      = action_dict.get("url", "")
            username = action_dict.get("username", "")
            password = action_dict.get("password", "")
            if not url:
                return "browser_login requires a 'url' field."
            if not username or not password:
                return "Please tell me the username/email and password to use for login."
            return browser_login(url, username, password)
        elif action == "browser_task":
            from src.browser_agent import browser_task as _browser_task
            url  = action_dict.get("url", "")
            task = action_dict.get("task", "")
            if not url:
                return "browser_task requires a 'url' field."
            return _browser_task(url, task)
        elif action == "browser_autopilot":
            from src.browser_agent import browser_autopilot as _browser_autopilot
            from src.browser_agent import parse_resume as _parse_resume
            url         = action_dict.get("url", "")
            task        = action_dict.get("task", "")
            resume_path = action_dict.get("resume", "")
            max_turns   = int(action_dict.get("max_turns", 15))
            if not url:
                return "browser_autopilot requires a 'url' field."
            if not task:
                return "browser_autopilot requires a 'task' field."
            return _browser_autopilot(url, task, resume_path=resume_path or None, max_turns=max_turns)
        elif action == "parse_resume":
            from src.browser_agent import parse_resume as _parse_resume
            resume_path = action_dict.get("path", "")
            if not resume_path:
                return "parse_resume requires a 'path' field."
            result = _parse_resume(resume_path)
            return json.dumps(result, indent=2)
        elif action == "create_file":
            path    = action_dict.get("path", "")
            content = action_dict.get("content", "")
            return handle_create_file(path, content)
        elif action == "read_file":
            path = action_dict.get("path", "")
            return handle_read_file(path)
        elif action == "append_file":
            path    = action_dict.get("path", "")
            content = action_dict.get("content", "")
            return handle_append_file(path, content)
        elif action == "replace_in_file":
            path    = action_dict.get("path", "")
            find    = action_dict.get("find", "")
            replace = action_dict.get("replace", "")
            return handle_replace_in_file(path, find, replace)
        elif action == "move_file":
            src = action_dict.get("src", "")
            dst = action_dict.get("dst", "")
            return handle_move_file(src, dst)
        elif action == "copy_file":
            src = action_dict.get("src", "")
            dst = action_dict.get("dst", "")
            return handle_copy_file(src, dst)
        elif action == "delete_file":
            path = action_dict.get("path", "")
            return handle_delete_file(path)
        elif action == "create_folder":
            path = action_dict.get("path", "")
            return handle_create_folder(path)
        elif action == "rename_file":
            path     = action_dict.get("path", "")
            new_name = action_dict.get("new_name", "")
            return handle_rename_file(path, new_name)
        elif action == "compress_files":
            paths  = action_dict.get("paths", [])
            output = action_dict.get("output", "")
            return handle_compress_files(paths, output)
        elif action == "extract_file":
            path = action_dict.get("path", "")
            dest = action_dict.get("dest", "")
            return handle_extract_file(path, dest)
        elif action == "download_file":
            url  = action_dict.get("url", "")
            path = action_dict.get("path", "")
            return handle_download_file(url, path)
        elif action == "brightness_up":
            return handle_brightness("up")
        elif action == "brightness_down":
            return handle_brightness("down")
        elif action in ("brightness_set", "set_brightness"):
            pct = action_dict.get("percent")
            if pct is None:
                pct = action_dict.get("pct", 50)
            if isinstance(pct, str):
                pct = pct.replace('%', '').strip()
            return handle_brightness_set(int(float(pct)))
        elif action == "volume_up":
            return handle_volume("up")
        elif action == "volume_down":
            return handle_volume("down")
        elif action == "volume_mute":
            return handle_volume("mute")
        elif action in ("volume_set", "set_volume"):
            pct = action_dict.get("percent")
            if pct is None:
                pct = action_dict.get("pct", 50)
            if isinstance(pct, str):
                pct = pct.replace('%', '').strip()
            return handle_volume_set(int(float(pct)))
        elif action == "say":
            text = action_dict.get("text", "")
            return handle_say(text)
        elif action == "system_info":
            what = action_dict.get("what", "all")
            return get_system_info(what)
        elif action == "clipboard_copy":
            text = action_dict.get("text", "")
            return clipboard_copy(text)
        elif action == "clipboard_read":
            return clipboard_read()
        elif action == "open_terminal":
            cmd = action_dict.get("command", "")
            return handle_open_terminal(cmd if cmd else None)
        elif action in ("git", "docker", "npm", "pip", "brew"):
            cmd_arg = action_dict.get("command", "")
            full_cmd = f"{action} {cmd_arg}"
            return handle_run_command(full_cmd)
        elif action == "window_close":
            return handle_window_close()
        elif action == "window_minimize":
            return handle_window_minimize()
        elif action == "window_maximize":
            return handle_window_maximize()
        elif action == "window_fullscreen":
            return handle_window_fullscreen()
        elif action == "switch_tab":
            direction = action_dict.get("direction", "next")
            return handle_switch_tab(direction)
        elif action == "wifi":
            state = action_dict.get("state", "on")
            return handle_wifi(state)
        elif action == "bluetooth":
            state = action_dict.get("state", "on")
            return handle_bluetooth(state)
        elif action == "vpn":
            act = action_dict.get("vpn_action") or action_dict.get("action", "connect")
            name = action_dict.get("name", "")
            return handle_vpn(act, name)
        elif action == "network_speed_test":
            return handle_speed_test()
        elif action == "flush_dns":
            return handle_flush_dns()
        elif action == "lock_screen":
            return handle_lock_screen()
        elif action == "sleep_computer":
            return handle_sleep()
        elif action == "restart_computer":
            return handle_restart()
        elif action == "shutdown_computer":
            return handle_shutdown()
        elif action == "do_not_disturb":
            state = action_dict.get("state", "on")
            return handle_dnd(state)
        elif action == "dark_mode":
            state = action_dict.get("state", "on")
            return handle_dark_mode(state)
        elif action == "night_shift":
            state = action_dict.get("state", "on")
            return handle_night_shift(state)
        elif action == "set_wallpaper":
            path = action_dict.get("path", "")
            return handle_set_wallpaper(path)
        elif action == "screenshot":
            path = action_dict.get("path", "")
            if not path:
                path = "~/Desktop/screenshot.png"
            return handle_screenshot(path)
        elif action == "screen_record":
            path = action_dict.get("path", "")
            duration = action_dict.get("duration", 10)
            return handle_screen_record(path, int(duration))
        elif action == "kill_process":
            name = action_dict.get("name", "")
            return handle_kill_process(name)
        elif action == "set_env":
            key = action_dict.get("key", "")
            val = action_dict.get("value", "")
            return handle_set_env(key, val)
        elif action == "notification":
            title = action_dict.get("title", "Iris")
            body = action_dict.get("body", "")
            return handle_notification(title, body)
        elif action == "take_note":
            content = action_dict.get("content", "")
            return handle_take_note(content)
        elif action == "empty_trash":
            return handle_empty_trash()
        elif action == "type_text":
            text = action_dict.get("text", "")
            return handle_type_text(text)
        elif action == "press_keys":
            keys = action_dict.get("keys", "")
            return handle_press_keys(keys)
        elif action == "focus_app":
            name = action_dict.get("name", "")
            return handle_focus_app(name)
        elif action == "media_play_pause":
            return handle_media("play_pause")
        elif action == "media_next":
            return handle_media("next")
        elif action == "media_previous":
            return handle_media("previous")
        elif action == "media_stop":
            return handle_media("stop")
        elif action == "chat":
            return ""
    except Exception as e:
        return f"Action failed: {e}"
    return f"Action '{action}' is defined in your training data but not yet implemented in controller.py!"

def _open_url(url: str):
    if not url.startswith("http"):
        url = "https://" + url
    log_action("browser", f"Opening {url}")
    webbrowser.open(url)

def handle_search_image_web(image_path: str) -> str:
    import os
    import subprocess
    import urllib.parse

    if not os.path.exists(image_path):
        return f"Image not found at {image_path}"

    log_action("search", "Uploading image for reverse search...")
    img_url = None

    cmd1 = ["curl", "-s", "-F", "reqtype=fileupload", "-F", "time=1h", "-F", f"fileToUpload=@{image_path}", "https://litterbox.catbox.moe/api.php"]
    try:
        res = subprocess.run(cmd1, capture_output=True, text=True, timeout=8)
        out = res.stdout.strip()
        if out.startswith("http"):
            img_url = out
    except Exception:
        pass

    if not img_url:
        import json
        cmd2 = ["curl", "-s", "-F", f"file=@{image_path}", "https://tmpfiles.org/api/v1/upload"]
        try:
            res = subprocess.run(cmd2, capture_output=True, text=True, timeout=15)
            data = json.loads(res.stdout)
            if data.get("status") == "success":
                url = data["data"]["url"]
                img_url = url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
        except Exception as e:
            pass

    if not img_url:
        return "Upload failed: All temporary image hosts timed out."

    bing_url = f"https://www.bing.com/images/search?view=detailv2&iss=sbi&FORM=SBIHMP&q=imgurl:{urllib.parse.quote(img_url)}"

    import urllib.request
    import ssl
    import re

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    }
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(bing_url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        title = ""
        title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
        if title_match:
            title = title_match.group(1).replace("- Bing Images", "").strip()

        clean_text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.IGNORECASE|re.DOTALL)
        clean_text = re.sub(r'<script[^>]*>.*?</script>', '', clean_text, flags=re.IGNORECASE|re.DOTALL)

        clean_text = re.sub(r'<[^>]+>', ' ', clean_text)

        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        return f"Silently performed reverse image search via Bing.\n\nPage Title: {title}\n\nVisible Page Text Snippet:\n{clean_text[:1000]}"
    except Exception as e:
        logger.warning(f"[Bing Scrape Error] {e}")
        pass

    return "Silently searched Bing Visual Search, but could not reliably extract the visual match."

def handle_website(match: re.Match):
    url = match.group(1).strip()
    _open_url(url)
    return f"Opening {url} in your browser."

def handle_website_from_url(url: str):
    _open_url(url)
    return f"Opening {url}."

def _launch_app(cmd: str):
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(cmd)
            return True
        elif system == "Darwin":
            subprocess.Popen(["open", "-a", cmd])
            return True
        else:
            subprocess.Popen([cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    except Exception as e:
        if system == "Windows":
            logger.warning(f"  [ERROR] Could not launch on Windows: {e}")
            return False
        try:
            subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e2:
            logger.warning(f"  [ERROR] Could not launch: {e2}")
            return False

def handle_app(match: re.Match, config: dict):
    app_name = match.group(1).strip().lower()
    return handle_app_by_name(app_name, config)

def _resolve_app_command(app_name: str, config: dict = None):
    if config is None:
        config = load_config()
    apps_map = config.get("apps", {})
    cmd = apps_map.get(app_name.lower())
    if not cmd:
        for key, val in apps_map.items():
            if key in app_name.lower() or app_name.lower() in key:
                cmd = val
                break
                
    if cmd and platform.system() != "Windows":
        if cmd.lower().endswith(".exe") or cmd.lower().startswith("shell:"):
            cmd = None
            
    if not cmd and platform.system() == "Linux":
        linux_defaults = {
            "settings": "gnome-control-center",
            "calculator": "gnome-calculator",
            "calc": "gnome-calculator",
            "notepad": "gedit",
            "text editor": "gnome-text-editor",
            "paint": "drawing",
            "store": "gnome-software",
            "software": "gnome-software",
            "camera": "cheese",
            "clock": "gnome-clocks",
            "clocks": "gnome-clocks",
            "mail": "thunderbird",
            "calendar": "gnome-calendar",
            "weather": "gnome-weather",
            "photos": "eog",
            "image viewer": "eog",
            "maps": "gnome-maps",
            "task manager": "gnome-system-monitor",
            "system monitor": "gnome-system-monitor",
            "terminal": "gnome-terminal",
            "files": "nautilus",
            "explorer": "nautilus",
            "videos": "totem",
            "music": "rhythmbox",
            "contacts": "gnome-contacts",
            "disks": "gnome-disks",
            "document viewer": "evince",
            "pdf": "evince",
            "characters": "gnome-characters",
            "fonts": "gnome-font-viewer",
            "passwords": "seahorse",
            "logs": "gnome-logs",
            "tweaks": "gnome-tweaks",
            "archive manager": "file-roller",
            "disk usage": "baobab",
            "screenshot": "gnome-screenshot",
            "scanner": "simple-scan",
            "help": "yelp",
            "browser": "firefox"
        }
        for k, v in linux_defaults.items():
            if k in app_name.lower() or app_name.lower() in k:
                cmd = v
                break
        
        if not cmd:
            import glob, re
            desktop_files = glob.glob("/usr/share/applications/*.desktop") + glob.glob(os.path.expanduser("~/.local/share/applications/*.desktop"))
            for desktop_file in desktop_files:
                try:
                    with open(desktop_file, "r", encoding="utf-8", errors="ignore") as f:
                        name = ""
                        exec_cmd = ""
                        for line in f:
                            if line.startswith("Name="):
                                name = line.split("=", 1)[1].strip().lower()
                            elif line.startswith("Exec="):
                                exec_cmd = line.split("=", 1)[1].strip()
                            if name and exec_cmd:
                                break
                        if name and (app_name.lower() in name or name in app_name.lower()) and exec_cmd:
                            cmd = re.sub(r'%[a-zA-Z]', '', exec_cmd).strip()
                            break
                except Exception:
                    continue
    
    if not cmd and platform.system() == "Windows":
        windows_defaults = {
            "settings": "ms-settings:",
            "calculator": "calc",
            "calc": "calc",
            "notepad": "notepad",
            "paint": "mspaint",
            "store": "ms-windows-store:",
            "camera": "microsoft.windows.camera:",
            "clock": "ms-clock:",
            "mail": "outlookmail:",
            "calendar": "outlookcal:",
            "weather": "bingweather:",
            "photos": "ms-photos:",
            "maps": "bingmaps:",
            "task manager": "taskmgr",
            "control panel": "control",
            "word": "winword",
            "excel": "excel",
            "powerpoint": "powerpnt"
        }
        cmd = windows_defaults.get(app_name.lower())

        if not cmd:
            try:
                import subprocess, json
                CREATE_NO_WINDOW = 0x08000000
                safe_name = app_name.replace("'", "''")
                ps_cmd = f"$n='{safe_name}'; Get-StartApps | Where-Object {{ $_.Name.ToLower().Contains($n.ToLower()) }} | Select-Object -First 1 AppID | ConvertTo-Json"
                res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
                if res.returncode == 0 and res.stdout.strip():
                    data = json.loads(res.stdout)
                    if data and "AppID" in data:
                        cmd = f"shell:AppsFolder\\{data['AppID']}"
            except Exception as e:
                logger.warning(f"  [App Search Error] {e}")

    if not cmd:
        cmd = app_name
    return cmd

def handle_app_by_name(app_name: str, config: dict = None):
    cmd = _resolve_app_command(app_name, config)
    log_action("app", f"Launching: {cmd}")
    success = _launch_app(cmd)
    if success:
        return f"Launching {app_name}."
    else:
        return f"I couldn't find '{app_name}'. Add it to {CONFIG_FILE} under 'apps'."

def handle_close_app_by_name(app_name: str, config: dict = None):
    cmd = _resolve_app_command(app_name, config)
    exec_name = extract_executable_name(cmd)
    if not exec_name:
        exec_name = app_name
    log_action("app", f"Closing app: {exec_name}")
    return handle_kill_process(exec_name)

def handle_open_settings():
    system = platform.system()
    if system == "Darwin":
        cmd = "open x-apple.systempreferences:"
    elif system == "Windows":
        cmd = "start ms-settings:"
    else:
        cmd = "gnome-control-center"
    log_action("system", f"Opening settings: {cmd}")
    try:
        subprocess.run(cmd, shell=True, start_new_session=True)
        return "Opened settings."
    except Exception as e:
        return f"Failed to open settings: {e}"

def _youtube_search_url(query: str) -> str:
    q = urllib.parse.quote_plus(query)
    return f"https://www.youtube.com/results?search_query={q}"

def _youtube_find_first_video(query: str) -> str | None:
    search_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    ctx = ssl.create_default_context()
    try:
        ctx.load_default_certs()
    except Exception:
        pass
    try:
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, ssl.SSLError) as e:
        logger.warning(f"  [YouTube] SSL error, retrying without verification: {e}")
        ctx = ssl._create_unverified_context()
        try:
            req2 = urllib.request.Request(search_url, headers=headers)
            with urllib.request.urlopen(req2, timeout=8, context=ctx) as resp2:
                html = resp2.read().decode("utf-8", errors="replace")
        except Exception as e2:
            logger.warning(f"  [YouTube search error] {e2}")
            return None
    video_ids = re.findall(r'"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"', html)
    if video_ids:
        return f"https://www.youtube.com/watch?v={video_ids[0]}"
    return None

def _youtube_find_channel(query: str) -> str | None:
    search_url = (
        "https://www.youtube.com/results?search_query="
        + urllib.parse.quote_plus(query + " channel")
        + "&sp=EgIQAg%3D%3D"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    ctx = ssl.create_default_context()
    try:
        ctx.load_default_certs()
    except Exception:
        pass
    try:
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, ssl.SSLError) as e:
        logger.warning(f"  [YouTube] SSL error, retrying without verification: {e}")
        ctx = ssl._create_unverified_context()
        try:
            req2 = urllib.request.Request(search_url, headers=headers)
            with urllib.request.urlopen(req2, timeout=8, context=ctx) as resp2:
                html = resp2.read().decode("utf-8", errors="replace")
        except Exception as e2:
            logger.warning(f"  [YouTube channel search error] {e2}")
            return None
    channel_ids = re.findall(r'"channelId"\s*:\s*"(UC[a-zA-Z0-9_-]{22})"', html)
    if channel_ids:
        return f"https://www.youtube.com/channel/{channel_ids[0]}"
    handles = re.findall(r'"canonicalBaseUrl"\s*:\s*"(/@[^"]+)"', html)
    if handles:
        return f"https://www.youtube.com{handles[0]}"
    return None

def handle_youtube_video(match: re.Match):
    return handle_youtube_video_from_query(match.group(1).strip())

def handle_youtube_video_from_query(query: str):
    log_action("youtube", f"Searching for video: '{query}'")
    url = _youtube_find_first_video(query)
    if url:
        _open_url(url)
        return f"Opening YouTube video: {url}"
    else:
        search_url = _youtube_search_url(query)
        _open_url(search_url)
        return f"Searching YouTube for '{query}'."

def handle_youtube_channel(match: re.Match):
    return handle_youtube_channel_from_name(match.group(1).strip())

def handle_youtube_channel_from_name(name: str):
    log_action("youtube", f"Searching for channel: '{name}'")
    url = _youtube_find_channel(name)
    if url:
        _open_url(url)
        return f"Opening YouTube channel: {name}"
    else:
        search_url = _youtube_search_url(name + " channel")
        _open_url(search_url)
        return f"Searching YouTube for channel '{name}'."

def handle_spotify(match: re.Match):
    return handle_spotify_song(match.group(1).strip())

def handle_spotify_song(query: str):
    log_action("spotify", f"Searching for: '{query}'")
    import urllib.parse
    q = urllib.parse.quote(query)
    url = f"https://open.spotify.com/search/{q}"
    _open_url(url)
    return f"Playing '{query}' on Spotify."

def _resolve_contact(raw: str, contacts: dict) -> str:
    if raw and "@" in raw:
        return raw.strip()
    return contacts.get(raw.strip().lower(), raw or "")

def _interactive_email_build(config: dict) -> dict | None:
    if not IS_INTERACTIVE:
        return None

    contacts = config.get("email", {}).get("contacts", {})
    if RICH_AVAILABLE:
        console.print("\n[bold cyan]── Compose Email ──────────────────────────────[/bold cyan]")
        raw_to = Prompt.ask("  [bold yellow]To (name or email)[/bold yellow]").strip()
    else:
        logger.info("\n  ── Compose Email ──────────────────────────────")
        raw_to = input("  To (name or email): ").strip()

    if not raw_to:
        return None
    to_addr = _resolve_contact(raw_to, contacts)
    if not to_addr or "@" not in to_addr:
        if RICH_AVAILABLE:
            console.print(f"  [red][!] '{raw_to}' not found in contacts and doesn't look like an email.[/red]")
            to_addr = Prompt.ask("  [bold yellow]Enter full email address[/bold yellow]").strip()
        else:
            logger.info(f"  [!] '{raw_to}' not found in contacts and doesn't look like an email.")
            to_addr = input("  Enter full email address: ").strip()
        if not to_addr:
            return None

    if RICH_AVAILABLE:
        subject = Prompt.ask("  [bold yellow]Subject[/bold yellow]", default="(no subject)").strip()
        console.print("  [bold yellow]Body[/bold yellow] (type [bold green]END[/bold green] on a new line to finish):")
    else:
        subject = input("  Subject: ").strip() or "(no subject)"
        logger.info("  Body (type END on a new line to finish):")
    lines = []
    while True:
        if RICH_AVAILABLE:
            line = input("    ")
        else:
            line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line)
    body = "\n".join(lines).strip()
    return {"to": to_addr, "subject": subject, "body": body}

def _send_email(to: str, subject: str, body: str, config: dict) -> str:
    email_cfg = config.get("email", {})
    sender = email_cfg.get("sender_address", "")
    password = email_cfg.get("sender_password", "")
    smtp_server = email_cfg.get("smtp_server", "smtp.gmail.com")
    smtp_port = int(email_cfg.get("smtp_port", 587))
    if not sender or sender == "your_email@gmail.com":
        return "You aren't logged in, Please edit control.conf"
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, to, msg.as_string())
        return f"Email sent to {to}."
    except smtplib.SMTPAuthenticationError:
        return "Authentication failed. For Gmail, use an App Password (myaccount.google.com → Security → App Passwords)."
    except Exception as e:
        return f"Failed to send email: {e}"

def handle_email(match: re.Match, config: dict) -> str:
    to_raw = (match.group("to") or "").strip()
    subject = (match.group("subject") or "").strip()
    body = (match.group("body") or "").strip()
    return handle_email_from_parts(to_raw, subject, body, config)

def handle_email_from_parts(to_raw: str, subject: str, body: str, config: dict) -> str:
    contacts = config.get("email", {}).get("contacts", {})
    to_addr = _resolve_contact(to_raw, contacts) if to_raw else ""
    if not to_addr or "@" not in to_addr:
        data = _interactive_email_build(config)
        if data is None:
            return "Email cancelled."
        to_addr, subject, body = data["to"], data["subject"], data["body"]
    else:
        if not subject:
            if IS_INTERACTIVE:
                if RICH_AVAILABLE:
                    subject = Prompt.ask(f"  [bold yellow]Subject for email to {to_addr}[/bold yellow]", default="(no subject)").strip()
                else:
                    subject = input(f"  Subject for email to {to_addr}: ").strip() or "(no subject)"
            else:
                subject = "(no subject)"
        if not body:
            if IS_INTERACTIVE:
                if RICH_AVAILABLE:
                    console.print("  [bold yellow]Body[/bold yellow] (type [bold green]END[/bold green] on a new line to finish):")
                else:
                    logger.info("  Body (type END on a new line to finish):")
                lines = []
                while True:
                    if RICH_AVAILABLE:
                        line = input("    ")
                    else:
                        line = input()
                    if line.strip().upper() == "END":
                        break
                    lines.append(line)
                body = "\n".join(lines).strip()
            else:
                body = "(no body)"

    if IS_INTERACTIVE:
        if RICH_AVAILABLE:
            console.print(f"\n[bold cyan]── Preview ─────────────────────────────────[/bold cyan]")
            console.print(f"  [bold yellow]To:[/bold yellow]      {to_addr}")
            console.print(f"  [bold yellow]Subject:[/bold yellow] {subject}")
            console.print(f"  [bold yellow]Body:[/bold yellow]\n{body}\n")
            confirm = Prompt.ask("  [bold green]Send?[/bold green]", choices=["y", "n"], default="n").strip().lower()
        else:
            logger.info(f"\n  ── Preview ─────────────────────────────────")
            logger.info(f"  To:      {to_addr}")
            logger.info(f"  Subject: {subject}")
            logger.info(f"  Body:\n{body}\n")
            confirm = input("  Send? [y/N]: ").strip().lower()
        if confirm != "y":
            return "Email cancelled."
    return _send_email(to_addr, subject, body, config)

def handle_open_file(path_str: str):
    path = Path(path_str).expanduser().resolve()
    if not path.exists():
        return f"Path does not exist: {path}"
    log_action("file", f"Opening {path}")
    try:
        if platform.system() == "Windows":
            os.startfile(str(path))
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return f"Opened {path}."
    except Exception as e:
        return f"Could not open {path}: {e}"

def handle_search_files(query: str, folder: str):
    folder_path = Path(folder).expanduser().resolve()
    if not folder_path.is_dir():
        return f"Folder not found: {folder_path}"
    log_action("search", f"Searching for '{query}' in {folder_path}")
    results = []
    for root, dirs, files in os.walk(folder_path):
        for name in files + dirs:
            if query.lower() in name.lower():
                results.append(str(Path(root) / name))
        if len(results) >= 20:
            break
    if not results:
        return f"No files or folders matching '{query}' found."
    out = "Found:\n" + "\n".join(results[:10])
    if len(results) > 10:
        out += f"\n... and {len(results)-10} more."
    return out

COMMAND_PACKAGE_MAP = {
    "ffmpeg": {
        "Windows": "Gyan.FFmpeg",
        "Darwin": "ffmpeg",
        "Linux": "ffmpeg"
    },
    "git": {
        "Windows": "Git.Git",
        "Darwin": "git",
        "Linux": "git"
    },
    "node": {
        "Windows": "OpenJS.NodeJS",
        "Darwin": "node",
        "Linux": "nodejs"
    },
    "npm": {
        "Windows": "OpenJS.NodeJS",
        "Darwin": "node",
        "Linux": "npm"
    },
    "npx": {
        "Windows": "OpenJS.NodeJS",
        "Darwin": "node",
        "Linux": "npm"
    },
    "curl": {
        "Windows": "cURL.cURL",
        "Darwin": "curl",
        "Linux": "curl"
    },
    "wget": {
        "Windows": "GNU.Wget",
        "Darwin": "wget",
        "Linux": "wget"
    },
    "jq": {
        "Windows": "jqlang.jq",
        "Darwin": "jq",
        "Linux": "jq"
    },
    "pandoc": {
        "Windows": "JohnMacFarlane.Pandoc",
        "Darwin": "pandoc",
        "Linux": "pandoc"
    },
    "graphviz": {
        "Windows": "Graphviz.Graphviz",
        "Darwin": "graphviz",
        "Linux": "graphviz"
    },
    "dot": {
        "Windows": "Graphviz.Graphviz",
        "Darwin": "graphviz",
        "Linux": "graphviz"
    },
    "nircmd": {
        "Windows": "NirSoft.NirCmd",
        "Darwin": None,
        "Linux": None
    },
    "tesseract": {
        "Windows": "UB-Mannheim.TesseractOCR",
        "Darwin": "tesseract",
        "Linux": "tesseract-ocr"
    },
    "python": {
        "Windows": "Python.Python.3.11",
        "Darwin": "python3",
        "Linux": "python3"
    },
    "python3": {
        "Windows": "Python.Python.3.11",
        "Darwin": "python3",
        "Linux": "python3"
    },
    "make": {
        "Windows": "Ezwinports.Make",
        "Darwin": "make",
        "Linux": "make"
    },
    "docker": {
        "Windows": "Docker.DockerDesktop",
        "Darwin": "docker",
        "Linux": "docker.io"
    }
}

SHELL_BUILTINS = {
    # Windows
    "dir", "cd", "echo", "copy", "del", "md", "mkdir", "rd", "rmdir", "type", 
    "ren", "rename", "move", "cls", "ver", "vol", "path", "set", "exit", "pause", 
    "prompt", "title", "start",
    # Unix
    "pwd", "local", "export", "alias", "unalias", "read", "unset", "history", 
    "builtin", "bg", "fg", "jobs", "ls"
}

def extract_executable_name(command_str: str) -> str:
    import shlex
    try:
        tokens = shlex.split(command_str)
    except Exception:
        tokens = command_str.split()
    
    if not tokens:
        return ""
    
    # Filter out environment variables at the start (e.g. VAR=value)
    start_idx = 0
    while start_idx < len(tokens) and "=" in tokens[start_idx] and not tokens[start_idx].startswith("-"):
        start_idx += 1
        
    if start_idx >= len(tokens):
        return ""
        
    exec_path = tokens[start_idx]
    # Get the basename without extension
    basename = os.path.basename(exec_path)
    name, ext = os.path.splitext(basename)
    return name.lower()

def reload_system_path():
    system = platform.system()
    if system == "Windows":
        try:
            import winreg
            paths = []
            # Read user PATH
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as key:
                    user_path, _ = winreg.QueryValueEx(key, "Path")
                    paths.extend(user_path.split(";"))
            except Exception:
                pass
            # Read system PATH
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"System\CurrentControlSet\Control\Session Manager\Environment", 0, winreg.KEY_READ) as key:
                    sys_path, _ = winreg.QueryValueEx(key, "Path")
                    paths.extend(sys_path.split(";"))
            except Exception:
                pass
            
            path_list = []
            for p in paths:
                p_str = os.path.expandvars(p.strip())
                if p_str and p_str not in path_list:
                    path_list.append(p_str)
            if path_list:
                os.environ["PATH"] = ";".join(path_list)
                logger.info("[System] Windows PATH reloaded from registry.")
        except Exception as e:
            logger.warning(f"[Warning] Failed to reload Windows PATH from registry: {e}")
    elif system == "Darwin":
        # Apple Silicon Homebrew path
        brew_bin = "/opt/homebrew/bin"
        if brew_bin not in os.environ.get("PATH", ""):
            os.environ["PATH"] = brew_bin + os.path.pathsep + os.environ.get("PATH", "")

def install_command(exec_name: str) -> bool:
    system = platform.system()
    pkg_name = exec_name
    
    if exec_name in COMMAND_PACKAGE_MAP:
        pkg_name = COMMAND_PACKAGE_MAP[exec_name].get(system)
        if not pkg_name:
            log_action("system", f"No mapped package for '{exec_name}' on {system}.")
            return False

    log_action("system", f"Attempting to install '{pkg_name}' via platform package manager...")

    if system == "Windows":
        if not shutil.which("winget"):
            log_action("system", "winget is not available on this system.")
            if pkg_name == "NirSoft.NirCmd":
                log_action("system", "Attempting manual download of NirCmd...")
                try:
                    import urllib.request
                    import zipfile
                    import io
                    url = "https://www.nirsoft.net/utils/nircmd.zip"
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=15) as response:
                        with zipfile.ZipFile(io.BytesIO(response.read())) as z:
                            target_dir = os.path.join(os.path.expanduser("~"), ".iris_bin")
                            os.makedirs(target_dir, exist_ok=True)
                            z.extract("nircmd.exe", target_dir)
                            
                            try:
                                import winreg
                                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
                                    user_path, _ = winreg.QueryValueEx(key, "Path")
                                    if target_dir not in user_path.split(";"):
                                        updated_path = user_path.rstrip(";") + ";" + target_dir
                                        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, updated_path)
                            except Exception as e:
                                log_action("system", f"Failed to update user PATH registry: {e}")
                            
                            os.environ["PATH"] = target_dir + os.pathsep + os.environ.get("PATH", "")
                            log_action("system", "Successfully installed NirCmd manually.")
                            return True
                except Exception as e:
                    log_action("system", f"Manual download of NirCmd failed: {e}")
            return False
        # Run winget install command
        cmd = f"winget install --silent --accept-source-agreements --accept-package-agreements {pkg_name}"
        log_action("system", f"Running: {cmd}")
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            log_action("system", f"Successfully installed '{pkg_name}' via winget.")
            reload_system_path()
            return True
        else:
            log_action("system", f"winget installation failed (Exit {res.returncode}): {res.stderr or res.stdout}")
            return False

    elif system == "Darwin":
        if not shutil.which("brew"):
            log_action("system", "brew (Homebrew) is not available on this system.")
            return False
        cmd = f"brew install {pkg_name}"
        log_action("system", f"Running: {cmd}")
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            log_action("system", f"Successfully installed '{pkg_name}' via brew.")
            reload_system_path()
            return True
        else:
            log_action("system", f"brew installation failed (Exit {res.returncode}): {res.stderr or res.stdout}")
            return False

    elif system == "Linux":
        # Check package managers
        if shutil.which("apt-get"):
            cmd = f"sudo apt-get update && sudo apt-get install -y {pkg_name}"
        elif shutil.which("dnf"):
            cmd = f"sudo dnf install -y {pkg_name}"
        elif shutil.which("yum"):
            cmd = f"sudo yum install -y {pkg_name}"
        elif shutil.which("pacman"):
            cmd = f"sudo pacman -S --noconfirm {pkg_name}"
        else:
            log_action("system", "No supported Linux package manager found (apt, dnf, yum, pacman).")
            return False

        log_action("system", f"Running: {cmd}")
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            log_action("system", f"Successfully installed '{pkg_name}'.")
            return True
        else:
            log_action("system", f"Linux installation failed (Exit {res.returncode}): {res.stderr or res.stdout}")
            return False

    return False

def is_command_missing_error(code: int, stderr: str, exec_name: str) -> bool:
    if code in (9009, 127):
        return True
    lower_err = stderr.lower()
    if "not recognized as an internal or external command" in lower_err:
        return True
    if "command not found" in lower_err:
        return True
    if exec_name and "no such file or directory" in lower_err and exec_name in lower_err:
        return True
    return False

def handle_run_command(command: str):
    cmd_lower = command.strip().lower()
    if platform.system() == "Windows" and (cmd_lower.startswith("open ") or cmd_lower.startswith("start ")):
        app_name = command.strip()[command.strip().find(" ")+1:].strip()
        log_action("intercept", f"Redirecting shell command '{command}' to native Windows app launcher.")
        return handle_app_by_name(app_name, load_config())
        
    log_action("terminal", f"Running: {command}")
    
    exec_name = extract_executable_name(command)
    is_missing = False
    if exec_name and exec_name not in SHELL_BUILTINS:
        if shutil.which(exec_name) is None:
            is_missing = True
            
    if is_missing:
        log_action("system", f"Command '{exec_name}' appears to be missing. Attempting automatic installation...")
        installed = install_command(exec_name)
        if not installed:
            return f"Error: Command '{exec_name}' is missing and automatic installation failed."

    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        code = result.returncode

        if code != 0 and is_command_missing_error(code, stderr, exec_name) and not is_missing:
            log_action("system", f"Command failed with missing executable error (Exit {code}). Attempting automatic installation...")
            installed = install_command(exec_name)
            if installed:
                log_action("terminal", f"Retrying: {command}")
                result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
                stdout = result.stdout.strip()
                stderr = result.stderr.strip()
                code = result.returncode

        if code == 0:
            return f"Success (Exit 0):\n{stdout or '(No output)'}"[:1500]
        else:
            return f"Error (Exit {code}):\n{stderr or stdout or '(No error message)'}"[:1500]
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds."
    except Exception as e:
        if exec_name and not is_missing:
            log_action("system", f"Execution failed: {e}. Attempting automatic installation...")
            installed = install_command(exec_name)
            if installed:
                try:
                    log_action("terminal", f"Retrying: {command}")
                    result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
                    stdout = result.stdout.strip()
                    stderr = result.stderr.strip()
                    code = result.returncode
                    if code == 0:
                        return f"Success (Exit 0):\n{stdout or '(No output)'}"[:1500]
                    else:
                        return f"Error (Exit {code}):\n{stderr or stdout or '(No error message)'}"[:1500]
                except Exception as retry_e:
                    return f"Execution failed after retry: {retry_e}"
        return f"Execution failed: {e}"

def handle_open_terminal(command: str = None):
    system = platform.system()
    log_action("terminal", "Opening visible terminal...")
    try:
        if system == "Darwin":
            if command:

                escaped = command.replace('"', '\\"')
                script = f'tell application "Terminal" to do script "{escaped}"'
                subprocess.run(["osascript", "-e", script])
                subprocess.run(["osascript", "-e", 'tell application "Terminal" to activate'])
                return f"Opened Terminal and executed: {command}"
            else:
                subprocess.run(["open", "-a", "Terminal"])
                return "Opened Terminal."
        elif system == "Windows":
            if command:
                subprocess.Popen(["cmd", "/k", command])
            else:
                subprocess.Popen(["cmd"])
            return "Opened Command Prompt."
        else:

            for term in ["gnome-terminal", "xterm", "konsole"]:
                if shutil.which(term):
                    if command:
                        subprocess.Popen([term, "-e", f"bash -c '{command}; exec bash'"])
                    else:
                        subprocess.Popen([term])
                    return f"Opened {term}."
            return "Could not find a terminal emulator."
    except Exception as e:
        return f"Failed to open terminal: {e}"

def handle_volume(action: str):
    system = platform.system()
    if system == "Darwin":
        if action == "up":
            cmd = "osascript -e 'set volume output volume (output volume of (get volume settings) + 6.25)'"
        elif action == "down":
            cmd = "osascript -e 'set volume output volume (output volume of (get volume settings) - 6.25)'"
        elif action == "mute":
            cmd = "osascript -e 'set volume with output muted'"
        else:
            return "Unknown volume action."
    elif system == "Windows":

        import ctypes
        VK_VOLUME_MUTE = 0xAD
        VK_VOLUME_DOWN = 0xAE
        VK_VOLUME_UP = 0xAF
        
        def send_key(vk):
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)

        if action == "up":
            send_key(VK_VOLUME_UP)
        elif action == "down":
            send_key(VK_VOLUME_DOWN)
        elif action == "mute":
            send_key(VK_VOLUME_MUTE)
        else:
            return "Unknown volume action."
        log_action("system", f"Adjusting volume: {action}")
        return f"Success: Volume adjusted ({action})."
    else:
        import shutil
        cmd = None
        if shutil.which("wpctl"):
            if action == "up": cmd = "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+"
            elif action == "down": cmd = "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"
            elif action == "mute": cmd = "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"
            else: return "Unknown volume action."
        elif shutil.which("pactl"):
            if action == "up": cmd = "pactl set-sink-volume @DEFAULT_SINK@ +5%"
            elif action == "down": cmd = "pactl set-sink-volume @DEFAULT_SINK@ -5%"
            elif action == "mute": cmd = "pactl set-sink-mute @DEFAULT_SINK@ toggle"
            else: return "Unknown volume action."
        else:
            return "Failed to adjust volume: No native audio server found (wpctl/pactl)."
    log_action("system", f"Adjusting volume: {action}")
    return handle_run_command(cmd)

def handle_volume_set(pct: int):
    system = platform.system()
    if system == "Darwin":
        cmd = f"osascript -e 'set volume output volume {pct}'"
    elif system == "Windows":
        pct = max(0, min(100, pct))
        level = pct / 100.0
        ps_script = f"""
$code = @"
using System.Runtime.InteropServices;
[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IAudioEndpointVolume {{
    int f(); int g(); int h(); int i();
    int SetMasterVolumeLevelScalar(float fLevel, System.Guid pguidEventContext);
    int j(); int GetMasterVolumeLevelScalar(out float pfLevel);
}}
[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IMMDevice {{
    int Activate(ref System.Guid id, int clsCtx, int activationParams, out IAudioEndpointVolume aev);
}}
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IMMDeviceEnumerator {{
    int f();
    int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint);
}}
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] public class MMDeviceEnumeratorComObject {{ }}
public class Audio {{
    public static void SetVolume(float level) {{
        IMMDeviceEnumerator de = (IMMDeviceEnumerator)new MMDeviceEnumeratorComObject();
        IMMDevice dev; de.GetDefaultAudioEndpoint(0, 1, out dev);
        IAudioEndpointVolume aev; System.Guid guid = typeof(IAudioEndpointVolume).GUID;
        dev.Activate(ref guid, 23, 0, out aev);
        aev.SetMasterVolumeLevelScalar(level, System.Guid.Empty);
    }}
}}
"@
Add-Type -TypeDefinition $code
[Audio]::SetVolume({level})
"""
        try:
            import subprocess
            CREATE_NO_WINDOW = 0x08000000
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], creationflags=CREATE_NO_WINDOW)
            log_action("system", f"Setting volume to {pct}%")
            return f"Success: Set volume to {pct}%"
        except Exception as e:
            return f"Failed to set volume: {e}"
    else:
        import shutil
        pct = max(0, min(100, pct))
        cmd = None
        if shutil.which("wpctl"):
            cmd = f"wpctl set-volume @DEFAULT_AUDIO_SINK@ {pct}%"
        elif shutil.which("pactl"):
            cmd = f"pactl set-sink-volume @DEFAULT_SINK@ {pct}%"
        else:
            return "Failed to set volume: No native audio server found (wpctl/pactl)."
    log_action("system", f"Setting volume to {pct}%")
    return handle_run_command(cmd)

def linux_get_brightness() -> int:
    import os
    import re
    import subprocess
    import shutil

    # 1. Native sysfs read
    sysfs_dir = "/sys/class/backlight"
    if os.path.exists(sysfs_dir):
        for dev in os.listdir(sysfs_dir):
            try:
                with open(os.path.join(sysfs_dir, dev, "max_brightness"), "r") as f:
                    mx = int(f.read().strip())
                with open(os.path.join(sysfs_dir, dev, "brightness"), "r") as f:
                    curr = int(f.read().strip())
                if mx > 0:
                    return int((curr / mx) * 100)
            except:
                continue

    # 2. Native GNOME Mutter D-Bus (Wayland/X11 Ubuntu default)
    if shutil.which("gdbus"):
        res = subprocess.run(
            'gdbus call --session --dest org.gnome.Mutter.DisplayConfig --object-path /org/gnome/Mutter/DisplayConfig --method org.freedesktop.DBus.Properties.Get org.gnome.Mutter.DisplayConfig Backlight',
            shell=True, capture_output=True, text=True
        )
        if res.returncode == 0:
            max_match = re.search(r"'max':\s*<(\d+)>", res.stdout)
            val_match = re.search(r"'value':\s*<(\d+)>", res.stdout)
            if max_match and val_match:
                mx = int(max_match.group(1))
                curr = int(val_match.group(1))
                if mx > 0:
                    return int((curr / mx) * 100)
                
    # 3. Native KDE D-Bus fallback
    if shutil.which("qdbus"):
        res = subprocess.run(
            'qdbus org.kde.Solid.PowerManagement /org/kde/Solid/PowerManagement/Actions/BrightnessControl org.kde.Solid.PowerManagement.Actions.BrightnessControl.brightness',
            shell=True, capture_output=True, text=True
        )
        if res.returncode == 0:
            try:
                return int(res.stdout.strip())
            except:
                pass

    return -1

def linux_set_brightness(pct: int) -> bool:
    import os
    import shutil
    import subprocess
    
    pct = max(0, min(100, pct))
    
    # 1. Native brightnessctl (Dependency-free on Ubuntu, passwordless)
    if shutil.which("brightnessctl"):
        res = subprocess.run(f"brightnessctl set {pct}%", shell=True, capture_output=True)
        if res.returncode == 0:
            return True

    # 2. Native sysfs write
    sysfs_dir = "/sys/class/backlight"
    success = False
    if os.path.exists(sysfs_dir):
        for dev in os.listdir(sysfs_dir):
            try:
                with open(os.path.join(sysfs_dir, dev, "max_brightness"), "r") as f:
                    mx = int(f.read().strip())
                target = int((pct / 100.0) * mx)
                with open(os.path.join(sysfs_dir, dev, "brightness"), "w") as f:
                    f.write(str(target))
                success = True
            except:
                continue
    if success:
        return True
            
    # 3. Native GNOME Mutter D-Bus (Wayland/X11 Ubuntu default)
    if shutil.which("gdbus"):
        res = subprocess.run(
            'gdbus call --session --dest org.gnome.Mutter.DisplayConfig --object-path /org/gnome/Mutter/DisplayConfig --method org.freedesktop.DBus.Properties.Get org.gnome.Mutter.DisplayConfig Backlight',
            shell=True, capture_output=True, text=True
        )
        if res.returncode == 0:
            import re
            serial_match = re.search(r'uint32\s+(\d+)', res.stdout)
            connector_match = re.search(r"'connector':\s*<'([^']+)'", res.stdout)
            max_match = re.search(r"'max':\s*<(\d+)>", res.stdout)
            if serial_match and connector_match and max_match:
                serial = serial_match.group(1)
                connector = connector_match.group(1)
                mx = int(max_match.group(1))
                target = int((pct / 100.0) * mx)
                
                set_cmd = f'gdbus call --session --dest org.gnome.Mutter.DisplayConfig --object-path /org/gnome/Mutter/DisplayConfig --method org.gnome.Mutter.DisplayConfig.SetBacklight {serial} "{connector}" {target}'
                set_res = subprocess.run(set_cmd, shell=True, capture_output=True)
                if set_res.returncode == 0:
                    return True
            
    # 3. Native KDE D-Bus fallback
    if shutil.which("qdbus"):
        res = subprocess.run(
            f'qdbus org.kde.Solid.PowerManagement /org/kde/Solid/PowerManagement/Actions/BrightnessControl org.kde.Solid.PowerManagement.Actions.BrightnessControl.setBrightness {pct}',
            shell=True, capture_output=True
        )
        if res.returncode == 0:
            return True

    # 4. Native sysfs write via pkexec (Polkit GUI popup)
    if shutil.which("pkexec") and os.path.exists(sysfs_dir):
        for dev in os.listdir(sysfs_dir):
            try:
                br_path = os.path.join(sysfs_dir, dev, "brightness")
                mx_path = os.path.join(sysfs_dir, dev, "max_brightness")
                if not os.path.exists(br_path) or not os.path.exists(mx_path):
                    continue
                with open(mx_path, "r") as f:
                    mx = int(f.read().strip())
                target = int((pct / 100.0) * mx)
                res = subprocess.run(
                    f"echo {target} | pkexec tee {br_path}",
                    shell=True, capture_output=True
                )
                if res.returncode == 0:
                    return True
            except:
                continue
                
    return False


def handle_brightness(action: str):
    system = platform.system()
    if system == "Darwin":
        try:
            import ctypes
            cg = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
            display_id = cg.CGMainDisplayID()
            
            ds = ctypes.CDLL('/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices')
            ds.DisplayServicesGetBrightness.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_float)]
            ds.DisplayServicesGetBrightness.restype = ctypes.c_int
            
            val = ctypes.c_float()
            err = ds.DisplayServicesGetBrightness(display_id, ctypes.byref(val))
            if err == 0:
                current = val.value
                step = 0.0625
                new_val = current + step if action == "up" else current - step
                new_val = max(0.0, min(1.0, new_val))
                
                ds.DisplayServicesSetBrightness.argtypes = [ctypes.c_int, ctypes.c_float]
                ds.DisplayServicesSetBrightness.restype = None
                ds.DisplayServicesSetBrightness(display_id, new_val)
                log_action("system", f"Adjusted brightness: {action} (from {current:.2f} to {new_val:.2f})")
                return f"Brightness adjusted {action}."
        except Exception as e:
            step = 0.0625
            if action == "up":
                cmd = f"brightness 0.0625"
            elif action == "down":
                cmd = f"brightness -0.0625"
            else:
                return "Unknown brightness action."
            log_action("system", f"Adjusting brightness via CLI fallback: {action}")
            return handle_run_command(cmd)
    elif system == "Windows":
        script = """
$monitor = Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness
$methods = Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods
$current = $monitor.CurrentBrightness
$step = 10
"""
        if action == "up":
            script += "$new = $current + $step\n"
        elif action == "down":
            script += "$new = $current - $step\n"
        else:
            return "Unknown brightness action."
            
        script += """
if ($new -gt 100) { $new = 100 }
if ($new -lt 0) { $new = 0 }
$methods.WmiSetBrightness(1, $new)
"""
        try:
            import subprocess
            CREATE_NO_WINDOW = 0x08000000
            subprocess.run(["powershell", "-NoProfile", "-Command", script], creationflags=CREATE_NO_WINDOW)
            log_action("system", f"Adjusted brightness: {action}")
            return f"Brightness adjusted {action}."
        except Exception as e:
            return f"Failed to adjust brightness: {e}"
    else:
        # Linux branch
        curr = linux_get_brightness()
        if curr == -1:
            curr = 50 # Default fallback if we cannot query it

        step = 10
        new_val = curr + step if action == "up" else curr - step
        new_val = max(0, min(100, new_val))
        if linux_set_brightness(new_val):
            return f"Brightness adjusted {action} (to {new_val}%)."
        else:
            return "Failed to adjust brightness natively. You may need to grant write permissions to /sys/class/backlight or ensure D-Bus is running."

def handle_brightness_set(pct: int):
    system = platform.system()
    if system == "Darwin":
        try:
            import ctypes
            cg = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
            display_id = cg.CGMainDisplayID()
            
            ds = ctypes.CDLL('/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices')
            ds.DisplayServicesSetBrightness.argtypes = [ctypes.c_int, ctypes.c_float]
            ds.DisplayServicesSetBrightness.restype = None
            
            val = float(pct / 100.0)
            ds.DisplayServicesSetBrightness(display_id, val)
            log_action("system", f"Set brightness to {pct}% natively")
            return f"Brightness set to {pct}%."
        except Exception as e:
            cmd = f"brightness {pct/100}"
            log_action("system", f"Setting brightness via CLI fallback to {pct}%")
            return handle_run_command(cmd)
    elif system == "Windows":
        cmd = f'powershell -NoProfile -Command "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {pct})"'
        try:
            import subprocess
            CREATE_NO_WINDOW = 0x08000000
            subprocess.run(cmd, shell=True, creationflags=CREATE_NO_WINDOW)
            log_action("system", f"Setting brightness to {pct}% natively via PowerShell")
            return f"Brightness set to {pct}%."
        except Exception as e:
            return f"Failed to set brightness: {e}"
    else:
        # Linux branch
        if linux_set_brightness(pct):
            return f"Brightness set to {pct}%."
        else:
            return f"Failed to set brightness to {pct}%. You may need to grant write permissions to /sys/class/backlight or ensure D-Bus is running."

def get_system_info(what: str = "all"):
    import platform as pf
    info = []
    def add(label, value):
        info.append(f"{label}: {value}")
    if what in ("cpu", "all"):
        add("CPU", pf.processor())
    if what in ("memory", "all"):
        try:
            import psutil
            mem = psutil.virtual_memory()
            add("RAM", f"{mem.total / (1024**3):.1f} GB total, {mem.percent}% used")
        except ImportError:
            if pf.system() == "Windows":
                try:
                    import subprocess, json
                    CREATE_NO_WINDOW = 0x08000000
                    res = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize, FreePhysicalMemory | ConvertTo-Json"],
                        capture_output=True, text=True, creationflags=CREATE_NO_WINDOW
                    )
                    data = json.loads(res.stdout)
                    total_kb = float(data["TotalVisibleMemorySize"])
                    free_kb = float(data["FreePhysicalMemory"])
                    used_kb = total_kb - free_kb
                    percent = (used_kb / total_kb) * 100
                    add("RAM", f"{total_kb / (1024**2):.1f} GB total, {percent:.1f}% used")
                except:
                    add("RAM", "Install psutil for memory info")
            else:
                add("RAM", "Install psutil for memory info")
    if what in ("disk", "all"):
        try:
            import shutil
            path = "C:\\" if pf.system() == "Windows" else "/"
            total, used, free = shutil.disk_usage(path)
            add("Disk", f"{free / (1024**3):.1f} GB free / {total / (1024**3):.1f} GB")
        except:
            add("Disk", "Unknown")
    if what in ("ip", "all"):
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            add("Local IP", ip)
        except:
            add("Local IP", "Unknown")
    if what in ("hostname", "all"):
        add("Hostname", pf.node())
    return "\n".join(info) if info else "No information available."

def clipboard_copy(text: str):
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run("pbcopy", input=text.encode('utf-8'))
        elif system == "Windows":
            subprocess.run("powershell -command Set-Clipboard", input=text.encode('utf-8'))
        else:
            import shutil
            if shutil.which("wl-copy"):
                subprocess.run("wl-copy", input=text.encode('utf-8'))
            elif shutil.which("xclip"):
                subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode('utf-8'))
            else:
                try:
                    import tkinter as tk
                    r = tk.Tk(); r.withdraw(); r.clipboard_clear(); r.clipboard_append(text); r.update(); r.destroy()
                except ImportError:
                    return "Clipboard copy failed: No native clipboard utility (wl-copy, xclip) or python3-tk found."
        return f"Copied to clipboard: {text[:50]}{'...' if len(text)>50 else ''}"
    except Exception as e:
        return f"Clipboard copy failed: {e}"

def clipboard_read():
    system = platform.system()
    try:
        if system == "Darwin":
            content = subprocess.run("pbpaste", capture_output=True, text=True).stdout
        elif system == "Windows":
            content = subprocess.run("powershell -command Get-Clipboard", capture_output=True, text=True).stdout
        else:
            import shutil
            if shutil.which("wl-paste"):
                content = subprocess.run("wl-paste", capture_output=True, text=True).stdout
            elif shutil.which("xclip"):
                content = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True).stdout
            else:
                try:
                    import tkinter as tk
                    r = tk.Tk(); r.withdraw(); content = r.clipboard_get(); r.destroy()
                except ImportError:
                    return "Clipboard read failed: No native clipboard utility (wl-paste, xclip) or python3-tk found."
        return f"Clipboard: {content[:200]}" if content else "Clipboard is empty."
    except Exception as e:
        return f"Clipboard read failed: {e}"

def handle_window_close():
    system = platform.system()
    if system == "Darwin":
        subprocess.run("osascript -e 'tell application \"System Events\" to keystroke \"w\" using command down'", shell=True)
    elif system == "Windows":
        subprocess.run('powershell -Command "(New-Object -ComObject WScript.Shell).SendKeys(\'%{F4}\')"', shell=True)
    else:
        subprocess.run("xdotool getactivewindow windowclose", shell=True)
    return "Closed window."

def handle_window_minimize():
    system = platform.system()
    if system == "Darwin":
        subprocess.run("osascript -e 'tell application \"System Events\" to keystroke \"m\" using command down'", shell=True)
    elif system == "Windows":
        subprocess.run('powershell -Command "(New-Object -ComObject Shell.Application).MinimizeAll()"', shell=True)
    else:
        subprocess.run("xdotool getactivewindow windowminimize", shell=True)
    return "Minimized window."

def handle_window_maximize():
    system = platform.system()
    if system == "Darwin":
        subprocess.run("osascript -e 'tell application \"System Events\" to tell process (name of first application process whose frontmost is true) to click (first button whose subrole is \"AXZoomButton\") of first window'", shell=True)
    elif system == "Windows":
        subprocess.run('powershell -Command "$wshell = New-Object -ComObject wscript.shell; $wshell.SendKeys(\'% {MAXIMIZE}\')"', shell=True)
    else:
        subprocess.run("xdotool getactivewindow windowsize 100% 100%", shell=True)
    return "Maximized window."

def handle_window_fullscreen():
    system = platform.system()
    if system == "Darwin":
        subprocess.run("osascript -e 'tell application \"System Events\" to keystroke \"f\" using {command down, control down}'", shell=True)
    elif system == "Windows":
        subprocess.run('powershell -Command "(New-Object -ComObject WScript.Shell).SendKeys(\'{F11}\')"', shell=True)
    else:
        subprocess.run("xdotool key F11", shell=True)
    return "Toggled fullscreen."

def handle_switch_tab(direction: str):
    system = platform.system()
    if system == "Darwin":
        if direction == "next":
            subprocess.run("osascript -e 'tell application \"System Events\" to key code 48 using control down'", shell=True)
        else:
            subprocess.run("osascript -e 'tell application \"System Events\" to key code 48 using {control down, shift down}'", shell=True)
    elif system == "Windows":
        keys = "^{TAB}" if direction == "next" else "^+{TAB}"
        subprocess.run(f'powershell -Command "(New-Object -ComObject WScript.Shell).SendKeys(\'{keys}\')"', shell=True)
    else:
        keys = "ctrl+Tab" if direction == "next" else "ctrl+shift+Tab"
        subprocess.run(f"xdotool key {keys}", shell=True)
    return f"Switched tab {direction}."

def handle_wifi(state: str) -> str:
    system = platform.system()
    if system == "Darwin":
        try:
            res = subprocess.run("networksetup -listallhardwareports", shell=True, capture_output=True, text=True)
            interface = "en0"
            lines = res.stdout.splitlines()
            for i, line in enumerate(lines):
                if "Wi-Fi" in line and i + 1 < len(lines):
                    interface = lines[i+1].split()[-1]
                    break
            subprocess.run(f"networksetup -setairportpower {interface} {state}", shell=True)
            return f"Wi-Fi turned {state}."
        except Exception as e:
            return f"Failed to set Wi-Fi: {e}"
    elif system == "Windows":
        admin_state = "enabled" if state == "on" else "disabled"
        try:
            subprocess.run(f'netsh interface set interface "Wi-Fi" admin={admin_state}', shell=True)
            return f"Wi-Fi turned {state}."
        except Exception as e:
            return f"Failed to set Wi-Fi: {e}"
    else:
        try:
            subprocess.run(f"nmcli radio wifi {state}", shell=True)
            return f"Wi-Fi turned {state}."
        except Exception as e:
            return f"Failed to set Wi-Fi: {e}"

def handle_bluetooth(state: str) -> str:
    system = platform.system()
    on_val = "1" if state == "on" else "0"
    if system == "Darwin":
        try:
            res = subprocess.run(f"blueutil -p {on_val}", shell=True, capture_output=True)
            if res.returncode == 0:
                return f"Bluetooth turned {state}."
            subprocess.run("osascript -e 'tell application \"System Events\" to tell secondary click of menu bar item 1 of menu bar 1 of process \"ControlCenter\" to click'", shell=True)
            return f"Attempted to set Bluetooth to {state} (install blueutil via brew for full reliability)."
        except Exception as e:
            return f"Failed to set Bluetooth: {e}"
    elif system == "Windows":
        try:
            subprocess.run('start ms-settings:bluetooth', shell=True)
            return f"Opened Bluetooth settings to turn it {state}."
        except Exception as e:
            return f"Failed to open Bluetooth settings: {e}"
    elif system == "Linux":
        cmd = "rfkill unblock bluetooth" if state == "on" else "rfkill block bluetooth"
        try:
            subprocess.run(cmd, shell=True)
            return f"Bluetooth turned {state}."
        except Exception as e:
            return f"Failed to set Bluetooth: {e}"
    return f"Bluetooth control not supported on {system}."

def handle_vpn(action: str, name: str) -> str:
    system = platform.system()
    if system == "Darwin":
        cmd = f"networksetup -{action}networkservice \"{name}\""
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return f"VPN {action} command executed: {res.stdout.strip() or res.stderr.strip()}"
    elif system == "Windows":
        cmd = f"rasdial \"{name}\"" if action == "connect" else f"rasdial \"{name}\" /disconnect"
        subprocess.run(cmd, shell=True)
        return f"VPN {action} command executed."
    elif system == "Linux":
        nmcli_action = "up" if action == "connect" else "down"
        cmd = f"nmcli con {nmcli_action} id \"{name}\""
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            return f"VPN {action} command executed natively."
        else:
            return f"VPN {action} failed: {res.stderr.strip()}"
    return f"VPN control not supported on {system}."

def handle_speed_test() -> str:
    system = platform.system()
    if system == "Darwin":
        res = subprocess.run("networkQuality", shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            return res.stdout.strip()
    import time
    import urllib.request
    try:
        url = "http://speedtest.tele2.net/10MB.zip"
        start = time.time()
        with urllib.request.urlopen(url, timeout=15) as response:
            data = response.read()
        end = time.time()
        mbps = (len(data) * 8 / (end - start)) / 1000000
        return f"Download speed: {mbps:.2f} Mbps (Native test)"
    except Exception as e:
        return f"Native speedtest failed: {e}"

def handle_flush_dns() -> str:
    system = platform.system()
    if system == "Darwin":
        subprocess.run("sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder", shell=True)
        return "DNS cache flushed (may prompt for sudo password)."
    elif system == "Windows":
        subprocess.run("ipconfig /flushdns", shell=True)
        return "DNS cache flushed."
    else:
        subprocess.run("resolvectl flush-caches || systemd-resolve --flush-caches", shell=True)
        return "DNS cache flushed."

def handle_lock_screen() -> str:
    system = platform.system()
    if system == "Darwin":
        subprocess.run("osascript -e 'tell application \"System Events\" to keystroke \"q\" using {control down, command down}'", shell=True)
        return "Screen locked."
    elif system == "Windows":
        subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True)
        return "Screen locked."
    else:
        subprocess.run("xdg-screensaver lock || gnome-screensaver-command -l", shell=True)
        return "Screen locked."

def handle_sleep() -> str:
    system = platform.system()
    if system == "Darwin":
        subprocess.run("osascript -e 'tell application \"System Events\" to sleep'", shell=True)
        return "Sleeping computer."
    elif system == "Windows":
        subprocess.run("rundll32.exe powrprof.dll,SetSuspendState Sleep", shell=True)
        return "Sleeping computer."
    else:
        subprocess.run("systemctl suspend", shell=True)
        return "Sleeping computer."

def handle_restart() -> str:
    system = platform.system()
    if system == "Darwin":
        subprocess.run("osascript -e 'tell application \"System Events\" to restart'", shell=True)
    elif system == "Windows":
        subprocess.run("shutdown /r /t 0", shell=True)
    else:
        subprocess.run("shutdown -r now", shell=True)
    return "Restarting computer..."

def handle_shutdown() -> str:
    system = platform.system()
    if system == "Darwin":
        subprocess.run("osascript -e 'tell application \"System Events\" to shut down'", shell=True)
    elif system == "Windows":
        subprocess.run("shutdown /s /t 0", shell=True)
    else:
        subprocess.run("shutdown -h now", shell=True)
    return "Shutting down computer..."

def handle_dnd(state: str) -> str:
    system = platform.system()
    if system == "Darwin":
        pass
    elif system == "Windows":
        subprocess.run('start ms-settings:quietmoments', shell=True)
        return f"Opened Focus Assist settings to turn {state}."
    else:
        val = "true" if state == "on" else "false"
        subprocess.run(f"gsettings set org.gnome.desktop.notifications show-banners {val}", shell=True)
    return f"Do Not Disturb set to {state}."

def handle_dark_mode(state: str) -> str:
    system = platform.system()
    if system == "Darwin":
        val = "true" if state == "on" else "false"
        subprocess.run(f"osascript -e 'tell application \"System Events\" to tell appearance preferences to set dark mode to {val}'", shell=True)
        return f"Dark mode turned {state}."
    elif system == "Windows":
        try:
            import winreg
            val = 0 if state == "on" else 1
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, val)
            winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, val)
            winreg.CloseKey(key)
            return f"Dark mode turned {state}."
        except Exception as e:
            return f"Failed to set dark mode: {e}"
    else:
        val = "prefer-dark" if state == "on" else "default"
        subprocess.run(f"gsettings set org.gnome.desktop.interface color-scheme '{val}'", shell=True)
        return f"Dark mode turned {state}."

def handle_night_shift(state: str) -> str:
    system = platform.system()
    if system == "Windows":
        subprocess.run('start ms-settings:nightlight', shell=True)
        return f"Opened Night Light settings to turn {state}."
    elif system == "Linux":
        val = "true" if state == "on" else "false"
        subprocess.run(f"gsettings set org.gnome.settings-daemon.plugins.color night-light-enabled {val}", shell=True)
    return f"Night Shift turned {state}."

def handle_set_wallpaper(path: str) -> str:
    system = platform.system()
    resolved_path = os.path.abspath(os.path.expanduser(path))
    if system == "Darwin":
        cmd = f"osascript -e 'tell application \"Finder\" to set desktop picture to POSIX file \"{resolved_path}\"'"
        subprocess.run(cmd, shell=True)
        return f"Wallpaper set to {resolved_path}."
    elif system == "Windows":
        import ctypes
        SPI_SETDESKWALLPAPER = 20
        SPIF_UPDATEINIFILE = 1
        SPIF_SENDWININICHANGE = 2
        ctypes.windll.user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, resolved_path, SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE)
        return f"Wallpaper set to {resolved_path}."
    elif system == "Linux":
        try:
            cmd = f"gsettings set org.gnome.desktop.background picture-uri file://{resolved_path}"
            cmd_dark = f"gsettings set org.gnome.desktop.background picture-uri-dark file://{resolved_path}"
            subprocess.run(cmd, shell=True)
            subprocess.run(cmd_dark, shell=True)
            return f"Wallpaper set to {resolved_path} (GNOME)."
        except Exception as e:
            return f"Failed to set wallpaper on Linux: {e}"
    return f"Wallpaper setting not supported on {system}."

def handle_screenshot(path: str) -> str:
    resolved_path = os.path.abspath(os.path.expanduser(path))
    system = platform.system()
    if system == "Darwin":
        subprocess.run(f"screencapture \"{resolved_path}\"", shell=True)
    elif system == "Windows":
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(resolved_path)
        except Exception:
            return "Failed to save screenshot. Install PIL/Pillow on Windows."
    else:
        import shutil
        if shutil.which("gnome-screenshot"):
            subprocess.run(f"gnome-screenshot -f \"{resolved_path}\"", shell=True)
        elif shutil.which("spectacle"):
            subprocess.run(f"spectacle -b -n -o \"{resolved_path}\"", shell=True)
        elif shutil.which("grim"):
            subprocess.run(f"grim \"{resolved_path}\"", shell=True)
        elif shutil.which("scrot"):
            subprocess.run(f"scrot \"{resolved_path}\"", shell=True)
        else:
            return "Failed to take screenshot: No native screenshot tool found (gnome-screenshot/spectacle/grim/scrot)."
    return f"Screenshot saved to {resolved_path}."

def handle_screen_record(path: str, duration: int) -> str:
    system = platform.system()
    resolved_path = os.path.abspath(os.path.expanduser(path))
    log_action("system", f"Starting screen recording for {duration} seconds to {resolved_path}...")
    
    if system == "Darwin":
        subprocess.Popen(f"screencapture -v -V {duration} \"{resolved_path}\"", shell=True)
        return f"Screen recording started for {duration} seconds. Saving to {resolved_path}."
    elif system == "Windows":
        import shutil
        if not shutil.which("ffmpeg"):
            return "Screen recording on Windows requires FFmpeg. Please install it (e.g. via Iris install command)."
        cmd = f"ffmpeg -f gdigrab -framerate 30 -i desktop -t {duration} \"{resolved_path}\""
        subprocess.Popen(cmd, shell=True, creationflags=0x08000000)
        return f"Screen recording started via FFmpeg for {duration} seconds."
    else:
        import shutil
        if not shutil.which("ffmpeg"):
            return "Screen recording on Linux requires FFmpeg. Please install it (e.g. sudo apt install ffmpeg)."
        cmd = f"ffmpeg -f x11grab -framerate 30 -video_size 1920x1080 -i :0.0 -t {duration} \"{resolved_path}\""
        subprocess.Popen(cmd, shell=True)
        return f"Screen recording started via FFmpeg for {duration} seconds."

def handle_media(action: str) -> str:
    system = platform.system()
    if system == "Darwin":
        for app in ("Spotify", "Music", "iTunes"):
            res = subprocess.run(f"osascript -e 'application \"{app}\" is running'", shell=True, capture_output=True, text=True)
            if "true" in res.stdout.lower():
                apple_action = action
                if action == "play_pause": apple_action = "playpause"
                subprocess.run(f"osascript -e 'tell application \"{app}\" to {apple_action}'", shell=True)
                return f"Media command '{action}' sent to {app}."
        return f"Media command '{action}' executed."
    elif system == "Windows":
        import ctypes
        VK_MEDIA_NEXT_TRACK = 0xB0
        VK_MEDIA_PREV_TRACK = 0xB1
        VK_MEDIA_STOP = 0xB2
        VK_MEDIA_PLAY_PAUSE = 0xB3
        
        vk = None
        if action == "play_pause": vk = VK_MEDIA_PLAY_PAUSE
        elif action == "next": vk = VK_MEDIA_NEXT_TRACK
        elif action == "previous": vk = VK_MEDIA_PREV_TRACK
        elif action == "stop": vk = VK_MEDIA_STOP
        
        if vk:
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        return f"Media command '{action}' executed."
    else:
        dbus_method = "PlayPause" if action == "play_pause" else action.capitalize()
        script = f'''
for player in $(dbus-send --session --dest=org.freedesktop.DBus --type=method_call --print-reply /org/freedesktop/DBus org.freedesktop.DBus.ListNames | grep org.mpris.MediaPlayer2 | awk -F'"' '{{print $2}}'); do
    dbus-send --print-reply --session --dest=$player /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.{dbus_method} >/dev/null 2>&1
done
'''
        subprocess.run(script, shell=True)
        return f"Media command '{action}' executed natively."

def handle_say(text: str) -> str:
    system = platform.system()
    if system == "Darwin":
        subprocess.run(f"say \"{text}\"", shell=True)
    elif system == "Windows":
        subprocess.run(f"powershell -Command \"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{text}')\"", shell=True)
    else:
        subprocess.run(f"spd-say \"{text}\" || espeak \"{text}\"", shell=True)
    return f"Said: '{text}'"

def handle_kill_process(name: str) -> str:
    system = platform.system()
    if name.isdigit():
        pid = int(name)
        os.kill(pid, 9)
        return f"Killed process PID {pid}."
    else:
        if system == "Windows":
            subprocess.run(f"taskkill /F /IM \"{name}\" || taskkill /F /IM \"{name}.exe\"", shell=True)
        elif system == "Darwin":
            subprocess.run(f"pkill -9 -i -f \"{name}\"", shell=True)
        else:
            subprocess.run(f"pkill -9 -i -f \"{name}\" || killall -9 -I \"{name}\"", shell=True)
        return f"Sent terminate signal to process '{name}'."

def handle_set_env(key: str, value: str) -> str:
    os.environ[key] = value
    return f"Environment variable {key} set to {value}."

def handle_notification(title: str, body: str) -> str:
    system = platform.system()
    if system == "Darwin":
        cmd = f"osascript -e 'display notification \"{body}\" with title \"{title}\"'"
        subprocess.run(cmd, shell=True)
    elif system == "Windows":
        ps = f'''
[reflection.assembly]::loadwithpartialname("System.Windows.Forms")
[reflection.assembly]::loadwithpartialname("System.Drawing")
$notify = new-object system.windows.forms.notifyicon
$notify.icon = [System.Drawing.SystemIcons]::Information
$notify.visible = $true
$notify.showballoontip(10,"{title}","{body}",[system.windows.forms.tooltipicon]::None)
'''
        subprocess.run(["powershell", "-Command", ps], shell=True)
    else:
        cmd = f'''dbus-send --session --dest=org.freedesktop.Notifications --type=method_call /org/freedesktop/Notifications org.freedesktop.Notifications.Notify string:"Iris" uint32:0 string:"" string:"{title}" string:"{body}" array:string:"" dict:string:variant:"" int32:5000'''
        subprocess.run(cmd, shell=True)
    return "Notification displayed."

def handle_take_note(content: str) -> str:
    import datetime
    notes_path = os.path.expanduser("~/iris_notes.md")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(notes_path, "a", encoding="utf-8") as f:
            f.write(f"### {timestamp}\n{content}\n\n")
        return f"Note added to ~/iris_notes.md"
    except Exception as e:
        return f"Failed to save note: {e}"

def handle_empty_trash() -> str:
    system = platform.system()
    if system == "Darwin":
        subprocess.run("osascript -e 'tell application \"Finder\" to empty trash'", shell=True)
    elif system == "Windows":
        subprocess.run("powershell -Command Clear-RecycleBin -Force", shell=True)
    else:
        subprocess.run("rm -rf ~/.local/share/Trash/files/* || gio trash --empty", shell=True)
    return "Trash emptied."

def handle_type_text(text: str) -> str:
    system = platform.system()
    if system == "Darwin":
        escaped = text.replace('"', '\\"')
        subprocess.run(f"osascript -e 'tell application \"System Events\" to keystroke \"{escaped}\"'", shell=True)
    elif system == "Windows":
        escaped = text.replace("'", "''")
        subprocess.run(f"powershell -Command \"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('{escaped}')\"", shell=True)
    else:
        subprocess.run(["xdotool", "type", text])
    return f"Typed text: '{text}'"

def handle_press_keys(keys: str) -> str:
    system = platform.system()
    if system == "Darwin":
        parts = keys.lower().split("+")
        key = parts[-1]
        mods = parts[:-1]
        apple_mods = []
        for m in mods:
            if m in ("cmd", "command"): apple_mods.append("command down")
            elif m == "shift": apple_mods.append("shift down")
            elif m in ("alt", "option"): apple_mods.append("option down")
            elif m in ("ctrl", "control"): apple_mods.append("control down")
        
        mods_str = ", ".join(apple_mods)
        if mods_str:
            cmd = f"osascript -e 'tell application \"System Events\" to keystroke \"{key}\" using {{{mods_str}}}'"
        else:
            cmd = f"osascript -e 'tell application \"System Events\" to keystroke \"{key}\"'"
        subprocess.run(cmd, shell=True)
    elif system == "Windows":
        import re
        ps_keys = keys.lower()
        ps_keys = re.sub(r'ctrl\+', '^', ps_keys)
        ps_keys = re.sub(r'shift\+', '+', ps_keys)
        ps_keys = re.sub(r'alt\+', '%', ps_keys)
        subprocess.run(f"powershell -Command \"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('{{{ps_keys}}}')\"", shell=True)
    else:
        subprocess.run(["xdotool", "key", keys])
    return f"Pressed keys: {keys}."

def handle_focus_app(name: str) -> str:
    system = platform.system()
    if system == "Darwin":
        cmd = f"osascript -e 'tell application \"{name}\" to activate'"
        subprocess.run(cmd, shell=True)
    elif system == "Windows":
        subprocess.run(f"powershell -Command \"(New-Object -ComObject WScript.Shell).AppActivate('{name}')\"", shell=True)
    else:
        subprocess.run(["wmctrl", "-a", name])
    return f"Focused app '{name}'."

def handle_fix_file(path: str, instructions: str, model=None, tokenizer=None, device=None):
    if not path:
        return "Path required."
    path_obj = Path(path).expanduser().resolve()
    if not path_obj.exists() or not path_obj.is_file():
        return f"File not found: {path_obj}"

    try:
        with open(path_obj, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return f"Read error: {e}"

    log_action("ai", f"Modifying {path_obj.name}...")

    sys_prompt = (
        "You are an expert software engineer. Analyze the provided file content and apply these instructions: " + instructions + "\n\n"
        "Output ONLY the raw, complete, modified file content. Do NOT include markdown blocks. "
        "Do NOT add conversational text."
    )
    user_msg = f"Current Content of {path_obj.name}:\n\n{content}"

    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_msg}]
    
    from src.iris import load_model, ModelRole, unload_model
    try:
        llm = load_model(ModelRole.CODE)
        res = llm.create_chat_completion(
            messages=messages,
            max_tokens=4096,
            temperature=0.2,
        )
        new_content = res["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Generation error: {e}"
    finally:
        unload_model()

    code_block_match = re.search(r'```[a-zA-Z]*\n(.*?)```', new_content, re.DOTALL)
    if code_block_match:
        new_content = code_block_match.group(1).strip()

    backup_path = path_obj.with_suffix(path_obj.suffix + ".bak")
    shutil.copy2(path_obj, backup_path)

    try:
        with open(path_obj, "w", encoding="utf-8") as f:
            f.write(new_content)
        return f"Modified {path_obj.name}. Backup created at {backup_path.name}."
    except Exception as e:
        return f"Write error: {e}"

def load_iris_model():
    return None, None, None

def iris_chat_reply(model, tokenizer, device, retriever, history: list, user_text: str) -> str:
    """Standard chat reply incorporating the RAG Knowledge base and live web search."""
    if model is None:
        return "(Iris model not loaded — only PC-control commands work right now.)"

    rag_category = route_category(user_text)
    context = retriever.retrieve(user_text, top_k=3, category=rag_category) if retriever else ""

    web_results = ""
    if should_web_search(user_text):
        log_action("search", f"Searching for: {user_text}")
        web_results = web_search(user_text)

    sys_prompt = _get_agent_system_prompt()

    if context:
        sys_prompt += (
            " Use the following reference material to answer accurately if relevant:\n\n"
            f"REFERENCE EXCERPT:\n{context}"
        )

    if web_results:
        sys_prompt += (
            "\n\nWEB SEARCH RESULTS (fetched live — use these to give an "
            "accurate, up-to-date answer):\n"
            f"{web_results}"
        )

    history.append({"role": "user", "content": user_text})

    prefix_msgs = [{"role": "system", "content": sys_prompt}] + history[-20:-1]
    prefix_key  = hash(json.dumps(prefix_msgs, ensure_ascii=False, sort_keys=True))

    if _reply_prefix_cache["key"] == prefix_key and _reply_prefix_cache["prompt"] is not None:

        last_turn   = tokenizer.apply_chat_template(
            history[-1:], tokenize=False, add_generation_prompt=False
        )
        prompt = _reply_prefix_cache["prompt"] + last_turn
    else:

        ctx    = [{"role": "system", "content": sys_prompt}] + history[-20:]
        prompt = tokenizer.apply_chat_template(ctx, tokenize=False, add_generation_prompt=True)

        prefix_prompt = tokenizer.apply_chat_template(
            prefix_msgs, tokenize=False, add_generation_prompt=False
        )
        _reply_prefix_cache["key"]    = prefix_key
        _reply_prefix_cache["prompt"] = prefix_prompt

    reply = generate_reply(model, tokenizer, prompt, device)

    history.append({"role": "assistant", "content": reply})
    return reply

HELP_TEXT = """
Commands you can use (regex + AI):
  open <website>                  → opens a website
  open <app name>                 → launches an application
  play <query> on youtube         → opens a YouTube video
  play <query> on spotify         → opens a song on Spotify
  open <name> channel on youtube  → opens a YouTube channel
  send email to <name/email>      → compose and send an email

NEW AI‑powered actions (just say what you want):
  • files & folders   → "open the budget.xlsx", "search for .pdf in Downloads"
  • system commands   → "ping google.com", "what's my hostname?"
  • volume & brightness → "volume up", "set brightness to 70%"
  • clipboard          → "copy this to clipboard", "read clipboard"
  • system info        → "how much RAM?", "what's my IP?"
  • Knowledge Base     → "What happened in chapter 3 of my book?"
  • AI Coder           → "Fix the bugs in app.py"
  • Any natural language request → Iris decides the right action!

  help                             → show this message
  quit / exit                      → close the controller
"""

def log_action(action_type: str, message: str):
    icon_map = {
        "browser": "[bold blue]Browser[/bold blue]",
        "app": "[bold green]App[/bold green]",
        "youtube": "[bold red]YouTube[/bold red]",
        "spotify": "[bold green]Spotify[/bold green]",
        "email": "[bold magenta]Email[/bold magenta]",
        "file": "[bold yellow]File[/bold yellow]",
        "terminal": "[bold cyan]Terminal[/bold cyan]",
        "system": "[bold white]System[/bold white]",
        "ai": "[bold cyan]AI Coder[/bold cyan]",
        "search": "[bold yellow]Search[/bold yellow]"
    }
    prefix = icon_map.get(action_type.lower(), f"[bold cyan]{action_type}[/bold cyan]")
    if RICH_AVAILABLE:
        chevron = ">" if platform.system() == "Windows" else "❯"
        console.print(f"  [dim]{chevron}[/dim] {prefix}: {message}")
    else:
        logger.info(f"  [→ {action_type.capitalize()}] {message}")
def print_banner():
    banner_text = r"""
  _____  _____   _____   _____             _____ 
 |_   _||  __ \ |_   _| / ____|    /\     |_   _|
   | |  | |__) |  | |  | (___     /  \      | |  
   | |  |  _  /   | |   \___ \   / /\ \     | |  
  _| |_ | | \ \  _| |_  ____) | / ____ \   _| |_ 
 |_____||_|  \_\|_____||_____/ /_/    \_\ |_____|
                                                 
    """
    if RICH_AVAILABLE:
        console.print(Align.center(Text(banner_text, style="bold cyan")))
        console.print(Align.center(Text("Natural-language control of your computer, powered by Iris", style="italic green")))
        console.print()
    else:
        logger.info("=" * 60)
        logger.info("  Iris AI PC Agent (RAG Enabled)")
        logger.info("  Type 'help' for commands, 'quit' to exit.")
        logger.info("=" * 60)
def print_system_status(model=None, retriever=None):
    if not RICH_AVAILABLE:
        return
    table = Table(show_header=False, box=ROUNDED, border_style="dim cyan", width=60)
    table.add_column("Key", style="bold yellow")
    table.add_column("Value", style="green")
    
    import platform as pf
    model_name = "iris_14b_model" if os.path.isdir("./iris_14b_model") else MLX_MODEL_ID
    table.add_row("Model", model_name if IRIS_AVAILABLE else "Rule-only Mode")
    table.add_row("Device", str(get_device().type) if IRIS_AVAILABLE else "CPU")
    table.add_row("OS", f"{pf.system()} {pf.release()} ({pf.machine()})")
    
    try:
        import psutil
        mem = psutil.virtual_memory()
        ram_info = f"{mem.total / (1024**3):.1f} GB total, {mem.percent}% used"
    except ImportError:
        ram_info = "N/A"
    table.add_row("Memory", ram_info)
    
    rag_status = "Loaded" if retriever and retriever.chunks else "Disabled"
    if retriever and retriever.chunks:
        rag_status += f" ({len(retriever.chunks)} chunks)"
    table.add_row("RAG Database", rag_status)
    
    config_status = "Loaded (control.conf)" if os.path.exists(CONFIG_FILE) else "Using Defaults"
    table.add_row("Config", config_status)
    
    console.print(Align.center(table))

from rich.console import Group

def format_assistant_message(content: str):
    if not content:
        return Text("")
        
    think_content = ""
    def replace_think(match):
        nonlocal think_content
        think_content = match.group(1).strip()
        return ""
    
    work = re.sub(r'<think>([\s\S]*?)(?:</think>|$)', replace_think, content, flags=re.IGNORECASE)
    
    action_text = ""
    chat_response = ""
    def replace_action(match):
        nonlocal action_text, chat_response
        raw_json = match.group(0)
        try:
            obj = json.loads(raw_json)
            action = obj.get("action", "chat")
            if action == "chat":
                chat_response = obj.get("response", "").strip()
            else:
                action_text = f"⚙️ Action: [bold magenta]{action}[/bold magenta] {json.dumps({k:v for k,v in obj.items() if k != 'action'}, ensure_ascii=False)}"
        except:
            chat_response = raw_json
        return ""
        
    work = re.sub(r'\{[\s]*"action"[\s]*:[\s\S]*?\}', replace_action, work)
    
    remaining = work.strip()
    
    renderables = []
    if think_content:
        from rich.panel import Panel
        renderables.append(Panel(Text.from_markup(f"[dim]{think_content}[/dim]"), title="[dim]Thinking[/dim]", title_align="left", border_style="dim", style="on #333333"))
        
    main_text = chat_response if chat_response else remaining
    if main_text:
        renderables.append(Markdown(main_text))
        
    if action_text:
        renderables.append(Text.from_markup(action_text))
        
    if not renderables:
        return Text("")
    return Group(*renderables)

# Global scroll offset — number of rendered lines to skip from the top of the chat body
_scroll_offset: int = 0

def _render_body_lines(history, cols: int) -> list[str]:
    """Render the full chat history into a list of terminal-width text lines.
    Returns plain text lines (with ANSI codes stripped for measurement).
    Returns rich-rendered lines for actual printing via a secondary capture.
    """
    measure_console = Console(color_system="truecolor", width=cols, highlight=False)
    table = Table(box=None, show_header=False, expand=True)
    table.add_column("Role", style="bold", width=10)
    table.add_column("Message")
    for msg in history:
        role = "You" if msg["role"] == "user" else "Iris"
        role_style = "bold yellow" if msg["role"] == "user" else "bold green"
        content_render = Markdown(msg["content"]) if msg["role"] == "user" else format_assistant_message(msg["content"])
        table.add_row(Text(role, style=role_style), content_render)
    with measure_console.capture() as cap:
        measure_console.print(table)
    return cap.get().splitlines()


def get_visible_history(history, body_height):
    """Legacy shim — not used in the new scroll-aware draw_layout."""
    if not RICH_AVAILABLE:
        return history
    return history


def draw_layout(model, tokenizer, retriever, history, status_text=None):
    global _scroll_offset
    if not RICH_AVAILABLE:
        return

    cols, rows = shutil.get_terminal_size()

    import platform as pf
    try:
        import psutil
        mem = psutil.virtual_memory()
        ram_info = f"{mem.total / (1024**3):.1f}GB ({mem.percent}% used)"
    except Exception:
        ram_info = "N/A"

    rag_status = "Loaded" if retriever and retriever.chunks else "Disabled"
    if retriever and retriever.chunks:
        rag_status += f" ({len(retriever.chunks)} chunks)"

    model_name = "iris_14b_model" if os.path.isdir("./iris_14b_model") else MLX_MODEL_ID

    status_line = (
        f" Model: [bold cyan]{model_name}[/bold cyan]"
        f" │ Device: [bold cyan]{get_device().type if IRIS_AVAILABLE else 'CPU'}[/bold cyan]"
        f" │ OS: [bold cyan]{pf.system()}[/bold cyan]"
        f" │ RAM: [bold cyan]{ram_info}[/bold cyan]"
        f" │ RAG: [bold cyan]{rag_status}[/bold cyan]"
    )

    divider = "─" * cols

    footer_msg = " Type '/help' for commands │ '/exit' to quit │ '/restart' to restart │ Ask anything in natural language"
    if status_text:
        footer_msg = f" [bold yellow]Status: {status_text}[/bold yellow] │{footer_msg}"

    # 2 lines header (status + divider) + 2 lines footer (divider + footer) + 1 prompt line = 5
    reserved_height = 5
    body_height = max(5, rows - reserved_height)

    # ── Clear and re-draw ──────────────────────────────────────────────────────
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()

    console.print(status_line)
    console.print(Text(divider, style="dim cyan"))

    if not history:
        welcome_md = """# Welcome to Iris AI CLI

This is a full-featured terminal interface for controlling your computer and chatting with Iris.

### Key Capabilities:
- **File System Operations**: Create, read, edit, delete, compress, or search files.
- **System Controls**: Adjust volume, brightness, run terminal commands, or get system information.
- **Web Integrations**: Search DuckDuckGo, open websites, search YouTube/Spotify.
- **RAG Memory**: Search local files in the `raw_data/` directory.
"""
        console.print(Markdown(welcome_md))
    else:
        # Render the entire chat to lines, then apply scroll window
        all_lines = _render_body_lines(history, cols)
        total_lines = len(all_lines)

        # Auto-scroll to bottom whenever new content arrives (offset 0 = bottom)
        max_offset = max(0, total_lines - body_height)

        # Clamp scroll offset
        _scroll_offset = max(0, min(_scroll_offset, max_offset))

        # Which lines to show: offset from top (0 = very beginning, max_offset = end visible)
        start = max_offset - _scroll_offset          # lines from top to start showing
        end   = start + body_height
        visible_lines = all_lines[start:end]

        # Print the sliced lines directly (they already have ANSI codes from the capture)
        for line in visible_lines:
            sys.stdout.write(line + "\n")

        # Padding to fill the body area if content is shorter
        for _ in range(body_height - len(visible_lines)):
            sys.stdout.write("\n")

        # Scroll indicator in the corner when there's more content
        if total_lines > body_height:
            pct = int(100 * (start + body_height) / total_lines)
            scroll_hint = f" ↑↓ scroll ({pct}%) "
            footer_msg = f"[dim]{scroll_hint}[/dim] │{footer_msg}"

    console.print(Text(divider, style="dim cyan"))
    console.print(Text.from_markup(footer_msg, style="dim white"))


def get_prompt_text() -> str:
    cwd = os.getcwd()
    home = os.path.expanduser("~")
    if cwd.startswith(home):
        cwd_short = cwd.replace(home, "~", 1)
    else:
        cwd_short = cwd
    
    prompt = Text()
    prompt.append("\niris ", style="bold cyan")
    prompt.append(cwd_short, style="bold blue")
    prompt.append(" ❯ ", style="bold green")
    return prompt

SLASH_COMMANDS = {
    "/help": "Show this help menu",
    "/clear": "Clear the screen",
    "/status": "Show detailed system and environment status",
    "/config": "View current config values (control.conf)",
    "/history": "Print recent chat history in this session",
    "/model": "Show details of the active model and config parameters",
    "/exit": "Quit the controller",
    "/quit": "Quit the controller",
    "/restart": "Restart the controller and model"
}

def show_help_menu():
    if not RICH_AVAILABLE:
        logger.info(HELP_TEXT)
        return
    table = Table(title="Iris CLI Commands", box=ROUNDED, border_style="cyan")
    table.add_column("Command", style="bold yellow")
    table.add_column("Description", style="green")
    
    for cmd, desc in SLASH_COMMANDS.items():
        table.add_row(cmd, desc)
        
    table.add_row("exit / quit", "Quit the controller")
    table.add_row("restart", "Restart the controller and model")
    table.add_row("help", "Show this help menu")
    table.add_row("clear", "Clear the screen")
    
    console.print(table)
    
    console.print("\n[bold cyan]Example Natural Language Requests:[/bold cyan]")
    console.print("  • [bold green]Files[/bold green]: 'open the budget.xlsx', 'search for .pdf in Downloads'")
    console.print("  • [bold green]System[/bold green]: 'ping google.com', 'how much RAM?'")
    console.print("  • [bold green]Media[/bold green]: 'play shape of you on spotify', 'youtube: lofi hip hop'")
    console.print("  • [bold green]AI Coder[/bold green]: 'fix bugs in app.py'")

def clear_screen(model=None, retriever=None):
    os.system("clear" if platform.system() != "Windows" else "cls")
    print_banner()

def show_detailed_status(model, tokenizer, retriever):
    if not RICH_AVAILABLE:
        return
    table = Table(title="System & Environment Status", box=ROUNDED, border_style="magenta")
    table.add_column("Parameter", style="bold yellow")
    table.add_column("Value", style="green")
    
    import platform as pf
    import socket
    
    table.add_row("Platform", pf.platform())
    table.add_row("Processor", pf.processor())
    table.add_row("Python Version", sys.version.split()[0])
    
    try:
        import psutil
        mem = psutil.virtual_memory()
        table.add_row("RAM Total", f"{mem.total / (1024**3):.1f} GB")
        table.add_row("RAM Available", f"{mem.available / (1024**3):.1f} GB")
        table.add_row("RAM Percent", f"{mem.percent}%")
        cpu_pct = psutil.cpu_percent(interval=0.1)
        table.add_row("CPU Load", f"{cpu_pct}%")
    except ImportError:
        pass
        
    try:
        total, used, free = shutil.disk_usage("/")
        table.add_row("Disk Total", f"{total / (1024**3):.1f} GB")
        table.add_row("Disk Free", f"{free / (1024**3):.1f} GB")
    except:
        pass
        
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        table.add_row("Local IP", ip)
    except:
        pass
        
    model_name = "iris_14b_model" if os.path.isdir("./iris_14b_model") else MLX_MODEL_ID
    table.add_row("Model Loaded", model_name if IRIS_AVAILABLE else "None")
    table.add_row("Device type", str(get_device().type) if IRIS_AVAILABLE else "N/A")
    table.add_row("RAG Chunks", str(len(retriever.chunks)) if retriever else "N/A")
    
    console.print(table)

def show_config():
    if not RICH_AVAILABLE:
        logger.info(load_config())
        return
    config = load_config()
    config_str = json.dumps(config, indent=2)
    panel = Panel(
        Syntax(config_str, "json", theme="monokai", line_numbers=True),
        title=f"Configuration: {CONFIG_FILE}",
        border_style="yellow",
        box=ROUNDED
    )
    console.print(panel)

def show_history(history):
    if not history:
        console.print("[yellow]No conversation history yet in this session.[/yellow]")
        return
        
    table = Table(title="Session History", box=ROUNDED, border_style="cyan", show_lines=True)
    table.add_column("Speaker", style="bold magenta", width=12)
    table.add_column("Message", style="white")
    
    for msg in history:
        role = "You" if msg["role"] == "user" else "Iris"
        role_style = "bold yellow" if msg["role"] == "user" else "bold green"
        table.add_row(Text(role, style=role_style), Markdown(msg["content"]))
        
    console.print(table)

def show_model_details():
    if not IRIS_AVAILABLE:
        console.print("[red]Iris model is not available or not loaded.[/red]")
        return
        
    from src.iris import load_generation_config
    cfg = load_generation_config()
    
    table = Table(title="Active Model Settings", box=ROUNDED, border_style="green")
    table.add_column("Setting", style="bold yellow")
    table.add_column("Value", style="green")
    
    model_name = "iris_14b_model" if os.path.isdir("./iris_14b_model") else MLX_MODEL_ID
    table.add_row("Model ID", model_name)
    table.add_row("Max New Tokens", str(cfg.get("max_new_tokens", 256)))
    table.add_row("Temperature", str(cfg.get("temperature", 0.7)))
    table.add_row("Top P", str(cfg.get("top_p", 0.9)))
    table.add_row("Repetition Penalty", str(cfg.get("repetition_penalty", 1.0)))
    table.add_row("RAG Disabled", str(cfg.get("disable_rag", False)))
    
    console.print(table)

def _read_input_with_scroll(prompt_str, model, tokenizer, retriever, history) -> str:
    """Read a line of input while allowing UP/DOWN arrow keys to scroll the chat.

    Uses termios raw-mode on Unix/macOS to intercept escape sequences before
    they reach readline, then redraws the layout for each scroll step.
    Falls back to console.input() if raw mode is unavailable (e.g. Windows).
    """
    global _scroll_offset

    import sys, os
    try:
        import tty, termios
    except ImportError:
        # Windows — fall back to blocking input
        console.print(prompt_str, end="")
        return input()

    cols, rows = shutil.get_terminal_size()
    reserved_height = 5
    body_height = max(5, rows - reserved_height)

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    buf = []
    try:
        tty.setraw(fd)
        # Print prompt
        console.print(prompt_str, end="")
        sys.stdout.flush()

        while True:
            ch = sys.stdin.read(1)

            if ch == "\r" or ch == "\n":
                # Enter pressed — submit
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                break

            elif ch == "\x03":
                # Ctrl-C
                raise KeyboardInterrupt

            elif ch == "\x04":
                # Ctrl-D / EOF
                raise EOFError

            elif ch == "\x7f" or ch == "\x08":
                # Backspace
                if buf:
                    buf.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()

            elif ch == "\x1b":
                # Escape sequence — read 2 more bytes
                seq = sys.stdin.read(2)
                if seq == "[A":
                    # UP arrow — scroll up (show older content)
                    _scroll_offset = min(_scroll_offset + (body_height // 3), 9999)
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    draw_layout(model, tokenizer, retriever, history)
                    tty.setraw(fd)
                    console.print(prompt_str, end="")
                    sys.stdout.write("".join(buf))
                    sys.stdout.flush()
                elif seq == "[B":
                    # DOWN arrow — scroll down (show newer content)
                    _scroll_offset = max(_scroll_offset - (body_height // 3), 0)
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    draw_layout(model, tokenizer, retriever, history)
                    tty.setraw(fd)
                    console.print(prompt_str, end="")
                    sys.stdout.write("".join(buf))
                    sys.stdout.flush()
                elif seq == "[5":
                    # Page Up
                    sys.stdin.read(1)  # consume trailing ~
                    _scroll_offset = min(_scroll_offset + body_height, 9999)
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    draw_layout(model, tokenizer, retriever, history)
                    tty.setraw(fd)
                    console.print(prompt_str, end="")
                    sys.stdout.write("".join(buf))
                    sys.stdout.flush()
                elif seq == "[6":
                    # Page Down
                    sys.stdin.read(1)  # consume trailing ~
                    _scroll_offset = max(_scroll_offset - body_height, 0)
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    draw_layout(model, tokenizer, retriever, history)
                    tty.setraw(fd)
                    console.print(prompt_str, end="")
                    sys.stdout.write("".join(buf))
                    sys.stdout.flush()
                # Ignore other escape sequences (left/right arrows, fn keys, etc.)

            elif ch >= " ":
                # Printable character
                buf.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    # Reset scroll to bottom whenever user submits a message
    _scroll_offset = 0
    return "".join(buf)


def main():
    import argparse
    from src.iris import ModelRole
    
    parser = argparse.ArgumentParser(description="Iris AI PC Agent")
    parser.add_argument("--model", choices=[m.value for m in ModelRole], default=None,
                        help="Force using a single specific model role for all queries (bypasses routing).")
    args, _ = parser.parse_known_args()
    
    if args.model:
        ai_agent_handle.force_role = ModelRole(args.model)

    config = load_config()
    
    if RICH_AVAILABLE:
        sys.stdout.write("\033[?1049h")
        sys.stdout.write("\033[H")
        sys.stdout.flush()

    try:
        if RICH_AVAILABLE:
            console.print("[bold yellow]Loading Iris LLM Core...[/bold yellow]")
        else:
            logger.info("[INFO] Loading Iris LLM Core...")
        model, tokenizer, device = load_iris_model()

        retriever = None
        if IRIS_AVAILABLE:
            if RICH_AVAILABLE:
                console.print("[bold yellow]Initializing RAG Knowledge Base...[/bold yellow]")
                try:
                    retriever = BookRetriever(raw_data_dir="raw_data")
                    retriever.load_and_index()
                except Exception as e:
                    console.print(f"[red][WARNING] Failed to load RAG: {e}[/red]")
            else:
                logger.info("[INFO] Initializing RAG Knowledge Base...")
                try:
                    retriever = BookRetriever(raw_data_dir="raw_data")
                    retriever.load_and_index()
                except Exception as e:
                    logger.warning(f"[WARNING] Failed to load RAG: {e}")
        history: list = []

        while True:
            if RICH_AVAILABLE:
                draw_layout(model, tokenizer, retriever, history)
                prompt_str = get_prompt_text()
                try:
                    raw = _read_input_with_scroll(
                        prompt_str, model, tokenizer, retriever, history
                    ).strip()
                except (EOFError, KeyboardInterrupt):
                    break
            else:
                try:
                    raw = input("\nYou: ").strip()
                except (EOFError, KeyboardInterrupt):
                    break

            if not raw:
                continue

            lower = raw.lower()
            
            if raw.startswith("/") or lower in ("help", "clear", "exit", "quit", "status", "config", "history", "model", "restart"):
                cmd = raw.split()[0].lower()
                if cmd == "/exit" or cmd == "/quit" or cmd in ("exit", "quit"):
                    break
                elif cmd == "/restart" or cmd == "restart":
                    if RICH_AVAILABLE:
                        console.print("[bold yellow]Restarting Iris...[/bold yellow]")
                    else:
                        logger.info("Restarting Iris...")
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                elif cmd == "/help" or cmd in ("help", "?"):
                    show_help_menu()
                    if RICH_AVAILABLE:
                        console.input("\nPress Enter to return to chat...")
                    continue
                elif cmd == "/clear" or cmd == "clear":
                    history.clear()
                    continue
                elif cmd == "/status" or cmd == "status":
                    show_detailed_status(model, tokenizer, retriever)
                    if RICH_AVAILABLE:
                        console.input("\nPress Enter to return to chat...")
                    continue
                elif cmd == "/config" or cmd == "config":
                    show_config()
                    if RICH_AVAILABLE:
                        console.input("\nPress Enter to return to chat...")
                    continue
                elif cmd == "/history" or cmd == "history":
                    show_history(history)
                    if RICH_AVAILABLE:
                        console.input("\nPress Enter to return to chat...")
                    continue
                elif cmd == "/model" or cmd == "model":
                    show_model_details()
                    if RICH_AVAILABLE:
                        console.input("\nPress Enter to return to chat...")
                    continue
                else:
                    if RICH_AVAILABLE:
                        console.print(f"[red]Unknown command: {cmd}. Type /help for assistance.[/red]")
                        console.input("\nPress Enter to return to chat...")
                    else:
                        logger.info(f"Unknown command: {cmd}")
                    continue

            try:
                display_history = list(history)
                display_history.append({"role": "user", "content": raw})
                display_history.append({"role": "assistant", "content": ""})
                
                status_text = "Thinking..."
                if RICH_AVAILABLE:
                    draw_layout(model, tokenizer, retriever, display_history, status_text=status_text)
                
                reply_parts = []
                final_reply = None
                for event in ai_agent_handle(raw, retriever, history):
                    ev_type = event.get("type")
                    content = event.get("content", "")
                    
                    if ev_type == "status":
                        status_text = content
                        if RICH_AVAILABLE:
                            draw_layout(model, tokenizer, retriever, display_history, status_text=status_text)
                        else:
                            logger.info(f"[{status_text}]")
                    elif ev_type == "token":
                        reply_parts.append(content)
                        display_history[-1]["content"] = "".join(reply_parts)
                        if RICH_AVAILABLE:
                            draw_layout(model, tokenizer, retriever, display_history, status_text="Responding...")
                        else:
                            logger.info(content, end="", flush=True)
                    elif ev_type == "action_result":
                        display_history.insert(-1, {"role": "assistant", "content": f"Running action returned:\n{content.strip()}"})
                        if RICH_AVAILABLE:
                            draw_layout(model, tokenizer, retriever, display_history, status_text="Executing action...")
                        else:
                            logger.info(f"\n[Action Output]\n{content}")
                    elif ev_type == "raw_response":
                        final_reply = content
                            
                if final_reply is None:
                    final_reply = "".join(reply_parts)
                history.append({"role": "user", "content": raw})
                history.append({"role": "assistant", "content": final_reply})
                
                # Auto-save code blocks
                try:
                    code_blocks = re.findall(r'```(\w*)\n([\s\S]*?)```', final_reply)
                    for i, (lang, code) in enumerate(code_blocks):
                        filename = None
                        for line in code.splitlines()[:3]:
                            m = re.search(r'^\s*(?://|#|/\*|<!--)\s*([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+)', line)
                            if m:
                                filename = m.group(1).strip()
                                break
                        if not filename:
                            ext = lang.strip().lower() or "txt"
                            ext_map = {"python": "py", "javascript": "js", "typescript": "ts", "cpp": "cpp", "c": "c", "java": "java", "html": "html", "css": "css", "bash": "sh", "sh": "sh"}
                            ext = ext_map.get(ext, ext)
                            filename = f"generated_code_{i+1}.{ext}"
                        
                        file_path = os.path.join(os.getcwd(), os.path.basename(filename))
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(code.strip() + "\n")
                        
                        if RICH_AVAILABLE:
                            console.print(f"[dim green]Auto-saved code block to: {file_path}[/dim green]")
                        else:
                            logger.info(f"Auto-saved code to: {file_path}")
                except Exception as save_err:
                    if not RICH_AVAILABLE:
                        logger.warning(f"Failed to auto-save code block: {save_err}")
                
            except Exception as e:
                if RICH_AVAILABLE:
                    console.print(f"[red]Error: {e}[/red]")
                    console.input("\nPress Enter to return to chat...")
                else:
                    logger.warning(f"Error: {e}")
    finally:
        if RICH_AVAILABLE:
            sys.stdout.write("\033[?1049l")
            sys.stdout.flush()
        logger.info("Goodbye!")
def _resolve(path: str):
    """Expand ~ and environment variables, return a Path object."""
    from pathlib import Path
    return Path(os.path.expandvars(os.path.expanduser(path)))

def handle_create_file(path: str, content: str = "") -> str:
    p = _resolve(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"File created: {p}"
    except Exception as e:
        return f"Could not create file: {e}"

def handle_read_file(path: str) -> str:
    p = _resolve(path)
    try:
        if not p.exists():
            return f"File not found: {p}"
        text = p.read_text(encoding="utf-8", errors="replace")
        if len(text) > 4000:
            text = text[:4000] + "\n… [truncated]"
        return f"Contents of {p}:\n\n{text}"
    except Exception as e:
        return f"Could not read file: {e}"

def handle_append_file(path: str, content: str) -> str:
    p = _resolve(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(content)
        return f"Appended to: {p}"
    except Exception as e:
        return f"Could not append to file: {e}"

def handle_replace_in_file(path: str, find: str, replace: str) -> str:
    p = _resolve(path)
    try:
        if not p.exists():
            return f"File not found: {p}"
        text = p.read_text(encoding="utf-8")
        if find not in text:
            return f"Text '{find}' not found in {p}"
        new_text = text.replace(find, replace)
        p.write_text(new_text, encoding="utf-8")
        return f"Replaced '{find}' with '{replace}' in {p}"
    except Exception as e:
        return f"Could not replace in file: {e}"

def handle_move_file(src: str, dst: str) -> str:
    import shutil
    s, d = _resolve(src), _resolve(dst)
    try:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s), str(d))
        return f"Moved {s} -> {d}"
    except Exception as e:
        return f"Could not move: {e}"

def handle_copy_file(src: str, dst: str) -> str:
    import shutil
    s, d = _resolve(src), _resolve(dst)
    try:
        d.parent.mkdir(parents=True, exist_ok=True)
        if s.is_dir():
            shutil.copytree(str(s), str(d))
        else:
            shutil.copy2(str(s), str(d))
        return f"Copied {s} -> {d}"
    except Exception as e:
        return f"Could not copy: {e}"

def handle_delete_file(path: str) -> str:
    import platform, shutil
    p = _resolve(path)
    if not p.exists():
        return f"File not found: {p}"
    try:
        import send2trash
        send2trash.send2trash(str(p))
        return f"Moved to Trash: {p}"
    except ImportError:
        try:
            p.unlink() if p.is_file() else shutil.rmtree(str(p))
            return f"Deleted: {p}"
        except Exception as e:
            return f"Could not delete: {e}"
    except Exception as e:
        return f"Could not delete: {e}"

def handle_create_folder(path: str) -> str:
    p = _resolve(path)
    try:
        p.mkdir(parents=True, exist_ok=True)
        return f"Folder created: {p}"
    except Exception as e:
        return f"Could not create folder: {e}"

def handle_rename_file(path: str, new_name: str) -> str:
    p = _resolve(path)
    try:
        if not p.exists():
            return f"Path not found: {p}"
        new_path = p.parent / new_name
        p.rename(new_path)
        return f"Renamed to: {new_path}"
    except Exception as e:
        return f"Could not rename: {e}"

def handle_compress_files(paths: list, output: str) -> str:
    import zipfile
    out = _resolve(output)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(str(out), "w", zipfile.ZIP_DEFLATED) as zf:
            for p_str in paths:
                p = _resolve(p_str)
                if p.is_dir():
                    for f in p.rglob("*"):
                        if f.is_file():
                            zf.write(f, f.relative_to(p.parent))
                elif p.exists():
                    zf.write(p, p.name)
        return f"Archive created: {out}"
    except Exception as e:
        return f"Could not compress: {e}"

def handle_extract_file(path: str, dest: str) -> str:
    import zipfile, tarfile
    p = _resolve(path)
    d = _resolve(dest)
    try:
        d.mkdir(parents=True, exist_ok=True)
        name = p.name.lower()
        if name.endswith(".zip"):
            with zipfile.ZipFile(str(p)) as zf:
                zf.extractall(str(d))
        elif any(name.endswith(s) for s in (".tar.gz", ".tgz", ".tar.bz2", ".tar")):
            with tarfile.open(str(p)) as tf:
                tf.extractall(str(d))
        else:
            return f"Unsupported archive format: {p.suffix}"
        return f"Extracted to: {d}"
    except Exception as e:
        return f"Could not extract: {e}"

def handle_download_file(url: str, path: str) -> str:
    import urllib.request, ssl
    p = _resolve(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        urllib.request.urlretrieve(url, str(p))
        return f"Downloaded to: {p}"
    except Exception as e:
        return f"Could not download: {e}"

if __name__ == "__main__":
    main()