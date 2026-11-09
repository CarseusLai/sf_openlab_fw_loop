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
import mixroute
from make_variant import ROOT, make_variant

FIX_TIMEOUT_S = 300
# No hooks, no MCP, no user settings: the fixer sees only this prompt and the sketch.
FIX_SETTINGS = json.dumps({"disableAllHooks": True})


class Run:
    def __init__(self, bug_id):
        self.dir = ROOT / "runs" / f"{time.strftime('%Y%m%d-%H%M%S')}-{bug_id}"
        self.dir.mkdir(parents=True)
        self.status = {"bug": bug_id, "stages": [], "result": "RUNNING", "doing": "", "say": ""}
        self.save()

    def save(self):
        # Write then rename, so the status page never reads a half-written file.
        tmp = self.dir / "status.json.tmp"
        tmp.write_text(json.dumps(self.status, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.dir / "status.json")

    def doing(self, text):
        self.status["doing"] = text
        self.save()

    def say(self, text):
        self.status["say"] = text
        self.save()

    def stage(self, name, ok, seconds, **info):
        self.status["stages"].append({"name": name, "ok": ok, "s": round(seconds, 1), **info})
        print(f"[{name}] {'ok' if ok else 'FAILED'} {seconds:.1f}s {info}", flush=True)
        self.save()

    def finish(self, result, why=""):
        self.status["result"], self.status["why"] = result, why
        self.status["doing"] = self.status["say"] = ""
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


def judge(run, chk, sketch, name):
    t = time.monotonic()
    run.doing("燒錄到板子，然後由板子判定")
    try:
        verdict, why = check.run(chk, str(sketch), on_say=run.say)
    except check.FlashError as e:
        verdict, why = check.FAIL, f"燒錄失敗：{e}"
    run.stage(name, verdict == check.PASS, time.monotonic() - t, verdict=verdict, why=why)
    return verdict, why


def mixroute_ladder(run, sketch, ticket, chk, ladder):
    """Try each model in turn on the planted bug; the board's verdict decides whether to go up a step."""
    buggy = (sketch / "app.cpp").read_text(encoding="utf-8")
    feedback, verdict, why = "", check.FAIL, ""
    for i, model in enumerate(ladder, 1):
        t = time.monotonic()
        run.doing(f"AI 修 bug 中（{'MixRoute Smart Routing' if model == mixroute.AUTO else model}）")
        try:
            code, summary, reported, usage = mixroute.fix(model, ticket, buggy, feedback)
        except mixroute.MixRouteError as e:
            run.stage(f"fix{i}", False, time.monotonic() - t, model=model, summary=str(e))
            continue
        diff = "".join(difflib.unified_diff(buggy.splitlines(True), (code or "").splitlines(True),
                                            "a/app.cpp", "b/app.cpp"))
        (run.dir / f"fix{i}.diff").write_text(diff, encoding="utf-8")
        run.stage(f"fix{i}", bool(code and diff), time.monotonic() - t, model=model, answered_by=reported,
                  tokens=usage.get("total_tokens"), summary=summary, diff=diff[:4000])
        if not (code and diff):
            feedback = "Your previous answer did not contain a changed app.cpp."
            continue
        (sketch / "app.cpp").write_text(code, encoding="utf-8")
        verdict, why = judge(run, chk, sketch, f"check{i}")
        if verdict != check.FAIL:
            return verdict, why          # PASS, or RETRY: nobody moved the board, so no verdict on the fix
        # Every retry starts from the buggy code and hears what the last attempt changed and what the board said.
        feedback = f"A previous attempt ({reported}) changed:\n{diff}\nOn the board it failed: {why}"
    return verdict, why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bug")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--fixer", choices=("claude-code", "mixroute"), default="mixroute")
    ap.add_argument("--ladder", default=f"{mixroute.AUTO},claude-sonnet-5-5",
                    help="MixRoute models to try in order; 'auto' is Smart Routing")
    args = ap.parse_args()
    bug_dir = ROOT / "bugs" / args.bug
    run = Run(args.bug)

    t = time.monotonic()
    # Outside the repo: the repo's CLAUDE.md links to the owner's whole agent rule set.
    sketch = make_variant(args.bug, tempfile.mkdtemp(prefix="openlab-fix-"))
    before = (sketch / "app.cpp").read_text(encoding="utf-8")
    run.stage("prepare", True, time.monotonic() - t, workspace=str(sketch))

    if args.fixer == "mixroute":
        with open(bug_dir / "check.json", encoding="utf-8") as f:
            chk = json.load(f)
        verdict, why = mixroute_ladder(run, sketch, (bug_dir / "ticket.md").read_text(encoding="utf-8"),
                                       chk, args.ladder.split(","))
        run.finish(verdict, why)
        print(f"{verdict}: {args.bug} {why}  ({run.dir})")
        sys.exit({check.PASS: 0, check.FAIL: 1, check.RETRY: 2}[verdict])

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

    with open(bug_dir / "check.json", encoding="utf-8") as f:
        chk = json.load(f)
    verdict, why = judge(run, chk, sketch, "check")
    run.finish(verdict, why)
    print(f"{verdict}: {args.bug} {why}  ({run.dir})")
    sys.exit({check.PASS: 0, check.FAIL: 1, check.RETRY: 2}[verdict])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:   # keep the status page from showing RUNNING forever after a crash
        import traceback
        traceback.print_exc()
        latest = max((ROOT / "runs").glob("*/status.json"), key=lambda p: p.stat().st_mtime, default=None)
        if latest:
            st = json.loads(latest.read_text(encoding="utf-8"))
            if st.get("result") == "RUNNING":
                st.update(result="ERROR", why=f"{type(e).__name__}: {e}", doing="", say="")
                latest.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        sys.exit(3)
