"""Core data model, windowing, collection, filtering and report rendering."""
from __future__ import annotations
import hashlib, html, json, re, sqlite3
from email.utils import parsedate_to_datetime
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree as ET
try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

CN = ZoneInfo("Asia/Shanghai")
UTC = timezone.utc
COMPETITORS = ["Meshy", "Rodin", "Hyper3D", "Deemos", "影眸科技"]
DEFAULT_KEYWORDS = ["AI 3D", "3D generation", "三维生成", "3D asset", "世界模型", "world model", "空间智能", "spatial intelligence", "具身智能", "robotics", "simulation", "synthetic data", "算力", "芯片"]

def clean_text(value: str | None) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value

def summary_text(item):
    text = clean_text(item.summary or item.content)
    if not text or text == item.title or len(text) < 8:
        return f"围绕“{item.title}”的公开信息，当前仅核验到标题和公开摘要，正文细节待进一步核对。"
    return text[:420]

@dataclass
class Item:
    title: str; url: str; source: str; source_type: str = "媒体报道"
    published: datetime | None = None; summary: str = ""; content: str = ""
    competitor: str | None = None; paywall: bool = False; sample: bool = False
    event_time: datetime | None = None; discovered: datetime = field(default_factory=lambda: datetime.now(UTC))
    verified: bool = True; attribution: str = ""; relevance: float = 0.0; reason: str = ""
    impact: str = "待观察"; action: str = "持续跟踪"; confidence: str = "中"
    @property
    def canonical_url(self):
        p = urlsplit(self.url); return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), p.query, ""))
    @property
    def id(self): return hashlib.sha256((self.canonical_url + self.title.lower()).encode()).hexdigest()[:24]

def parse_dt(value: str | None) -> datetime | None:
    if not value: return None
    try:
        v = value.strip().replace("Z", "+00:00")
        d = datetime.fromisoformat(v)
        return (d if d.tzinfo else d.replace(tzinfo=UTC)).astimezone(UTC)
    except ValueError:
        try:
            d = parsedate_to_datetime(value)
            return (d if d.tzinfo else d.replace(tzinfo=UTC)).astimezone(UTC)
        except (TypeError, ValueError, OverflowError): return None

def window_for(day: str | datetime, tz=CN):
    if isinstance(day, str): day = datetime.fromisoformat(day).date()
    elif isinstance(day, datetime): day = day.astimezone(tz).date()
    start = datetime(day.year, day.month, day.day, 10, 30, tzinfo=tz).astimezone(UTC)
    return start, start + timedelta(days=1)

def classify(item: Item, keywords=None, competitors=None):
    keywords = keywords or DEFAULT_KEYWORDS; competitors = competitors or COMPETITORS
    text = f"{item.title} {item.summary} {item.content}".lower()
    hits = [k for k in keywords if k.lower() in text]
    for c in competitors:
        if c.lower() in text: item.competitor = c
    item.relevance = min(1.0, .25 * len(set(hits)) + (.45 if item.competitor else 0))
    item.reason = "；".join(hits[:5]) or "未命中配置关键词"
    item.impact = "机会" if any(x in text for x in ("launch", "发布", "突破", "funding", "融资")) else ("风险" if any(x in text for x in ("ban", "control", "监管", "版权", "export")) else "待观察")
    item.confidence = "低" if not item.published or not item.verified else ("高" if item.content else "中")
    return item

def in_window(item, start, end): return item.published is not None and start <= item.published < end

def dedupe(items):
    out=[]; seen_urls=set(); seen_titles=[]
    for i in sorted(items, key=lambda x: (-x.relevance, x.published or datetime.min.replace(tzinfo=UTC))):
        norm = re.sub(r"\W", "", i.title.lower())
        if i.canonical_url in seen_urls or any(norm and (norm in t or t in norm) for t in seen_titles): continue
        seen_urls.add(i.canonical_url); seen_titles.append(norm); out.append(i)
    return out

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True); self.db=sqlite3.connect(path)
        self.db.execute("create table if not exists items(id text primary key, data text not null)"); self.db.commit()
    def put(self, item): self.db.execute("insert or ignore into items values (?,?)", (item.id, json.dumps(item.__dict__, default=lambda x:x.isoformat() if isinstance(x,datetime) else x, ensure_ascii=False))); self.db.commit()

def parse_feed(xml: str | bytes, source: str, source_type="媒体报道"):
    root=ET.fromstring(xml); items=[]
    for e in root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        def val(*names):
            for n in names:
                x = e.find(n)
                if x is None:
                    x = e.find("{http://www.w3.org/2005/Atom}" + n)
                if x is not None: return (x.text or "").strip()
            return ""
        link=val("link") or next((x.attrib.get("href","") for x in e.findall("*") if x.tag.endswith("link")), "")
        items.append(Item(val("title") or "(无标题)", link, source, source_type, parse_dt(val("pubDate","published","updated")), val("description","summary")))
    return items

