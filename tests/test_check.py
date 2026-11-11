import contextlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "loop"))
import check  # noqa: E402

BLINK = {"trigger": "SHAKE", "window_s": 1.2, "expect": {"count": {"LED,ON": 3}}}


class FakeBoard:
    """Serial port and clock in one: each readline jumps the clock to the next scripted line's time."""

    def __init__(self, lines):
        self.lines, self.t = list(lines), 0.0

    def now(self):
        return self.t

    def readline(self):
        if not self.lines:
            self.t += 0.5
            return b""
        self.t, line = self.lines.pop(0)
        return (line + "\r\n").encode()


def blinks(t):
    return [(t + 0.15 * i, f"EVT,0,LED,{'ON' if i % 2 == 0 else 'OFF'}") for i in range(6)]


def run_b2(monkeypatch, gentle_blinks):
    lines = [(0.1, "READY,base"), (3.0, "EVT,0,SHAKE")] + blinks(3.0)
    lines += [(5.0, "EVT,0,MOTION,4.80")]                                        # step 1's shake, reported late
    lines += [(10.0, "EVT,0,SHAKE")] + blinks(10.0) + [(10.9, "EVT,0,MOTION,4.40")]   # too hard
    lines += ([(15.0, "EVT,0,SHAKE")] + blinks(15.0) if gentle_blinks else []) + [(15.8, "EVT,0,MOTION,3.10")]
    board = FakeBoard(lines)
    monkeypatch.setenv("CHECK_SAY", "0")
    monkeypatch.setattr(check.time, "monotonic", board.now)
    monkeypatch.setattr(check, "flash", lambda sketch: ("COM0", None, 0, 0))
    monkeypatch.setattr(check, "open_board", lambda port: contextlib.nullcontext(board))
    said, seen = [], []
    chk = json.loads((ROOT / "bugs" / "b2" / "check.json").read_text(encoding="utf-8"))
    return check.run(chk, "unused", on_say=said.append, on_event=seen.append), said, seen


def test_b2_passes_when_a_gentle_shake_blinks_after_a_too_hard_one_is_sent_back(monkeypatch):
    (verdict, why), said, seen = run_b2(monkeypatch, gentle_blinks=True)
    assert (verdict, why) == (check.PASS, "")
    advice = [s for s in said if s.startswith("這次")]
    assert advice == ["這次 4.4 g，太用力了，請輕一點再搖一下"]   # the late 4.8 g from step 1 is not advice
    assert seen[:2] == ["SHAKE", "LED,ON"] and "MOTION,3.10" in seen


def test_b2_fails_when_only_a_hard_shake_blinks(monkeypatch):
    (verdict, why), _, _ = run_b2(monkeypatch, gentle_blinks=False)
    assert verdict == check.FAIL
    assert why == "第 2 步（搖到 3.1 g）：LED,ON 預期 3 次，實際 0 次"


def test_parse_keeps_the_event_name_and_drops_other_lines():
    assert check.parse("EVT,1234,SHAKE\r\n") == "SHAKE"
    assert check.parse("EVT,1234,LED,ON") == "LED,ON"
    assert check.parse("READY,base") is None
    assert check.parse("") is None


def test_three_blinks_inside_the_window_pass():
    events = [(10.0, "SHAKE")] + [(10.0 + 0.3 * i, k) for i in range(3) for k in ("LED,ON",)]
    assert check.judge(BLINK, events, 10.0, "OFF") == ""


def test_two_blinks_fail_with_the_counts():
    events = [(10.0, "SHAKE"), (10.0, "LED,ON"), (10.3, "LED,ON")]
    assert check.judge(BLINK, events, 10.0, "OFF") == "LED,ON 預期 3 次，實際 2 次"


def test_blinks_from_an_earlier_shake_do_not_count():
    events = [(5.0, "LED,ON"), (5.3, "LED,ON"), (10.0, "SHAKE"), (10.0, "LED,ON"), (10.3, "LED,ON")]
    assert check.judge(BLINK, events, 10.0, "OFF") == "LED,ON 預期 3 次，實際 2 次"


def test_no_trigger_after_the_board_moved_is_the_firmwares_fault():
    step = {"trigger": "SHAKE", "timeout_s": 20}
    events = [(4.0, "MOTION,9.90"), (12.0, "MOTION,3.82"), (13.0, "MOTION,2.10")]
    verdict, why = check.no_trigger(step, events, 10.0)
    assert verdict == check.FAIL
    assert why == "板子有被動到（最大 3.8 g），但韌體沒有回報 SHAKE"   # the 9.9 g before the step does not count


def test_no_trigger_without_any_motion_asks_to_do_it_again():
    step = {"trigger": "SHAKE", "timeout_s": 20}
    verdict, why = check.no_trigger(step, [(4.0, "MOTION,3.00"), (11.0, "LED,ON")], 10.0)
    assert verdict == check.RETRY
    assert why == "20 秒內板子都沒有被動到，請重做"


def test_a_shake_outside_the_band_gets_advice_and_one_inside_does_not():
    step = {"peak": [2.6, 3.8]}
    assert check.peak_off(step, 2.1) == "太輕了，請稍微用力一點再搖一下"
    assert check.peak_off(step, 4.4) == "太用力了，請輕一點再搖一下"
    assert check.peak_off(step, 2.6) == "" and check.peak_off(step, 3.8) == ""
    assert check.peak_off(step, 2.56) == ""   # heard as "2.6 g", so judged as 2.6


def test_blinks_before_a_motion_report_count_when_the_window_opens_earlier():
    # MOTION arrives after the shake ends, so the blinks it caused come before it.
    step = {"trigger": "MOTION", "window_s": 1.2, "expect": {"count": {"LED,ON": 3}}}
    events = [(9.0, "LED,ON"), (20.1, "SHAKE"), (20.1, "LED,ON"), (20.4, "LED,ON"), (20.7, "LED,ON"),
              (20.8, "MOTION,3.10")]
    assert check.judge(step, events, 20.8, "OFF") == "LED,ON 預期 3 次，實際 0 次"
    assert check.judge(step, events, 20.8, "OFF", start=20.0) == ""   # the 9.0 blink is before the attempt


def test_the_led_state_after_the_window_is_checked():
    step = {"trigger": "SHAKE", "window_s": 1.5, "expect": {"led": "ON"}}
    assert check.judge(step, [(1.0, "SHAKE")], 1.0, "ON") == ""
    assert check.judge(step, [(1.0, "SHAKE")], 1.0, "OFF") == "燈預期 ON，實際 OFF"
