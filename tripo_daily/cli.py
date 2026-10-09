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
    def json_items(payload, s):
        adapter=s.get("adapter"); source_type=s.get("type","公开 API")
        if adapter == "gdelt":
            return [Item(a.get("title") or "(无标题)", a.get("url") or "", a.get("domain") or s["name"], source_type, parse_dt(a.get("seendate")), a.get("title") or "") for a in payload.get("articles",[])]
        if adapter == "semantic_scholar":
            return [Item(a.get("title") or "(无标题)", a.get("url") or "", s["name"], source_type, parse_dt(a.get("publicationDate")), a.get("abstract") or "", attribution="研究论文") for a in payload.get("data",[])]
        if adapter == "openalex":
            out=[]
            for a in payload.get("results",[]):
                loc=a.get("primary_location") or {}; url=(loc.get("landing_page_url") or a.get("doi") or a.get("id") or "")
                out.append(Item(a.get("display_name") or "(无标题)", url, s["name"], source_type, parse_dt(a.get("publication_date")), "", attribution="研究论文"))
            return out
        if adapter == "crossref":
            out=[]
            for a in payload.get("message",{}).get("items",[]):
                title=" ".join(a.get("title") or []) or "(无标题)"; dates=(a.get("published-online") or a.get("published-print") or a.get("created") or {}).get("date-parts",[])
                published=None
                if dates and dates[0]:
                    parts=(dates[0]+[1,1])[:3]; published=parse_dt(f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}")
                out.append(Item(title, a.get("URL") or "", s["name"], source_type, published, " ".join(a.get("subtitle") or []), attribution="正式发表论文"))
            return out
        if adapter == "federal_register":
            return [Item(a.get("title") or "(无标题)", a.get("html_url") or a.get("pdf_url") or "", s["name"], source_type, parse_dt(a.get("publication_date")), a.get("abstract") or "", attribution="美国监管原文") for a in payload.get("results",[])]
        return []
    def fetch(s):
        if requests:
            headers={"User-Agent":os.getenv("USER_AGENT","tripo-daily/0.1")}
            # Public APIs occasionally throttle or return a transient 5xx.
            # Retry only those recoverable responses so a brief provider-side
            # fluctuation does not mark the whole daily report incomplete.
            for attempt in range(3):
                r=requests.get(s["url"], timeout=14, headers=headers)
                if r.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
                    break
                sleep(1.5 * (attempt + 1))
            r.raise_for_status(); body=r.content
        else:
            with urlopen(Request(s["url"], headers={"User-Agent":os.getenv("USER_AGENT","tripo-daily/0.1")}), timeout=12) as resp: body=resp.read()
        if s.get("adapter") in {"gdelt","semantic_scholar","openalex","crossref","federal_register"}:
            items = json_items(json.loads(body),s)
        else:
            items = parse_feed(body,s["name"],s.get("type","媒体报道"))
        if s.get("priority_media"):
            for item in items:
                item.section = "priority_media"
                item.relevance = 1.0
                item.paywall = bool(s.get("paywall"))
                item.attribution = s.get("priority_media")
        return items
    # Sources are independent. Parallel collection keeps the Vercel refresh
    # within its function limit even as the public-source catalog grows.
    with ThreadPoolExecutor(max_workers=min(16, max(1, len(enabled)))) as pool:
        futures = {pool.submit(fetch, s): s for s in enabled}
        for future in as_completed(futures):
            s = futures[future]
            try:
                all_items += future.result(); ok += 1
            except Exception as e:
                failures.append(f"{s.get('name',s.get('url'))}: {type(e).__name__}")
    return all_items, failures, ok
def select_items(candidates, start, end, limit=30):
    priority=[]; seen=set()
    for item in sorted(candidates, key=lambda x: x.published or datetime.min.replace(tzinfo=UTC), reverse=True):
        if item.section == "priority_media" and in_window(item,start,end) and item.canonical_url not in seen:
            priority.append(item); seen.add(item.canonical_url)
    regular=dedupe([i for i in candidates if i.section != "priority_media" and (i.sample or (i.published is not None and i.relevance>0))])
    return priority + [i for i in regular if i.sample or topic_has_window_article(i,start,end)][:limit]

def run(day, sample=False, preview=False, db="data/tripo.db", sources=DEFAULT_SOURCES):
    start,end=window_for(day); raw, failures, ok=collect(sources_config(sources),sample); candidates=[classify(i) for i in raw]; chosen=select_items(candidates,start,end); pending=dedupe([i for i in candidates if i.published is None and i.relevance>0])
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
