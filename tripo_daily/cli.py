from __future__ import annotations
import argparse, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep
from pathlib import Path
try:
    import requests
except ImportError:  # 允许未安装可选依赖时仍运行样本/本地模式
    requests = None
from urllib.request import Request, urlopen
from .core import *

ROOT=Path(__file__).resolve().parents[1]; DEFAULT_SOURCES=ROOT/"config/sources.json"
def sources_config(path):
    if not Path(path).exists(): return []
    return json.loads(Path(path).read_text())
def collect(sources, sample=False):
    all_items=[]; failures=[]; ok=0
    if sample:
        all_items=[Item("样本：Tripo AI 发布新的 3D 生成能力", "https://example.invalid/sample-tripo", "本地样本", "新闻稿", datetime.now(UTC)-timedelta(hours=2), "样本数据，仅用于演示。", sample=True), Item("样本：监管机构发布 AI 版权讨论稿", "https://example.invalid/sample-policy", "本地样本", "监管原文", datetime.now(UTC)-timedelta(hours=3), "样本数据，仅用于演示。", sample=True)]
        return all_items, [], 1
    enabled = [s for s in sources if s.get("enabled", True)]
    def fetch(s):
        if requests:
            r=requests.get(s["url"], timeout=18, headers={"User-Agent":os.getenv("USER_AGENT","tripo-daily/0.1")})
            if r.status_code == 429 and s.get("adapter") == "gdelt":
                sleep(6); r=requests.get(s["url"], timeout=18, headers={"User-Agent":os.getenv("USER_AGENT","tripo-daily/0.1")})
            r.raise_for_status(); body=r.content
        else:
            with urlopen(Request(s["url"], headers={"User-Agent":os.getenv("USER_AGENT","tripo-daily/0.1")}), timeout=12) as resp: body=resp.read()
        if s.get("adapter") == "gdelt":
            payload=json.loads(body); items=[]
            for article in payload.get("articles",[]):
                items.append(Item(article.get("title") or "(无标题)", article.get("url") or "", article.get("domain") or s["name"], s.get("type","媒体聚合"), parse_dt(article.get("seendate")), article.get("title") or ""))
            return items
        return parse_feed(body,s["name"],s.get("type","媒体报道"))
    # Sources are independent. Parallel collection keeps the Vercel refresh
    # within its function limit even as the public-source catalog grows.
    with ThreadPoolExecutor(max_workers=min(10, max(1, len(enabled)))) as pool:
        futures = {pool.submit(fetch, s): s for s in enabled}
        for future in as_completed(futures):
            s = futures[future]
            try:
                all_items += future.result(); ok += 1
            except Exception as e:
                failures.append(f"{s.get('name',s.get('url'))}: {type(e).__name__}")
    return all_items, failures, ok
def run(day, sample=False, preview=False, db="data/tripo.db", sources=DEFAULT_SOURCES):
    start,end=window_for(day); raw, failures, ok=collect(sources_config(sources),sample); candidates=[classify(i) for i in raw]; all_topics=dedupe([i for i in candidates if i.sample or (i.published is not None and i.relevance>0)]); chosen=[i for i in all_topics if i.sample or topic_has_window_article(i,start,end)][:30]; pending=dedupe([i for i in candidates if i.published is None and i.relevance>0])
    if preview:
        for i in candidates: print(f"{'入选' if i in chosen else '待审核'} | {i.title} | {i.reason} | {i.url}")
        return 0
    store=Store(db)
    for i in chosen: store.put(i)
    md=render_report(day,start,end,chosen,{"ok":ok,"failed":len(failures),"candidates":len(candidates)},failures,pending)
    out=ROOT/"reports"; out.mkdir(exist_ok=True); date=str(day); (out/f"{date}.md").write_text(md,encoding="utf-8"); (out/f"{date}.html").write_text(html_report(md),encoding="utf-8"); print(out/f"{date}.md"); return 1 if failures else 0
def main(argv=None):
    p=argparse.ArgumentParser(prog="tripo-daily"); sub=p.add_subparsers(dest="cmd",required=True)
    for n in ("run","preview","backfill"):
        q=sub.add_parser(n); q.add_argument("--date",default=None); q.add_argument("--sample",action="store_true")
    q=sub.add_parser("sources"); q.add_argument("action",choices=["check"])
    a=p.parse_args(argv)
    if a.cmd=="sources":
        _,fails,ok=collect(sources_config(DEFAULT_SOURCES)); print(f"成功 {ok}，失败 {len(fails)}"); [print(x) for x in fails]; return 1 if fails else 0
    day=a.date or datetime.now(CN).date().isoformat()
    if a.cmd=="backfill": return run(day,a.sample)
    return run(day,a.sample,a.cmd=="preview")
if __name__=="__main__": sys.exit(main())
