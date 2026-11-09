"""One fix run: plant a bug, let Claude Code fix it, then let the board decide.

Usage: python loop/run.py b1 [--model sonnet]
Writes runs/<time>-<bug>/status.json after every stage, plus the AI's diff and reply.
"""
import argparse
import difflib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import check
from make_variant import ROOT, make_variant

FIX_TIMEOUT_S = 300
# No hooks, no MCP, no user settings: the fixer sees only this prompt and the sketch.
FIX_SETTINGS = json.dumps({"disableAllHooks": True})


class Run:
    def __init__(self, bug_id):
        self.dir = ROOT / "runs" / f"{time.strftime('%Y%m%d-%H%M%S')}-{bug_id}"
        self.dir.mkdir(parents=True)
        self.status = {"bug": bug_id, "stages": [], "result": "RUNNING"}
        self.save()

    def save(self):
        (self.dir / "status.json").write_text(json.dumps(self.status, ensure_ascii=False, indent=2), encoding="utf-8")

    def stage(self, name, ok, seconds, **info):
        self.status["stages"].append({"name": name, "ok": ok, "s": round(seconds, 1), **info})
        print(f"[{name}] {'ok' if ok else 'FAILED'} {seconds:.1f}s {info}", flush=True)
        self.save()

    def finish(self, result, why=""):
        self.status["result"], self.status["why"] = result, why
        self.save()


def ask_fixer(sketch, ticket, model):
    prompt = (ROOT / "loop" / "fix_prompt.md").read_text(encoding="utf-8").replace("{ticket}", ticket.strip())
    claude = shutil.which("claude")   # claude.cmd on Windows; subprocess does not try PATHEXT
    if not claude:
        return {"is_error": True, "result": "claude CLI not found on PATH"}
    cmd = [claude, "-p", "--model", model, "--output-format", "json",
           "--tools", "Read,Edit,Glob,Grep", "--permission-mode", "acceptEdits",
           "--settings", FIX_SETTINGS, "--setting-sources", "project", "--strict-mcp-config"]
    r = subprocess.run(cmd, input=prompt.encode("utf-8"), capture_output=True, cwd=sketch, timeout=FIX_TIMEOUT_S)
    try:
        return json.loads(r.stdout.decode("utf-8", "replace"))
    except ValueError:
        return {"is_error": True, "result": (r.stderr or r.stdout).decode("utf-8", "replace")[-500:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bug")
    ap.add_argument("--model", default="sonnet")
    args = ap.parse_args()
    bug_dir = ROOT / "bugs" / args.bug
    run = Run(args.bug)

    t = time.monotonic()
    # Outside the repo: the repo's CLAUDE.md links to the owner's whole agent rule set.
    sketch = make_variant(args.bug, tempfile.mkdtemp(prefix="openlab-fix-"))
    before = (sketch / "app.cpp").read_text(encoding="utf-8")
    run.stage("prepare", True, time.monotonic() - t, workspace=str(sketch))

    t = time.monotonic()
    reply = ask_fixer(sketch, (bug_dir / "ticket.md").read_text(encoding="utf-8"), args.model)
    after = (sketch / "app.cpp").read_text(encoding="utf-8")
    diff = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), "a/app.cpp", "b/app.cpp"))
    (run.dir / "fix.diff").write_text(diff, encoding="utf-8")
    (run.dir / "reply.json").write_text(json.dumps(reply, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = not reply.get("is_error") and bool(diff)
    run.stage("fix", ok, time.monotonic() - t, model=args.model, cost_usd=reply.get("total_cost_usd"),
              turns=reply.get("num_turns"), summary=str(reply.get("result", ""))[:300])
    if not ok:
        run.finish("FAIL", "AI 沒有改到 app.cpp" if not diff else "AI 回報錯誤")
        sys.exit(1)

    t = time.monotonic()
    with open(bug_dir / "check.json", encoding="utf-8") as f:
        chk = json.load(f)
    try:
        verdict, why = check.run(chk, str(sketch))
    except check.FlashError as e:
        verdict, why = check.FAIL, f"燒錄失敗：{e}"
    run.stage("check", verdict == check.PASS, time.monotonic() - t, verdict=verdict, why=why)
    run.finish(verdict, why)
    print(f"{verdict}: {args.bug} {why}  ({run.dir})")
    sys.exit({check.PASS: 0, check.FAIL: 1, check.RETRY: 2}[verdict])


if __name__ == "__main__":
    main()
