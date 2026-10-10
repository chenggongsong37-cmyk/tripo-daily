"""Optional Supabase persistence and Feishu delivery via public REST APIs."""
from __future__ import annotations
import hashlib, hmac, json, os, time, base64
from datetime import datetime
import requests

def configured(): return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

def _headers(prefer="return=representation"):
    key=os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {"apikey":key,"Authorization":f"Bearer {key}","Content-Type":"application/json","Prefer":prefer}

def save_report(day, markdown, html, status, items):
    if not configured(): return False
    payload={"report_date":str(day),"markdown":markdown,"html":html,"status":status,"items":items,"generated_at":datetime.utcnow().isoformat()+"Z"}
    url=os.environ["SUPABASE_URL"].rstrip("/")+"/rest/v1/daily_reports?on_conflict=report_date"
    r=requests.post(url,headers=_headers("resolution=merge-duplicates,return=minimal"),data=json.dumps(payload,ensure_ascii=False),timeout=8); r.raise_for_status(); return True

def latest_report():
    if not configured(): return None
    url=os.environ["SUPABASE_URL"].rstrip("/")+"/rest/v1/daily_reports?select=*&order=report_date.desc&limit=1"
    r=requests.get(url,headers=_headers(),timeout=6); r.raise_for_status(); rows=r.json(); return rows[0] if rows else None

def send_feishu(day, status, items):
    webhook=os.getenv("FEISHU_WEBHOOK_URL")
    if not webhook: return False
    lines=[]
    for item in items[:5]: lines.append(f"• [{item['title']}]({item['url']})：{item.get('impact','待观察')}")
    content={"msg_type":"interactive","card":{"header":{"title":{"tag":"plain_text","content":f"{day} Tripo AI 舆情日报"},"template":"blue"},"elements":[{"tag":"markdown","content":f"**采集状态**：成功 {status.get('ok',0)}，失败 {status.get('failed',0)}，入选 {len(items)}\n\n"+"\n".join(lines)+"\n\n[查看完整日报](https://tripo-daily.vercel.app/)"}]}}
    secret=os.getenv("FEISHU_SIGNING_SECRET")
    if secret:
        timestamp=str(int(time.time())); string_to_sign=f"{timestamp}\n{secret}".encode(); sign=base64.b64encode(hmac.new(string_to_sign,digestmod=hashlib.sha256).digest()).decode(); content.update({"timestamp":timestamp,"sign":sign})
    r=requests.post(webhook,json=content,timeout=8); r.raise_for_status()
    try:
        result=r.json()
    except ValueError as exc:
        raise RuntimeError("飞书返回了无法解析的响应") from exc
    # Custom bot responses use either `code` or the legacy `StatusCode`.
    # HTTP 200 alone does not mean that Feishu accepted the message.
    code=result.get("code", result.get("StatusCode", 0))
    if code not in (0, "0", None):
        message=result.get("msg") or result.get("StatusMessage") or "未知错误"
        raise RuntimeError(f"飞书拒绝消息（{code}）：{message}")
    return True
