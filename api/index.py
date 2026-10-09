"""Vercel serverless entrypoint; reports are generated in memory."""
from __future__ import annotations
import json, os
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from tripo_daily.web import PAGE
from tripo_daily.cli import collect, sources_config, DEFAULT_SOURCES, select_items
from tripo_daily.core import CN, Item, parse_dt, classify, dedupe, in_window, render_report, window_for, html_report, export_xlsx, summary_text, translate_to_chinese, translate_to_english, topic_has_window_article
from tripo_daily.storage import latest_report, save_report, send_feishu

_latest_html = ""
_latest_priority_html = ""
_latest_day = None
_latest_source_status = {"configured": 0, "ok": 0, "failed": 0}
_latest_items = []

def make_report(day=None):
    global _latest_html, _latest_priority_html, _latest_day, _latest_source_status, _latest_items
    day = day or datetime.now(CN).date().isoformat()
    start, end = window_for(day)
    raw, failures, ok = collect(sources_config(DEFAULT_SOURCES))
    _latest_source_status = {"configured": ok + len(failures), "ok": ok, "failed": len(failures)}
    candidates = [classify(i) for i in raw]
    chosen = select_items(candidates, start, end)
    _latest_items = chosen
    pending = dedupe([i for i in candidates if i.published is None and i.relevance > 0])
    # Translation calls are independent. Warm their caches concurrently so a
    # report does not spend up to six seconds per item in sequence.
    def pretranslate(item):
        text = summary_text(item)
        if any("\u4e00" <= c <= "\u9fff" for c in text): translate_to_english(text)
        else: translate_to_chinese(text)
    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(pretranslate, chosen))
    status={"configured":ok+len(failures),"ok":ok,"failed":len(failures),"candidates":len(candidates),"chosen":len(chosen)}
    md = render_report(day, start, end, chosen, status, failures, pending)
    marker = "## 重点关注媒体"
    next_marker = "## 竞品动态追踪"
    before, rest = md.split(marker, 1)
    priority_body, after = rest.split(next_marker, 1)
    main_md = before + next_marker + after
    priority_md = before + marker + priority_body
    _latest_html, _latest_priority_html, _latest_day = html_report(main_md), html_report(priority_md), day
    serialized=[{"title":i.title,"url":i.url,"source":i.source,"source_type":i.source_type,"published":i.published.isoformat() if i.published else None,"summary":i.summary,"content":i.content,"competitor":i.competitor,"section":i.section,"impact":i.impact,"reason":i.reason,"action":i.action,"confidence":i.confidence,"verified":i.verified,"paywall":i.paywall,"attribution":i.attribution,"related_articles":[{**a,"published":a.get("published").isoformat() if a.get("published") else None} for a in i.related_articles]} for i in chosen]
    save_report(day,md,_latest_html,status,serialized)
    return _latest_html, failures, len(candidates), len(chosen)

class handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def send_body(self, body, content_type="text/html; charset=utf-8", code=200):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", content_type); self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        global _latest_html
        path = self.path.split("?", 1)[0]
        if path in ("/", "/priority"): return self.send_body(PAGE)
        if path == "/api/status":
            if not _latest_html:
                try:
                    saved=latest_report()
                    if saved:
                        globals()["_latest_day"]=saved["report_date"]; globals()["_latest_source_status"]=saved.get("status",{})
                        restored=[]
                        for row in saved.get("items",[]):
                            data=dict(row); data["published"]=parse_dt(data.get("published")); data["related_articles"]=[{**a,"published":parse_dt(a.get("published"))} for a in data.get("related_articles",[])]
                            restored.append(Item(**{k:v for k,v in data.items() if k in Item.__dataclass_fields__}))
                        globals()["_latest_items"]=restored
                        start,end=window_for(saved["report_date"]); status=saved.get("status",{}); full_md=render_report(saved["report_date"],start,end,restored,status)
                        before,rest=full_md.split("## 重点关注媒体",1); priority_body,after=rest.split("## 竞品动态追踪",1)
                        globals()["_latest_html"]=html_report(before+"## 竞品动态追踪"+after); globals()["_latest_priority_html"]=html_report(before+"## 重点关注媒体"+priority_body)
                except Exception: saved=None
                if saved: return self.send_body(json.dumps({"url":"/api/report","message":f"最新日报：{_latest_day}","sources":_latest_source_status},ensure_ascii=False),"application/json; charset=utf-8")
                configured = len(sources_config(DEFAULT_SOURCES))
                return self.send_body(json.dumps({"url":None,"message":"尚未生成日报，请点击刷新日报","sources":{"configured":configured,"ok":0,"failed":0}}, ensure_ascii=False), "application/json; charset=utf-8")
            return self.send_body(json.dumps({"url":"/api/report","message":f"最新日报：{_latest_day}","sources":_latest_source_status}, ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/api/report": return self.send_body(_latest_html or "暂无日报")
        if path == "/api/priority": return self.send_body(_latest_priority_html or "暂无重点媒体日报")
        if path == "/api/export.xlsx":
            if not _latest_html: return self.send_body("请先点击刷新日报，再导出 Excel", "text/plain; charset=utf-8", 409)
            body = export_xlsx(_latest_items, _latest_day)
            self.send_response(200); self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"); self.send_header("Content-Disposition", f'attachment; filename="tripo-daily-{_latest_day}.xlsx"'); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if path == "/api/cron/daily":
            auth=self.headers.get("Authorization",""); secret=os.getenv("CRON_SECRET","")
            if secret and auth != f"Bearer {secret}": return self.send_body("Unauthorized","text/plain",401)
            _,failures,candidates,chosen=make_report(); saved=latest_report(); sent=send_feishu(_latest_day,_latest_source_status,(saved or {}).get("items",[]))
            return self.send_body(json.dumps({"ok":not failures,"day":_latest_day,"candidates":candidates,"chosen":chosen,"feishu_sent":sent},ensure_ascii=False),"application/json; charset=utf-8")
        self.send_error(404)
    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/refresh": return self.send_error(404)
        try:
            _, failures, candidates, chosen = make_report()
            msg = "刷新完成" if not failures else "刷新完成，但部分来源失败；请查看报告顶部状态"
            return self.send_body(json.dumps({"ok": not failures, "message": msg, "candidates": candidates, "chosen": chosen, "day": _latest_day, "html": _latest_html, "sources": _latest_source_status}, ensure_ascii=False), "application/json; charset=utf-8")
        except Exception as e:
            return self.send_body(json.dumps({"ok":False,"message":f"刷新失败：{type(e).__name__}"}, ensure_ascii=False), "application/json; charset=utf-8", 500)
