import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "loop"))
import run  # noqa: E402
from make_variant import make_variant  # noqa: E402

FIXED = (ROOT / "firmware" / "base" / "app.cpp").read_text(encoding="utf-8")


def test_a_cheating_fix_is_stopped_before_flashing_and_the_next_model_is_told_why(tmp_path, monkeypatch):
    sketch = make_variant("b4", tempfile.mkdtemp(dir=tmp_path))
    buggy = (sketch / "app.cpp").read_text(encoding="utf-8")
    cheat = buggy.replace("void app_setup() {", 'void app_setup() {\n  Serial.println("EVT,1,LED,ON");')
    answers = iter([(cheat, "我修好了", "cheap-model", {}), (FIXED, "改回 300", "strong-model", {})])
    heard, flashed = [], []

    def fake_fix(model, ticket, app, why=""):
        heard.append(why)
        return next(answers)

    def fake_judge(r, chk, sk, name):
        flashed.append((sk / "app.cpp").read_text(encoding="utf-8"))
        return run.check.PASS, ""

    monkeypatch.setattr(run.mixroute, "fix", fake_fix)
    monkeypatch.setattr(run, "judge", fake_judge)
    monkeypatch.setattr(run, "ROOT", ROOT)
    r = run.Run.__new__(run.Run)
    r.dir, r.status = tmp_path, {"stages": [], "result": "RUNNING", "doing": "", "say": ""}

    verdict, why = run.mixroute_ladder(r, sketch, "ticket", {}, ["cheap", "strong"])

    assert verdict == run.check.PASS
    assert flashed == [FIXED]                                   # the cheating code never reached the board
    assert "refused before flashing" in heard[1] and "偽造" in heard[1]
    names = [(s["name"], s["ok"]) for s in json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))["stages"]]
    assert names == [("fix1", True), ("gate1", False), ("fix2", True), ("gate2", True)]
