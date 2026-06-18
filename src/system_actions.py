import os
import platform
import subprocess

def set_volume(action: str, amount: str = "5%"):
    os_name = platform.system()
    try:
        if os_name == "Linux":
            if action == "volume_mute":
                subprocess.run(["amixer", "set", "Master", "toggle"], check=True)
            elif action == "volume_up":
                subprocess.run(["amixer", "set", "Master", f"{amount}+"], check=True)
            elif action == "volume_down":
                subprocess.run(["amixer", "set", "Master", f"{amount}-"], check=True)
            return f"✅ Volume action '{action}' executed."
        elif os_name == "Windows":
            return "✅ Volume action simulated on Windows (requires nircmd or custom script)."
        elif os_name == "Darwin":
            if action == "volume_mute":
                subprocess.run(["osascript", "-e", "set volume output muted not (output muted of (get volume settings))"])
            elif action == "volume_up":
                subprocess.run(["osascript", "-e", "set volume output volume (output volume of (get volume settings) + 5)"])
            elif action == "volume_down":
                subprocess.run(["osascript", "-e", "set volume output volume (output volume of (get volume settings) - 5)"])
            return f"✅ Volume action '{action}' executed."
    except Exception as e:
        return f"❌ Failed to control volume: {e}"

def set_brightness(action: str, amount: str = "5%"):
    os_name = platform.system()
    try:
        if os_name == "Linux":
            if action == "brightness_up":
                subprocess.run(["brightnessctl", "set", f"+{amount}"], check=True)
            elif action == "brightness_down":
                subprocess.run(["brightnessctl", "set", f"{amount}-"], check=True)
            return f"✅ Brightness action '{action}' executed."
        elif os_name == "Darwin":
            return "❌ Brightness control on macOS requires 3rd party tools like 'brightness'."
        elif os_name == "Windows":
            return "✅ Brightness action simulated on Windows."
    except Exception as e:
        return f"❌ Failed to control brightness: {e}"

def control_power(action: str):
    os_name = platform.system()
    try:
        if os_name == "Linux":
            if action == "lock_screen":
                subprocess.run(["xdg-screensaver", "lock"], check=False)
                return "✅ Screen locked."
            elif action == "sleep_computer":
                subprocess.run(["systemctl", "suspend"], check=True)
                return "✅ Computer suspended."
            elif action == "shutdown_computer":
                subprocess.run(["systemctl", "poweroff"], check=True)
                return "✅ Computer shutting down."
            elif action == "restart_computer":
                subprocess.run(["systemctl", "reboot"], check=True)
                return "✅ Computer restarting."
        elif os_name == "Windows":
            if action == "lock_screen":
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
            elif action == "sleep_computer":
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            elif action == "shutdown_computer":
                subprocess.run(["shutdown", "/s", "/t", "0"])
            elif action == "restart_computer":
                subprocess.run(["shutdown", "/r", "/t", "0"])
            return f"✅ Power action '{action}' executed."
        elif os_name == "Darwin":
            if action == "lock_screen":
                subprocess.run(["pmset", "displaysleepnow"])
            elif action == "sleep_computer":
                subprocess.run(["pmset", "sleepnow"])
            elif action == "shutdown_computer":
                subprocess.run(["osascript", "-e", 'tell app "System Events" to shut down'])
            elif action == "restart_computer":
                subprocess.run(["osascript", "-e", 'tell app "System Events" to restart'])
            return f"✅ Power action '{action}' executed."
    except Exception as e:
        return f"❌ Failed to execute power action: {e}"

def manage_clipboard(action: str, text: str = ""):
    try:
        import pyperclip
        if action == "read_clipboard":
            content = pyperclip.paste()
            return f"📋 Clipboard content:\n{content}"
        elif action == "write_clipboard":
            pyperclip.copy(text)
            return "✅ Copied to clipboard."
    except ImportError:
        return "❌ Clipboard actions require the 'pyperclip' package. Run `pip install pyperclip`."
    except Exception as e:
        return f"❌ Clipboard error: {e}"

import shutil
import glob
import re

def find_chrome_pwa_exec(app_name: str):
    home_dir = os.path.expanduser("~")
    desktop_files = glob.glob(os.path.join(home_dir, ".local/share/applications", "chrome-*.desktop"))
    app_name_lower = app_name.lower()
    
    for file_path in desktop_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            name_match = re.search(r"^Name=(.*)$", content, re.MULTILINE)
            exec_match = re.search(r"^Exec=(.*)$", content, re.MULTILINE)
            if name_match and exec_match:
                name_val = name_match.group(1).strip().lower()
                exec_val = exec_match.group(1).strip()
                if app_name_lower in name_val:
                    # Return command split to make Popen happy or just run it via shell
                    return exec_val
        except Exception:
            pass
    return None

def open_app(name: str):
    os_name = platform.system()
    try:
        if os_name == "Linux":
            # 1. Try Chrome PWA first (e.g. WhatsApp Web PWA, Telegram Web PWA)
            pwa_exec = find_chrome_pwa_exec(name)
            if pwa_exec:
                # Launch via shell because Exec has arguments
                subprocess.Popen(pwa_exec, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"✅ Opened '{name}' (via Chrome PWA)."

            common_map = {
                "chrome": "google-chrome",
                "whatsapp": "whatsapp-for-linux",
                "telegram": "telegram-desktop",
                "spotify": "spotify",
                "vscode": "code"
            }
            exe = common_map.get(name.lower(), name.lower())
            if not shutil.which(exe):
                return f"❌ Could not find application '{name}' in PATH or as a Chrome PWA."
            subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"✅ Opened '{name}'."
        elif os_name == "Windows":
            subprocess.Popen(f"start {name}", shell=True)
            return f"✅ Opened '{name}'."
        elif os_name == "Darwin":
            subprocess.Popen(["open", "-a", name])
            return f"✅ Opened '{name}'."
    except Exception as e:
        return f"❌ Failed to open app: {e}"
