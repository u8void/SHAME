

import os
import platform
import sys


def _ensure_open_interpreter():
    try:
        import interpreter as _test  
    except ImportError:
        import subprocess as _sp

        print("\n[Iris] Installing open-interpreter — one-time setup...", flush=True)
        pip_args = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-q",
            "--upgrade",
            "open-interpreter",
        ]
        if platform.system() == "Linux":
            pip_args.append("--break-system-packages")
        env = os.environ.copy()
        env["PYO3_USE_ABI3_FORWARD_COMPATIBILITY"] = "1"
        _sp.run(pip_args, check=True, env=env)
        print("[Iris] open-interpreter installed ✓\n", flush=True)


_ensure_open_interpreter()




sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.logger import get_logger

logger = get_logger("controller")





import json
import platform
import re
import shutil
import smtplib
import subprocess
import subprocess as _subprocess
import time
from pathlib import Path
from typing import Optional




try:
    
    from interpreter import interpreter as _oi

    _oi.auto_run = True   
    _oi.verbose = False
    _oi.max_output = 4000
    _oi.offline = True    
    _oi.sync_computer = False  
    _oi.loop = False      

    _oi.llm.supports_functions = False
    _oi.llm.supports_vision = False
    
    
    
    
    def _iris_native_oi_llm(*args, **kwargs):
        from src.iris_engine import _model_pool, load_model, ModelRole
        
        
        
        if not _model_pool:
            load_model(ModelRole.CONTROL)
            
        active_role = next(reversed(_model_pool))
        model_obj = _model_pool[active_role]
        
        clean_kwargs = {
            "messages": kwargs.get("messages", []),
            "stream": True,
            "max_tokens": 1024,
            "temperature": 0.2
        }
        
        
        for chunk in model_obj.create_chat_completion(**clean_kwargs):
            yield chunk

    _oi.llm.completions = _iris_native_oi_llm
    _oi.llm.api_base = None
    _oi.llm.model = "iris-native"
    _oi.llm.context_window = 8192
    _oi.llm.max_tokens = 1024
    _oi.computer.languages = [lang for lang in _oi.computer.languages if lang.__name__ == "Python"]

    _oi.system_message = (
        "You are Iris, an AI PC assistant. "
        "Write and execute ONLY Python code to fulfill the user's request. NEVER write raw Bash or Shell commands.\n"
        "CRITICAL RULES:\n"
        "1. NEVER use 'sudo' or administrative privileges.\n"
        "2. ALWAYS launch desktop/GUI applications or files using non-blocking, fully-detached background processes so they DO NOT block the execution flow.\n"
        "   Before launching, ALWAYS verify if the executable is available on the system path using `shutil.which`. If it does not exist (for example, 'whatsapp' or 'spotify' is not installed), fall back to opening its web interface in the default browser using Python's built-in `webbrowser` module (e.g., `webbrowser.open('https://web.whatsapp.com')`).\n"
        "   When launching an executable, redirect stdout/stderr to subprocess.DEVNULL and set start_new_session=True. Example: import subprocess, shutil, webbrowser; cmd = 'gnome-control-center'; subprocess.Popen([cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True) if shutil.which(cmd) else webbrowser.open('https://example.com')\n"
        "3. NEVER wait for GUI applications to exit, NEVER call .wait(), and NEVER write monitoring loops (e.g., polling with .poll() or using time.sleep) to check if the process is still running. Once you start the process with Popen, the task is complete. Return immediately.\n"
        "4. To close/kill an application, write Python code to terminate its processes. Keep in mind that some launcher commands differ from the running process names: 'google-chrome' runs as 'chrome', 'libreoffice' runs as 'soffice' or 'soffice.bin', and 'gnome-terminal' runs as 'gnome-terminal-server'. Be careful to terminate the correct process names, and avoid matching substring patterns that might terminate this agent workspace (e.g., do not kill 'chrome-sandbox' or 'antigravity').\n"
        "5. NEVER use the webbrowser module or python requests to perform a web search or look up information. If you are asked to perform a system action like installing a package or changing a setting, write the python script to do exactly that (e.g. using subprocess). Do not search the web for how to do it."
    )

    OI_AVAILABLE = True
    logger.info("[OI] Open Interpreter ready (offline mode) ✓")

except Exception as _oi_err:
    OI_AVAILABLE = False
    logger.warning(f"[OI] Open Interpreter unavailable: {_oi_err}")






class _FakeResult:
    

    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _shell(cmd, **kw) -> _FakeResult:
    
    defaults = dict(shell=isinstance(cmd, str), capture_output=True, text=True)
    defaults.update(kw)
    try:
        r = _subprocess.run(cmd, **defaults)
        return _FakeResult(r.stdout or "", r.stderr or "", r.returncode)
    except Exception as e:
        logger.warning(f"[Shell] command failed: {e}")
        return _FakeResult("", str(e), 1)


def _popen(cmd, shell: bool = False, **kw) -> None:
    
    suppress = dict(stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL)
    suppress.update(kw)
    try:
        return _subprocess.Popen(cmd, shell=shell, start_new_session=True, **suppress)
    except Exception as e:
        
        if not shell and isinstance(cmd, list):
            try:
                shell_cmd = " ".join(cmd)
                return _subprocess.Popen(shell_cmd, shell=True, start_new_session=True, **suppress)
            except Exception as e2:
                logger.warning(f"[Popen] shell fallback also failed: {e2}")
        else:
            logger.warning(f"[Popen] launch failed: {e}")
        return None















def _exec_shell_cmd(cmd: str) -> str:
    
    try:
        r = _subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return (r.stdout or r.stderr or "Done.").strip()
    except _subprocess.TimeoutExpired:
        return "Command timed out (30s limit)."
    except Exception as e:
        return f"Command failed: {e}"


def _run_oi_task(task: str) -> str:
    
    if not OI_AVAILABLE:
        return "Open Interpreter unavailable. Install: pip install open-interpreter"
    try:
        _oi.messages = []
        parts = []
        for chunk in _oi.chat(task, display=True, stream=True, blocking=True):
            if not isinstance(chunk, dict):
                continue
            chunk_type = chunk.get("type", "")
            role = chunk.get("role", "")
            content = chunk.get("content", "")
            if chunk_type == "message" and role == "assistant":
                if isinstance(content, str) and content.strip():
                    parts.append(content.strip())
            elif (
                chunk_type == "console" and chunk.get("format") == "output" and content
            ):
                parts.append(str(content).strip())
            elif role == "computer" and content:
                if isinstance(content, list):
                    for item in content:
                        out = (
                            item.get("output", item.get("content", ""))
                            if isinstance(item, dict)
                            else ""
                        )
                        if out:
                            parts.append(str(out).strip())
                elif isinstance(content, str) and content.strip():
                    parts.append(content.strip())
        result = "\n".join(p for p in parts if p).strip()
        logger.info(f"[OI] chat completed: {task[:80]!r}")
        return result or "Task completed (no output)."
    except Exception as e:
        logger.error(f"[OI] chat error: {e}")
        return f"Could not execute via OI: {e}"



