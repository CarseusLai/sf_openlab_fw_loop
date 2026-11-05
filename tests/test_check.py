import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "loop"))
import check  # noqa: E402

BLINK = {"trigger": "SHAKE", "window_s": 1.2, "expect": {"count": {"LED,ON": 3}}}


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


def test_the_led_state_after_the_window_is_checked():
    step = {"trigger": "SHAKE", "window_s": 1.5, "expect": {"led": "ON"}}
    assert check.judge(step, [(1.0, "SHAKE")], 1.0, "ON") == ""
    assert check.judge(step, [(1.0, "SHAKE")], 1.0, "OFF") == "燈預期 ON，實際 OFF"
