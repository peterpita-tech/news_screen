"""本機儀表板伺服器（純標準函式庫）。執行：python app.py  → http://localhost:8763
參數：--demo 使用離線示範資料；--port 指定埠號；--interval 自動更新分鐘數（預設 15）。
"""
from __future__ import annotations

import argparse
import http.server
import json
import threading
import time
import traceback
from functools import partial
from pathlib import Path

from dashboard import build

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
CACHE = ROOT / "data" / "data.json"

_lock = threading.Lock()
_state = {"busy": False, "last_error": ""}


def refresh(demo: bool) -> None:
    with _lock:
        if _state["busy"]:
            return
        _state["busy"] = True
    try:
        print("[更新] 抓取新聞、行情與總經指標中…", flush=True)
        data = build.collect(demo=demo)
        build.write(CACHE, data)
        _state["last_error"] = ""
        c = data["counts"]
        print(f"[更新完成] {data['generated_at_tpe']} 標的 {c['tickers']}/{c['universe']}、新聞 {c['news']} 則、"
              f"錯誤 {data['error_count']} 筆，耗時 {data['elapsed_sec']}s", flush=True)
    except Exception as e:  # noqa: BLE001
        _state["last_error"] = str(e)
        traceback.print_exc()
    finally:
        _state["busy"] = False


class Handler(http.server.SimpleHTTPRequestHandler):
    demo = False

    def log_message(self, fmt, *args):  # 安靜模式
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/data.json", "/api/data"):
            if not CACHE.exists():
                return self._json({"loading": True, "busy": _state["busy"], "error": _state["last_error"]}, 503)
            body = CACHE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/status":
            return self._json({"busy": _state["busy"], "error": _state["last_error"], "local": True})
        return super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] == "/api/refresh":
            threading.Thread(target=refresh, args=(self.demo,), daemon=True).start()
            return self._json({"started": True})
        self.send_error(404)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8763)
    ap.add_argument("--demo", action="store_true", help="使用離線示範資料")
    ap.add_argument("--interval", type=int, default=15, help="自動更新間隔（分鐘）")
    args = ap.parse_args()

    def loop():
        while True:
            refresh(args.demo)
            time.sleep(max(args.interval, 3) * 60)

    threading.Thread(target=loop, daemon=True).start()
    Handler.demo = args.demo
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory=str(WEB)))
    print(f"儀表板：http://localhost:{args.port}  （Ctrl+C 或關閉視窗即停止）", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
