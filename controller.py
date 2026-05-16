"""
iris_controller.py — Iris AI PC Agent
======================================
Natural-language control of your computer, powered by Iris.
"""

import os
import re
import sys
import json
import time
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

IS_INTERACTIVE = True

# ──────────────────────────────────────────────────────────────────────────────
#  WEB SEARCH  (DuckDuckGo HTML — no API key required)
# ──────────────────────────────────────────────────────────────────────────────

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
    """Return True when the query looks like a factual / informational question."""
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

        # ── parse titles ──────────────────────────────────────────────────────
        titles   = re.findall(
            r'class=["\']result__a["\'][^>]*>(.*?)</a>',
            body, re.DOTALL,
        )
        # ── parse snippets ────────────────────────────────────────────────────
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


try:
    import pyperclip
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False
    print("[INFO] Install 'pyperclip' for clipboard support: pip install pyperclip")

try:
    # Added BookRetriever to import
    from iris import load_model as _mlx_load_model, get_device, generate_reply, solve_math, BookRetriever, analyze_image
    IRIS_AVAILABLE = True
except ImportError:
    IRIS_AVAILABLE = False
    print("[WARNING] iris.py not found or dependencies missing. Running in rule-only mode.")

CONFIG_FILE  = "./config/control.conf"

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
        "notepad":      "notepad.exe",
        "calculator":   "calc.exe",
        "paint":        "mspaint.exe",
        "spotify":      "spotify",
        "vscode":       "code",
        "chrome":       "google-chrome",
        "firefox":      "firefox",
        "explorer":     "explorer.exe",
        "terminal":     "cmd.exe",
        "word":         "winword.exe",
        "excel":        "excel.exe"
    },
    "browser": "default"
}

def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        print(f"[INFO] Created config template at {CONFIG_FILE}")
        print("       Edit it with your email credentials and app paths before sending mail.")
    with open(CONFIG_FILE) as f:
        return json.load(f)

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

AI_AGENT_SYSTEM_PROMPT = """
You are an AI PC assistant. The user will ask you to perform tasks.
Before providing the final JSON action, you MUST think about the request inside <think>...</think> tags.
In your thinking, analyze the intent, identify the correct tool, and verify any parameters.
Finally, respond with a single JSON object that describes the action to take.

Available actions:
- open_website(url)
- open_app(name)
- youtube_video(query)
- youtube_channel(name)
- spotify_song(query)
- send_email(to, subject, body)
- open_file(path)
- search_files(query, folder)
- run_command(command)
- open_terminal(command)
- run_code(code)                         // Executes Python and returns stdout/stderr.
- analyze_image(image_path, prompt)      // Analyse/describe an image file on disk.
- volume_up, volume_down, volume_mute
- volume_set(percent)
- brightness_up, brightness_down, brightness_set(percent)
- system_info(what)
- clipboard_copy(text)
- clipboard_read
- fix_file(path, instructions)           // Reads a file, applies your instructions, and overwrites it.
- chat(response)

For actions that need parameters, output JSON exactly like:
{"action": "open_website", "url": "https://example.com"}
{"action": "run_command", "command": "ping -c 4 google.com"}
{"action": "run_code", "code": "print(sum(range(1,101)))"}
{"action": "analyze_image", "image_path": "/tmp/photo.jpg", "prompt": "What objects are in this image?"}
{"action": "fix_file", "path": "app.py", "instructions": "Fix the route handler logic"}
{"action": "chat", "response": "Hello! How can I help?"}

CRITICAL RULES:
1. If the user asks to "send" or "show" code/information TO THEM in this chat, use the "chat" action.
2. ONLY use "send_email" if the user explicitly specifies an email recipient or says "email this".
3. NEVER refuse a request for code. Provide full, complete implementations when asked.
4. For layouts (like product grids), avoid using `Container maxWidth="sm"` as it forces items to stack vertically. Use `maxWidth="lg"` or `"xl"` for horizontal arrangements.
5. Output ONLY the JSON object. No other conversational text should be outside the JSON.
6. When WEB SEARCH RESULTS are provided in your context, use them to give an accurate, up-to-date answer. Summarise the findings naturally in your "chat" response — do not expose raw result numbers to the user.
7. If the user says your previous answer was wrong (e.g., "Wrong Answer", "WA", "bug"), DO NOT repeat the same logic. Thoroughly re-evaluate the problem, find the flaw in your reasoning, and provide a fixed or completely different approach.
8. For analyze_image: the image_path is the saved path of the uploaded image. Use the prompt the user provided about the image, or "Describe this image in detail." if unspecified.
9. NEVER use open_website with a youtube.com/watch URL you invented or guessed. YouTube video IDs cannot be inferred from a title — guessed IDs open wrong or non-existent videos. ALWAYS use youtube_video(query) with the video title as the query when the user wants to watch a YouTube video, whether they described it in text or shared a screenshot/image of it.
10. When the user shares an image of a YouTube video and asks to open/play/launch it, extract the video title from the image and use youtube_video(query) with that title.
""".strip()


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

