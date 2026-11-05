"""Flash a sketch, walk a person through bugs/<bug>/check.json, and judge the board's events.

Usage: python loop/check.py bugs/b1/check.json firmware/base      (PASS expected)
       python loop/check.py bugs/b1/check.json work/b1/base       (FAIL expected)
Set CHECK_SAY=0 to print the prompts without speaking them.
"""
import base64
import json
import os
import subprocess
import sys
import time

from flash_check import FlashError, flash, open_board

VOICE = "Microsoft Hanhan Desktop"


def say(text):
    print(f">>> {text}", flush=True)
    if os.environ.get("CHECK_SAY") == "0":
        return
    quoted = text.replace("'", "''")
    script = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"try {{ $s.SelectVoice('{VOICE}') }} catch {{}}; $s.Speak('{quoted}')")
    # -EncodedCommand keeps the Chinese text out of the console code page.
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", encoded], capture_output=True)


def parse(line):
    """'EVT,1234,LED,ON' -> 'LED,ON'; anything that is not an event -> None."""
    parts = line.strip().split(",")
    if len(parts) < 3 or parts[0] != "EVT":
        return None
    return ",".join(parts[2:])


def judge(step, events, trigger_at, led):
    """Return "" when the step passed, else why not.

    events: (host time, key) seen so far; trigger_at: host time of the trigger event;
    led: the LED state after the window ("ON"/"OFF").
    """
    expect = step.get("expect", {})
    end = trigger_at + step.get("window_s", 1.0)
    window = [k for t, k in events if trigger_at <= t <= end]
    for key, want in expect.get("count", {}).items():
        got = window.count(key)
        if got != want:
            return f"{key} 預期 {want} 次，實際 {got} 次"
    if "led" in expect and led != expect["led"]:
        return f"燈預期 {expect['led']}，實際 {led}"
    return ""


def run(check, sketch, timeout=10):
    app, _, _, _ = flash(sketch)
    events, led = [], "OFF"
    with open_board(app) as ser:
        def read_until(deadline, want=None):
            nonlocal led
            while time.monotonic() < deadline:
                key = parse(ser.readline().decode("utf-8", "replace"))
                if key is None:
                    continue
                now = time.monotonic()
                events.append((now, key))
                if key.startswith("LED,"):
                    led = key.split(",")[1]
                if key == want:
                    return now
            return None

        # READY comes right after the port opens; past this point nothing the board sends is lost.
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if ser.readline().decode("utf-8", "replace").startswith("READY"):
                break
        else:
            return False, "燒錄後沒收到 READY"

        for i, step in enumerate(check["steps"], 1):
            say(step["say"])
            trigger_at = read_until(time.monotonic() + step.get("timeout_s", 20), step["trigger"])
            if trigger_at is None:
                return False, f"第 {i} 步：等了 {step.get('timeout_s', 20)} 秒沒偵測到 {step['trigger']}"
            read_until(trigger_at + step.get("window_s", 1.0))
            why = judge(step, events, trigger_at, led)
            if why:
                return False, f"第 {i} 步：{why}"
    return True, ""


def main():
    check_path, sketch = sys.argv[1], sys.argv[2]
    with open(check_path, encoding="utf-8") as f:
        check = json.load(f)
    try:
        ok, why = run(check, sketch)
    except FlashError as e:
        ok, why = False, f"燒錄失敗：{e}"
    print(f"PASS: {check['title']}" if ok else f"FAIL: {check['title']} — {why}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
