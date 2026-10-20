"""新聞內文節錄：建置時抓取原文頁面，擷取前幾段作為摘要（附來源與原文連結）。

- Google News 連結先解析成原始媒體網址（DotsSplashUi batchexecute，與 googlenewsdecoder 相同做法）
- 內文優先取 JSON-LD 的 articleBody，其次取 <p> 段落；只保留前 4 段、約 700 字，避免轉載全文
- 沿用上一版已發布 data.json 的節錄，只抓新出現的新聞，降低對媒體網站的請求量
"""
from __future__ import annotations

import html
import json
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from . import fetchers

MAX_PARAS = 4
MAX_CHARS = 700
BOILER = re.compile(r"(cookie|subscribe|sign up|newsletter|all rights reserved|copyright|©|訂閱|版權所有|延伸閱讀|"
                    r"點我|加入會員|免責聲明|下載.{0,4}app|advertisement|廣告|相關新聞|更多新聞|請繼續往下閱讀)", re.I)


def decode_google(url: str) -> str:
    """news.google.com/rss/articles/<id> → 原始網址；失敗則回傳原網址。"""
    m = re.search(r"news\.google\.com/(?:rss/)?articles/([^?/]+)", url)
    if not m:
        return url
    gid = m.group(1)
    page = fetchers.http_get(f"https://news.google.com/rss/articles/{gid}", timeout=12, retries=0).decode("utf-8", "replace")
    sg = re.search(r'data-n-a-sg="([^"]+)"', page)
    ts = re.search(r'data-n-a-ts="([^"]+)"', page)
    if not sg or not ts:
        return url
    inner = ('["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
             f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{gid}",{ts.group(1)},"{sg.group(1)}"]')
    body = "f.req=" + urllib.parse.quote(json.dumps([[["Fbv4je", inner]]]))
    raw = fetchers.http_post("https://news.google.com/_/DotsSplashUi/data/batchexecute", body.encode()).decode("utf-8", "replace")
    data = json.loads(raw.split("\n\n")[1])[:-2]
    return json.loads(data[0][2])[1]


def _decode(raw: bytes) -> str:
    m = re.search(rb'charset=["\']?([\w-]+)', raw[:3000], re.I)
    enc = (m.group(1).decode() if m else "utf-8").lower()
    try:
        return raw.decode(enc, "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


def _ld_body(page: str) -> str:
    for blk in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(blk.strip())
        except ValueError:
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                b = x.get("articleBody")
                if isinstance(b, str) and len(b) > 80:
                    return html.unescape(b)
                stack.extend(x.values())
            elif isinstance(x, list):
                stack.extend(x)
    return ""


def extract(page: str) -> list[str]:
    """回傳前幾段內文。"""
    body = _ld_body(page)
    if body:
        paras = [p.strip() for p in re.split(r"\n+|(?<=[。！？])\s+", body) if p.strip()]
    else:
        scope = page
        m = re.search(r"<article[^>]*>(.*?)</article>", page, re.S | re.I)
        if m and len(m.group(1)) > 500:
            scope = m.group(1)
        paras = [fetchers.clean_html(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", scope, re.S | re.I)]
    out, total = [], 0
    for p in paras:
        cjk = len(re.findall(r"[一-鿿]", p))
        if (len(p) < 40 and cjk < 18) or BOILER.search(p):
            continue
        if out and p == out[-1]:
            continue
        if total + len(p) > MAX_CHARS:
            if not out:
                out.append(p[:MAX_CHARS].rstrip() + "…")
            break
        out.append(p)
        total += len(p)
        if len(out) >= MAX_PARAS:
            break
    return out


def fetch_one(item: dict) -> dict:
    url = item["link"]
    if "news.google.com" in url:
        url = decode_google(url)
    page = _decode(fetchers.http_get(url, timeout=12, retries=0))
    return {"url": url, "body": extract(page)}


def load_prev(url: str) -> dict:
    """上一版已發布資料：{id: {"url","body"}}。"""
    try:
        d = json.loads(fetchers.http_get(url, timeout=20, retries=0))
        return {n["id"]: {"url": n.get("url"), "body": n.get("body")} for n in d.get("news", []) if n.get("id") and n.get("body")}
    except Exception:  # noqa: BLE001
        return {}


def enrich(items: list[dict], errors: list[str], prev_url: str | None = None, limit: int = 150) -> dict:
    prev = load_prev(prev_url) if prev_url else {}
    todo = []
    for it in items:
        p = prev.get(it.get("id"))
        if p:
            it["body"], it["url"] = p["body"], p.get("url") or it["link"]
        elif len(todo) < limit:
            todo.append(it)
    ok = fail = 0

    def run(it):
        try:
            return it, fetch_one(it), None
        except Exception as e:  # noqa: BLE001
            return it, None, e

    with ThreadPoolExecutor(max_workers=10) as ex:
        for it, res, err in ex.map(run, todo):
            if res and res["body"]:
                it["body"], it["url"] = res["body"], res["url"]
                ok += 1
            else:
                if res:
                    it["url"] = res["url"]
                fail += 1
    stats = {"reused": sum(1 for it in items if it.get("body")) - ok, "fetched": ok, "failed": fail}
    if fail and not ok and todo:
        errors.append(f"新聞內文節錄：{fail} 則全數抓取失敗")
    return stats