def ai_agent_handle(user_input: str, model, tokenizer, device, retriever, history: list):
    """Generator that yields events for the frontend: tokens, actions, results."""
    if model is None:
        yield {"type": "text", "content": "Iris model not available."}
        return

    # ── RAG: search local knowledge base ────────────────────────────────────
    context = retriever.retrieve(user_input, top_k=3) if retriever else ""

    # ── Web search: run automatically for informational queries ─────────────
    web_results = ""
    if should_web_search(user_input):
        yield {"type": "status", "content": "Searching the web..."}
        web_results = web_search(user_input)

    sys_prompt = AI_AGENT_SYSTEM_PROMPT
    if context:
        sys_prompt += f"\n\nREFERENCE EXCERPT:\n{context}"
    if web_results:
        sys_prompt += f"\n\nWEB SEARCH RESULTS:\n{web_results}"

    messages = [{"role": "system", "content": sys_prompt}]
    for msg in history[-8:] + [{"role": "user", "content": user_input}]:
        if messages[-1]["role"] == msg["role"]:
            messages[-1]["content"] += "\n" + msg["content"]
        else:
            messages.append(msg)

    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    
    from iris import generate_reply_stream
    
    full_reply = ""
    for token in generate_reply_stream(model, tokenizer, prompt, device):
        full_reply += token
        yield {"type": "token", "content": token}

    # Post-generation: Check for actions
    action_dict = parse_ai_response(full_reply)
    if action_dict:
        action = action_dict.get("action", "chat")
        yield {"type": "status", "content": f"Executing {action}..."}
        
        # Execute action logic (simplified call)
        result = execute_action_by_dict(action_dict)
        if result:
            yield {"type": "action_result", "content": result}
            
            # Recurse for image analysis or web search to allow follow-up actions
            if action == "analyze_image" or "Web search results" in result:
                followup_prompt = f"The action '{action}' returned: {result}\nNow provide your final answer or take the next necessary action based on this info."
                messages.append({"role": "assistant", "content": full_reply})
                messages.append({"role": "user", "content": followup_prompt})
                
                new_prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                for token in generate_reply_stream(model, tokenizer, new_prompt, device):
                    yield {"type": "token", "content": token}

def execute_action_by_dict(action_dict: dict) -> str:
    """Helper to execute an action from a dictionary."""
    action = action_dict.get("action", "chat")
    try:
        if action == "open_website":
            url = action_dict.get("url", "")
            # Safety net: if the model passed a youtube.com/watch URL, it almost
            # certainly guessed the video ID. Route it through the proper YouTube
            # search instead so the user gets the right video.
            import re as _re
            if _re.search(r"youtube\.com/watch\?v=", url):
                # Extract any title hint from the url itself (there usually isn't one),
                # fall back to a YouTube search for the bare domain so the user can
                # at least find their video manually.
                print(f"[WARN] open_website with YouTube watch URL intercepted: {url}")
                print("[WARN] Use youtube_video(query) instead. Opening YouTube search.")
                _open_url("https://www.youtube.com")
                return "Opened YouTube (tip: use video title next time for accurate results)."
            return handle_website_from_url(url)
        elif action == "open_app":
            app = action_dict.get("name", "")
            return handle_app_by_name(app, load_config())
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
            return handle_command_execution(cmd)
        elif action == "run_code":
            code = action_dict.get("code", "")
            return handle_run_code(code)
        elif action == "analyze_image":
            from iris import analyze_image
            path = action_dict.get("image_path", "")
            prompt = action_dict.get("prompt", "Describe this image in detail.")
            return analyze_image(path, prompt)
        elif action == "fix_file":
            path = action_dict.get("path", "")
            instr = action_dict.get("instructions", "")
            return handle_fix_file(path, instr)
        elif action == "chat":
            return action_dict.get("response", "")
    except Exception as e:
        return f"Action failed: {e}"
    return ""

