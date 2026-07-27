"""
Mac Remote Control Client
=========================
Runs on your Mac. Polls the server for commands and streams screenshots.
Can ONLY be stopped via the Disconnect button on the dashboard.

USAGE:
  python3 mac_client.py <client-name>

EXAMPLES:
  python3 mac_client.py gaming-pc
  python3 mac_client.py laptop

SETUP:
  pip3 install pyautogui Pillow requests
  Grant Accessibility: System Settings → Privacy & Security → Accessibility → add Terminal
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

# ─── CONFIG ───────────────────────────────────────────────────────────────────

SERVER_URL = "https://remote-control-3gj9.onrender.com"
API_KEY = "key4api321"

POLL_INTERVAL = 1.0
SCREENSHOT_INTERVAL = 0.5
SCREENSHOT_QUALITY = 45

# ──────────────────────────────────────────────────────────────────────────────

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05

# Block Ctrl+C — only dashboard can disconnect
signal.signal(signal.SIGINT, lambda s, f: print("\n  [blocked] Use the Disconnect button on the dashboard to stop."))
signal.signal(signal.SIGTERM, lambda s, f: None)

running = True

def get_client_name():
    if len(sys.argv) > 1:
        return sys.argv[1]
    name = input("Enter a name for this machine (e.g. gaming-pc): ").strip()
    return name or "my-mac"

CLIENT_NAME = get_client_name()
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

def take_screenshot_b64():
    img = pyautogui.screenshot()
    img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=SCREENSHOT_QUALITY, optimize=True)
    return base64.b64encode(buf.getvalue()).decode()

def upload_screenshot():
    try:
        img_b64 = take_screenshot_b64()
        mx, my = pyautogui.position()
        sw, sh = pyautogui.size()
        requests.post(
            f"{SERVER_URL}/api/screenshot",
            json={
                "client": CLIENT_NAME,
                "image": img_b64,
                "mouse_x": mx,
                "mouse_y": my,
                "screen_w": sw,
                "screen_h": sh,
            },
            headers=HEADERS,
            timeout=8
        )
    except Exception as e:
        print(f"  [screen] {e}")

def execute_command(cmd):
    global running
    t = cmd.get("type")
    args = cmd.get("args", {})
    print(f"  ▶ {t} {args}")
    try:
        if t == "shutdown":
            print("\n  Disconnecting as requested from dashboard...")
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
        else:
            print(f"  Unknown command: {t}")
    except Exception as e:
        print(f"  Error: {e}")

def screenshot_loop():
    while running:
        upload_screenshot()
        time.sleep(SCREENSHOT_INTERVAL)

def poll_loop():
    while running:
        try:
            r = requests.get(
                f"{SERVER_URL}/api/poll",
                params={"client": CLIENT_NAME},
                headers=HEADERS,
                timeout=8
            )
            if r.status_code == 200:
                for cmd in r.json().get("commands", []):
                    execute_command(cmd)
            else:
                print(f"  Poll error: {r.status_code}")
        except requests.exceptions.ConnectionError:
            print("  Connection failed, retrying...")
        except Exception as e:
            print(f"  Poll error: {e}")
        time.sleep(POLL_INTERVAL)

def main():
    print(f"\n✅ Remote control client started")
    print(f"   Name   : {CLIENT_NAME}")
    print(f"   Server : {SERVER_URL}")
    print(f"   To stop: use Disconnect button on dashboard\n")

    t = threading.Thread(target=screenshot_loop, daemon=True)
    t.start()
    poll_loop()

if __name__ == "__main__":
    main()
