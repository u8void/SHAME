import os
import platform
import subprocess

import sys
import subprocess as _subprocess
from src.logger import get_logger

logger = get_logger("system_actions")

IS_INTERACTIVE = sys.stdout.isatty()

try:
    from rich.console import Console
    console = Console()
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    console = None

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

def _popen(cmd, shell: bool = False, **kw):
    suppress = dict(stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL)
    suppress.update(kw)
    try:
        return _subprocess.Popen(cmd, shell=shell, start_new_session=True, **suppress)
    except Exception as e:
        if not shell and isinstance(cmd, list):
            try:
                cmd_str = " ".join(cmd)
                return _subprocess.Popen(cmd_str, shell=True, start_new_session=True, **suppress)
            except Exception:
                pass
        logger.warning(f"[Shell] popen failed: {e}")
        return None


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
            return f"[SUCCESS] Volume action '{action}' executed."
        elif os_name == "Windows":
            return "[SUCCESS] Volume action simulated on Windows (requires nircmd or custom script)."
        elif os_name == "Darwin":
            if action == "volume_mute":
                subprocess.run(["osascript", "-e", "set volume output muted not (output muted of (get volume settings))"])
            elif action == "volume_up":
                subprocess.run(["osascript", "-e", "set volume output volume (output volume of (get volume settings) + 5)"])
            elif action == "volume_down":
                subprocess.run(["osascript", "-e", "set volume output volume (output volume of (get volume settings) - 5)"])
            return f"[SUCCESS] Volume action '{action}' executed."
    except Exception as e:
        return f"[ERROR] Failed to control volume: {e}"

def set_brightness(action: str, amount: str = "5%"):
    os_name = platform.system()
    try:
        if os_name == "Linux":
            if action == "brightness_up":
                subprocess.run(["brightnessctl", "set", f"+{amount}"], check=True)
            elif action == "brightness_down":
                subprocess.run(["brightnessctl", "set", f"{amount}-"], check=True)
            return f"[SUCCESS] Brightness action '{action}' executed."
        elif os_name == "Darwin":
            return "[ERROR] Brightness control on macOS requires 3rd party tools like 'brightness'."
        elif os_name == "Windows":
            return "[SUCCESS] Brightness action simulated on Windows."
    except Exception as e:
        return f"[ERROR] Failed to control brightness: {e}"

def control_power(action: str):
    os_name = platform.system()
    try:
        if os_name == "Linux":
            if action == "lock_screen":
                subprocess.run(["xdg-screensaver", "lock"], check=False)
                return "[SUCCESS] Screen locked."
            elif action == "sleep_computer":
                subprocess.run(["systemctl", "suspend"], check=True)
                return "[SUCCESS] Computer suspended."
            elif action == "shutdown_computer":
                subprocess.run(["systemctl", "poweroff"], check=True)
                return "[SUCCESS] Computer shutting down."
            elif action == "restart_computer":
                subprocess.run(["systemctl", "reboot"], check=True)
                return "[SUCCESS] Computer restarting."
        elif os_name == "Windows":
            if action == "lock_screen":
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
            elif action == "sleep_computer":
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            elif action == "shutdown_computer":
                subprocess.run(["shutdown", "/s", "/t", "0"])
            elif action == "restart_computer":
                subprocess.run(["shutdown", "/r", "/t", "0"])
            return f"[SUCCESS] Power action '{action}' executed."
        elif os_name == "Darwin":
            if action == "lock_screen":
                subprocess.run(["pmset", "displaysleepnow"])
            elif action == "sleep_computer":
                subprocess.run(["pmset", "sleepnow"])
            elif action == "shutdown_computer":
                subprocess.run(["osascript", "-e", 'tell app "System Events" to shut down'])
            elif action == "restart_computer":
                subprocess.run(["osascript", "-e", 'tell app "System Events" to restart'])
            return f"[SUCCESS] Power action '{action}' executed."
    except Exception as e:
        return f"[ERROR] Failed to execute power action: {e}"

def manage_clipboard(action: str, text: str = ""):
    try:
        import pyperclip
        if action == "read_clipboard":
            content = pyperclip.paste()
            return f"📋 Clipboard content:\n{content}"
        elif action == "write_clipboard":
            pyperclip.copy(text)
            return "[SUCCESS] Copied to clipboard."
    except ImportError:
        return "[ERROR] Clipboard actions require the 'pyperclip' package. Run `pip install pyperclip`."
    except Exception as e:
        return f"[ERROR] Clipboard error: {e}"

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
                                                                                       
                    return exec_val
        except Exception:
            pass
    return None

