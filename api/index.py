"""Vercel serverless entrypoint; reports are generated in memory."""
from __future__ import annotations
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from tripo_daily.web import PAGE
from tripo_daily.cli import collect, sources_config, DEFAULT_SOURCES
from tripo_daily.core import CN, classify, dedupe, in_window, render_report, window_for, html_report

_latest_html = ""
_latest_day = None

def make_report(day=None):
    global _latest_html, _latest_day
    day = day or datetime.now(CN).date().isoformat()
    start, end = window_for(day)
    raw, failures, ok = collect(sources_config(DEFAULT_SOURCES))
    candidates = [classify(i) for i in raw]
    chosen = dedupe([i for i in candidates if in_window(i, start, end) and i.relevance > 0])[:30]
    pending = [i for i in candidates if i.published is None or (not in_window(i, start, end) and i.relevance > 0)]
    md = render_report(day, start, end, chosen, {"ok": ok, "failed": len(failures), "candidates": len(candidates)}, failures, pending)
    _latest_html, _latest_day = html_report(md), day
    return _latest_html, failures, len(candidates), len(chosen)

class handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def send_body(self, body, content_type="text/html; charset=utf-8", code=200):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        global _latest_html
        path = self.path.split("?", 1)[0]
        if path == "/": return self.send_body(PAGE)
        if path == "/api/status":
            if not _latest_html:
                try: make_report()
                except Exception as e: return self.send_body(json.dumps({"url":None,"message":f"采集失败：{type(e).__name__}"}, ensure_ascii=False), "application/json; charset=utf-8", 502)
            return self.send_body(json.dumps({"url":"/api/report","message":f"最新日报：{_latest_day}"}, ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/api/report": return self.send_body(_latest_html or "暂无日报")
        self.send_error(404)
    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/refresh": return self.send_error(404)
        try:
            _, failures, candidates, chosen = make_report()
            msg = "刷新完成" if not failures else "刷新完成，但部分来源失败；请查看报告顶部状态"
            return self.send_body(json.dumps({"ok": not failures, "message": msg, "candidates": candidates, "chosen": chosen}, ensure_ascii=False), "application/json; charset=utf-8")
        except Exception as e:
            return self.send_body(json.dumps({"ok":False,"message":f"刷新失败：{type(e).__name__}"}, ensure_ascii=False), "application/json; charset=utf-8", 500)