def _open_url(url: str):
    if not url.startswith("http"):
        url = "https://" + url
    print(f"  [→ Browser] {url}")
    webbrowser.open(url)

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
        elif system == "Darwin":
            subprocess.Popen(["open", "-a", cmd])
        else:
            subprocess.Popen([cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        try:
            subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"  [ERROR] Could not launch: {e}")
            return False

def handle_app(match: re.Match, config: dict):
    app_name = match.group(1).strip().lower()
    return handle_app_by_name(app_name, config)

def handle_app_by_name(app_name: str, config: dict = None):
    if config is None:
        config = load_config()
    apps_map = config.get("apps", {})
    cmd = apps_map.get(app_name.lower())
    if not cmd:
        for key, val in apps_map.items():
            if key in app_name.lower() or app_name.lower() in key:
                cmd = val
                break
    if not cmd:
        cmd = app_name
    print(f"  [→ App] Launching: {cmd}")
    success = _launch_app(cmd)
    if success:
        return f"Launching {app_name}."
    else:
        return f"I couldn't find '{app_name}'. Add it to {CONFIG_FILE} under 'apps'."

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
        print(f"  [YouTube] SSL error, retrying without verification: {e}")
        ctx = ssl._create_unverified_context()
        try:
            req2 = urllib.request.Request(search_url, headers=headers)
            with urllib.request.urlopen(req2, timeout=8, context=ctx) as resp2:
                html = resp2.read().decode("utf-8", errors="replace")
        except Exception as e2:
            print(f"  [YouTube search error] {e2}")
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
        print(f"  [YouTube] SSL error, retrying without verification: {e}")
        ctx = ssl._create_unverified_context()
        try:
            req2 = urllib.request.Request(search_url, headers=headers)
            with urllib.request.urlopen(req2, timeout=8, context=ctx) as resp2:
                html = resp2.read().decode("utf-8", errors="replace")
        except Exception as e2:
            print(f"  [YouTube channel search error] {e2}")
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
    print(f"  [→ YouTube] Searching for video: '{query}'")
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
    print(f"  [→ YouTube] Searching for channel: '{name}'")
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
    print(f"  [→ Spotify] Searching for: '{query}'")
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
    import sys
    if not IS_INTERACTIVE:
        return None

    contacts = config.get("email", {}).get("contacts", {})
    print("\n  ── Compose Email ──────────────────────────────")
    raw_to = input("  To (name or email): ").strip()
    if not raw_to:
        return None
    to_addr = _resolve_contact(raw_to, contacts)
    if not to_addr or "@" not in to_addr:
        print(f"  [!] '{raw_to}' not found in contacts and doesn't look like an email.")
        to_addr = input("  Enter full email address: ").strip()
        if not to_addr:
            return None
    subject = input("  Subject: ").strip() or "(no subject)"
    print("  Body (type END on a new line to finish):")
    lines = []
    while True:
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
        return f"Email sent to {to} ✓"
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
                subject = input(f"  Subject for email to {to_addr}: ").strip() or "(no subject)"
            else:
                subject = "(no subject)"
        if not body:
            if IS_INTERACTIVE:
                print("  Body (type END on a new line to finish):")
                lines = []
                while True:
                    line = input()
                    if line.strip().upper() == "END":
                        break
                    lines.append(line)
                body = "\n".join(lines).strip()
            else:
                body = "(no body)"

    if IS_INTERACTIVE:
        print(f"\n  ── Preview ─────────────────────────────────")
        print(f"  To:      {to_addr}")
        print(f"  Subject: {subject}")
        print(f"  Body:\n{body}\n")
        confirm = input("  Send? [y/N]: ").strip().lower()
        if confirm != "y":
            return "Email cancelled."
    return _send_email(to_addr, subject, body, config)

def handle_open_file(path_str: str):
    path = Path(path_str).expanduser().resolve()
    if not path.exists():
        return f"Path does not exist: {path}"
    print(f"  [→ Open] {path}")
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
    print(f"  [→ Search] Searching for '{query}' in {folder_path}")
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

def handle_run_command(command: str):
    print(f"  [→ Run] {command}")
    try:
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
        return f"Execution failed: {e}"

def handle_open_terminal(command: str = None):
    system = platform.system()
    print(f"  [→ Terminal] Opening visible terminal...")
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

        nircmd = shutil.which("nircmd")
        if not nircmd:
            return "Volume control on Windows needs nircmd (https://www.nirsoft.net/utils/nircmd.html)"
        if action == "up":
            cmd = f"{nircmd} changesysvolume 2000"
        elif action == "down":
            cmd = f"{nircmd} changesysvolume -2000"
        elif action == "mute":
            cmd = f"{nircmd} mutesysvolume 2"
        else:
            return "Unknown volume action."
    else:
        if action == "up":
            cmd = "amixer -D pulse sset Master 5%+"
        elif action == "down":
            cmd = "amixer -D pulse sset Master 5%-"
        elif action == "mute":
            cmd = "amixer -D pulse sset Master toggle"
        else:
            return "Unknown volume action."
    print(f"  [→ Volume] {cmd}")
    return handle_run_command(cmd)

def handle_volume_set(pct: int):
    system = platform.system()
    if system == "Darwin":
        cmd = f"osascript -e 'set volume output volume {pct}'"
    elif system == "Windows":
        nircmd = shutil.which("nircmd")
        if not nircmd:
            return "Needs nircmd for Windows volume control."
        cmd = f"{nircmd} setsysvolume {pct*655.35:.0f}"
    else:
        cmd = f"amixer -D pulse sset Master {pct}%"
    print(f"  [→ Volume set] {cmd}")
    return handle_run_command(cmd)

def handle_brightness(action: str):
    system = platform.system()
    if system == "Darwin":

        step = 0.0625
        if action == "up":
            cmd = f"brightness 0.0625"
        elif action == "down":
            cmd = f"brightness -0.0625"
        else:
            return "Unknown brightness action."
    elif system == "Windows":
        import ctypes, ctypes.wintypes

        try:
            import wmi
        except ImportError:
            return "Brightness control on Windows requires 'wmi' (pip install wmi)."
        c = wmi.WMI(namespace='wmi')
        methods = c.WmiMonitorBrightnessMethods()[0]
        if action == "up":
            methods.WmiSetBrightness(10, 0)
        elif action == "down":
            methods.WmiSetBrightness(-10, 0)
        else:
            return "Unknown brightness action."
        return "Brightness adjusted."
    else:
        try:
            import subprocess
            if action == "up":
                subprocess.run("xbacklight -inc 10", shell=True)
            elif action == "down":
                subprocess.run("xbacklight -dec 10", shell=True)
            else:
                return "Unknown brightness action."
        except Exception:
            return "xbacklight not found. Install xbacklight for brightness control."
        return "Brightness adjusted."
    print(f"  [→ Brightness] {cmd}")
    return handle_run_command(cmd) if system == "Darwin" else "Brightness adjusted."

def handle_brightness_set(pct: int):
    system = platform.system()
    if system == "Darwin":
        cmd = f"brightness {pct/100}"
    elif system == "Windows":
        try:
            import wmi
        except ImportError:
            return "Needs 'wmi' for brightness control on Windows."
        c = wmi.WMI(namespace='wmi')
        methods = c.WmiMonitorBrightnessMethods()[0]
        methods.WmiSetBrightness(pct, 0)
        return f"Brightness set to {pct}%."
    else:
        try:
            subprocess.run(f"xbacklight -set {pct}", shell=True)
            return f"Brightness set to {pct}%."
        except Exception:
            return "xbacklight not found."
    print(f"  [→ Brightness set] {cmd}")
    return handle_run_command(cmd) if system == "Darwin" else f"Brightness set to {pct}%."

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
            add("RAM", "Install psutil for memory info")
    if what in ("disk", "all"):
        try:
            total, used, free = shutil.disk_usage("/")
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
    if not CLIPBOARD_AVAILABLE:
        return "Clipboard not available (install pyperclip)."
    try:
        pyperclip.copy(text)
        return f"Copied to clipboard: {text[:50]}{'...' if len(text)>50 else ''}"
    except Exception as e:
        return f"Clipboard copy failed: {e}"

def clipboard_read():
    if not CLIPBOARD_AVAILABLE:
        return "Clipboard not available (install pyperclip)."
    try:
        content = pyperclip.paste()
        return f"Clipboard: {content[:200]}" if content else "Clipboard is empty."
    except Exception as e:
        return f"Clipboard read failed: {e}"

def handle_fix_file(path: str, instructions: str, model, tokenizer, device):
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

    print(f"  [→ AI Coder] Modifying {path_obj.name}...")

    sys_prompt = (
        "You are an expert software engineer. Analyze the provided file content and apply these instructions: " + instructions + "\n\n"
        "Output ONLY the raw, complete, modified file content. Do NOT include markdown blocks. "
        "Do NOT add conversational text."
    )
    user_msg = f"Current Content of {path_obj.name}:\n\n{content}"

    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_msg}]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    new_content = generate_reply(model, tokenizer, prompt, device, raw_output=True, max_new_tokens=4096)
    new_content = new_content.strip()

    # Robust regex extraction to find the code inside ```...``` blocks,
    # completely ignoring any conversational text generated before or after.
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
    """
    Load the phi-4 MLX model + LoRA adapters.
    Returns (model, tokenizer, device) matching the old API.
    """
    if not IRIS_AVAILABLE:
        return None, None, None
    model, tokenizer = _mlx_load_model()
    device = get_device()
    return model, tokenizer, device

