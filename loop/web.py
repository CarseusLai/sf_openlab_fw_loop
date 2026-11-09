"""Local status page: shows the latest run and starts new ones. Standard library only.

Usage: python loop/web.py      -> open http://127.0.0.1:8765
Works offline; only the AI calls inside a run need the network.
"""
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
PAGE = Path(__file__).resolve().parent / "web" / "index.html"
PORT = 8765

_lock = threading.Lock()
_proc = None   # the one run.py allowed at a time


def bugs():
    out = []
    for d in sorted((ROOT / "bugs").iterdir()):
        try:
            title = json.loads((d / "check.json").read_text(encoding="utf-8"))["title"]
            ticket = (d / "ticket.md").read_text(encoding="utf-8").strip()
        except (OSError, ValueError, KeyError):
            continue
        out.append({"id": d.name, "title": title, "ticket": ticket})
    return out


def latest_runs(n=8):
    if not RUNS.is_dir():
        return []
    out = []
    for d in sorted((p for p in RUNS.iterdir() if p.is_dir()), reverse=True)[:n]:
        try:
            out.append({"id": d.name, **json.loads((d / "status.json").read_text(encoding="utf-8"))})
        except (OSError, ValueError):
            continue
    return out


def running():
    return _proc is not None and _proc.poll() is None


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, kind="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/status":
            self._send(200, {"running": running(), "bugs": bugs(), "runs": latest_runs()})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        global _proc
        if self.path != "/api/run":
            return self._send(404, {"error": "not found"})
        try:
            bug = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")["bug"]
        except (ValueError, KeyError):
            return self._send(400, {"error": "need {\"bug\": \"b1\"}"})
        if bug not in {b["id"] for b in bugs()}:
            return self._send(400, {"error": f"unknown bug {bug}"})
        with _lock:
            if running():
                return self._send(409, {"error": "a run is already going"})
            RUNS.mkdir(exist_ok=True)
            log = open(RUNS / "web-runs.log", "ab")   # every run's output, so a crash leaves a trace
            log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} {bug}\n".encode())
            log.flush()
            _proc = subprocess.Popen([sys.executable, str(ROOT / "loop" / "run.py"), bug], cwd=ROOT,
                                     stdout=log, stderr=subprocess.STDOUT,
                                     env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        self._send(202, {"started": bug})

    def log_message(self, *args):
        pass   # the page polls every second; keep the console quiet


def preflight():
    """Problems that would make every run fail; checked before serving the page."""
    import shutil
    from flash_check import CLI
    problems = []
    if not (os.path.isfile(CLI) or shutil.which(CLI)):
        problems.append(f"找不到 arduino-cli（{CLI}）：把 ARDUINO_CLI 設成 arduino-cli.exe 的完整路徑再啟動")
    return problems


if __name__ == "__main__":
    bad = preflight()
    if bad:
        sys.exit("無法啟動：\n- " + "\n- ".join(bad))
    print(f"http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