def open_app(name: str):
    os_name = platform.system()
    try:
        if os_name == "Linux":
                                                                               
            pwa_exec = find_chrome_pwa_exec(name)
            if pwa_exec:
                                                             
                subprocess.Popen(pwa_exec, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"[SUCCESS] Opened '{name}' (via Chrome PWA)."

            common_map = {
                "chrome": "google-chrome",
                "whatsapp": "whatsapp-for-linux",
                "telegram": "telegram-desktop",
                "spotify": "spotify",
                "vscode": "code",
                "rhythmbox": "rhythmbox",
                "rythembox": "rhythmbox"
            }
            exe = common_map.get(name.lower(), name.lower())
            if not shutil.which(exe):
                return f"[ERROR] Could not find application '{name}' in PATH or as a Chrome PWA."
            subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"[SUCCESS] Opened '{name}'."
        elif os_name == "Windows":
            subprocess.Popen(f"start {name}", shell=True)
            return f"[SUCCESS] Opened '{name}'."
        elif os_name == "Darwin":
            subprocess.Popen(["open", "-a", name])
            return f"[SUCCESS] Opened '{name}'."
    except Exception as e:
        return f"[ERROR] Failed to open app: {e}"

def _resolve_linux_app_exec(app_name: str) -> str:
                                                                                    
    import os, glob
    app_name = app_name.lower()
    dirs = [
        '/usr/share/applications', 
        os.path.expanduser('~/.local/share/applications'),
        '/var/lib/flatpak/exports/share/applications',
        os.path.expanduser('~/.local/share/flatpak/exports/share/applications')
    ]
    
    exact_match_exec = None
    partial_match_exec = None
    
    for d in dirs:
        if not os.path.isdir(d): continue
        for desktop_file in glob.glob(os.path.join(d, '**/*.desktop'), recursive=True):
            try:
                with open(desktop_file, 'r', encoding='utf-8') as f:
                    file_content = f.read().lower()
                    if 'type=application' not in file_content: continue
                        
                    lines = file_content.split('\n')
                    exec_cmd = None
                    
                    for line in lines:
                        if line.startswith('exec='):
                            cmd = line.split('=', 1)[1].strip()
                            exec_cmd = cmd.split()[0].split('/')[-1].replace('"', '').replace("'", "")
                            
                    for line in lines:
                        if line.startswith('name=') or line.startswith('name['):
                            entry_name = line.split('=', 1)[1].strip()
                            if app_name == entry_name:
                                exact_match_exec = exec_cmd
                            elif app_name in entry_name:
                                partial_match_exec = exec_cmd
            except:
                pass
                
    return exact_match_exec or partial_match_exec

def close_app(name: str):
    os_name = platform.system()
    
    aliases = []
    name_lower = name.lower()
    
    alias_map = {
        "setting": ["gnome-control-center", "systemsettings", "unity-control-center"],
        "settings": ["gnome-control-center", "systemsettings", "unity-control-center"],
        "files": ["nautilus", "dolphin", "nemo", "thunar"],
        "file manager": ["nautilus", "dolphin", "nemo", "thunar"],
        "terminal": ["gnome-terminal", "gnome-terminal-server", "konsole", "xterm", "alacritty", "kitty"],
        "browser": ["google-chrome", "chrome", "firefox", "brave", "edge", "chromium"],
        "chrome": ["google-chrome"],
        "word": ["libreoffice", "soffice.bin", "soffice"],
        "excel": ["libreoffice", "soffice.bin", "soffice"],
        "powerpoint": ["libreoffice", "soffice.bin", "soffice"],
        "calculator": ["gnome-calculator", "kcalc"],
        "discord": ["Discord", "discord-bin"],
        "spotify": ["spotify", "com.spotify.Client"],
        "rhythmbox": ["rhythmbox"],
        "rythembox": ["rhythmbox"]
    }
    
    if name_lower in alias_map:
        aliases.extend(alias_map[name_lower])
        
    if os_name == "Linux":
        dynamic_alias = _resolve_linux_app_exec(name)
        if dynamic_alias and dynamic_alias not in aliases:
            aliases.append(dynamic_alias)
            
    is_fallback = False
    if not aliases:
        aliases = [name]
        is_fallback = True
        
    try:
        if os_name == "Linux":
            import subprocess
            success = False
            for target in aliases:
                                                                                                                                
                if is_fallback:
                    r1 = subprocess.run(f"pkill -9 -i -x '{target}'", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    r2 = subprocess.run(f"killall -9 -I -e '{target}'", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if r1.returncode == 0 or r2.returncode == 0:
                        success = True
                else:
                    r1 = subprocess.run(f"pkill -9 -i '{target}'", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    r2 = subprocess.run(f"killall -9 -I '{target}'", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    r3 = subprocess.run(f"pkill -9 -i -f '{target}'", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if r1.returncode == 0 or r2.returncode == 0 or r3.returncode == 0:
                        success = True
            
            if success:
                return f"[SUCCESS] Closed '{name}'."
            else:
                return f"[ERROR] Could not find any running process matching '{name}' to close."
        elif os_name == "Windows":
            import subprocess
            success = False
            for target in aliases:
                                                                    
                result = subprocess.run(["taskkill", "/IM", f"{target}.exe", "/F"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if result.returncode == 0:
                    success = True
            
            if success:
                return f"[SUCCESS] Closed '{name}'."
            else:
                return f"[ERROR] Could not find any running process matching '{name}' to close."
        elif os_name == "Darwin":
            import subprocess
            success = False
            for target in aliases:
                if is_fallback:
                    result = subprocess.run(["pkill", "-9", "-i", "-x", target], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    result = subprocess.run(["pkill", "-9", "-i", "-f", target], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                if result.returncode == 0:
                    success = True

            if success:
                return f"[SUCCESS] Closed '{name}'."
            else:
                return f"[ERROR] Could not find any running process matching '{name}' to close."
    except Exception as e:
        return f"[ERROR] Failed to close app '{name}': {e}"

def open_file(path: str):
    os_name = platform.system()
    try:
        if os_name == "Linux":
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"[SUCCESS] Opened file '{path}'."
        elif os_name == "Windows":
            os.startfile(path)
            return f"[SUCCESS] Opened file '{path}'."
        elif os_name == "Darwin":
            subprocess.Popen(["open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"[SUCCESS] Opened file '{path}'."
    except Exception as e:
        return f"[ERROR] Failed to open file '{path}': {e}"

def search_files(query: str, folder: str = ""):
    os_name = platform.system()
    if not folder:
        folder = os.path.expanduser("~")
    try:
        if os_name == "Linux" or os_name == "Darwin":
            result = subprocess.run(["find", folder, "-iname", f"*{query}*"], capture_output=True, text=True)
            files = result.stdout.strip().split('\n')
            if files and files[0]:
                return f"🔍 Found {len(files)} matches. First few:\n" + "\n".join(files[:5])
            else:
                return f"[ERROR] No files found matching '{query}' in {folder}."
        elif os_name == "Windows":
            result = subprocess.run(["cmd", "/c", "dir", "/s", "/b", f"*{query}*"], cwd=folder, capture_output=True, text=True)
            files = result.stdout.strip().split('\n')
            if files and files[0]:
                return f"🔍 Found {len(files)} matches. First few:\n" + "\n".join(files[:5])
            else:
                return f"[ERROR] No files found matching '{query}' in {folder}."
    except Exception as e:
        return f"[ERROR] Failed to search for file: {e}"


def handle_media_command(action: str) -> str:
    key_map = {
        "media_play_pause": "playpause",
        "media_next": "nexttrack",
        "media_previous": "prevtrack",
        "media_stop": "stop",
    }
    key_name = key_map.get(action)
    if not key_name:
        return f"Unknown media action: {action}"

    system = platform.system()
    try:
        if system == "Linux":
                                 
            if shutil.which("playerctl"):
                sub_cmd = "play-pause" if action == "media_play_pause" else action.replace("media_", "")
                subprocess.run(["playerctl", sub_cmd], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"[SUCCESS] Executed media action: {action} (via playerctl)"
                         
            elif shutil.which("xdotool"):
                xdo_keys = {
                    "media_play_pause": "XF86AudioPlay",
                    "media_next": "XF86AudioNext",
                    "media_previous": "XF86AudioPrev",
                    "media_stop": "XF86AudioStop",
                }
                subprocess.run(["xdotool", "key", xdo_keys[action]], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"[SUCCESS] Executed media action: {action} (via xdotool)"
            
                                                                           
            elif shutil.which("dbus-send"):
                dbus_cmd = {
                    "media_play_pause": "PlayPause",
                    "media_next": "Next",
                    "media_previous": "Previous",
                    "media_stop": "Stop",
                }.get(action)
                if dbus_cmd:
                    try:
                        bus_list = subprocess.run(
                            ["dbus-send", "--print-reply", "--dest=org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus.ListNames"],
                            capture_output=True, text=True
                        )
                        players = [line.split('"')[1] for line in bus_list.stdout.splitlines() if "org.mpris.MediaPlayer2." in line]
                        if players:
                            for player in players:
                                subprocess.run(
                                    ["dbus-send", "--print-reply", f"--dest={player}", "/org/mpris/MediaPlayer2", f"org.mpris.MediaPlayer2.Player.{dbus_cmd}"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                                )
                            return f"[SUCCESS] Executed media action: {action} (via dbus/MPRIS)"
                    except Exception as e:
                        logger.warning(f"dbus-send media control failed: {e}")
        elif system == "Darwin":
            scripts = {
                "media_play_pause": "tell application \"System Events\" to key code 16",
                "media_next": "tell application \"System Events\" to key code 19",
                "media_previous": "tell application \"System Events\" to key code 18",
                "media_stop": "tell application \"System Events\" to key code 17",
            }
            subprocess.run(["osascript", "-e", scripts[action]], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"[SUCCESS] Executed media action: {action} (via osascript)"
    except Exception as e:
        pass                        

                           
    try:
        import pyautogui
        if not hasattr(pyautogui, 'press'):
            raise AttributeError("PyAutoGUI is incomplete or improperly initialized")
        pyautogui.press(key_name)
        return f"[SUCCESS] Executed media action: {action} (via PyAutoGUI)"
    except Exception as e:
        if platform.system() == "Linux":
            return f"[ERROR] Failed to execute media action {action}. Please install 'playerctl' via your package manager."
        return f"[ERROR] Failed to execute media action {action}: {e}"


def get_hardcoded_action_json(query: str) -> str | None:
\
\
\
       
    if not query:
        return None
    import json
    import re
    q = query.strip().lower().rstrip("?.!")
    q = re.sub(r"\bplease\b", "", q).strip()
    q = re.sub(r"\s+", " ", q)
    
                    
    mute_phrases = (
        "mute", "unmute", "mute volume", "unmute volume", "silence", "silence the computer",
        "silence the pc", "toggle mute", "toggle sound", "mute computer", "mute sound",
        "sound off", "silent mode", "turn off sound", "disable sound", "disable audio",
        "turn off audio", "enable audio", "audio off", "quiet mode", "turn sound off",
        "turn sound on", "sound on", "sound mute", "sound unmute", "audio mute", "audio unmute"
    )
    if q in mute_phrases:
        return json.dumps({"action": "volume_mute"})
        
                       
    vol_up_phrases = (
        "volume up", "increase volume", "louder", "make it louder", "turn volume up",
        "turn the volume up", "increase the volume", "raise volume", "raise the volume",
        "volume higher", "higher volume", "turn up volume", "turn up the volume",
        "more sound", "crank it up", "boost volume", "volume boost", "boost sound",
        "increase sound", "raise sound", "make louder", "make sound louder"
    )
    if q in vol_up_phrases:
        return json.dumps({"action": "volume_up"})

    vol_down_phrases = (
        "volume down", "decrease volume", "quieter", "make it quieter", "softer",
        "turn volume down", "turn the volume down", "decrease the volume", "lower volume",
        "lower the volume", "volume lower", "lower volume", "turn down volume",
        "turn down the volume", "less sound", "reduce volume", "reduce sound",
        "reduce the volume", "decrease sound", "lower sound", "make quieter", "make sound quieter"
    )
    if q in vol_down_phrases:
        return json.dumps({"action": "volume_down"})
        
                   
    if q in (
        "max volume", "volume max", "maximum volume", "full volume", "turn volume to max",
        "set volume to max", "volume to 100", "volume 100", "100% volume"
    ):
        return json.dumps({"action": "volume_set", "percent": 100})
    if q in (
        "volume at half", "half volume", "set volume to half", "medium volume",
        "volume to 50", "volume 50", "50% volume"
    ):
        return json.dumps({"action": "volume_set", "percent": 50})
    m = re.match(r"^(?:set\s+)?volume\s+(?:to\s+)?(\d+)\s*%?$", q)
    if m:
        val = int(m.group(1))
        return json.dumps({"action": "volume_set", "percent": val})
    m = re.match(r"^(\d+)\s*%?\s*volume$", q)
    if m:
        val = int(m.group(1))
        return json.dumps({"action": "volume_set", "percent": val})
    m = re.match(r"^(?:turn\s+)?volume\s+(?:up\s+|down\s+)?to\s+(\d+)\s*%?$", q)
    if m:
        val = int(m.group(1))
        return json.dumps({"action": "volume_set", "percent": val})
    m = re.match(r"^change\s+volume\s+(?:to\s+)?(\d+)\s*%?$", q)
    if m:
        val = int(m.group(1))
        return json.dumps({"action": "volume_set", "percent": val})
    m = re.match(r"^put\s+volume\s+(?:to\s+)?(\d+)\s*%?$", q)
    if m:
        val = int(m.group(1))
        return json.dumps({"action": "volume_set", "percent": val})
        
                           
    bright_up_phrases = (
        "brightness up", "increase brightness", "brighter", "make screen brighter",
        "make the screen brighter", "turn brightness up", "turn up brightness",
        "increase screen brightness", "raise brightness", "raise the brightness",
        "brighter screen", "screen brighter", "more brightness", "turn up screen brightness",
        "raise screen brightness", "increase screen light", "more screen light",
        "brightness higher", "higher brightness", "increase display brightness",
        "raise display brightness", "make display brighter"
    )
    if q in bright_up_phrases:
        return json.dumps({"action": "brightness_up"})

    bright_down_phrases = (
        "brightness down", "decrease brightness", "lower brightness", "lower the brightness",
        "dim the screen", "dim screen", "dim", "turn brightness down", "turn down brightness",
        "decrease screen brightness", "dimmer", "make screen dimmer", "make the screen dimmer",
        "less brightness", "reduce brightness", "reduce screen brightness", "lower screen light",
        "less screen light", "brightness lower", "lower brightness", "decrease display brightness",
        "lower display brightness", "make display dimmer"
    )
    if q in bright_down_phrases:
        return json.dumps({"action": "brightness_down"})
        
                       
    if q in (
        "max brightness", "brightness max", "maximum brightness", "full brightness",
        "set brightness to max", "brightness to max", "brightness to 100", "brightness 100",
        "100% brightness"
    ):
        return json.dumps({"action": "brightness_set", "percent": 100})
    if q in (
        "minimum brightness", "min brightness", "lowest brightness", "brightness to min",
        "set brightness to min", "brightness at half", "half brightness", "medium brightness"
    ):
        return json.dumps({"action": "brightness_set", "percent": 5})
    m = re.match(r"^(?:set\s+)?brightness\s+(?:to\s+)?(\d+)\s*%?$", q)
    if m:
        val = int(m.group(1))
        return json.dumps({"action": "brightness_set", "percent": val})
    m = re.match(r"^(?:turn\s+)?brightness\s+(?:up\s+|down\s+)?to\s+(\d+)\s*%?$", q)
    if m:
        val = int(m.group(1))
        return json.dumps({"action": "brightness_set", "percent": val})
    m = re.match(r"^change\s+brightness\s+(?:to\s+)?(\d+)\s*%?$", q)
    if m:
        val = int(m.group(1))
        return json.dumps({"action": "brightness_set", "percent": val})
        
                       
    play_pause_phrases = (
        "play/pause", "play or pause", "play", "pause", "pause the music", "resume",
        "resume music", "pause the video", "play music", "play video", "resume playback",
        "pause playback", "toggle play", "toggle playback", "start music", "start video",
        "start playback", "unpause", "unpause music", "toggle play/pause", "media play",
        "media pause", "play song", "pause song", "resume song", "music play", "music pause"
    )
    if q in play_pause_phrases:
        return json.dumps({"action": "media_play_pause"})

    next_phrases = (
        "next", "next track", "next song", "skip", "skip this track", "skip song",
        "play the next song", "next item", "go to next track", "go to next song",
        "forward", "fast forward", "skip forward", "next media", "play next",
        "skip track", "skip this song", "skip the song"
    )
    if q in next_phrases:
        return json.dumps({"action": "media_next"})

    prev_phrases = (
        "prev", "previous", "previous track", "previous song", "go back a song",
        "play the previous track", "go to previous song", "previous item", "go back a track",
        "go back", "rewind", "previous media", "play previous", "previous track",
        "go to the previous song", "go to the previous track"
    )
    if q in prev_phrases:
        return json.dumps({"action": "media_previous"})

    stop_phrases = (
        "stop", "stop music", "stop the music", "stop playback", "stop video",
        "halt music", "halt playback", "turn off music", "stop media", "turn music off","pause",
        "pause music", "pause video", "pause playback", "pause music","pause video",
        
    )
    if q in stop_phrases:
        return json.dumps({"action": "media_stop"})
        
                            
    lock_phrases = (
        "lock", "lock screen", "lock the screen", "lock my computer", "lock computer",
        "lock pc", "lock the pc", "lock session", "secure screen", "lock work station",
        "lock workstation", "lock windows", "lock linux", "lock mac"
    )
    if q in lock_phrases:
        return json.dumps({"action": "lock_screen"})

    sleep_phrases = (
        "sleep", "sleep computer", "sleep the computer", "put the pc to sleep",
        "put computer to sleep", "sleep mode", "suspend", "suspend computer",
        "suspend pc", "suspend the computer", "put to sleep", "go to sleep",
        "activate sleep mode", "hibernate", "hibernate computer", "hibernate pc"
    )
    if q in sleep_phrases:
        return json.dumps({"action": "sleep_computer"})

    restart_phrases = (
        "restart", "restart computer", "restart the computer", "reboot",
        "reboot computer", "reboot the computer", "restart pc", "reboot pc",
        "restart machine", "reboot machine", "system restart", "system reboot"
    )
    if q in restart_phrases:
        return json.dumps({"action": "restart_computer"})

    shutdown_phrases = (
        "shut down", "shutdown", "shut down the computer", "power off",
        "turn off the computer", "turn off pc", "shutdown computer", "shutdown pc",
        "turn off machine", "power down", "power off computer", "power off pc",
        "shut down pc", "shut down computer", "turn machine off"
    )
    if q in shutdown_phrases:
        return json.dumps({"action": "shutdown_computer"})
        
                          
    dark_on_phrases = (
        "turn on dark mode", "switch to dark mode", "enable dark mode", "dark mode on",
        "activate dark mode", "go dark", "dark theme on", "enable dark theme",
        "switch to dark theme", "turn dark mode on", "set dark mode", "set dark theme"
    )
    if q in dark_on_phrases:
        return json.dumps({"action": "dark_mode", "state": "on"})

    dark_off_phrases = (
        "turn off dark mode", "switch to light mode", "disable dark mode", "dark mode off",
        "light mode on", "activate light mode", "light theme on", "enable light theme",
        "switch to light theme", "turn dark mode off", "set light mode", "set light theme"
    )
    if q in dark_off_phrases:
        return json.dumps({"action": "dark_mode", "state": "off"})
        
                                        
    night_on_phrases = (
        "enable night light", "turn on blue light filter", "turn on night light",
        "warm screen tones", "night shift on", "activate night light", "enable night shift",
        "turn on night shift", "night light on", "blue light filter on", "set night light",
        "turn night light on", "turn night shift on", "night shift enable"
    )
    if q in night_on_phrases:
        return json.dumps({"action": "night_shift", "state": "on"})

    night_off_phrases = (
        "disable night light", "turn off night light", "turn off blue light filter",
        "night shift off", "deactivate night light", "disable night shift",
        "turn off night shift", "night light off", "blue light filter off",
        "turn night light off", "turn night shift off", "night shift disable"
    )
    if q in night_off_phrases:
        return json.dumps({"action": "night_shift", "state": "off"})
        
                        
    dnd_on_phrases = (
        "enable do not disturb", "turn on focus assist", "turn on do not disturb",
        "do not disturb on", "dnd on", "activate do not disturb", "turn dnd on",
        "enable dnd", "focus mode on", "activate focus mode", "silent mode on",
        "turn do not disturb on"
    )
    if q in dnd_on_phrases:
        return json.dumps({"action": "do_not_disturb", "state": "on"})

    dnd_off_phrases = (
        "disable do not disturb", "turn off focus mode", "turn off focus assist",
        "turn off do not disturb", "do not disturb off", "dnd off", "deactivate do not disturb",
        "turn dnd off", "disable dnd", "focus mode off", "deactivate focus mode",
        "silent mode off", "turn do not disturb off"
    )
    if q in dnd_off_phrases:
        return json.dumps({"action": "do_not_disturb", "state": "off"})
        
                                                          
    m = re.match(r"^copy\s+['\"](.*?)['\"]\s+to\s+clipboard$", query, re.IGNORECASE)
    if m:
        return json.dumps({"action": "clipboard_copy", "text": m.group(1)})
    m = re.match(r"^copy\s+the\s+text:\s*(.+)$", query, re.IGNORECASE)
    if m:
        return json.dumps({"action": "clipboard_copy", "text": m.group(1)})
    m = re.match(r"^copy\s+this\s+to\s+clipboard:\s*(.+)$", query, re.IGNORECASE)
    if m:
        return json.dumps({"action": "clipboard_copy", "text": m.group(1)})
    m = re.match(r"^copy\s+['\"](.*?)['\"]$", query, re.IGNORECASE)
    if m:
        return json.dumps({"action": "clipboard_copy", "text": m.group(1)})
    m = re.match(r"^copy\s+(.+?)\s+to\s+(?:the\s+)?clipboard$", query, re.IGNORECASE)
    if m:
        return json.dumps({"action": "clipboard_copy", "text": m.group(1)})
    
    clipboard_read_phrases = (
        "read clipboard", "what's on my clipboard", "what's on the clipboard",
        "show clipboard content", "paste what's on the clipboard", "paste clipboard",
        "get clipboard content", "view clipboard", "read from clipboard",
        "paste from clipboard", "clipboard content", "show clipboard", "get clipboard"
    )
    if q in clipboard_read_phrases:
        return json.dumps({"action": "clipboard_read"})
        
                     
    ip_phrases = (
        "what's my ip address", "what is my ip", "show ip", "my ip", "get my ip",
        "show ip address", "what is my ip address", "what's my ip", "ip address",
        "check my ip", "check ip", "get ip"
    )
    if q in ip_phrases:
        return json.dumps({"action": "system_info", "what": "ip"})

    ram_phrases = (
        "how much ram do i have", "show memory", "check ram", "ram size", "memory info",
        "get ram info", "how much ram", "check memory usage", "ram usage", "show ram",
        "ram stats", "memory details", "how much memory", "check memory"
    )
    if q in ram_phrases:
        return json.dumps({"action": "system_info", "what": "memory"})

    hostname_phrases = (
        "show me the hostname", "what's the hostname", "get hostname", "hostname",
        "what is the hostname", "check hostname", "show hostname", "my hostname"
    )
    if q in hostname_phrases:
        return json.dumps({"action": "system_info", "what": "hostname"})

    cpu_phrases = (
        "what's my cpu", "show cpu info", "cpu details", "my cpu", "check cpu",
        "get cpu info", "cpu specs", "processor info", "what is my processor",
        "show processor", "cpu statistics", "check processor"
    )
    if q in cpu_phrases:
        return json.dumps({"action": "system_info", "what": "cpu"})

    battery_phrases = (
        "show battery level", "how much battery do i have", "battery percentage",
        "battery status", "check battery", "battery level", "how is my battery",
        "show battery", "battery state", "check battery level", "check battery status"
    )
    if q in battery_phrases:
        return json.dumps({"action": "system_info", "what": "battery"})

    uptime_phrases = (
        "how long has my pc been on", "check uptime", "uptime", "system uptime",
        "how long has my computer been on", "how long has my pc been running",
        "check system uptime", "how long has the computer been running",
        "how long has the pc been on", "computer uptime"
    )
    if q in uptime_phrases:
        return json.dumps({"action": "system_info", "what": "uptime"})

    sysinfo_phrases = (
        "system info", "full system report", "show system info", "system specifications",
        "system details", "about my pc", "about my computer", "system specs", "about pc",
        "get system info", "display system specs", "show system details"
    )
    if q in sysinfo_phrases:
        return json.dumps({"action": "system_info", "what": "all"})
        
                        
    storage_phrases = (
        "check how much storage left", "see my storage", "how much disk space do i have",
        "what is my disk usage", "disk space left", "how much storage do i have",
        "check storage", "show storage", "check disk space", "disk usage", "storage left",
        "free disk space", "how much free storage", "check hard drive space", "show storage info",
        "check drive space", "show disk space"
    )
    if q in storage_phrases or ("storage left" in q) or ("disk space" in q and "left" in q) or ("storage space" in q and "left" in q):
        return json.dumps({"action": "check_storage"})
        
    m = re.match(r"^(?:check\s+)?disk\s+usage\s+(?:of|for)\s+(.+)$", query, re.IGNORECASE)
    if m:
        return json.dumps({"action": "disk_usage", "path": m.group(1).strip()})
    m = re.match(r"^(?:check\s+)?storage\s+(?:of|for)\s+(.+)$", query, re.IGNORECASE)
    if m:
        return json.dumps({"action": "disk_usage", "path": m.group(1).strip()})
        
                                                  
    screenshot_phrases = (
        "take a screenshot", "screenshot the screen", "capture the screen", "screenshot",
        "take screenshot", "capture screen", "print screen", "take screen shot",
        "capture screenshot", "save screenshot", "snap screen", "snap the screen"
    )
    if q in screenshot_phrases:
        return json.dumps({"action": "screenshot", "path": "~/Desktop/screenshot.png"})
    m = re.match(r"^(?:take\s+)?(?:an?\s+)?screenshot\s+(?:and\s+)?save\s+(?:it\s+)?to\s+(.+)$", query, re.IGNORECASE)
    if m:
        path = m.group(1).strip().strip("'\"")
        path_lower = path.lower()
        if path_lower in ("desktop", "downloads", "pictures"):
            path = f"~/{path_lower.capitalize()}/screenshot.png"
        return json.dumps({"action": "screenshot", "path": path})
        
                       
    settings_phrases = (
        "open settings", "open system settings", "go to settings", "show settings",
        "launch settings", "open control panel", "go to control panel", "open system preferences",
        "show system settings", "launch system settings"
    )
    if q in settings_phrases:
        return json.dumps({"action": "open_settings"})
        
                                                  
    m = re.match(r"^take\s+note\s*(?:of)?:\s*(.+)$", query, re.IGNORECASE)
    if m:
        return json.dumps({"action": "take_note", "content": m.group(1).strip()})
    m = re.match(r"^take\s+note\s*(?:of)?\s+(.+)$", query, re.IGNORECASE)
    if m:
        return json.dumps({"action": "take_note", "content": m.group(1).strip()})
    m = re.match(r"^remember\s+(.+)$", query, re.IGNORECASE)
    if m:
        return json.dumps({"action": "take_note", "content": m.group(1).strip()})
    m = re.match(r"^note\s+this:\s*(.+)$", query, re.IGNORECASE)
    if m:
        return json.dumps({"action": "take_note", "content": m.group(1).strip()})
    m = re.match(r"^add\s+(.+?)\s+to\s+my\s+notes$", query, re.IGNORECASE)
    if m:
        return json.dumps({"action": "take_note", "content": m.group(1).strip()})
    m = re.match(r"^write\s+down:\s*(.+)$", query, re.IGNORECASE)
    if m:
        return json.dumps({"action": "take_note", "content": m.group(1).strip()})
        
                                                                      
    m = re.match(r"^(?:search\s+for|find\s+all|look\s+for|locate|find)\s+(.+?)\s+(?:in|on|at|inside)\s+(.+)$", query, re.IGNORECASE)
    if m:
        return json.dumps({"action": "search_files", "query": m.group(1).strip(), "folder": m.group(2).strip()})
        
                                                                    
    m = re.match(r"^(?:open|launch|show|view|explore)\s+(.+)$", query, re.IGNORECASE)
    if m:
        path_val = m.group(1).strip()
        path_val_lower = path_val.lower()
        
                                                      
        is_folder_word = False
        for kw in (" folder", " directory"):
            if path_val_lower.endswith(kw):
                path_val = path_val[:-len(kw)].strip()
                path_val_lower = path_val_lower[:-len(kw)].strip()
                is_folder_word = True
                break
                
        known_apps = {
            "chrome", "google chrome", "firefox", "edge", "safari", "opera", "brave",
            "spotify", "whatsapp", "telegram", "discord", "slack", "zoom", "teams", "microsoft teams",
            "vscode", "code", "notepad", "calculator", "terminal", "system monitor", "file explorer",
            "file manager", "finder", "nautilus", "music", "disks", "gedit", "pycharm", "android studio",
            "vlc", "postman", "docker"
        }
        
                                                                                        
        if path_val_lower in known_apps and not is_folder_word:
            return json.dumps({"action": "open_app", "name": path_val_lower})
        
                                                                         
        if re.search(r"\.(?:com|org|net|edu|gov|io|co|info|me|xyz|app|dev|sh|online)(?:/|$)", path_val_lower):
            return None
            
        is_path = (
            is_folder_word or 
            "/" in path_val or 
            "\\" in path_val or 
            path_val.startswith("~") or 
            "." in path_val or 
            path_val_lower in ("desktop", "downloads", "documents", "pictures", "videos")
        )
        if is_path:
            if path_val_lower in ("desktop", "downloads", "documents", "pictures", "videos"):
                path_val = f"~/{path_val_lower.capitalize()}"
            return json.dumps({"action": "open_file", "path": path_val})

                                           
    m = re.match(r"^(?:open|launch|start|run|execute|open\s+the\s+app|launch\s+the\s+app)\s+(?:the\s+|an?\s+)?(.+?)(?:\s+app)?$", q)
    if m:
        app_name = m.group(1).strip()
        if app_name not in ("settings", "system settings", "terminal", "console", "shell"):
            return json.dumps({"action": "open_app", "name": app_name})
            
                                         
    m = re.match(r"^(?:close|kill|terminate|stop|force\s+quit|force\s+close|quit)\s+(?:the\s+|an?\s+)?(.+?)(?:\s+app)?$", q)
    if m:
        app_name = m.group(1).strip()
        return json.dumps({"action": "close_app", "name": app_name})

    return None


def handle_window_close():
    system = platform.system()
    if system == "Darwin":
        _shell(
            'osascript -e \'tell application "System Events" to keystroke "w" using command down\'',
            shell=True,
        )
    elif system == "Windows":
        _shell(
            "powershell -Command \"(New-Object -ComObject WScript.Shell).SendKeys('%{F4}')\"",
            shell=True,
        )
    else:
        _shell("xdotool getactivewindow windowclose", shell=True)
    return "Closed window."


def handle_window_minimize():
    system = platform.system()
    if system == "Darwin":
        _shell(
            'osascript -e \'tell application "System Events" to keystroke "m" using command down\'',
            shell=True,
        )
    elif system == "Windows":
        _shell(
            'powershell -Command "(New-Object -ComObject Shell.Application).MinimizeAll()"',
            shell=True,
        )
    else:
        _shell("xdotool getactivewindow windowminimize", shell=True)
    return "Minimized window."


def handle_window_maximize():
    system = platform.system()
    if system == "Darwin":
        _shell(
            'osascript -e \'tell application "System Events" to tell process (name of first application process whose frontmost is true) to click (first button whose subrole is "AXZoomButton") of first window\'',
            shell=True,
        )
    elif system == "Windows":
        _shell(
            "powershell -Command \"$wshell = New-Object -ComObject wscript.shell; $wshell.SendKeys('% {MAXIMIZE}')\"",
            shell=True,
        )
    else:
        _shell("xdotool getactivewindow windowsize 100% 100%", shell=True)
    return "Maximized window."


def handle_window_fullscreen():
    system = platform.system()
    if system == "Darwin":
        _shell(
            'osascript -e \'tell application "System Events" to keystroke "f" using {command down, control down}\'',
            shell=True,
        )
    elif system == "Windows":
        _shell(
            "powershell -Command \"(New-Object -ComObject WScript.Shell).SendKeys('{F11}')\"",
            shell=True,
        )
    else:
        _shell("xdotool key F11", shell=True)
    return "Toggled fullscreen."


def handle_switch_tab(direction: str):
    system = platform.system()
    if system == "Darwin":
        if direction == "next":
            _shell(
                "osascript -e 'tell application \"System Events\" to key code 48 using control down'",
                shell=True,
            )
        else:
            _shell(
                "osascript -e 'tell application \"System Events\" to key code 48 using {control down, shift down}'",
                shell=True,
            )
    elif system == "Windows":
        keys = "^{TAB}" if direction == "next" else "^+{TAB}"
        _shell(
            f"powershell -Command \"(New-Object -ComObject WScript.Shell).SendKeys('{keys}')\"",
            shell=True,
        )
    else:
        keys = "ctrl+Tab" if direction == "next" else "ctrl+shift+Tab"
        _shell(f"xdotool key {keys}", shell=True)
    return f"Switched tab {direction}."


def handle_wifi(state: str) -> str:
    system = platform.system()
    if system == "Darwin":
        try:
            res = _shell(
                "networksetup -listallhardwareports",
                shell=True,
                capture_output=True,
                text=True,
            )
            interface = "en0"
            lines = res.stdout.splitlines()
            for i, line in enumerate(lines):
                if "Wi-Fi" in line and i + 1 < len(lines):
                    interface = lines[i + 1].split()[-1]
                    break
            _shell(f"networksetup -setairportpower {interface} {state}", shell=True)
            return f"Wi-Fi turned {state}."
        except Exception as e:
            return f"Failed to set Wi-Fi: {e}"
    elif system == "Windows":
        admin_state = "enabled" if state == "on" else "disabled"
        try:
            _shell(
                f'netsh interface set interface "Wi-Fi" admin={admin_state}', shell=True
            )
            return f"Wi-Fi turned {state}."
        except Exception as e:
            return f"Failed to set Wi-Fi: {e}"
    else:
        try:
            _shell(f"nmcli radio wifi {state}", shell=True)
            return f"Wi-Fi turned {state}."
        except Exception as e:
            return f"Failed to set Wi-Fi: {e}"


def handle_bluetooth(state: str) -> str:
    system = platform.system()
    on_val = "1" if state == "on" else "0"
    if system == "Darwin":
        try:
            res = _shell(f"blueutil -p {on_val}", shell=True, capture_output=True)
            if res.returncode == 0:
                return f"Bluetooth turned {state}."
            _shell(
                'osascript -e \'tell application "System Events" to tell secondary click of menu bar item 1 of menu bar 1 of process "ControlCenter" to click\'',
                shell=True,
            )
            return f"Attempted to set Bluetooth to {state} (install blueutil via brew for full reliability)."
        except Exception as e:
            return f"Failed to set Bluetooth: {e}"
    elif system == "Windows":
        try:
            _shell("start ms-settings:bluetooth", shell=True)
            return f"Opened Bluetooth settings to turn it {state}."
        except Exception as e:
            return f"Failed to open Bluetooth settings: {e}"
    elif system == "Linux":
        cmd = "rfkill unblock bluetooth" if state == "on" else "rfkill block bluetooth"
        try:
            _shell(cmd, shell=True)
            return f"Bluetooth turned {state}."
        except Exception as e:
            return f"Failed to set Bluetooth: {e}"
    return f"Bluetooth control not supported on {system}."


def handle_vpn(action: str, name: str) -> str:
    system = platform.system()
    if system == "Darwin":
        cmd = f'networksetup -{action}networkservice "{name}"'
        res = _shell(cmd, shell=True, capture_output=True, text=True)
        return (
            f"VPN {action} command executed: {res.stdout.strip() or res.stderr.strip()}"
        )
    elif system == "Windows":
        cmd = (
            f'rasdial "{name}"'
            if action == "connect"
            else f'rasdial "{name}" /disconnect'
        )
        _shell(cmd, shell=True)
        return f"VPN {action} command executed."
    elif system == "Linux":
        nmcli_action = "up" if action == "connect" else "down"
        cmd = f'nmcli con {nmcli_action} id "{name}"'
        res = _shell(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            return f"VPN {action} command executed natively."
        else:
            return f"VPN {action} failed: {res.stderr.strip()}"
    return f"VPN control not supported on {system}."


def handle_speed_test() -> str:
    system = platform.system()
    if system == "Darwin":
        res = _shell("networkQuality", shell=True, capture_output=True, text=True)
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
        _shell(
            "sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder", shell=True
        )
        return "DNS cache flushed (may prompt for sudo password)."
    elif system == "Windows":
        _shell("ipconfig /flushdns", shell=True)
        return "DNS cache flushed."
    else:
        _shell("resolvectl flush-caches || systemd-resolve --flush-caches", shell=True)
        return "DNS cache flushed."


def handle_lock_screen() -> str:
    system = platform.system()
    if system == "Darwin":
        _shell(
            'osascript -e \'tell application "System Events" to keystroke "q" using {control down, command down}\'',
            shell=True,
        )
        return "Screen locked."
    elif system == "Windows":
        _shell("rundll32.exe user32.dll,LockWorkStation", shell=True)
        return "Screen locked."
    else:
        _shell("xdg-screensaver lock || gnome-screensaver-command -l", shell=True)
        return "Screen locked."


def handle_sleep() -> str:
    system = platform.system()
    if system == "Darwin":
        _shell("osascript -e 'tell application \"System Events\" to sleep'", shell=True)
        return "Sleeping computer."
    elif system == "Windows":
        _shell("rundll32.exe powrprof.dll,SetSuspendState Sleep", shell=True)
        return "Sleeping computer."
    else:
        _shell("systemctl suspend", shell=True)
        return "Sleeping computer."


def handle_restart() -> str:
    system = platform.system()
    if system == "Darwin":
        _shell(
            "osascript -e 'tell application \"System Events\" to restart'", shell=True
        )
    elif system == "Windows":
        _shell("shutdown /r /t 0", shell=True)
    else:
        _shell("shutdown -r now", shell=True)
    return "Restarting computer..."


def handle_shutdown() -> str:
    system = platform.system()
    if system == "Darwin":
        _shell(
            "osascript -e 'tell application \"System Events\" to shut down'", shell=True
        )
    elif system == "Windows":
        _shell("shutdown /s /t 0", shell=True)
    else:
        _shell("shutdown -h now", shell=True)
    return "Shutting down computer..."


def handle_dnd(state: str) -> str:
    system = platform.system()
    if system == "Darwin":
        pass
    elif system == "Windows":
        _shell("start ms-settings:quietmoments", shell=True)
        return f"Opened Focus Assist settings to turn {state}."
    else:
        val = "true" if state == "on" else "false"
        _shell(
            f"gsettings set org.gnome.desktop.notifications show-banners {val}",
            shell=True,
        )
    return f"Do Not Disturb set to {state}."


def handle_dark_mode(state: str) -> str:
    system = platform.system()
    if system == "Darwin":
        val = "true" if state == "on" else "false"
        _shell(
            f"osascript -e 'tell application \"System Events\" to tell appearance preferences to set dark mode to {val}'",
            shell=True,
        )
        return f"Dark mode turned {state}."
    elif system == "Windows":
        try:
            import winreg

            val = 0 if state == "on" else 1
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                0,
                winreg.KEY_SET_VALUE,
            )
            winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, val)
            winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, val)
            winreg.CloseKey(key)
            return f"Dark mode turned {state}."
        except Exception as e:
            return f"Failed to set dark mode: {e}"
    else:
        val = "prefer-dark" if state == "on" else "default"
        _shell(
            f"gsettings set org.gnome.desktop.interface color-scheme '{val}'",
            shell=True,
        )
        return f"Dark mode turned {state}."


def handle_night_shift(state: str) -> str:
    system = platform.system()
    if system == "Windows":
        _shell("start ms-settings:nightlight", shell=True)
        return f"Opened Night Light settings to turn {state}."
    elif system == "Linux":
        val = "true" if state == "on" else "false"
        _shell(
            f"gsettings set org.gnome.settings-daemon.plugins.color night-light-enabled {val}",
            shell=True,
        )
    return f"Night Shift turned {state}."


def handle_set_wallpaper(path: str) -> str:
    system = platform.system()
    resolved_path = os.path.abspath(os.path.expanduser(path))
    if system == "Darwin":
        cmd = f'osascript -e \'tell application "Finder" to set desktop picture to POSIX file "{resolved_path}"\''
        _shell(cmd, shell=True)
        return f"Wallpaper set to {resolved_path}."
    elif system == "Windows":
        import ctypes

        SPI_SETDESKWALLPAPER = 20
        SPIF_UPDATEINIFILE = 1
        SPIF_SENDWININICHANGE = 2
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER,
            0,
            resolved_path,
            SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE,
        )
        return f"Wallpaper set to {resolved_path}."
    elif system == "Linux":
        try:
            cmd = f"gsettings set org.gnome.desktop.background picture-uri file://{resolved_path}"
            cmd_dark = f"gsettings set org.gnome.desktop.background picture-uri-dark file://{resolved_path}"
            _shell(cmd, shell=True)
            _shell(cmd_dark, shell=True)
            return f"Wallpaper set to {resolved_path} (GNOME)."
        except Exception as e:
            return f"Failed to set wallpaper on Linux: {e}"
    return f"Wallpaper setting not supported on {system}."


def handle_screenshot(path: str) -> str:
    resolved_path = os.path.abspath(os.path.expanduser(path))
    system = platform.system()
    if system == "Darwin":
        _shell(f'screencapture "{resolved_path}"', shell=True)
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
            _shell(f'gnome-screenshot -f "{resolved_path}"', shell=True)
        elif shutil.which("spectacle"):
            _shell(f'spectacle -b -n -o "{resolved_path}"', shell=True)
        elif shutil.which("grim"):
            _shell(f'grim "{resolved_path}"', shell=True)
        elif shutil.which("scrot"):
            _shell(f'scrot "{resolved_path}"', shell=True)
        else:
            return "Failed to take screenshot: No native screenshot tool found (gnome-screenshot/spectacle/grim/scrot)."
    return f"Screenshot saved to {resolved_path}."


def handle_screen_record(path: str, duration: int) -> str:
    system = platform.system()
    resolved_path = os.path.abspath(os.path.expanduser(path))
    log_action(
        "system",
        f"Starting screen recording for {duration} seconds to {resolved_path}...",
    )

    if system == "Darwin":
        _popen(f'screencapture -v -V {duration} "{resolved_path}"', shell=True)
        return f"Screen recording started for {duration} seconds. Saving to {resolved_path}."
    elif system == "Windows":
        import shutil

        if not shutil.which("ffmpeg"):
            return "Screen recording on Windows requires FFmpeg. Please install it (e.g. via Iris install command)."
        cmd = f'ffmpeg -f gdigrab -framerate 30 -i desktop -t {duration} "{resolved_path}"'
        _popen(cmd, shell=True, creationflags=0x08000000)
        return f"Screen recording started via FFmpeg for {duration} seconds."
    else:
        import shutil

        if not shutil.which("ffmpeg"):
            return "Screen recording on Linux requires FFmpeg. Please install it (e.g. sudo apt install ffmpeg)."
        cmd = f'ffmpeg -f x11grab -framerate 30 -video_size 1920x1080 -i :0.0 -t {duration} "{resolved_path}"'
        _popen(cmd, shell=True)
        return f"Screen recording started via FFmpeg for {duration} seconds."


def handle_media(action: str) -> str:
    system = platform.system()
    if system == "Darwin":
        for app in ("Spotify", "Music", "iTunes"):
            res = _shell(
                f"osascript -e 'application \"{app}\" is running'",
                shell=True,
                capture_output=True,
                text=True,
            )
            if "true" in res.stdout.lower():
                apple_action = action
                if action == "play_pause":
                    apple_action = "playpause"
                _shell(
                    f"osascript -e 'tell application \"{app}\" to {apple_action}'",
                    shell=True,
                )
                return f"Media command '{action}' sent to {app}."
        return f"Media command '{action}' executed."
    elif system == "Windows":
        import ctypes

        VK_MEDIA_NEXT_TRACK = 0xB0
        VK_MEDIA_PREV_TRACK = 0xB1
        VK_MEDIA_STOP = 0xB2
        VK_MEDIA_PLAY_PAUSE = 0xB3

        vk = None
        if action == "play_pause":
            vk = VK_MEDIA_PLAY_PAUSE
        elif action == "next":
            vk = VK_MEDIA_NEXT_TRACK
        elif action == "previous":
            vk = VK_MEDIA_PREV_TRACK
        elif action == "stop":
            vk = VK_MEDIA_STOP

        if vk:
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        return f"Media command '{action}' executed."
    else:
        dbus_method = "PlayPause" if action == "play_pause" else action.capitalize()
        script = f"""
for player in $(dbus-send --session --dest=org.freedesktop.DBus --type=method_call --print-reply /org/freedesktop/DBus org.freedesktop.DBus.ListNames | grep org.mpris.MediaPlayer2 | awk -F'"' '{{print $2}}'); do
    dbus-send --print-reply --session --dest=$player /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.{dbus_method} >/dev/null 2>&1
done
"""
        _shell(script, shell=True)
        return f"Media command '{action}' executed natively."


def handle_say(text: str) -> str:
    system = platform.system()
    if system == "Darwin":
        _shell(f'say "{text}"', shell=True)
    elif system == "Windows":
        _shell(
            f"powershell -Command \"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{text}')\"",
            shell=True,
        )
    else:
        _shell(f'spd-say "{text}" || espeak "{text}"', shell=True)
    return f"Said: '{text}'"


def handle_kill_process(name: str) -> str:
    system = platform.system()
    if name.isdigit():
        pid = int(name)
        os.kill(pid, 9)
        return f"Killed process PID {pid}."
    else:
                                             
        aliases = [name]
        name_lower = name.lower()
        
        alias_map = {
            "settings": ["gnome-control-center", "systemsettings", "unity-control-center"],
            "files": ["nautilus", "dolphin", "nemo", "thunar"],
            "file manager": ["nautilus", "dolphin", "nemo", "thunar"],
            "terminal": ["gnome-terminal", "gnome-terminal-server", "konsole", "xterm", "alacritty", "kitty"],
            "browser": ["google-chrome", "chrome", "firefox", "brave", "edge", "chromium"],
            "chrome": ["google-chrome"],
            "word": ["libreoffice", "soffice.bin", "soffice"],
            "excel": ["libreoffice", "soffice.bin", "soffice"],
            "powerpoint": ["libreoffice", "soffice.bin", "soffice"],
            "calculator": ["gnome-calculator", "kcalc"],
            "discord": ["Discord", "discord-bin"],
            "spotify": ["spotify", "com.spotify.Client"],
            "rhythmbox": ["rhythmbox"],
            "rythembox": ["rhythmbox"]
        }
        
        if name_lower in alias_map:
            aliases.extend(alias_map[name_lower])

        if system == "Linux":
            dynamic_alias = _resolve_linux_app_exec(name)
            if dynamic_alias and dynamic_alias not in aliases:
                aliases.append(dynamic_alias)

        if system == "Windows":
            targets = []
            for a in aliases:
                targets.extend([a, f"{a}.exe"])
                                                      
            seen = set()
            unique_targets = [x for x in targets if not (x in seen or seen.add(x))]
            
            success = False
            for t in unique_targets:
                r = _shell(f'taskkill /F /IM "{t}"', shell=True)
                if r.returncode == 0:
                    success = True
            if success:
                return f"Sent terminate signal to process '{name}'."
            else:
                return f"[ERROR] Could not find any running process matching '{name}' to terminate."
        else:
            success = False
            for target in aliases:
                r1 = _shell(f"pkill -9 -i '{target}'", shell=True)
                r2 = _shell(f"killall -9 -I '{target}'", shell=True)
                r3 = _shell(f"pkill -9 -i -f '{target}'", shell=True)
                if r1.returncode == 0 or r2.returncode == 0 or r3.returncode == 0:
                    success = True
            
            if success:
                return f"Sent terminate signal to process '{name}'."
            else:
                return f"[ERROR] Could not find any running process matching '{name}' to terminate."


def handle_set_env(key: str, value: str) -> str:
    os.environ[key] = value
    return f"Environment variable {key} set to {value}."


def handle_notification(title: str, body: str) -> str:
    system = platform.system()
    if system == "Darwin":
        cmd = f'osascript -e \'display notification "{body}" with title "{title}"\''
        _shell(cmd, shell=True)
    elif system == "Windows":
        ps = f'''
[reflection.assembly]::loadwithpartialname("System.Windows.Forms")
[reflection.assembly]::loadwithpartialname("System.Drawing")
$notify = new-object system.windows.forms.notifyicon
$notify.icon = [System.Drawing.SystemIcons]::Information
$notify.visible = $true
$notify.showballoontip(10,"{title}","{body}",[system.windows.forms.tooltipicon]::None)
'''
        _shell(["powershell", "-Command", ps], shell=True)
    else:
        cmd = f'''dbus-send --session --dest=org.freedesktop.Notifications --type=method_call /org/freedesktop/Notifications org.freedesktop.Notifications.Notify string:"Iris" uint32:0 string:"" string:"{title}" string:"{body}" array:string:"" dict:string:variant:"" int32:5000'''
        _shell(cmd, shell=True)
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
        _shell("osascript -e 'tell application \"Finder\" to empty trash'", shell=True)
    elif system == "Windows":
        _shell("powershell -Command Clear-RecycleBin -Force", shell=True)
    else:
        _shell("rm -rf ~/.local/share/Trash/files/* || gio trash --empty", shell=True)
    return "Trash emptied."


def handle_type_text(text: str) -> str:
    system = platform.system()
    if system == "Darwin":
        escaped = text.replace('"', '\\"')
        _shell(
            f'osascript -e \'tell application "System Events" to keystroke "{escaped}"\'',
            shell=True,
        )
    elif system == "Windows":
        escaped = text.replace("'", "''")
        _shell(
            f"powershell -Command \"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('{escaped}')\"",
            shell=True,
        )
    else:
        _shell(["xdotool", "type", text])
    return f"Typed text: '{text}'"


def handle_press_keys(keys: str) -> str:
    system = platform.system()
    if system == "Darwin":
        parts = keys.lower().split("+")
        key = parts[-1]
        mods = parts[:-1]
        apple_mods = []
        for m in mods:
            if m in ("cmd", "command"):
                apple_mods.append("command down")
            elif m == "shift":
                apple_mods.append("shift down")
            elif m in ("alt", "option"):
                apple_mods.append("option down")
            elif m in ("ctrl", "control"):
                apple_mods.append("control down")

        mods_str = ", ".join(apple_mods)
        if mods_str:
            cmd = f'osascript -e \'tell application "System Events" to keystroke "{key}" using {{{mods_str}}}\''
        else:
            cmd = f'osascript -e \'tell application "System Events" to keystroke "{key}"\''
        _shell(cmd, shell=True)
    elif system == "Windows":
        import re

        ps_keys = keys.lower()
        ps_keys = re.sub(r"ctrl\+", "^", ps_keys)
        ps_keys = re.sub(r"shift\+", "+", ps_keys)
        ps_keys = re.sub(r"alt\+", "%", ps_keys)
        _shell(
            f"powershell -Command \"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('{{{ps_keys}}}')\"",
            shell=True,
        )
    else:
        _shell(["xdotool", "key", keys])
    return f"Pressed keys: {keys}."


def handle_focus_app(name: str) -> str:
    system = platform.system()
    if system == "Darwin":
        cmd = f"osascript -e 'tell application \"{name}\" to activate'"
        _shell(cmd, shell=True)
    elif system == "Windows":
        _shell(
            f"powershell -Command \"(New-Object -ComObject WScript.Shell).AppActivate('{name}')\"",
            shell=True,
        )
    else:
        _shell(["wmctrl", "-a", name])
    return f"Focused app '{name}'."


def handle_fix_file(
    path: str, instructions: str, model=None, tokenizer=None, device=None
):
    if not path:
        return "Path required."
    from pathlib import Path
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
        "You are an expert software engineer. Analyze the provided file content and apply these instructions: "
        + instructions
        + "\n\n"
        "Output ONLY the raw, complete, modified file content. Do NOT include markdown blocks. "
        "Do NOT add conversational text."
    )
    user_msg = f"Current Content of {path_obj.name}:\n\n{content}"

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_msg},
    ]

    from src.iris import ModelRole, load_model, unload_model

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

    code_block_match = re.search(r"```[a-zA-Z]*\n(.*?)```", new_content, re.DOTALL)
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


def _resolve(path: str):
                                                                   
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
    import platform
    import shutil

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
    import tarfile
    import zipfile

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
    import ssl
    import urllib.request

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
        _popen(cmd, shell=True)
        return "Opened settings."
    except Exception as e:
        return f"Failed to open settings: {e}"

def handle_run_command(command: str):
    cmd_lower = command.strip().lower()
    if platform.system() == "Windows" and (
        cmd_lower.startswith("open ") or cmd_lower.startswith("start ")
    ):
        app_name = command.strip()[command.strip().find(" ") + 1 :].strip()
        log_action(
            "intercept",
            f"Redirecting shell command '{command}' to native Windows app launcher.",
        )
        from src.system_actions import open_app
        return open_app(app_name)

    log_action("terminal", f"Running: {command}")

    exec_name = extract_executable_name(command)
    is_missing = False
    if exec_name and exec_name not in SHELL_BUILTINS:
        if shutil.which(exec_name) is None:
            is_missing = True

    if is_missing:
        log_action(
            "system",
            f"Command '{exec_name}' appears to be missing. Attempting automatic installation...",
        )
        installed = install_command(exec_name)
        if not installed:
            return f"Error: Command '{exec_name}' is missing and automatic installation failed."

    try:
        result = _shell(command, shell=True, capture_output=True, text=True, timeout=30)
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        code = result.returncode

        if (
            code != 0
            and is_command_missing_error(code, stderr, exec_name)
            and not is_missing
        ):
            log_action(
                "system",
                f"Command failed with missing executable error (Exit {code}). Attempting automatic installation...",
            )
            installed = install_command(exec_name)
            if installed:
                log_action("terminal", f"Retrying: {command}")
                result = _shell(
                    command, shell=True, capture_output=True, text=True, timeout=30
                )
                stdout = result.stdout.strip()
                stderr = result.stderr.strip()
                code = result.returncode

        if code == 0:
            return f"Success (Exit 0):\n{stdout or '(No output)'}"[:1500]
        else:
            return f"Error (Exit {code}):\n{stderr or stdout or '(No error message)'}"[
                :1500
            ]
    except _subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds."
    except Exception as e:
        if exec_name and not is_missing:
            log_action(
                "system", f"Execution failed: {e}. Attempting automatic installation..."
            )
            installed = install_command(exec_name)
            if installed:
                try:
                    log_action("terminal", f"Retrying: {command}")
                    result = _shell(
                        command, shell=True, capture_output=True, text=True, timeout=30
                    )
                    stdout = result.stdout.strip()
                    stderr = result.stderr.strip()
                    code = result.returncode
                    if code == 0:
                        return f"Success (Exit 0):\n{stdout or '(No output)'}"[:1500]
                    else:
                        return f"Error (Exit {code}):\n{stderr or stdout or '(No error message)'}"[
                            :1500
                        ]
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
                _shell(["osascript", "-e", script])
                _shell(["osascript", "-e", 'tell application "Terminal" to activate'])
                return f"Opened Terminal and executed: {command}"
            else:
                _shell(["open", "-a", "Terminal"])
                return "Opened Terminal."
        elif system == "Windows":
            if command:
                _popen(["cmd", "/k", command])
            else:
                _popen(["cmd"])
            return "Opened Command Prompt."
        else:
            for term in ["gnome-terminal", "xterm", "konsole"]:
                if shutil.which(term):
                    if command:
                        _popen([term, "-e", f"bash -c '{command}; exec bash'"])
                    else:
                        _popen([term])
                    return f"Opened {term}."
            return "Could not find a terminal emulator."
    except Exception as e:
        return f"Failed to open terminal: {e}"

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
            CREATE_NO_WINDOW = 0x08000000
            _shell(
                ["powershell", "-NoProfile", "-Command", ps_script],
                creationflags=CREATE_NO_WINDOW,
            )
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

def handle_brightness(action: str):
    system = platform.system()
    if system == "Darwin":
        try:
            import ctypes

            cg = ctypes.CDLL(
                "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
            )
            display_id = cg.CGMainDisplayID()

            ds = ctypes.CDLL(
                "/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices"
            )
            ds.DisplayServicesGetBrightness.argtypes = [
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_float),
            ]
            ds.DisplayServicesGetBrightness.restype = ctypes.c_int

            val = ctypes.c_float()
            err = ds.DisplayServicesGetBrightness(display_id, ctypes.byref(val))
            if err == 0:
                current = val.value
                step = 0.0625
                new_val = current + step if action == "up" else current - step
                new_val = max(0.0, min(1.0, new_val))

                ds.DisplayServicesSetBrightness.argtypes = [
                    ctypes.c_int,
                    ctypes.c_float,
                ]
                ds.DisplayServicesSetBrightness.restype = None
                ds.DisplayServicesSetBrightness(display_id, new_val)
                log_action(
                    "system",
                    f"Adjusted brightness: {action} (from {current:.2f} to {new_val:.2f})",
                )
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
            CREATE_NO_WINDOW = 0x08000000
            _shell(
                ["powershell", "-NoProfile", "-Command", script],
                creationflags=CREATE_NO_WINDOW,
            )
            log_action("system", f"Adjusted brightness: {action}")
            return f"Brightness adjusted {action}."
        except Exception as e:
            return f"Failed to adjust brightness: {e}"
    else:
                      
        curr = linux_get_brightness()
        if curr == -1:
            curr = 50                                          

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

            cg = ctypes.CDLL(
                "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
            )
            display_id = cg.CGMainDisplayID()

            ds = ctypes.CDLL(
                "/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices"
            )
            ds.DisplayServicesSetBrightness.argtypes = [ctypes.c_int, ctypes.c_float]
            ds.DisplayServicesSetBrightness.restype = None

            val = float(pct / 100.0)
            ds.DisplayServicesSetBrightness(display_id, val)
            log_action("system", f"Set brightness to {pct}% natively")
            return f"Brightness set to {pct}%."
        except Exception as e:
            cmd = f"brightness {pct / 100}"
            log_action("system", f"Setting brightness via CLI fallback to {pct}%")
            return handle_run_command(cmd)
    elif system == "Windows":
        cmd = f'powershell -NoProfile -Command "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {pct})"'
        try:
            CREATE_NO_WINDOW = 0x08000000
            _shell(cmd, shell=True, creationflags=CREATE_NO_WINDOW)
            log_action(
                "system", f"Setting brightness to {pct}% natively via PowerShell"
            )
            return f"Brightness set to {pct}%."
        except Exception as e:
            return f"Failed to set brightness: {e}"
    else:
                      
        if linux_set_brightness(pct):
            return f"Brightness set to {pct}%."
        else:
            return f"Failed to set brightness to {pct}%. You may need to grant write permissions to /sys/class/backlight or ensure D-Bus is running."


_SIMPLE_ACTIONS: set = {
                    
    "open_app", "close_app", "focus_app", "kill_app", "kill_process",
                       
    "window_close", "window_minimize", "window_maximize", "window_fullscreen", "switch_tab",
                    
    "volume_up", "volume_down", "volume_mute", "volume_set",
    "media_play_pause", "media_next", "media_previous", "media_stop",
                          
    "brightness_up", "brightness_down", "brightness_set",
    "dark_mode", "night_shift", "set_wallpaper",
           
    "lock_screen", "sleep_computer", "shutdown_computer", "restart_computer",
    "do_not_disturb",
               
    "clipboard_copy", "clipboard_read", "read_clipboard", "write_clipboard",
                                   
    "system_info", "check_storage", "disk_usage", "open_settings",
                     
    "create_file", "delete_file", "create_folder", "rename_file",
    "move_file", "copy_file", "open_file", "search_files",
    "read_file", "append_file", "replace_in_file", "compress_files",
    "extract_file", "download_file",
                  
    "type_text", "press_keys", "say", "take_note", "notification",
                            
    "screenshot", "screen_record",
                                       
    "wifi", "bluetooth", "vpn", "flush_dns",
                             
    "youtube_video", "youtube_channel", "spotify_song", "open_website",
                               
    "run_command", "open_terminal",
}

_COMPLEX_ACTIONS: set = {
    "gui_action",
    "browser_task", "browser_autopilot", "browser_login",
    "send_email",
    "web_search",
    "run_code",
    "parse_resume",
    "npm", "pip", "git", "docker", "brew", "apt", "winget",
    "network_speed_test",
}


from typing import List, Dict

def is_complex_control(query: str, history: List[Dict[str, str]]) -> bool:
\
\
\
\
       
    q = query.lower()
    
                                         
                                                                                                
    complex_indicators = {
                                                                
        "click", "gui", "mouse", "drag", "right-click", "double-click", "right click", "double click",
        "scroll down", "scroll up", "scroll", "move mouse", "hover",
                                                             
        "whatsapp", "telegram", "discord", "slack", "teams", "skype", "send a message", "send message",
        "text him", "text her", "message him", "message her", "chat with", "whatsapp message",
                                                              
        "browser_task", "browser_autopilot", "browser_login", "autopilot",
        "fill form", "fill out", "fill in", "web form", "checkout",
        "login to", "log in to", "sign in to", "log into", "sign into",
        "apply for", "job application", "submit application",
        "scrape", "extract text from website", "extract data from website",
                           
        "send email", "send an email", "compose email", "write email", "draft email", "email him", "email her",
                                              
        "run code", "execute code", "run script", "execute script", "python code", "run python",
        "write a python script", "bash script", "powershell script", "execute bash",
                                               
        "pip", "npm", "gem", "cargo", "docker", "brew", "apt", "winget", "pacman", "yum", "dnf",
        "install package", "install dependency",
                                                
        "set env", "environment variable", "set environment variable", "add to path", "export env",
    }
    if any(ind in q for ind in complex_indicators):
        return True
        
    return False





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
        "search": "[bold yellow]Search[/bold yellow]",
    }
    prefix = icon_map.get(action_type.lower(), f"[bold cyan]{action_type}[/bold cyan]")
    if RICH_AVAILABLE:
        chevron = ">" if platform.system() == "Windows" else "❯"
        console.print(f"  [dim]{chevron}[/dim] {prefix}: {message}")
    else:
        logger.info(f"  [→ {action_type.capitalize()}] {message}")





COMMAND_PACKAGE_MAP = {
    "ffmpeg": {"Windows": "Gyan.FFmpeg", "Darwin": "ffmpeg", "Linux": "ffmpeg"},
    "git": {"Windows": "Git.Git", "Darwin": "git", "Linux": "git"},
    "node": {"Windows": "OpenJS.NodeJS", "Darwin": "node", "Linux": "nodejs"},
    "npm": {"Windows": "OpenJS.NodeJS", "Darwin": "node", "Linux": "npm"},
    "npx": {"Windows": "OpenJS.NodeJS", "Darwin": "node", "Linux": "npm"},
    "curl": {"Windows": "cURL.cURL", "Darwin": "curl", "Linux": "curl"},
    "wget": {"Windows": "GNU.Wget", "Darwin": "wget", "Linux": "wget"},
    "jq": {"Windows": "jqlang.jq", "Darwin": "jq", "Linux": "jq"},
    "pandoc": {
        "Windows": "JohnMacFarlane.Pandoc",
        "Darwin": "pandoc",
        "Linux": "pandoc",
    },
    "graphviz": {
        "Windows": "Graphviz.Graphviz",
        "Darwin": "graphviz",
        "Linux": "graphviz",
    },
    "dot": {"Windows": "Graphviz.Graphviz", "Darwin": "graphviz", "Linux": "graphviz"},
    "nircmd": {"Windows": "NirSoft.NirCmd", "Darwin": None, "Linux": None},
    "tesseract": {
        "Windows": "UB-Mannheim.TesseractOCR",
        "Darwin": "tesseract",
        "Linux": "tesseract-ocr",
    },
    "python": {
        "Windows": "Python.Python.3.11",
        "Darwin": "python3",
        "Linux": "python3",
    },
    "python3": {
        "Windows": "Python.Python.3.11",
        "Darwin": "python3",
        "Linux": "python3",
    },
    "make": {"Windows": "Ezwinports.Make", "Darwin": "make", "Linux": "make"},
    "docker": {
        "Windows": "Docker.DockerDesktop",
        "Darwin": "docker",
        "Linux": "docker.io",
    },
}

SHELL_BUILTINS = {
             
    "dir",
    "cd",
    "echo",
    "copy",
    "del",
    "md",
    "mkdir",
    "rd",
    "rmdir",
    "type",
    "ren",
    "rename",
    "move",
    "cls",
    "ver",
    "vol",
    "path",
    "set",
    "exit",
    "pause",
    "prompt",
    "title",
    "start",
          
    "pwd",
    "local",
    "export",
    "alias",
    "unalias",
    "read",
    "unset",
    "history",
    "builtin",
    "bg",
    "fg",
    "jobs",
    "ls",
}


def extract_executable_name(command_str: str) -> str:
    import shlex

    try:
        tokens = shlex.split(command_str)
    except Exception:
        tokens = command_str.split()

    if not tokens:
        return ""

                                                                    
    start_idx = 0
    while (
        start_idx < len(tokens)
        and "=" in tokens[start_idx]
        and not tokens[start_idx].startswith("-")
    ):
        start_idx += 1

    if start_idx >= len(tokens):
        return ""

    exec_path = tokens[start_idx]
                                        
    basename = os.path.basename(exec_path)
    name, ext = os.path.splitext(basename)
    return name.lower()


def reload_system_path():
    system = platform.system()
    if system == "Windows":
        try:
            import winreg

            paths = []
                            
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ
                ) as key:
                    user_path, _ = winreg.QueryValueEx(key, "Path")
                    paths.extend(user_path.split(";"))
            except Exception:
                pass
                              
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"System\CurrentControlSet\Control\Session Manager\Environment",
                    0,
                    winreg.KEY_READ,
                ) as key:
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
            logger.warning(
                f"[Warning] Failed to reload Windows PATH from registry: {e}"
            )
    elif system == "Darwin":
                                     
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

    log_action(
        "system", f"Attempting to install '{pkg_name}' via platform package manager..."
    )

    if system == "Windows":
        if not shutil.which("winget"):
            log_action("system", "winget is not available on this system.")
            if pkg_name == "NirSoft.NirCmd":
                log_action("system", "Attempting manual download of NirCmd...")
                try:
                    import io
                    import urllib.request
                    import zipfile

                    url = "https://www.nirsoft.net/utils/nircmd.zip"
                    req = urllib.request.Request(
                        url, headers={"User-Agent": "Mozilla/5.0"}
                    )
                    with urllib.request.urlopen(req, timeout=15) as response:
                        with zipfile.ZipFile(io.BytesIO(response.read())) as z:
                            target_dir = os.path.join(
                                os.path.expanduser("~"), ".iris_bin"
                            )
                            os.makedirs(target_dir, exist_ok=True)
                            z.extract("nircmd.exe", target_dir)

                            try:
                                import winreg

                                with winreg.OpenKey(
                                    winreg.HKEY_CURRENT_USER,
                                    "Environment",
                                    0,
                                    winreg.KEY_READ | winreg.KEY_WRITE,
                                ) as key:
                                    user_path, _ = winreg.QueryValueEx(key, "Path")
                                    if target_dir not in user_path.split(";"):
                                        updated_path = (
                                            user_path.rstrip(";") + ";" + target_dir
                                        )
                                        winreg.SetValueEx(
                                            key,
                                            "Path",
                                            0,
                                            winreg.REG_EXPAND_SZ,
                                            updated_path,
                                        )
                            except Exception as e:
                                log_action(
                                    "system",
                                    f"Failed to update user PATH registry: {e}",
                                )

                            os.environ["PATH"] = (
                                target_dir + os.pathsep + os.environ.get("PATH", "")
                            )
                            log_action(
                                "system", "Successfully installed NirCmd manually."
                            )
                            return True
                except Exception as e:
                    log_action("system", f"Manual download of NirCmd failed: {e}")
            return False
                                    
        cmd = f"winget install --silent --accept-source-agreements --accept-package-agreements {pkg_name}"
        log_action("system", f"Running: {cmd}")
        res = _shell(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            log_action("system", f"Successfully installed '{pkg_name}' via winget.")
            reload_system_path()
            return True
        else:
            log_action(
                "system",
                f"winget installation failed (Exit {res.returncode}): {res.stderr or res.stdout}",
            )
            return False

    elif system == "Darwin":
        if not shutil.which("brew"):
            log_action("system", "brew (Homebrew) is not available on this system.")
            return False
        cmd = f"brew install {pkg_name}"
        log_action("system", f"Running: {cmd}")
        res = _shell(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            log_action("system", f"Successfully installed '{pkg_name}' via brew.")
            reload_system_path()
            return True
        else:
            log_action(
                "system",
                f"brew installation failed (Exit {res.returncode}): {res.stderr or res.stdout}",
            )
            return False

    elif system == "Linux":
                                
        if shutil.which("apt-get"):
            cmd = f"sudo apt-get update && sudo apt-get install -y {pkg_name}"
        elif shutil.which("dnf"):
            cmd = f"sudo dnf install -y {pkg_name}"
        elif shutil.which("yum"):
            cmd = f"sudo yum install -y {pkg_name}"
        elif shutil.which("pacman"):
            cmd = f"sudo pacman -S --noconfirm {pkg_name}"
        else:
            log_action(
                "system",
                "No supported Linux package manager found (apt, dnf, yum, pacman).",
            )
            return False

        log_action("system", f"Running: {cmd}")
        res = _shell(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            log_action("system", f"Successfully installed '{pkg_name}'.")
            return True
        else:
            log_action(
                "system",
                f"Linux installation failed (Exit {res.returncode}): {res.stderr or res.stdout}",
            )
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
    if (
        exec_name
        and "no such file or directory" in lower_err
        and exec_name in lower_err
    ):
        return True
    return False









def linux_get_brightness() -> int:
    import os
    import re
    import shutil

                          
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

                                                               
    if shutil.which("gdbus"):
        res = _shell(
            "gdbus call --session --dest org.gnome.Mutter.DisplayConfig --object-path /org/gnome/Mutter/DisplayConfig --method org.freedesktop.DBus.Properties.Get org.gnome.Mutter.DisplayConfig Backlight",
            shell=True,
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            max_match = re.search(r"'max':\s*<(\d+)>", res.stdout)
            val_match = re.search(r"'value':\s*<(\d+)>", res.stdout)
            if max_match and val_match:
                mx = int(max_match.group(1))
                curr = int(val_match.group(1))
                if mx > 0:
                    return int((curr / mx) * 100)

                                  
    if shutil.which("qdbus"):
        res = _shell(
            "qdbus org.kde.Solid.PowerManagement /org/kde/Solid/PowerManagement/Actions/BrightnessControl org.kde.Solid.PowerManagement.Actions.BrightnessControl.brightness",
            shell=True,
            capture_output=True,
            text=True,
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

    pct = max(0, min(100, pct))

                                                                       
    if shutil.which("brightnessctl"):
        res = _shell(f"brightnessctl set {pct}%", shell=True, capture_output=True)
        if res.returncode == 0:
            return True

                           
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

                                                               
    if shutil.which("gdbus"):
        res = _shell(
            "gdbus call --session --dest org.gnome.Mutter.DisplayConfig --object-path /org/gnome/Mutter/DisplayConfig --method org.freedesktop.DBus.Properties.Get org.gnome.Mutter.DisplayConfig Backlight",
            shell=True,
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            import re

            serial_match = re.search(r"uint32\s+(\d+)", res.stdout)
            connector_match = re.search(r"'connector':\s*<'([^']+)'", res.stdout)
            max_match = re.search(r"'max':\s*<(\d+)>", res.stdout)
            if serial_match and connector_match and max_match:
                serial = serial_match.group(1)
                connector = connector_match.group(1)
                mx = int(max_match.group(1))
                target = int((pct / 100.0) * mx)

                set_cmd = f'gdbus call --session --dest org.gnome.Mutter.DisplayConfig --object-path /org/gnome/Mutter/DisplayConfig --method org.gnome.Mutter.DisplayConfig.SetBacklight {serial} "{connector}" {target}'
                set_res = _shell(set_cmd, shell=True, capture_output=True)
                if set_res.returncode == 0:
                    return True

                                  
    if shutil.which("qdbus"):
        res = _shell(
            f"qdbus org.kde.Solid.PowerManagement /org/kde/Solid/PowerManagement/Actions/BrightnessControl org.kde.Solid.PowerManagement.Actions.BrightnessControl.setBrightness {pct}",
            shell=True,
            capture_output=True,
        )
        if res.returncode == 0:
            return True

                                                         
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
                res = _shell(
                    f"echo {target} | pkexec tee {br_path}",
                    shell=True,
                    capture_output=True,
                )
                if res.returncode == 0:
                    return True
            except:
                continue

    return False