def iris_chat_reply(model, tokenizer, device, retriever, history: list, user_text: str) -> str:
    """Standard chat reply incorporating the RAG Knowledge base and live web search."""
    if model is None:
        return "(Iris model not loaded — only PC-control commands work right now.)"
    
    # ── Local knowledge base ────────────────────────────────────────────────
    context = retriever.retrieve(user_text, top_k=3) if retriever else ""

    # ── Live web search for informational queries ───────────────────────────
    web_results = ""
    if should_web_search(user_text):
        print(f"[Web Search] Searching for: {user_text}")
        web_results = web_search(user_text)

    sys_prompt = (
        "You are Iris, a helpful AI assistant. Always provide full, complete, and detailed code examples when requested. "
        "IMPORTANT: If the user says your previous answer was wrong or failed a test, DO NOT repeat yourself. "
        "Re-read the problem carefully, identify the logic error, and provide a corrected solution."
    )

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
    
    # Prepend the dynamic system prompt to the rolling window of history
    ctx = [{"role": "system", "content": sys_prompt}] + history[-20:]
    prompt = tokenizer.apply_chat_template(ctx, tokenize=False, add_generation_prompt=True)
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
    print("=" * 60)
    print("  Iris AI PC Agent (RAG Enabled)")
    print("  Type 'help' for commands, 'quit' to exit.")
    print("=" * 60)

