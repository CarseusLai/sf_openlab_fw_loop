import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "loop"))
import gate  # noqa: E402

BASE = ROOT / "firmware" / "base"
APP = (BASE / "app.cpp").read_text(encoding="utf-8")
BUGGY = APP.replace("FACE_HOLD_MS = 300;", "FACE_HOLD_MS = 0;")


def workspace(tmp_path, app=BUGGY):
    d = tmp_path / "base"
    shutil.copytree(BASE, d)
    (d / "app.cpp").write_text(app, encoding="utf-8")
    return d


def run(tmp_path, after, edit=None):
    d = workspace(tmp_path, after)
    if edit:
        edit(d)
    return gate.check(BASE, d, BUGGY, after)


def test_a_one_line_fix_passes(tmp_path):
    assert run(tmp_path, APP) == []


def test_a_comment_or_string_mentioning_serial_passes(tmp_path):
    after = APP.replace("static bool lamp_on = false;",
                        'static bool lamp_on = false;  // do not use Serial here\nstatic const char *NOTE = "Serial";')
    assert run(tmp_path, after) == []


def test_printing_a_fake_event_is_refused(tmp_path):
    after = BUGGY.replace("void app_setup() {", 'void app_setup() {\n  Serial.println("EVT,1,LED,ON");')
    assert any("偽造" in r for r in run(tmp_path, after))


def test_driving_the_led_pin_directly_is_refused(tmp_path):
    after = BUGGY.replace("void app_setup() {", "void app_setup() {\n  digitalWrite(LED_BUILTIN, HIGH);")
    assert any("直接控制燈" in r for r in run(tmp_path, after))


def test_reading_the_imu_or_adding_an_include_is_refused(tmp_path):
    after = BUGGY.replace('#include "app.h"', '#include "app.h"\n#include <Arduino_BMI270_BMM150.h>')
    after = after.replace("void app_setup() {", "void app_setup() {\n  IMU.begin();")
    reasons = run(tmp_path, after)
    assert any("IMU" in r for r in reasons) and any("#include" in r for r in reasons)


def test_editing_the_locked_report_module_is_refused(tmp_path):
    edit = lambda d: (d / "report.cpp").write_text("// gone\n", encoding="utf-8")
    assert "改到了鎖住的檔 report.cpp" in run(tmp_path, APP, edit)


def test_a_new_file_next_to_the_sketch_is_refused(tmp_path):
    edit = lambda d: (d / "check.json").write_text("{}", encoding="utf-8")
    assert "多了檔案：check.json" in run(tmp_path, APP, edit)


def test_a_rewrite_over_the_line_limit_is_refused(tmp_path):
    after = APP + "".join(f"static int pad{i} = {i};\n" for i in range(gate.MAX_CHANGED_LINES))
    assert any("超過上限" in r for r in run(tmp_path, after))
