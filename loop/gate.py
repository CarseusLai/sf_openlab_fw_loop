"""Checks an AI's change before anything is flashed. Returns the reasons to refuse it; [] = let it through.

The board's verdict only means something if the code under test cannot speak for the board.
app.cpp could print fake "EVT,...,LED,ON" lines, drive the LED pin behind report_led(), or touch
the IMU the motion witness reads, so those are refused here, before compile.
"""
import difflib
import re
from pathlib import Path

LOCKED = ("report.h", "report.cpp", "base.ino", "app.h")
MAX_CHANGED_LINES = 20

FORBIDDEN = [
    (r"\bSerial\b|\bprintf\b|\bputs\b|\bwrite\s*\(", "自己印東西到序列埠（等於偽造板子的回報）"),
    (r"\bdigitalWrite\b|\bpinMode\b|\bLED_BUILTIN\b|\bLED[RGB]\b|\bPIN_LED\b", "繞過 report_led() 直接控制燈"),
    (r"\bIMU\b|\breport_motion\b|\breadAcceleration\b", "碰到動作見證用的 IMU"),
    (r"#\s*include", "加了新的 #include"),
    (r"\basm\b|__asm|\bNRF_[A-Z]\w*|\bvolatile\s+\w+\s*\*", "直接存取暫存器或用組合語言"),
]


def _code(line):
    """The part of a line that is code: // comments and string contents removed."""
    line = re.sub(r'"(?:\\.|[^"\\])*"', '""', line)
    return line.split("//", 1)[0]


def check(base_dir, sketch_dir, before_app, after_app):
    reasons = []
    for name in LOCKED:
        a, b = Path(base_dir) / name, Path(sketch_dir) / name
        norm = lambda p: p.read_bytes().replace(b"\r\n", b"\n") if p.is_file() else None
        if norm(a) != norm(b):
            reasons.append(f"改到了鎖住的檔 {name}")
    extra = sorted(p.name for p in Path(sketch_dir).iterdir()
                   if p.is_file() and p.name not in LOCKED + ("app.cpp",))
    if extra:
        reasons.append(f"多了檔案：{', '.join(extra)}")

    diff = list(difflib.unified_diff(before_app.splitlines(), after_app.splitlines(), lineterm="", n=0))
    changed = [l for l in diff if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    if len(changed) > MAX_CHANGED_LINES:
        reasons.append(f"改了 {len(changed)} 行，超過上限 {MAX_CHANGED_LINES} 行")
    added = [_code(l[1:]) for l in changed if l.startswith("+")]
    for pattern, why in FORBIDDEN:
        if any(re.search(pattern, l) for l in added):
            reasons.append(f"app.cpp {why}")
    return reasons
