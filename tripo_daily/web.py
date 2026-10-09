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
PAGE = r"""<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Tripo AI 舆情日报</title><style>
:root{--ink:#162033;--muted:#667085;--blue:#2563eb;--purple:#7c3aed;--cyan:#0891b2}*{box-sizing:border-box}body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;color:var(--ink);background:#f4f7fb}.shell{max-width:1180px;margin:auto;padding:24px}.hero{padding:26px 30px;border-radius:16px;color:white;background:linear-gradient(110deg,#174ea6,#6340b5 65%,#07849b);box-shadow:0 10px 24px #1e3a5f30}.hero h1{margin:0 0 8px;font-size:28px}.hero p{margin:0;color:#e0ecff;font-size:15px}.toolbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:20px}.btn{border:0;border-radius:8px;padding:10px 15px;font-weight:650;cursor:pointer}.primary{background:white;color:#174ea6}.secondary{background:#ffffff24;color:white}.grid{display:grid;grid-template-columns:230px minmax(0,1fr);gap:18px;margin-top:18px}.panel,.report{background:white;border:1px solid #e1e7f0;border-radius:14px;box-shadow:0 5px 16px #3341550d}.panel{padding:16px;height:max-content}.panel h2{margin:0 0 12px;font-size:15px;color:#344054}.source{padding:10px;border-radius:8px;background:#eef4ff;margin:7px 0;font-size:12px;line-height:1.5}.source:nth-of-type(2){background:#f5f0ff}.source:nth-of-type(3){background:#eafaf7}.source b{display:block;color:#174ea6;font-size:13px}.history button{width:100%;text-align:left;background:#f6f3ff;color:#4c1d95;margin:5px 0;font-size:12px}.report{padding:26px 30px;min-height:650px}.report .daily-report>h1{font-size:24px;line-height:1.3;color:#143d78;border-bottom:3px solid #8bb9ff;padding-bottom:14px;margin-top:0}.report h2{font-size:19px;color:#6436a5;background:#f6f1ff;border-left:5px solid #8b5cf6;padding:10px 12px;margin:28px 0 14px;border-radius:0 8px 8px 0}.report h2:nth-of-type(2n){color:#08758a;background:#ecfbfd;border-left-color:#18a8bd}.report h3{font-size:16px;color:#194f90;background:#f2f7ff;padding:9px 11px;border-radius:8px;margin:16px 0 9px}.report p{font-size:14px;line-height:1.7;color:#475467;margin:7px 0}.report a{color:#175cd3;text-decoration:none;font-weight:600}.report a:hover{text-decoration:underline}.report ul{margin:8px 0;padding:0;list-style:none}.report li{font-size:14px;line-height:1.65;padding:8px 11px;margin:6px 0;background:#fafbfc;border-left:3px solid #bfd2ef;border-radius:5px}.meta{display:flex;gap:10px;flex-wrap:wrap;color:#e5edff;font-size:13px}.badge{display:inline-block;padding:4px 9px;border-radius:999px;background:#dcfce7;color:#166534}.empty{padding:50px;text-align:center;color:var(--muted)}@media(max-width:800px){.shell{padding:12px}.grid{grid-template-columns:1fr}.report{padding:20px}.hero h1{font-size:23px}}
</style><body><div class='shell'><section class='hero'><h1>Tripo AI 舆情与行业日报</h1><p>面向 VAST / Tripo AI 的 AI 3D、竞品与行业政策情报中心</p><div class='toolbar'><button class='btn primary' id='b' onclick='refresh()'>刷新日报</button><button class='btn secondary' onclick='load()'>重新加载</button><span id='s' class='meta'>正在读取...</span></div></section><div class='grid'><aside class='panel'><h2>来源概览</h2><div class='source'><b>10 个公开来源</b>官方公告、研究论文、行业 RSS、Google News 摘要</div><div class='source'><b>覆盖方向</b>AI 3D · 世界模型 · 机器人 · 政策 · 芯片</div><div class='source'><b>数据原则</b>原始链接、时间窗口、失败来源透明标记</div><h2 style='margin-top:25px'>历史日报</h2><div id='history' class='history'></div></aside><main class='report' id='report'><div class='empty'>正在加载日报...</div></main></div></div><script>
const KEY='tripo-report-history-v1';function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}function save(day,html){let a=JSON.parse(localStorage.getItem(KEY)||'[]').filter(x=>x.day!==day);a.unshift({day,html,time:new Date().toLocaleString()});localStorage.setItem(KEY,JSON.stringify(a.slice(0,30)));drawHistory()}function drawHistory(){let a=JSON.parse(localStorage.getItem(KEY)||'[]');history.innerHTML=a.length?a.map((x,i)=>`<button class='btn' onclick='showHistory(${i})'>${esc(x.day)}<small style='display:block;color:#64748b'>${esc(x.time)}</small></button>`).join(''):'<div style="color:#94a3b8;font-size:13px">刷新后自动保存历史</div>'}function showHistory(i){let a=JSON.parse(localStorage.getItem(KEY)||'[]');if(a[i])report.innerHTML=a[i].html;s.textContent='已查看历史日报：'+a[i].day}async function load(){try{let d=await (await fetch('/api/status')).json();s.innerHTML=`<span class='badge'>${esc(d.message)}</span>`;let h=await (await fetch(d.url||'/api/report')).text();report.innerHTML=h;save(d.message.replace('最新日报：',''),h)}catch(e){s.textContent='加载失败：'+e}}async function refresh(){b.disabled=true;b.textContent='采集中...';s.textContent='正在访问公开来源并生成日报';try{let d=await (await fetch('/api/refresh',{method:'POST'})).json();s.textContent=d.message;await load()}catch(e){s.textContent='刷新失败：'+e}finally{b.disabled=false;b.textContent='刷新日报'}}drawHistory();load();</script></body></html>"""
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