import ssl
import urllib.error
import urllib.parse
import urllib.request
import warnings
import webbrowser
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

warnings.filterwarnings("ignore")

try:
    from rich.align import Align
    from rich.box import DOUBLE, ROUNDED
    from rich.console import Console
    from rich.live import Live
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.text import Text

    console = Console()
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

IS_INTERACTIVE = True

ROUTER_KEYWORDS: dict = {
    "medical": [
        "symptom",
        "symptoms",
        "diagnosis",
        "diagnose",
        "treatment",
        "medicine",
        "medication",
        "doctor",
        "health",
        "disease",
        "pain",
        "hospital",
        "surgery",
        "patient",
        "clinical",
        "therapy",
        "drug",
        "prescription",
        "fever",
        "injury",
        "chronic",
        "infection",
        "vaccine",
        "anatomy",
        "blood",
        "heart",
        "lung",
    ],
    "coding": [
        "python",
        "javascript",
        "typescript",
        "function",
        "code",
        "debug",
        "error",
        "import",
        "class",
        "algorithm",
        "variable",
        "loop",
        "array",
        "api",
        "sql",
        "database",
        "framework",
        "library",
        "bug",
        "syntax",
        "compile",
        "runtime",
        "async",
        "thread",
        "git",
        "docker",
        "linux",
        "bash",
        "script",
        "regex",
        "html",
        "css",
        "react",
        "node",
        "flask",
        "django",
        "mlx",
        "pytorch",
    ],
    "finance": [
        "tax",
        "taxes",
        "budget",
        "expense",
        "expenses",
        "investment",
        "invest",
        "stock",
        "stocks",
        "money",
        "salary",
        "income",
        "profit",
        "loss",
        "revenue",
        "accounting",
        "bank",
        "loan",
        "mortgage",
        "interest",
        "rate",
        "crypto",
        "bitcoin",
        "portfolio",
        "dividend",
        "inflation",
        "economy",
        "financial",
    ],
}


def route_category(text: str) -> Optional[str]:
    lower = text.lower()
    scores: dict = {}
    for cat, keywords in ROUTER_KEYWORDS.items():
        score = sum(
            1 for kw in keywords if re.search(r"\b" + re.escape(kw) + r"\b", lower)
        )
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


def should_web_search(text: str) -> bool:
    """Determine if web search is likely beneficial based on trigger words."""
    if len(text.split()) < 3:
        return False
    return bool(_WEB_SEARCH_TRIGGERS.search(text))


def web_search(query: str, max_results: int = 5) -> str:
    
    try:
        q = urllib.parse.quote_plus(query)
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
        ctx.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="ignore")

        titles = re.findall(
            r'class=["\']result__a["\'][^>]*>(.*?)</a>',
            body,
            re.DOTALL,
        )

        snippets = re.findall(
            r'class=["\']result__snippet["\'][^>]*>(.*?)</(?:a|span)>',
            body,
            re.DOTALL,
        )

        def clean(s: str) -> str:
            s = re.sub(r"<[^>]+>", "", s)
            return _html.unescape(s).strip()

        results = []
        for i, (t, s) in enumerate(zip(titles[:max_results], snippets[:max_results])):
            t, s = clean(t), clean(s)
            if t or s:
                results.append(f"[Result {i + 1}] {t}\n{s}")

        if not results:
            return "(No web results found for this query.)"

        return "\n\n".join(results)

    except Exception as exc:
        return f"(Web search unavailable: {exc})"



CLIPBOARD_AVAILABLE = True
try:
    from src.iris import ask_stream
    from src.iris_rag import BookRetriever
    from src.iris_vision import analyze_image
    from src.iris_engine import get_hardware_profile as get_device

    IRIS_AVAILABLE = True
except ImportError:
    IRIS_AVAILABLE = False
    logger.warning(
        "[WARNING] iris.py not found or dependencies missing. Running in rule-only mode."
    )

MLX_MODEL_ID = os.environ.get("IRIS_MODEL_ID", "")
if not MLX_MODEL_ID:
    try:
        with open("./config/iris.conf") as f:
            cfg = json.load(f)
        MLX_MODEL_ID = cfg.get("size", "medium") + " tier"
    except:
        MLX_MODEL_ID = "Iris AI"

CONFIG_FILE = "./config/control.conf"

DEFAULT_CONFIG = {
    "email": {
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "sender_address": "your_email@gmail.com",
        "sender_password": "your_app_password",
        "contacts": {},
    },
    "browser": "default",
}


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        logger.info(f"[INFO] Created config template at {CONFIG_FILE}")
        logger.info(
            "       Edit it with your email credentials and app paths before sending mail."
        )
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception as e:
        logger.error(
            f"[ERROR] Failed to load {CONFIG_FILE}: {e}. Using default config."
        )
        return DEFAULT_CONFIG



import os

_prompt_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "training", "control", "control.md"
)
try:
    with open(_prompt_path, "r", encoding="utf-8") as f:
        _content = f.read().strip()
        
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
    AI_AGENT_SYSTEM_PROMPT = (
        "You are an AI PC assistant. Please respond with JSON actions."
    )

MAX_SYS_PROMPT_CHARS = 4096

_agent_prompt_cache = {"text": None, "mtime": 0}


