"""Local web UI for viewing and refreshing reports."""
from __future__ import annotations
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from .cli import run
from .core import CN

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
PAGE = """<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Tripo AI 舆情日报</title><style>body{font-family:system-ui;max-width:1100px;margin:auto;padding:24px;background:#f5f7fb;color:#172033}header{display:flex;justify-content:space-between;align-items:center}button{background:#1769e0;color:white;border:0;border-radius:6px;padding:10px 16px;font-size:15px}#status{margin:16px 0;padding:12px;background:white;border-radius:8px}iframe{width:100%;height:75vh;border:1px solid #dce1ea;background:white;border-radius:8px}</style><header><h1>Tripo AI 舆情与行业日报</h1><button id=b onclick=refresh()>刷新日报</button></header><div id=s>读取中...</div><iframe id=r></iframe><script>async function load(){let d=await (await fetch('/api/status')).json();s.textContent=d.message;r.src=d.url||'about:blank'}async function refresh(){b.disabled=true;b.textContent='采集中...';s.textContent='正在访问来源并生成日报';let d=await (await fetch('/api/refresh',{method:'POST'})).json();s.textContent=d.message;await load();b.disabled=false;b.textContent='刷新日报'}load()</script>"""
def latest():
    x=sorted(REPORTS.glob('*.html'),reverse=True); return x[0] if x else None
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def out(self,obj,code=200):
        b=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        p=urlparse(self.path).path
        if p=='/':
            b=PAGE.encode(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b); return
        if p=='/api/status':
            f=latest(); self.out({'url':'/reports/'+f.name if f else None,'message':f'最新日报：{f.stem}' if f else '暂无日报，请点击刷新'}); return
        if p.startswith('/reports/'):
            f=REPORTS/Path(p.removeprefix('/reports/')).name
            if f.exists() and f.suffix=='.html':
                b=f.read_bytes(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b); return
        self.send_error(404)
    def do_POST(self):
        if urlparse(self.path).path!='/api/refresh': self.send_error(404); return
        day=datetime.now(CN).date().isoformat(); rc=run(day); self.out({'ok':rc==0,'message':'刷新完成' if rc==0 else '刷新完成，但部分来源失败；请查看日报顶部状态'})
def main():
    import argparse, os
    p=argparse.ArgumentParser(); p.add_argument('--host',default=os.getenv('HOST','127.0.0.1')); p.add_argument('--port',type=int,default=int(os.getenv('PORT','8765'))); a=p.parse_args(); print(f'网页地址：http://{a.host}:{a.port}'); ThreadingHTTPServer((a.host,a.port),Handler).serve_forever()
if __name__=='__main__': main()