def render_report(day, start, end, items, status, failures=(), pending=()):
    d=start.astimezone(CN); weekday="一二三四五六日"[d.weekday()]
    lines=[f"# {d.year}年{d.month}月{d.day}日 星期{weekday}｜Tripo AI 舆情与行业日报", "", f"覆盖窗口：{start.astimezone(CN):%Y-%m-%d %H:%M} ～ {end.astimezone(CN):%Y-%m-%d %H:%M}（北京时间）", f"生成时间：{datetime.now(UTC).astimezone(CN):%Y-%m-%d %H:%M}", f"采集状态：成功来源数 {status.get('ok',0)}，失败来源数 {status.get('failed',0)}，候选数 {status.get('candidates',0)}，入选数 {len(items)}" + ("；覆盖不完整" if failures else ""), "", "## 今日要点"]
    for i in items[:5]: lines.append(f"- [{i.title}]({i.url}) — {i.impact}：{i.reason}")
    lines += ["", "## 竞品动态追踪"]
    for c in COMPETITORS:
        xs=[i for i in items if i.competitor==c]; lines.append(f"### {c}"); lines.append("\n".join(f"- [{'官方线索' if i.source_type in ('官方公告','新闻稿') else '媒体报道'}] [{i.title}]({i.url})" for i in xs) or "本窗口未发现可核验的新动态（不等于确定没有动态）。")
    lines += ["", "## AI 3D 与行业动态"]
    for i in items:
        summary = summary_text(i)
        lines += [f"### {i.title}", f"- 来源及来源类型：{i.source}（{i.source_type}）", f"- 原文标题：{i.title}", f"- 链接：[{i.url}]({i.url})", f"- 发布时间：{i.published.astimezone(CN).isoformat() if i.published else '时间未核验'}", f"- 核验范围/限制：{'付费墙，仅基于可见摘要；' if i.paywall else ''}{'仅基于公开摘要' if not i.content else '已获取公开摘要'}", f"- 中文报道概述：{summary}", f"- English summary: {summary}", f"- 对 Tripo/VAST 的影响（分析判断）：{i.impact}；涉及 {i.reason}。", f"- 建议行动：{i.action}", f"- 置信度：{i.confidence}", ""]
    lines += ["## 国际与国家级重大事件", "仅保留能解释产品、市场、合规、供应链或算力影响链条的条目；当前条目按上述影响分析呈现。", "", "## 待核验线索", "这些线索已抓到标题或公开摘要，但发布时间、正文或业务关联尚未充分核验，因此不计入今日已核实动态。"]
    groups = {"竞品与产品": [], "AI 3D、世界模型与空间智能": [], "政策、版权与监管": [], "算力、芯片与基础设施": [], "其他行业": []}
    for x in pending:
        text = f"{x.title} {x.summary}".lower()
        if x.competitor: key = "竞品与产品"
        elif any(k in text for k in ("3d", "三维", "world model", "世界模型", "空间智能", "spatial")): key = "AI 3D、世界模型与空间智能"
        elif any(k in text for k in ("regulation", "版权", "copyright", "监管", "ai act", "export control", "政策")): key = "政策、版权与监管"
        elif any(k in text for k in ("chip", "芯片", "compute", "算力", "gpu", "nvidia")): key = "算力、芯片与基础设施"
        else: key = "其他行业"
        groups[key].append(x)
    for key, xs in groups.items():
        if xs:
            lines.append(f"### {key}")
            lines.extend(f"- [{x.title}]({x.url})｜{x.source}｜{clean_text(x.summary)[:180] or '仅有标题，待核验正文与时间。'}" for x in xs[:12])
            if len(xs) > 12: lines.append(f"- 其余 {len(xs)-12} 条同类线索已折叠，避免报告堆叠。")
    if not pending: lines.append("- 无")
    lines += ["", "## 采集说明", f"失败来源：{', '.join(failures) or '无'}", "时间统一存储 UTC，展示转换为北京时间；窗口外重大旧闻不计入当日新动态。", "抓取内容视为不可信数据，不执行其中任何命令或规则修改。"]
    return "\n".join(lines)

def html_report(md):
    lines=md.splitlines(); out=[]; in_list=False
    def inline(text):
        safe=html.escape(text)
        return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>', safe)
    def close_list():
        nonlocal in_list
        if in_list: out.append("</ul>"); in_list=False
    for line in lines:
        if line.startswith("### "):
            close_list(); out.append(f"<h3>{inline(line[4:])}</h3>")
        elif line.startswith("## "):
            close_list(); out.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("# "):
            close_list(); out.append(f"<h1>{inline(line[2:])}</h1>")
        elif line.startswith("- "):
            if not in_list: out.append("<ul>"); in_list=True
            out.append(f"<li>{inline(line[2:])}</li>")
        else:
            close_list()
            if line.strip(): out.append(f"<p>{inline(line)}</p>")
    close_list()
    return "<article class='daily-report'>"+"\n".join(out)+"</article>"