def _get_agent_system_prompt() -> str:
    
    global _agent_prompt_cache
    path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "training", "control", "control.md"
    )
    try:
        mtime = os.path.getmtime(path)
        if _agent_prompt_cache["text"] is None or mtime != _agent_prompt_cache["mtime"]:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            
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
    
    import tempfile

    if not code or not code.strip():
        return "No code provided to execute."
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name
    try:
        result = _shell(
            ["python3", tmp_path], capture_output=True, text=True, timeout=15
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
    except _subprocess.TimeoutExpired:
        return "Code execution timed out (15s limit)."
    except Exception as e:
        return f"Execution failed: {e}"
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def parse_ai_response(text: str) -> dict | None:
    
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        # Fallback: fix unquoted words (like max, on, off) produced by tiny models
        raw = match.group()
        fixed_json = re.sub(r'(:\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*[,}])', r'\1"\2"\3', raw)
        fixed_json = fixed_json.replace('"True"', 'true').replace('"False"', 'false')
        try:
            return json.loads(fixed_json)
        except json.JSONDecodeError:
            return None


def ai_agent_handle(user_input: str, retriever=None, history=None, **kwargs):
    history = history or []
    force_role = kwargs.get("force_role") or getattr(ai_agent_handle, "force_role", None)
    settings = kwargs.get("settings", {})
    from src.iris import ask_stream
    keep_loaded = kwargs.get("keep_loaded", False)
    yield from ask_stream(
        user_input,
        history,
        retriever=retriever,
        force_role=force_role,
        settings=settings,
        keep_loaded=keep_loaded,
    )


def ai_agent_handle_pro(user_input: str, retriever=None, history=None, **kwargs):
    
    import asyncio
    import queue
    import threading

    import src.iris_pro as iris_pro

    q = queue.Queue()
    mode = kwargs.get("settings", {}).get("mode", "smart")

    def run_async():
        async def task():
            try:
                agen = iris_pro.ask_stream(
                    user_input, history or [], mode=mode, workspace_root=os.getcwd()
                )
                async for event in agen:
                    q.put(event)
            except Exception as e:
                q.put(e)
            finally:
                q.put(None)

        asyncio.run(task())

    t = threading.Thread(target=run_async)
    t.start()

    while True:
        item = q.get()
        if item is None:
            break
        if isinstance(item, Exception):
            yield {
                "type": "raw_response",
                "content": f"\n\n> [ERROR] **Iris Pro Error:** {item}",
            }
            break
        yield item


def _handle_check_storage(action_dict: dict) -> str:
    
    import shutil
    path = action_dict.get("path", "/")
    if platform.system() == "Windows":
        path = "C:\\"
    try:
        total, used, free = shutil.disk_usage(path)
        if total == 0:
            return f"Disk Usage for {path}: Unable to determine (total space is 0)"
        total_gb = total / (1024**3)
        used_gb = used / (1024**3)
        free_gb = free / (1024**3)
        percent = (used / total) * 100
        return (
            f"Disk Usage for {path}:\n"
            f"  Total: {total_gb:.1f} GB\n"
            f"  Used:  {used_gb:.1f} GB ({percent:.1f}%)\n"
            f"  Free:  {free_gb:.1f} GB"
        )
    except Exception as e:
        return f"Failed to check disk usage: {e}"


def _dispatch_action(action: str, d: dict) -> str:
    
    g = d.get  

    def clean_url(url_val):
        if not url_val:
            return ""
        
        m = re.match(r'^\[.*?\]\((.*?)\)$', str(url_val).strip())
        if m:
            return m.group(1).strip()
        return str(url_val).strip()

    
    if action == "open_website":
        return handle_website_from_url(clean_url(g("url", "")))
    if action == "web_search":
        return web_search(g("query", ""))
    if action == "youtube_video":
        return handle_youtube_video_from_query(g("query") or g("name", ""))
    if action == "youtube_channel":
        return handle_youtube_channel_from_name(g("name") or g("query", ""))
    if action == "spotify_song":
        return handle_spotify_song(g("query") or g("name", ""))
    if action in ("browser_task", "browser_login", "browser_autopilot"):
        try:
            from src.browser_agent import (
                browser_autopilot,
                browser_login,
                browser_task,
            )
        except Exception as e:
            return f"Browser automation unavailable: {e}"
        url_clean = clean_url(g("url", ""))
        if action == "browser_login":
            return browser_login(url_clean, g("username", ""), g("password", ""))
        if action == "browser_task":
            return browser_task(url_clean, g("task", ""))
        return browser_autopilot(
            url_clean, g("task", ""), resume_path=g("resume_path")
        )

    
    if action == "gui_action":
        try:
            from src.gui_agent import perform_gui_action
            return perform_gui_action(g("task", ""))
        except Exception as e:
            return f"GUI automation unavailable: {e}"

    if action == "parse_resume":
        try:
            from src.browser_agent import parse_resume

            return str(parse_resume(g("path", "")))
        except Exception as e:
            return f"Resume parsing unavailable: {e}"

    

    if action == "analyze_image":
        try:
            from src.iris import analyze_image

            return analyze_image(
                g("image_path", ""), g("prompt", "Describe this image in detail.")
            )
        except Exception as e:
            return f"Vision unavailable: {e}"
    if action == "search_image_web":
        return handle_search_image_web(g("image_path", ""))

    if action == "send_email":
        return handle_email_from_parts(
            g("to", ""), g("subject", ""), g("body", ""), load_config()
        )

    return None

def _pct(val) -> int:
    val_str = str(val).lower().replace("%", "").strip()
    if val_str == "max":
        return 100
    if val_str == "min":
        return 0
    try:
        return max(0, min(100, int(float(val_str))))
    except (ValueError, TypeError):
        return 50




_RISKY_ACTIONS = {
    "delete_file",
    "shutdown_computer",
    "restart_computer",
    "sleep_computer",
    "empty_trash",
    "kill_process",
    "send_email",
}

_RISKY_CMD_RE = re.compile(
    r"""(?xi)
    \brm\s+-[rf]      |   # rm -rf / rm -f
    \bsudo\b          |
    \bmkfs\b          |
    \bdd\s+if=        |
    \b(shutdown|reboot|halt|poweroff)\b |
    \bgit\s+push\b    |
    \bgit\s+reset\s+--hard |
    >\s*/dev/sd       |
    :\s*>\s           |   # truncate
    \bchmod\s+-R\b
    """
)


def is_risky_action(action_dict: dict) -> bool:
    
    action = action_dict.get("action", "")
    if action in _RISKY_ACTIONS:
        return True
    if action in ("run_command", "open_terminal"):
        return bool(_RISKY_CMD_RE.search(str(action_dict.get("command", ""))))
    return False


def _confirm_risky(action_dict: dict) -> bool:
    
    if not IS_INTERACTIVE:
        return False
    action = action_dict.get("action", "")
    detail = json.dumps(
        {k: v for k, v in action_dict.items() if k != "action"}, ensure_ascii=False
    )
    if RICH_AVAILABLE:
        console.print(
            f"  [bold red]⚠ Confirm risky action[/bold red]: "
            f"[bold magenta]{action}[/bold magenta] {detail}"
        )
        ans = (
            Prompt.ask("  [bold]Proceed?[/bold]", choices=["y", "n"], default="n")
            .strip()
            .lower()
        )
    else:
        ans = input(f"  ⚠ Confirm risky action '{action}' {detail} — proceed? [y/N]: ").strip().lower()
    return ans == "y"


def execute_action_by_dict(action_dict: dict) -> str:
    
    action = action_dict.get("action", "chat")

    
    if action in ("chat", "finish", "none", ""):
        return ""

    
    try:
        result = _dispatch_action(action, action_dict)
    except Exception as e:
        logger.warning(f"[Dispatch] '{action}' raised: {e}")
        return f"Action '{action}' failed: {e}"
    if result is not None:
        logger.info(f"[Action] {action} → handled natively (simple)")
        return result

    


    logger.info(f"[Action] {action} → routing to 3B+OI for complex execution")
    task_parts = [f"Please perform the following action on my system:\nAction: {action}"]
    for key, val in action_dict.items():
        if key != "action":
            task_parts.append(f"{key}: {val}")
    task_str = "\n".join(task_parts)
    
    
    _prime_oi_with_control()
    return _run_oi_task(task_str)


_AGENT_LOOP_ADDENDUM = """

# ===============================================================================
# AGENT LOOP PROTOCOL
# ===============================================================================
You operate as a multi-step agent. A single request may need several actions.

- Emit exactly ONE JSON action per turn (optionally preceded by a brief <think>).
- After each action runs, you receive an `OBSERVATION:` message with the result.
  Read it, then decide the next action.
- When the task is fully complete, emit:
  {"action": "finish", "summary": "<one-line summary of what you accomplished>"}
- If the task is a single step, do that step, then on the next turn emit finish.
- If an OBSERVATION shows an error, diagnose it and try a different action.
- Use the "chat" action only for pure conversation that needs no execution.
"""











def _is_complex_action(action: str) -> bool:
    return True


def _prime_oi_with_control():
    
    if not OI_AVAILABLE:
        return
    from src.iris_engine import ModelRole, load_model, _model_pool
    
    try:
        load_model(ModelRole.CONTROL)
        logger.info("[OI] Primed with CONTROL model for complex action.")
    except Exception as e:
        logger.warning(f"[OI] Could not prime 3B model: {e}")


def _generate_control_action(messages: list, user_query: str = "", max_tokens: int = 1024) -> str:
    


    from src.iris import ModelRole, load_model

    logger.info("[Model] Using CONTROL model for control action")
    llm = load_model(ModelRole.CONTROL)

    out = ""
    for chunk in llm.create_chat_completion(
        messages=messages, max_tokens=max_tokens, stream=True, temperature=0.1
    ):
        delta = chunk["choices"][0].get("delta", {})
        if "content" in delta and delta["content"]:
            out += delta["content"]
    return out


def agentic_control_loop(
    user_query: str,
    history: list = None,
    max_steps: int = 8,
    settings: dict = None,
    model_callable=None,
):
    
    history = history or []
    settings = settings or {}
    auto_confirm = bool(settings.get("auto_confirm", False))
    gen = model_callable or (lambda msgs: _generate_control_action(msgs, user_query=user_query))

    sys_prompt = _get_agent_system_prompt() + _AGENT_LOOP_ADDENDUM
    messages = [{"role": "system", "content": sys_prompt}]
    for m in history[-6:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_query})

    transcript = []  
    parse_failures = 0

    for step in range(max_steps):
        yield {"type": "status", "content": f"Planning step {step + 1}…"}
        try:
            raw = gen(messages)
        except Exception as e:
            logger.error(f"[Agent] generation failed: {e}")
            yield {"type": "status", "content": "Model generation failed."}
            break

        action_dict = parse_ai_response(raw)
        if not action_dict:
            parse_failures += 1
            if parse_failures >= 2:
                fail = "I couldn't translate that into an action I can run."
                yield {"type": "token", "content": fail}
                yield {"type": "raw_response", "content": fail}
                if not settings.get("keep_loaded"):
                    _unload_control_model()
                return
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": "OBSERVATION: Your reply was not valid JSON. Reply with a single JSON action object.",
                }
            )
            continue
        parse_failures = 0

        action = action_dict.get("action", "chat")
        messages.append({"role": "assistant", "content": raw})

        
        if _is_complex_action(action):
            yield {"type": "status", "content": f"Complex action '{action}' → 3B+OI"}
        else:
            yield {"type": "status", "content": f"Simple action '{action}' → native handler"}

        
        if action in ("finish", "none"):
            summary = action_dict.get("summary", "")
            final = summary or _join_transcript(transcript) or "Done."
            yield {"type": "token", "content": final}
            yield {"type": "raw_response", "content": final}
            if not settings.get("keep_loaded"):
                _unload_control_model()
            return
        if action == "chat":
            reply = action_dict.get("response", "") or _join_transcript(transcript)
            yield {"type": "token", "content": reply}
            yield {"type": "raw_response", "content": reply}
            if not settings.get("keep_loaded"):
                _unload_control_model()
            return

        
        if is_risky_action(action_dict) and not auto_confirm:
            if not _confirm_risky(action_dict):
                obs = f"Action '{action}' was cancelled by the user."
                transcript.append(obs)
                yield {"type": "status", "content": obs}
                messages.append({"role": "user", "content": f"OBSERVATION: {obs}"})
                continue

        
        yield {"type": "status", "content": f"Executing: {action}"}
        result = execute_action_by_dict(action_dict)
        result = (result or "Done.").strip()
        transcript.append(f"{action}: {result}")
        yield {
            "type": "action_result",
            "content": f"Action '{action}' Executed.\nResult:\n{result}",
        }
        
        observation_content = f"OBSERVATION: {result[:2000]}"
        if action == "open_app" and result.startswith("✅"):
            _original_task_lower = user_query.lower()
            _gui_followup_keywords = {
                "whatsapp", "telegram", "message", "send", "text", "chat",
                "click", "type", "search for", "open the chat", "im iris"
            }
            if any(kw in _original_task_lower for kw in _gui_followup_keywords):
                app_opened = action_dict.get("name", "the app")
                observation_content = (
                    f"OBSERVATION: {result}\n"
                    f"{app_opened} is now open on screen. "
                    f"The original task is NOT complete yet — you must continue. "
                    f"Use gui_action with a detailed step-by-step task description to finish: {user_query}"
                )
        messages.append({"role": "user", "content": observation_content})

    
    final = _join_transcript(transcript) or "Reached the step limit."
    yield {"type": "status", "content": "Step limit reached."}
    yield {"type": "token", "content": final}
    yield {"type": "raw_response", "content": final}
    if not settings.get("keep_loaded"):
        _unload_control_model()


