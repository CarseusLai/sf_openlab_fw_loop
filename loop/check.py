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
import threading
import time

from flash_check import FlashError, flash, open_board

VOICE = "Microsoft Hanhan Desktop"
PASS, FAIL, RETRY = "PASS", "FAIL", "RETRY"
# MOTION is reported 300 ms after the board goes still, so the previous step's shake can land
# early in the next step; nobody can hear a prompt and finish a shake this fast.
LEFTOVER_S = 2.5


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


def judge(step, events, trigger_at, led, start=None):
    """Return "" when the step passed, else why not.

    events: (host time, key) seen so far; trigger_at: host time of the trigger event;
    led: the LED state after the window ("ON"/"OFF"); start: where the window opens when
    the effect comes before the trigger (MOTION is reported only after the shake ends).
    """
    expect = step.get("expect", {})
    end = trigger_at + step.get("window_s", 1.0)
    window = [k for t, k in events if (trigger_at if start is None else start) <= t <= end]
    for key, want in expect.get("count", {}).items():
        got = window.count(key)
        if got != want:
            return f"{key} 預期 {want} 次，實際 {got} 次"
    if "led" in expect and led != expect["led"]:
        return f"燈預期 {expect['led']}，實際 {led}"
    return ""


def no_trigger(step, events, step_start):
    """The trigger never came. The locked MOTION witness says whether the person moved the board:
    moved -> the firmware missed it (FAIL); not moved -> nobody's fault, do it again (RETRY)."""
    peaks = [float(k.split(",")[1]) for t, k in events if t >= step_start and k.startswith("MOTION,")]
    if peaks:
        return FAIL, f"板子有被動到（最大 {max(peaks):.1f} g），但韌體沒有回報 {step['trigger']}"
    return RETRY, f"{step.get('timeout_s', 20)} 秒內板子都沒有被動到，請重做"


def peak_off(step, peak):
    """"" when the witness's peak is inside step["peak"] = [low, high], else what to tell the person.
    A band lets a check catch a threshold set too high, which a hard shake would pass."""
    low, high = step["peak"]
    peak = round(peak, 1)   # judge the number the person hears; 2.69 must not be "2.7 g, too light"
    if peak < low:
        return "太輕了，請稍微用力一點再搖一下"
    if peak > high:
        return "太用力了，請輕一點再搖一下"
    return ""


def run(check, sketch, timeout=10, on_say=None, on_event=None):
    """on_say(text) is told each instruction as it is spoken, and "" when the check ends;
    on_event(key) is told each event the board reports, as it arrives."""
    try:
        return _run(check, sketch, timeout, on_say or (lambda text: None), on_event or (lambda key: None))
    finally:
        if on_say:
            on_say("")


def _run(check, sketch, timeout, on_say, on_event):
    app, _, _, _ = flash(sketch)
    events, led = [], "OFF"
    with open_board(app) as ser:
        pending = []   # a line read after one call's deadline belongs to the next call, or its trigger is lost

        def read_until(deadline, want=None):
            nonlocal led
            while True:
                if pending:
                    now, key = pending.pop()
                else:
                    if time.monotonic() >= deadline:
                        return None
                    key = parse(ser.readline().decode("utf-8", "replace"))
                    if key is None:
                        continue
                    now = time.monotonic()
                if now > deadline:
                    pending.append((now, key))
                    return None
                events.append((now, key))
                on_event(key)
                if key.startswith("LED,"):
                    led = key.split(",")[1]
                if want and (key == want or key.startswith(want + ",")):   # "MOTION" matches "MOTION,3.21"
                    return now

        def speak(text):
            # Speak in the background: a blocking say() left the port unread for ~5 s, and
            # lines sent meanwhile were stamped with the time they were read, not sent.
            on_say(text)
            threading.Thread(target=say, args=(text,), daemon=True).start()

        # READY comes right after the port opens; past this point nothing the board sends is lost.
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if ser.readline().decode("utf-8", "replace").startswith("READY"):
                break
        else:
            return FAIL, "燒錄後沒收到 READY"

        for i, step in enumerate(check["steps"], 1):
            step_start = time.monotonic()
            speak(step["say"])
            if "peak" in step:
                # Keep asking until one shake lands inside the band; the firmware is judged on that one.
                low, high = step["peak"]
                window_s = step.get("window_s", 1.0)
                attempt_start = step_start
                while True:
                    trigger_at = read_until(step_start + step.get("timeout_s", 40), step["trigger"])
                    if trigger_at is None:
                        return RETRY, f"第 {i} 步：{step.get('timeout_s', 40)} 秒內沒有一次搖在 {low}–{high} g 之間，請重做"
                    peak = float(events[-1][1].split(",")[1])
                    leftover = trigger_at - step_start < LEFTOVER_S
                    off = "" if leftover else peak_off(step, peak)
                    if not leftover and not off:
                        break
                    read_until(trigger_at + window_s)   # blinks from a shake that is not judged must not count
                    attempt_start = time.monotonic()
                    if off:
                        speak(f"這次 {peak:.1f} g，{off}")
                read_until(trigger_at + window_s)
                why = judge(step, events, trigger_at, led, start=attempt_start)
                if why:
                    return FAIL, f"第 {i} 步（搖到 {peak:.1f} g）：{why}"
                continue
            trigger_at = read_until(step_start + step.get("timeout_s", 20), step["trigger"])
            if trigger_at is None:
                verdict, why = no_trigger(step, events, step_start)
                return verdict, f"第 {i} 步：{why}"
            read_until(trigger_at + step.get("window_s", 1.0))
            why = judge(step, events, trigger_at, led)
            if why:
                return FAIL, f"第 {i} 步：{why}"
    return PASS, ""


def main():
    check_path, sketch = sys.argv[1], sys.argv[2]
    with open(check_path, encoding="utf-8") as f:
        check = json.load(f)
    try:
        verdict, why = run(check, sketch, on_event=lambda key: print(f"    板子：{key}", flush=True))
    except FlashError as e:
        verdict, why = FAIL, f"燒錄失敗：{e}"
    print(f"{verdict}: {check['title']}" + (f" — {why}" if why else ""))
    sys.exit({PASS: 0, FAIL: 1, RETRY: 2}[verdict])


if __name__ == "__main__":
    main()
