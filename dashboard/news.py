"""新聞抓取、去重、主題標註與受惠 / 受壓標的推導。"""
from __future__ import annotations

import re
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from . import fetchers
from .themes import DOWN_WORDS, THEMES, UP_WORDS


def _gnews(q: str, lang: str) -> str:
    qq = urllib.parse.quote(q + " when:2d")
    if lang == "zh":
        return f"https://news.google.com/rss/search?q={qq}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    return f"https://news.google.com/rss/search?q={qq}&hl=en-US&gl=US&ceid=US:en"


SOURCES = [
    ("rss", "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en", "Google News", "en"),
    ("rss", "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=zh-TW&gl=TW&ceid=TW:zh-Hant", "Google 新聞", "zh"),
    ("rss", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "CNBC", "en"),
    ("rss", "https://www.cnbc.com/id/20910258/device/rss/rss.html", "CNBC", "en"),
    ("rss", "https://feeds.content.dowjones.io/public/rss/mw_topstories", "MarketWatch", "en"),
    ("rss", "https://finance.yahoo.com/news/rssindex", "Yahoo Finance", "en"),
    ("cnyes", "", "鉅亨網", "zh"),
]
for q in ["stock market", "Federal Reserve rates", "oil prices", "semiconductor AI chips", "China economy",
          "Taiwan", "treasury yields", "gold price", "Bank of Japan", "tariffs", "credit spreads", "Nikkei Kospi"]:
    SOURCES.append(("rss", _gnews(q, "en"), "Google News", "en"))
for q in ["台股", "美股", "聯準會", "半導體", "油價", "匯率 台幣", "AI 伺服器", "日股 韓股", "陸股 港股"]:
    SOURCES.append(("rss", _gnews(q, "zh"), "Google 新聞", "zh"))


def _fetch_one(src):
    kind, url, label, lang = src
    if kind == "cnyes":
        return fetchers.cnyes_items()
    return fetchers.rss_items(url, label, lang)


def _norm(t: str) -> str:
    return re.sub(r"[\W_]+", "", t.lower())[:60]


def _has(text: str, word: str) -> bool:
    if re.match(r"^[a-z]", word):
        return re.search(r"\b" + re.escape(word), text) is not None
    return word in text


def tag_item(item: dict) -> dict:
    text = " " + item["title"].lower() + " "
    ups = sum(1 for w in UP_WORDS if _has(text, w))
    downs = sum(1 for w in DOWN_WORDS if _has(text, w))
    tags = []
    for th in THEMES:
        hits = [k for k in th["kw"] if _has(text, k.lower())]
        if not hits:
            continue
        u, d = ups, downs
        for w in th.get("invert_words", []):
            if _has(text, w):
                d += 1
                u = max(0, u - 1)
        direction = 1 if u > d else -1 if d > u else 0
        tags.append({"theme": th["id"], "name": th["name"], "dir": direction})
    item["tags"] = tags
    benefit, hurt, related = set(), set(), set()
    th_by_id = {t["id"]: t for t in THEMES}
    for tg in tags:
        th = th_by_id[tg["theme"]]
        if tg["dir"] > 0:
            benefit.update(th["up_benefit"]); hurt.update(th["up_hurt"])
        elif tg["dir"] < 0:
            benefit.update(th["up_hurt"]); hurt.update(th["up_benefit"])
        else:  # 方向不明：僅標「相關」，不計入多空分數
            related.update(th["up_benefit"] + th["up_hurt"])
    both = benefit & hurt  # 多主題互相抵銷者視為相關
    benefit -= both; hurt -= both
    item["benefit"] = sorted(benefit)[:12]
    item["hurt"] = sorted(hurt)[:12]
    item["related"] = sorted((related | both) - benefit - hurt)[:12]
    item["indicators"] = sorted({i for tg in tags for i in th_by_id[tg["theme"]]["indicators"]})
    return item


def collect(max_age_hours: int = 72, limit: int = 400) -> tuple[list[dict], list[dict], list[str]]:
    """回傳 (news_items, theme_summary, errors)。"""
    errors, raw = [], []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_fetch_one, s): s for s in SOURCES}
        for f, s in futs.items():
            try:
                raw.extend(f.result())
            except Exception as e:  # noqa: BLE001
                errors.append(f"新聞來源 {s[2]}：{str(e)[:120]}")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    seen, items = set(), []
    for it in raw:
        key = _norm(it["title"])
        if not key or key in seen:
            continue
        seen.add(key)
        if it["time"]:
            try:
                if datetime.strptime(it["time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) < cutoff:
                    continue
            except ValueError:
                pass
        items.append(tag_item(it))
    items.sort(key=lambda x: x["time"] or "", reverse=True)
    items = items[:limit]
    return items, summarize(items), errors


def summarize(items: list[dict]) -> list[dict]:
    agg = defaultdict(lambda: {"count": 0, "up": 0, "down": 0, "headlines": []})
    for it in items:
        for tg in it["tags"]:
            a = agg[tg["theme"]]
            a["count"] += 1
            a["up"] += tg["dir"] > 0
            a["down"] += tg["dir"] < 0
            if len(a["headlines"]) < 3:
                a["headlines"].append(it["title"])
    out = []
    for th in THEMES:
        a = agg.get(th["id"])
        if not a:
            continue
        net = a["up"] - a["down"]
        direction = 1 if net > 0 else -1 if net < 0 else 0
        benefit = th["up_benefit"] if direction >= 0 else th["up_hurt"]
        hurt = th["up_hurt"] if direction >= 0 else th["up_benefit"]
        out.append({"id": th["id"], "name": th["name"], "count": a["count"], "up": a["up"], "down": a["down"],
                    "dir": direction, "benefit": benefit, "hurt": hurt, "headlines": a["headlines"],
                    "indicators": th["indicators"]})
    out.sort(key=lambda x: x["count"], reverse=True)
    return out


def ticker_news_scores(items: list[dict]) -> dict[str, float]:
    """每檔標的的新聞淨分數：受惠 +1、受壓 −1（近 24 小時加權 1.5）。"""
    now = datetime.now(timezone.utc)
    score = defaultdict(float)
    for it in items:
        w = 1.0
        if it["time"]:
            try:
                age = now - datetime.strptime(it["time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                w = 1.5 if age < timedelta(hours=24) else 1.0
            except ValueError:
                pass
        for s in it["benefit"]:
            score[s] += w
        for s in it["hurt"]:
            score[s] -= w
    return dict(score)
