# -*- coding: utf-8 -*-
"""Cursor 额度小服务（只读）。

- 从 Cursor 的 state.vscdb 取登录 token（只复制一份，不动原库）
- 调 aiserver.v1.DashboardService/GetCurrentPeriodUsage
- 在 127.0.0.1:47821 暴露 /usage 给注入到 Cursor 界面里的小挂件
"""
import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 47821
API = "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage"
DB = os.path.expandvars(r"%APPDATA%\Cursor\User\globalStorage\state.vscdb")
CACHE_TTL = 45.0

_lock = threading.Lock()
_cache = {"data": None, "ts": 0.0}
_token = {"value": None, "ts": 0.0}


def read_token(force=False):
    with _lock:
        if not force and _token["value"] and time.time() - _token["ts"] < 600:
            return _token["value"]
    # 直接以只读方式连接 Cursor 的真实 state.vscdb（SQLite 共享读锁，
    # Cursor 运行时也能读）。不再复制整个库——该库现已 500MB+，复制易被写锁打断。
    last = None
    for _ in range(6):
        try:
            con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
            try:
                row = con.execute(
                    "SELECT value FROM ItemTable WHERE key='cursorAuth/accessToken'"
                ).fetchone()
            finally:
                con.close()
            if not row:
                raise RuntimeError("no accessToken in state.vscdb")
            tok = row[0]
            tok = tok.decode() if isinstance(tok, bytes) else tok
            with _lock:
                _token["value"] = tok
                _token["ts"] = time.time()
            return tok
        except Exception as e:
            last = e
            time.sleep(0.4)
    raise RuntimeError("read accessToken failed: %s" % last)


def fetch_usage():
    body = b"{}"
    req = urllib.request.Request(API, data=body, method="POST")
    req.add_header("Authorization", "Bearer " + read_token())
    req.add_header("Content-Type", "application/json")
    req.add_header("Connect-Protocol-Version", "1")
    req.add_header("User-Agent", "cursor-quota-widget/1.0")
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def normalize(raw):
    pu = raw.get("planUsage") or {}
    total = pu.get("totalPercentUsed")
    auto = pu.get("autoPercentUsed")
    api = pu.get("apiPercentUsed")
    if total is None:
        total = max([v for v in (auto, api) if isinstance(v, (int, float))] or [0])
    return {
        "ok": True,
        "used": round(float(total), 1),
        "autoUsed": round(float(auto), 1) if isinstance(auto, (int, float)) else None,
        "apiUsed": round(float(api), 1) if isinstance(api, (int, float)) else None,
        "resetAt": int(raw.get("billingCycleEnd") or 0),
        "startAt": int(raw.get("billingCycleStart") or 0),
        "message": raw.get("displayMessage") or "",
        "autoMessage": raw.get("autoModelSelectedDisplayMessage") or "",
        "apiMessage": raw.get("namedModelSelectedDisplayMessage") or "",
        "enabled": bool(raw.get("enabled")),
        "fetchedAt": int(time.time() * 1000),
    }


def get_usage(force=False):
    now = time.time()
    with _lock:
        if not force and _cache["data"] and now - _cache["ts"] < CACHE_TTL:
            return _cache["data"]
    raw = fetch_usage()
    data = normalize(raw)
    with _lock:
        _cache["data"] = data
        _cache["ts"] = time.time()
    return data


class Handler(BaseHTTPRequestHandler):
    server_version = "cursor-quota/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        path = self.path.split("?")[0]
        if path not in ("/usage", "/health"):
            self._send(404, {"ok": False, "error": "not found"})
            return
        if path == "/health":
            self._send(200, {"ok": True, "service": "cursor-quota"})
            return
        try:
            force = "refresh=1" in self.path
            self._send(200, get_usage(force))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                try:
                    read_token(force=True)
                except Exception:
                    pass
            self._send(200, {"ok": False, "error": "HTTP %s" % e.code})
        except Exception as e:
            self._send(200, {"ok": False, "error": str(e)[:200]})


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    srv.daemon_threads = True
    print("cursor-quota listening on http://127.0.0.1:%d" % PORT, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