def main():
    print_banner()
    config = load_config()
    model, tokenizer, device = load_iris_model()
    
    # Initialize the RAG index when starting the CLI controller
    retriever = None
    if IRIS_AVAILABLE:
        print("[INFO] Initializing RAG Knowledge Base...")
        retriever = BookRetriever(raw_data_dir="raw_data")
        retriever.load_and_index()
        
    history: list = []

    while True:
        try:
            raw = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not raw:
            continue

        lower = raw.lower()

        if lower in ("quit", "exit", "bye", "goodbye"):
            print("Iris: Goodbye!")
            break

        if lower in ("help", "?", "commands"):
            print(HELP_TEXT)
            continue

        intent, match = detect_intent(raw)

        if intent != "ai_agent":
            try:
                if intent == "website":
                    reply = handle_website(match)
                elif intent == "app":
                    reply = handle_app(match, config)
                elif intent == "youtube_video":
                    reply = handle_youtube_video(match)
                elif intent == "youtube_channel":
                    reply = handle_youtube_channel(match)
                elif intent == "open_terminal":
                    reply = handle_open_terminal()
                elif intent == "spotify":
                    reply = handle_spotify(match)
                elif intent == "email":
                    reply = handle_email(match, config)
                else:
                    reply = iris_chat_reply(model, tokenizer, device, retriever, history, raw)
            except Exception as e:
                reply = f"[Error] {e}"
        else:
            try:
                reply = ai_agent_handle(raw, model, tokenizer, device, retriever, history)
            except Exception as e:
                reply = f"[AI Agent error] {e}"

        print(f"Iris: {reply}")

if __name__ == "__main__":
    main()