def _join_transcript(transcript: list) -> str:
    if not transcript:
        return ""
    return "Here's what I did:\n" + "\n".join(f"- {t}" for t in transcript)


def _unload_control_model():
    try:
        from src.iris import unload_model

        unload_model()
    except Exception:
        pass


def _open_url(url: str):
    if not url.startswith("http"):
        url = "https://" + url
    log_action("browser", f"Opening {url}")
    webbrowser.open(url)


def handle_search_image_web(image_path: str) -> str:
    import os
    import urllib.parse

    if not os.path.exists(image_path):
        return f"Image not found at {image_path}"

    log_action("search", "Uploading image for reverse search...")
    img_url = None

    cmd1 = [
        "curl",
        "-s",
        "-F",
        "reqtype=fileupload",
        "-F",
        "time=1h",
        "-F",
        f"fileToUpload=@{image_path}",
        "https://litterbox.catbox.moe/api.php",
    ]
    try:
        res = _shell(cmd1, capture_output=True, text=True, timeout=8)
        out = res.stdout.strip()
        if out.startswith("http"):
            img_url = out
    except Exception:
        pass

    if not img_url:
        import json

        cmd2 = [
            "curl",
            "-s",
            "-F",
            f"file=@{image_path}",
            "https://tmpfiles.org/api/v1/upload",
        ]
        try:
            res = _shell(cmd2, capture_output=True, text=True, timeout=15)
            data = json.loads(res.stdout)
            if data.get("status") == "success":
                url = data["data"]["url"]
                img_url = url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
        except Exception as e:
            pass

    if not img_url:
        return "Upload failed: All temporary image hosts timed out."

    bing_url = f"https://www.bing.com/images/search?view=detailv2&iss=sbi&FORM=SBIHMP&q=imgurl:{urllib.parse.quote(img_url)}"

    import re
    import ssl
    import urllib.request

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
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

        clean_text = re.sub(
            r"<style[^>]*>.*?</style>", "", html, flags=re.IGNORECASE | re.DOTALL
        )
        clean_text = re.sub(
            r"<script[^>]*>.*?</script>",
            "",
            clean_text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        clean_text = re.sub(r"<[^>]+>", " ", clean_text)

        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        return f"Silently performed reverse image search via Bing.\n\nPage Title: {title}\n\nVisible Page Text Snippet:\n{clean_text[:1000]}"
    except Exception as e:
        logger.warning(f"[Bing Scrape Error] {e}")
        pass

    return "Silently searched Bing Visual Search, but could not reliably extract the visual match."


def handle_website(match: re.Match):
    url = match.group(1).strip()
    _open_url(url)
    return f"Opening {url} in your browser."


_YOUTUBE_HOST_RE = re.compile(r"(?:^|\.)(?:youtube\.com|youtu\.be)$", re.IGNORECASE)
_YOUTUBE_VALID_WATCH_RE = re.compile(
    r"^https?://(?:www\.)?(?:youtube\.com/watch\?(?:[\w=&%+.-]*&)?v=[a-zA-Z0-9_-]{11}(?:&\S*)?"
    r"|youtu\.be/[a-zA-Z0-9_-]{11}(?:\?\S*)?)$",
    re.IGNORECASE,
)
_YOUTUBE_VALID_SEARCH_RE = re.compile(
    r"^https?://(?:www\.)?youtube\.com/results\?search_query=\S+$", re.IGNORECASE
)
_YOUTUBE_VALID_CHANNEL_RE = re.compile(
    r"^https?://(?:www\.)?youtube\.com/(?:channel/UC[a-zA-Z0-9_-]{22}|@\S+)$",
    re.IGNORECASE,
)


def handle_website_from_url(url: str):
    
    url = (url or "").strip()
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        parsed = None

    is_youtube_host = bool(parsed and _YOUTUBE_HOST_RE.search(parsed.netloc or ""))
    if is_youtube_host:
        if (
            _YOUTUBE_VALID_WATCH_RE.match(url)
            or _YOUTUBE_VALID_SEARCH_RE.match(url)
            or _YOUTUBE_VALID_CHANNEL_RE.match(url)
        ):
            pass  
        else:
            
            
            
            
            guess_bits = [parsed.path, parsed.query, parsed.fragment]
            guess = " ".join(b for b in guess_bits if b)
            guess = re.sub(r"^[/?#]+", "", guess)
            guess = re.sub(r"^watch\b[\s=:/-]*", "", guess, flags=re.IGNORECASE)
            guess = re.sub(r"[=&/_+]+", " ", guess).strip()
            if guess:
                return handle_youtube_video_from_query(guess)
            
            
            url = "https://www.youtube.com"

    _open_url(url)
    return f"Opening {url}."





def _youtube_search_url(query: str) -> str:
    q = urllib.parse.quote_plus(query)
    return f"https://www.youtube.com/results?search_query={q}"


def _youtube_video_available(video_id: str) -> bool:
    
    url = (
        "https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v="
        + video_id
        + "&format=json"
    )
    ctx = ssl.create_default_context()
    try:
        ctx.load_default_certs()
    except Exception:
        pass
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            return bool(data.get("title"))
    except urllib.error.HTTPError:
        return False  
    except Exception:
        return True  


def _youtube_find_first_video(query: str) -> str | None:
    search_url = (
        "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
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
            logger.warning(f"  [YouTube search error] {e2}")
            return None

    
    
    
    
    ids: list[str] = []
    seen = set()
    for vid in re.findall(
        r'"videoRenderer"\s*:\s*\{\s*"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"', html
    ):
        if vid not in seen:
            seen.add(vid)
            ids.append(vid)

    
    if not ids:
        for vid in re.findall(r'"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"', html):
            if vid not in seen:
                seen.add(vid)
                ids.append(vid)

    if not ids:
        return None

    
    for vid in ids[:5]:
        if _youtube_video_available(vid):
            return f"https://www.youtube.com/watch?v={vid}"

    
    return f"https://www.youtube.com/watch?v={ids[0]}"


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
        console.print(
            "\n[bold cyan]── Compose Email ──────────────────────────────[/bold cyan]"
        )
        raw_to = Prompt.ask("  [bold yellow]To (name or email)[/bold yellow]").strip()
    else:
        logger.info("\n  ── Compose Email ──────────────────────────────")
        raw_to = input("  To (name or email): ").strip()

    if not raw_to:
        return None
    to_addr = _resolve_contact(raw_to, contacts)
    if not to_addr or "@" not in to_addr:
        if RICH_AVAILABLE:
            console.print(
                f"  [red][!] '{raw_to}' not found in contacts and doesn't look like an email.[/red]"
            )
            to_addr = Prompt.ask(
                "  [bold yellow]Enter full email address[/bold yellow]"
            ).strip()
        else:
            logger.info(
                f"  [!] '{raw_to}' not found in contacts and doesn't look like an email."
            )
            to_addr = input("  Enter full email address: ").strip()
        if not to_addr:
            return None

    if RICH_AVAILABLE:
        subject = Prompt.ask(
            "  [bold yellow]Subject[/bold yellow]", default="(no subject)"
        ).strip()
        console.print(
            "  [bold yellow]Body[/bold yellow] (type [bold green]END[/bold green] on a new line to finish):"
        )
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
                    subject = Prompt.ask(
                        f"  [bold yellow]Subject for email to {to_addr}[/bold yellow]",
                        default="(no subject)",
                    ).strip()
                else:
                    subject = (
                        input(f"  Subject for email to {to_addr}: ").strip()
                        or "(no subject)"
                    )
            else:
                subject = "(no subject)"
        if not body:
            if IS_INTERACTIVE:
                if RICH_AVAILABLE:
                    console.print(
                        "  [bold yellow]Body[/bold yellow] (type [bold green]END[/bold green] on a new line to finish):"
                    )
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
            console.print(
                f"\n[bold cyan]── Preview ─────────────────────────────────[/bold cyan]"
            )
            console.print(f"  [bold yellow]To:[/bold yellow]      {to_addr}")
            console.print(f"  [bold yellow]Subject:[/bold yellow] {subject}")
            console.print(f"  [bold yellow]Body:[/bold yellow]\n{body}\n")
            confirm = (
                Prompt.ask(
                    "  [bold green]Send?[/bold green]", choices=["y", "n"], default="n"
                )
                .strip()
                .lower()
            )
        else:
            logger.info(f"\n  ── Preview ─────────────────────────────────")
            logger.info(f"  To:      {to_addr}")
            logger.info(f"  Subject: {subject}")
            logger.info(f"  Body:\n{body}\n")
            confirm = input("  Send? [y/N]: ").strip().lower()
        if confirm != "y":
            return "Email cancelled."
    return _send_email(to_addr, subject, body, config)



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
                    import json
                    import subprocess

                    CREATE_NO_WINDOW = 0x08000000
                    res = _shell(
                        [
                            "powershell",
                            "-NoProfile",
                            "-Command",
                            "Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize, FreePhysicalMemory | ConvertTo-Json",
                        ],
                        capture_output=True,
                        text=True,
                        creationflags=CREATE_NO_WINDOW,
                    )
                    data = json.loads(res.stdout)
                    total_kb = float(data["TotalVisibleMemorySize"])
                    free_kb = float(data["FreePhysicalMemory"])
                    used_kb = total_kb - free_kb
                    percent = (used_kb / total_kb) * 100
                    add(
                        "RAM",
                        f"{total_kb / (1024**2):.1f} GB total, {percent:.1f}% used",
                    )
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
            _shell("pbcopy", input=text)
        elif system == "Windows":
            _shell("powershell -command Set-Clipboard", input=text)
        else:
            import shutil

            if shutil.which("wl-copy"):
                _shell("wl-copy", input=text)
            elif shutil.which("xclip"):
                _shell(["xclip", "-selection", "clipboard"], input=text)
            else:
                try:
                    import tkinter as tk

                    r = tk.Tk()
                    r.withdraw()
                    r.clipboard_clear()
                    r.clipboard_append(text)
                    r.update()
                    r.destroy()
                except ImportError:
                    return "Clipboard copy failed: No native clipboard utility (wl-copy, xclip) or python3-tk found."
        return f"Copied to clipboard: {text[:50]}{'...' if len(text) > 50 else ''}"
    except Exception as e:
        return f"Clipboard copy failed: {e}"


def clipboard_read():
    system = platform.system()
    try:
        if system == "Darwin":
            content = _shell("pbpaste", capture_output=True, text=True).stdout
        elif system == "Windows":
            content = _shell(
                "powershell -command Get-Clipboard", capture_output=True, text=True
            ).stdout
        else:
            import shutil

            if shutil.which("wl-paste"):
                content = _shell("wl-paste", capture_output=True, text=True).stdout
            elif shutil.which("xclip"):
                content = _shell(
                    ["xclip", "-selection", "clipboard", "-o"],
                    capture_output=True,
                    text=True,
                ).stdout
            else:
                try:
                    import tkinter as tk

                    r = tk.Tk()
                    r.withdraw()
                    content = r.clipboard_get()
                    r.destroy()
                except ImportError:
                    return "Clipboard read failed: No native clipboard utility (wl-paste, xclip) or python3-tk found."
        return f"Clipboard: {content[:200]}" if content else "Clipboard is empty."
    except Exception as e:
        return f"Clipboard read failed: {e}"




def load_iris_model():
    return None, None, None


def iris_chat_reply(
    model, tokenizer, device, retriever, history: list, user_text: str
) -> str:
    
    if model is None:
        return "(Iris model not loaded — only PC-control commands work right now.)"

    rag_category = route_category(user_text)
    context = (
        retriever.retrieve(user_text, top_k=3, category=rag_category)
        if retriever
        else ""
    )

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
    prefix_key = hash(json.dumps(prefix_msgs, ensure_ascii=False, sort_keys=True))

    if (
        _reply_prefix_cache["key"] == prefix_key
        and _reply_prefix_cache["prompt"] is not None
    ):
        last_turn = tokenizer.apply_chat_template(
            history[-1:], tokenize=False, add_generation_prompt=False
        )
        prompt = _reply_prefix_cache["prompt"] + last_turn
    else:
        ctx = [{"role": "system", "content": sys_prompt}] + history[-20:]
        prompt = tokenizer.apply_chat_template(
            ctx, tokenize=False, add_generation_prompt=True
        )

        prefix_prompt = tokenizer.apply_chat_template(
            prefix_msgs, tokenize=False, add_generation_prompt=False
        )
        _reply_prefix_cache["key"] = prefix_key
        _reply_prefix_cache["prompt"] = prefix_prompt

    def generate_reply(model, tokenizer, prompt, device):
        return "(Reply generation is currently disabled or unimplemented)"

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
        console.print(
            Align.center(
                Text(
                    "Natural-language control of your computer, powered by Iris",
                    style="italic green",
                )
            )
        )
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

    config_status = (
        "Loaded (control.conf)" if os.path.exists(CONFIG_FILE) else "Using Defaults"
    )
    table.add_row("Config", config_status)

    console.print(Align.center(table))


from rich.console import Group


def format_assistant_message(content: str, is_active: bool = False):
    if not content:
        return Text("")

    think_content = ""

    def replace_think(match):
        nonlocal think_content
        think_content = match.group(1).strip()
        return ""

    work = re.sub(
        r"<think>([\s\S]*?)(?:</think>|$)", replace_think, content, flags=re.IGNORECASE
    )

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
                action_text = f"⚙️ Action: [bold magenta]{action}[/bold magenta] {json.dumps({k: v for k, v in obj.items() if k != 'action'}, ensure_ascii=False)}"
        except:
            chat_response = raw_json
        return ""

    work = re.sub(r'\{[\s]*"action"[\s]*:[\s\S]*?\}', replace_action, work)

    remaining = work.strip()

    renderables = []
    if think_content:
        from rich.panel import Panel

        if is_active:
            renderables.append(
                Panel(
                    Text.from_markup(f"[dim]{think_content}[/dim]"),
                    title="[dim]Thinking[/dim]",
                    title_align="left",
                    border_style="dim",
                    style="on #333333",
                )
            )
        else:
            renderables.append(
                Text.from_markup("[dim]💭 (Thought process omitted)[/dim]")
            )

    main_text = chat_response if chat_response else remaining
    if main_text:
        renderables.append(Markdown(main_text))

    if action_text:
        renderables.append(Text.from_markup(action_text))

    if not renderables:
        return Text("")
    return Group(*renderables)



_scroll_offset: int = 0


def _render_body_lines(history, cols: int, is_generating: bool = False) -> list[str]:
    
    measure_console = Console(color_system="truecolor", width=cols, highlight=False)
    table = Table(box=None, show_header=False, expand=True)
    table.add_column("Role", style="bold", width=10)
    table.add_column("Message")
    for i, msg in enumerate(history):
        role = "You" if msg["role"] == "user" else "Iris"
        role_style = "bold yellow" if msg["role"] == "user" else "bold green"
        is_active = is_generating and (i == len(history) - 1)
        content_render = (
            Markdown(msg["content"])
            if msg["role"] == "user"
            else format_assistant_message(msg["content"], is_active=is_active)
        )
        table.add_row(Text(role, style=role_style), content_render)
    with measure_console.capture() as cap:
        measure_console.print(table)
    return cap.get().splitlines()


def get_visible_history(history, body_height):
    
    if not RICH_AVAILABLE:
        return history
    return history


def draw_layout(model, tokenizer, retriever, history, status_text=None, is_generating=False):
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

    
    reserved_height = 5
    body_height = max(5, rows - reserved_height)

    
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()

    console.print(status_line)
    console.print(Text(divider, style="dim cyan"))

    if not history:
        welcome_md = """# Iris AI CLI

This is a full-featured terminal interface for controlling your computer and chatting with Iris.

### Key Capabilities:
- **File System Operations**: Create, read, edit, delete, compress, or search files.
- **System Controls**: Adjust volume, brightness, run terminal commands, or get system information.
- **Web Integrations**: Search DuckDuckGo, open websites, search YouTube/Spotify.
- **RAG Memory**: Search local files in the `raw_data/` directory.
"""
        console.print(Markdown(welcome_md))
    else:
        
        all_lines = _render_body_lines(history, cols - 2, is_generating=is_generating)
        total_lines = len(all_lines)

        
        max_offset = max(0, total_lines - body_height)

        
        _scroll_offset = max(0, min(_scroll_offset, max_offset))

        
        start = max_offset - _scroll_offset  
        end = start + body_height
        visible_lines = all_lines[start:end]

        
        for line in visible_lines:
            sys.stdout.write(line + "\n")

        
        for _ in range(body_height - len(visible_lines)):
            sys.stdout.write("\n")

        
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
    "/restart": "Restart the controller and model",
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
    console.print(
        "  • [bold green]Files[/bold green]: 'open the budget.xlsx', 'search for .pdf in Downloads'"
    )
    console.print(
        "  • [bold green]System[/bold green]: 'ping google.com', 'how much RAM?'"
    )
    console.print(
        "  • [bold green]Media[/bold green]: 'play shape of you on spotify', 'youtube: lofi hip hop'"
    )
    console.print("  • [bold green]AI Coder[/bold green]: 'fix bugs in app.py'")


def clear_screen(model=None, retriever=None):
    os.system("clear" if platform.system() != "Windows" else "cls")
    print_banner()


def show_detailed_status(model, tokenizer, retriever):
    if not RICH_AVAILABLE:
        return
    table = Table(
        title="System & Environment Status", box=ROUNDED, border_style="magenta"
    )
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
        box=ROUNDED,
    )
    console.print(panel)


def show_history(history):
    if not history:
        console.print("[yellow]No conversation history yet in this session.[/yellow]")
        return

    table = Table(
        title="Session History", box=ROUNDED, border_style="cyan", show_lines=True
    )
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
    
    global _scroll_offset

    import os
    import sys

    try:
        import termios
        import tty
    except ImportError:
        
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
        
        console.print(prompt_str, end="")
        sys.stdout.flush()
 
        while True:
            ch = sys.stdin.read(1)
 
            if ch == "\r" or ch == "\n":
                
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                break
 
            elif ch == "\x03":
                
                raise KeyboardInterrupt
 
            elif ch == "\x04":
                
                raise EOFError
 
            elif ch == "\x7f" or ch == "\x08":
                
                if buf:
                    buf.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
 
            elif ch == "\x1b":
                
                seq = sys.stdin.read(2)
                if seq in ("[A", "OA"):
                    
                    _scroll_offset = min(_scroll_offset + (body_height // 3), 9999)
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    draw_layout(model, tokenizer, retriever, history)
                    tty.setraw(fd)
                    console.print(prompt_str, end="")
                    sys.stdout.write("".join(buf))
                    sys.stdout.flush()
                elif seq in ("[B", "OB"):
                    
                    _scroll_offset = max(_scroll_offset - (body_height // 3), 0)
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    draw_layout(model, tokenizer, retriever, history)
                    tty.setraw(fd)
                    console.print(prompt_str, end="")
                    sys.stdout.write("".join(buf))
                    sys.stdout.flush()
                elif seq == "[5":
                    
                    sys.stdin.read(1)  
                    _scroll_offset = min(_scroll_offset + body_height, 9999)
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    draw_layout(model, tokenizer, retriever, history)
                    tty.setraw(fd)
                    console.print(prompt_str, end="")
                    sys.stdout.write("".join(buf))
                    sys.stdout.flush()
                elif seq == "[6":
                    
                    sys.stdin.read(1)  
                    _scroll_offset = max(_scroll_offset - body_height, 0)
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    draw_layout(model, tokenizer, retriever, history)
                    tty.setraw(fd)
                    console.print(prompt_str, end="")
                    sys.stdout.write("".join(buf))
                    sys.stdout.flush()
                
 
            elif ch >= " ":
                
                buf.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()
 
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    
    _scroll_offset = 0
    return "".join(buf)


def main():
    import argparse

    from src.iris import ModelRole

    parser = argparse.ArgumentParser(description="Iris AI PC Agent")
    parser.add_argument(
        "--model",
        choices=[m.value for m in ModelRole],
        default=None,
        help="Force using a single specific model role for all queries (bypasses routing).",
    )
    parser.add_argument(
        "--pro",
        action="store_true",
        help="Use Iris Pro (cloud models) instead of local Iris.",
    )
    args, _ = parser.parse_known_args()

    global PRO_MODE
    PRO_MODE = args.pro
    if args.model:
        ai_agent_handle.force_role = ModelRole(args.model)

    config = load_config()

    if RICH_AVAILABLE:
        sys.stdout.write("\033[?1049h")
        sys.stdout.write("\033[H")
        sys.stdout.flush()

    try:
        if not PRO_MODE:
            if RICH_AVAILABLE:
                console.print("[bold yellow]Loading Iris LLM Core...[/bold yellow]")
            else:
                logger.info("[INFO] Loading Iris LLM Core...")
            model, tokenizer, device = load_iris_model()
        else:
            model, tokenizer, device = None, None, None
            if RICH_AVAILABLE:
                console.print("[bold cyan]Using Iris Pro (Cloud API)...[/bold cyan]")
            else:
                logger.info("[INFO] Using Iris Pro (Cloud API)...")

        retriever = None
        if IRIS_AVAILABLE:
            if RICH_AVAILABLE:
                console.print(
                    "[bold yellow]Initializing RAG Knowledge Base...[/bold yellow]"
                )
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

            if raw.startswith("/") or lower in (
                "help",
                "clear",
                "exit",
                "quit",
                "status",
                "config",
                "history",
                "model",
                "restart",
            ):
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
                        console.print(
                            f"[red]Unknown command: {cmd}. Type /help for assistance.[/red]"
                        )
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
                    draw_layout(
                        model,
                        tokenizer,
                        retriever,
                        display_history,
                        status_text=status_text,
                        is_generating=True,
                    )

                reply_parts = []
                final_reply = None

                agent_gen = (
                    ai_agent_handle_pro(raw, retriever, history)
                    if PRO_MODE
                    else ai_agent_handle(raw, retriever, history)
                )

                in_thinking_stream = False
                for event in agent_gen:
                    ev_type = event.get("type")
                    content = event.get("content", "")

                    if ev_type == "status":
                        status_text = content
                        if RICH_AVAILABLE:
                            draw_layout(
                                model,
                                tokenizer,
                                retriever,
                                display_history,
                                status_text=status_text,
                                is_generating=True,
                            )
                        else:
                            logger.info(f"[{status_text}]")
                    elif ev_type == "clear":
                        reply_parts.clear()
                        in_thinking_stream = False
                        display_history[-1]["content"] = ""
                        if RICH_AVAILABLE:
                            draw_layout(
                                model,
                                tokenizer,
                                retriever,
                                display_history,
                                status_text="Refining...",
                                is_generating=True,
                            )
                        else:
                            logger.info("\n--- Clearing generation buffer ---")
                    elif ev_type == "thinking":
                        if not in_thinking_stream:
                            reply_parts.append("\n<think>\n")
                            in_thinking_stream = True
                        reply_parts.append(content)
                        display_history[-1]["content"] = "".join(reply_parts)
                        if RICH_AVAILABLE:
                            draw_layout(
                                model,
                                tokenizer,
                                retriever,
                                display_history,
                                status_text="Thinking...",
                                is_generating=True,
                            )
                        else:
                            logger.info(content, end="", flush=True)
                    elif ev_type == "token":
                        if in_thinking_stream:
                            reply_parts.append("\n</think>\n")
                            in_thinking_stream = False
                        reply_parts.append(content)
                        display_history[-1]["content"] = "".join(reply_parts)
                        if RICH_AVAILABLE:
                            draw_layout(
                                model,
                                tokenizer,
                                retriever,
                                display_history,
                                status_text="Responding...",
                                is_generating=True,
                            )
                        else:
                            logger.info(content, end="", flush=True)
                    elif ev_type == "action_result":
                        if in_thinking_stream:
                            reply_parts.append("\n</think>\n")
                            in_thinking_stream = False
                        display_history.insert(
                            -1,
                            {
                                "role": "assistant",
                                "content": f"Running action returned:\n{content.strip()}",
                            },
                        )
                        if RICH_AVAILABLE:
                            draw_layout(
                                model,
                                tokenizer,
                                retriever,
                                display_history,
                                status_text="Executing action...",
                                is_generating=True,
                            )
                        else:
                            logger.info(f"\n[Action Output]\n{content}")
                    elif ev_type == "raw_response":
                        final_reply = content

                if in_thinking_stream:
                    reply_parts.append("\n</think>\n")
                    in_thinking_stream = False

                if final_reply is None:
                    final_reply = "".join(reply_parts)
                history.append({"role": "user", "content": raw})
                history.append({"role": "assistant", "content": final_reply})

                
                try:
                    code_blocks = re.findall(r"```(\w*)\n([\s\S]*?)```", final_reply)
                    for i, (lang, code) in enumerate(code_blocks):
                        filename = None
                        for line in code.splitlines()[:3]:
                            m = re.search(
                                r"^\s*(?://|#|/\*|<!--)\s*([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+)",
                                line,
                            )
                            if m:
                                filename = m.group(1).strip()
                                break
                        if not filename:
                            ext = lang.strip().lower() or "txt"
                            ext_map = {
                                "python": "py",
                                "javascript": "js",
                                "typescript": "ts",
                                "cpp": "cpp",
                                "c": "c",
                                "java": "java",
                                "html": "html",
                                "css": "css",
                                "bash": "sh",
                                "sh": "sh",
                            }
                            ext = ext_map.get(ext, ext)
                            filename = f"generated_code_{i + 1}.{ext}"

                        file_path = os.path.join(
                            os.getcwd(), os.path.basename(filename)
                        )
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(code.strip() + "\n")

                        if RICH_AVAILABLE:
                            console.print(
                                f"[dim green]Auto-saved code block to: {file_path}[/dim green]"
                            )
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




if __name__ == "__main__":
    main()


