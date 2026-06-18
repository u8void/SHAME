import os
import time
import json
import re
import subprocess
from typing import Dict, Any

try:
    import pyautogui
    pyautogui.FAILSAFE = False  # Disable the corner failsafe
except ImportError:
    pyautogui = None

from src.iris import analyze_image


def _type_text_reliably(text: str):
    """Type text using clipboard paste (xdotool/xclip) for reliable unicode support."""
    # Try xdotool first (most reliable on Linux/GNOME Wayland/X11)
    try:
        subprocess.run(["xdotool", "type", "--clearmodifiers", "--", text], check=True, timeout=10)
        return
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    # Fallback: use xclip + Ctrl+V paste
    try:
        proc = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
        proc.communicate(input=text.encode("utf-8"))
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)
        return
    except (FileNotFoundError, Exception):
        pass
    # Final fallback: pyautogui write (may miss special chars)
    pyautogui.write(text, interval=0.05)


def perform_gui_action(task: str, wait_seconds: float = 3.0) -> str:
    """
    Takes a screenshot, passes it to the Vision model to locate coordinates,
    and executes PyAutoGUI actions.

    Args:
        task: Natural language description of what to do on screen.
        wait_seconds: Seconds to wait before taking the screenshot (gives apps time to open).
    """
    if pyautogui is None:
        return "❌ GUI action failed: pyautogui is not installed. Please run `pip install pyautogui`."

    # Wait for app to render before capturing
    if wait_seconds > 0:
        print(f"  [GUI] Waiting {wait_seconds}s for app to open...")
        time.sleep(wait_seconds)

    # 1. Take a screenshot
    screenshot_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gui_screenshot.jpg"))
    try:
        pyautogui.screenshot(screenshot_path)
        screen_w, screen_h = pyautogui.size()
    except Exception as e:
        return f"❌ GUI action failed: Could not capture screen: {e}"

    # 2. Prompt the vision model
    prompt = f"""You are a GUI automation agent controlling the user's mouse and keyboard.
Task: {task}
Screen dimensions: {screen_w}x{screen_h}

Analyze the screenshot carefully. Identify the exact pixel coordinates of every UI element you need to interact with.
Output ONLY a valid JSON array of actions. No markdown fences, no explanations, no prose — raw JSON only.

Available actions:
- {{"action": "click", "x": x_coord, "y": y_coord}}
- {{"action": "type", "text": "text to type"}}
- {{"action": "press", "key": "enter/esc/tab/ctrl+a/etc"}}
- {{"action": "sleep", "seconds": 1.5}}

IMPORTANT:
- Always click on an input field before typing into it.
- After typing a search query, add a sleep of 1.5 seconds before clicking the result.
- Use exact pixel coordinates, not percentages.

Example for sending a WhatsApp message:
[
  {{"action": "click", "x": 85, "y": 55}},
  {{"action": "sleep", "seconds": 0.5}},
  {{"action": "type", "text": "Ahmed Barakat"}},
  {{"action": "sleep", "seconds": 1.5}},
  {{"action": "click", "x": 85, "y": 120}},
  {{"action": "click", "x": 640, "y": 950}},
  {{"action": "type", "text": "im iris"}},
  {{"action": "press", "key": "enter"}}
]
"""
    try:
        print(f"\n[GUI] Analyzing screen ({screen_w}x{screen_h}) for task: '{task}'...")
        # analyze_image unloads the model by default
        response = analyze_image(screenshot_path, prompt, unload_after=True)

        # 3. Parse JSON from response — strip markdown fences if present
        clean = re.sub(r"```(?:json)?", "", response).strip().strip("`").strip()
        m = re.search(r"\[.*\]", clean, re.DOTALL)
        if m:
            actions = json.loads(m.group(0))
        else:
            actions = json.loads(clean)

        if not isinstance(actions, list):
            actions = [actions]

        # 4. Execute actions
        for act in actions:
            action_type = act.get("action")
            if action_type == "click":
                x, y = int(act["x"]), int(act["y"])
                print(f"  [GUI] Clicking ({x}, {y})")
                pyautogui.click(x, y)
                time.sleep(0.4)
            elif action_type == "type":
                text = act.get("text", "")
                print(f"  [GUI] Typing '{text}'")
                _type_text_reliably(text)
                time.sleep(0.4)
            elif action_type == "press":
                key = act.get("key", "")
                print(f"  [GUI] Pressing '{key}'")
                # Support combos like ctrl+a
                if "+" in key:
                    keys = key.split("+")
                    pyautogui.hotkey(*keys)
                else:
                    pyautogui.press(key)
                time.sleep(0.4)
            elif action_type == "sleep":
                sec = float(act.get("seconds", 1))
                print(f"  [GUI] Sleeping {sec}s")
                time.sleep(sec)

        return "✅ GUI task executed successfully."
    except json.JSONDecodeError:
        return f"❌ GUI task failed: Vision model returned non-JSON response:\n{response}"
    except Exception as e:
        return f"❌ GUI task failed: {e}"
