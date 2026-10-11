"""資料抓取：Yahoo Finance 日線、FRED CSV、RSS / JSON 新聞。只用標準函式庫，Windows 免安裝套件即可執行。"""
from __future__ import annotations

import csv
import io
import json
import os
import ssl
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def _ssl_context():
    ctx = ssl.create_default_context()
    bundle = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if bundle and os.path.exists(bundle):
        ctx.load_verify_locations(bundle)
    return ctx


_CTX = _ssl_context()


def http_get(url: str, timeout: int = 20, retries: int = 2, headers: dict | None = None) -> bytes:
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"}
    if headers:
        h.update(headers)
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - 網路錯誤一律重試
            last = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET 失敗 {url}: {last}")


# ---------------------------------------------------------------- Yahoo Finance
def yahoo_history(symbol: str, range_: str = "2y", interval: str = "1d") -> dict:
    """回傳 {"symbol","name","currency","dates":[YYYY-MM-DD],"close":[float]}。"""
    q = urllib.parse.quote(symbol)
    last = None
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?range={range_}&interval={interval}&includeAdjustedClose=true"
        try:
            data = json.loads(http_get(url, retries=1))
            res = data["chart"]["result"][0]
            ts = res.get("timestamp") or []
            quote = res["indicators"]["quote"][0]
            closes = quote.get("close") or []
            meta = res.get("meta", {})
            dates, out = [], []
            for t, c in zip(ts, closes):
                if c is None:
                    continue
                dates.append(datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d"))
                out.append(float(c))
            # 盤中最新價（日線最後一根可能尚未收盤）
            rmp = meta.get("regularMarketPrice")
            if rmp and out and abs(rmp - out[-1]) / out[-1] < 0.25:
                out[-1] = float(rmp)
            if not out:
                raise ValueError("無收盤資料")
            return {
                "symbol": symbol,
                "name": meta.get("longName") or meta.get("shortName") or symbol,
                "currency": meta.get("currency", ""),
                "dates": dates,
                "close": out,
            }
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"Yahoo {symbol}: {last}")


# ---------------------------------------------------------------- FRED
def fred_series(series_id: str) -> list[tuple[str, float]]:
    """FRED 公開 CSV（免 API key）。回傳 [(date, value)]，略過缺值。"""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    raw = http_get(url, timeout=30).decode("utf-8", "replace")
    rows = list(csv.reader(io.StringIO(raw)))
    out = []
    for r in rows[1:]:
        if len(r) < 2:
            continue
        try:
            out.append((r[0], float(r[1])))
        except ValueError:
            continue
    if not out:
        raise RuntimeError(f"FRED {series_id}: 無資料")
    return out


# ---------------------------------------------------------------- News
def _text(el, tag):
    x = el.find(tag)
    return (x.text or "").strip() if x is not None and x.text else ""


def _parse_time(s: str) -> str:
    if not s:
        return ""
    try:
        dt = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rss_items(url: str, source_label: str, lang: str) -> list[dict]:
    root = ET.fromstring(http_get(url))
    items = []
    for it in root.iter("item"):
        title = _text(it, "title")
        src_el = it.find("source")
        source = (src_el.text or "").strip() if src_el is not None and src_el.text else source_label
        # Google News 標題結尾帶「 - 媒體名」
        if source != source_label and title.endswith(" - " + source):
            title = title[: -len(" - " + source)]
        items.append({
            "title": title,
            "link": _text(it, "link"),
            "time": _parse_time(_text(it, "pubDate")),
            "source": source,
            "lang": lang,
        })
    ns = "{http://www.w3.org/2005/Atom}"
    for it in root.iter(ns + "entry"):
        link = it.find(ns + "link")
        items.append({
            "title": _text(it, ns + "title"),
            "link": link.get("href", "") if link is not None else "",
            "time": _parse_time(_text(it, ns + "updated") or _text(it, ns + "published")),
            "source": source_label,
            "lang": lang,
        })
    return [i for i in items if i["title"]]


def cnyes_items(limit: int = 60) -> list[dict]:
    """鉅亨網頭條（JSON）。"""
    url = f"https://api.cnyes.com/media/api/v1/newslist/category/headline?limit={limit}"
    data = json.loads(http_get(url))
    out = []
    for n in data.get("items", {}).get("data", []):
        t = n.get("publishAt")
        out.append({
            "title": n.get("title", "").strip(),
            "link": f"https://news.cnyes.com/news/id/{n.get('newsId')}",
            "time": datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if t else "",
            "source": "鉅亨網",
            "lang": "zh",
        })
    return [i for i in out if i["title"]]
