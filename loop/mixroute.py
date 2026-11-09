"""Minimal MixRoute client (OpenAI-compatible), standard library only.

Usage: python loop/mixroute.py models      -> lists the model IDs this key may use
The key is read from MIXROUTE_API_KEY, or from the repo's .env file; it is never printed.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://api.mixroute.ai/v1"
ROOT = Path(__file__).resolve().parent.parent


class MixRouteError(Exception):
    pass


AUTO = "auto"   # Smart Routing: the route's key picks the tier per request


def api_key(var="MIXROUTE_API_KEY"):
    key = os.environ.get(var, "").strip()
    if not key:
        env = ROOT / ".env"
        if env.is_file():
            for line in env.read_text(encoding="utf-8-sig").splitlines():
                name, _, value = line.partition("=")
                if name.strip() == var:
                    key = value.strip().strip('"').strip("'")
    if not key:
        raise MixRouteError(f"缺少 {var}（.env 裡沒有，或等號後面是空的）")
    return key


def call(path, body=None, timeout=180, var="MIXROUTE_API_KEY"):
    req = urllib.request.Request(BASE + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {api_key(var)}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise MixRouteError(f"HTTP {e.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise MixRouteError(f"沒有回應：{e}") from None


def models():
    return sorted(m["id"] for m in call("/models").get("data", []))


def chat(model, messages, **extra):
    """Return (text, model reported by the response, usage dict)."""
    var = "MIXROUTE_ROUTE_KEY" if model == AUTO else "MIXROUTE_API_KEY"
    r = call("/chat/completions", {"model": model, "messages": messages, **extra}, var=var)
    return r["choices"][0]["message"]["content"], r.get("model"), r.get("usage", {})


FIX_RULES = """You are fixing the firmware of an Arduino Nano 33 BLE Sense Rev2.

A user reported this problem (in Chinese):

{ticket}

Here is app.cpp, the only file you may change. report.h/report.cpp drive the LED and report what
the board does; base.ino reads the IMU and calls app_loop(fresh, x, y, z, now) with values in g.
You cannot compile or run anything; after you answer, the board is flashed and a person tests it.

```cpp
{app}
```
{feedback}
Reply with the complete corrected app.cpp in one ```cpp block, making the smallest change that
fixes the problem, then one sentence in Traditional Chinese saying what was wrong and what you changed."""

FEEDBACK = """
Your previous fix was flashed and tested on the board, and it did not pass:
{why}
"""


def fix(model, ticket, app, why=""):
    """Ask one model for a fixed app.cpp. Return (new app.cpp or None, summary, model, usage)."""
    prompt = FIX_RULES.format(ticket=ticket.strip(), app=app.rstrip(),
                              feedback=FEEDBACK.format(why=why) if why else "")
    text, reported, usage = chat(model, [{"role": "user", "content": prompt}])
    start = text.find("```cpp")
    end = text.find("```", start + 6) if start >= 0 else -1
    if start < 0 or end < 0:
        return None, text.strip()[:300], reported, usage
    code = text[start + 6:end].strip("\n") + "\n"
    return code, text[end + 3:].strip()[:300], reported, usage


def env_names():
    """Names in the repo's .env and whether each has a value; values are never returned."""
    env = ROOT / ".env"
    if not env.is_file():
        return None
    out = []
    for line in env.read_text(encoding="utf-8-sig").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            name, eq, value = line.partition("=")
            out.append((repr(name), bool(eq), bool(value.strip())))
    return out


if __name__ == "__main__":
    if sys.argv[1:] == ["names"]:
        names = env_names()
        if names is None:
            sys.exit("沒有找到 .env（可能存成了 .env.txt）")
        env = ROOT / ".env"
        raw = env.read_bytes()
        import time as _t
        print(f"修改時間 {_t.strftime('%m-%d %H:%M:%S', _t.localtime(env.stat().st_mtime))}，"
              f"{len(raw)} bytes，{raw.count(b'\\n')} 個換行，"
              f"{'UTF-16' if raw[:2] in (b'\\xff\\xfe', b'\\xfe\\xff') else 'UTF-8／ANSI'}，"
              f"以 # 開頭的行 {sum(1 for l in raw.splitlines() if l.lstrip().startswith(b'#'))} 行")
        for name, eq, has_value in names:
            print(f"{name}  {'有等號' if eq else '沒有等號'}  {'有值' if has_value else '空的'}")
    if sys.argv[1:] == ["models"]:
        try:
            ids = models()
        except MixRouteError as e:
            sys.exit(f"FAIL: {e}")
        print(f"{len(ids)} models")
        print("\n".join(ids))
