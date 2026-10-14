"""新聞抓取、去重、主題標註與受惠 / 受壓標的推導。"""
from __future__ import annotations

import hashlib
import re
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from . import fetchers
from .themes import DOWN_WORDS, THEMES, UP_WORDS


def _gnews(q: str, lang: str) -> str:
    qq = urllib.parse.quote(q + " when:7d")
    if lang == "zh":
        return f"https://news.google.com/rss/search?q={qq}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    return f"https://news.google.com/rss/search?q={qq}&hl=en-US&gl=US&ceid=US:en"


SOURCES = [
    ("rss", "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en", "Google News", "en"),
    ("rss", "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=zh-TW&gl=TW&ceid=TW:zh-Hant", "Google 新聞", "zh"),
    ("rss", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "CNBC", "en"),
    ("rss", "https://www.cnbc.com/id/20910258/device/rss/rss.html", "CNBC", "en"),
    ("rss", "https://feeds.content.dowjones.io/public/rss/mw_topstories", "MarketWatch", "en"),
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


THEME_CAT = {
    "fed_rates": ["總經"], "inflation": ["總經"], "recession": ["總經"], "dollar": ["總經"], "credit": ["總經"],
    "japan": ["總經"], "gold": ["總經"], "china": ["政策", "總經"], "tariff": ["政策"], "oil_mideast": ["能源", "地緣"],
    "shipping": ["能源"], "ai_power": ["科技", "能源"], "ai_semis": ["科技"], "memory": ["科技"], "ai_credit": ["科技"],
    "apple": ["科技"], "satellite": ["科技"], "ev_auto": ["科技"], "crypto": ["科技"], "taiwan_geo": ["地緣"],
    "defense": ["地緣"], "pharma": ["公司"],
}
CATEGORIES = ["總經", "公司", "政策", "能源", "科技", "地緣"]
REGIONS = [
    ("台灣", ["台灣", "台股", "taiwan", "taiex", "新台幣", "台積電", "tsmc", "國發會", "央行總裁楊金龍"]),
    ("美國", ["美國", "美股", "fed", "聯準會", "u.s.", "us", "wall street", "s&p", "nasdaq", "treasury", "華爾街", "白宮", "trump", "川普"]),
    ("中國", ["中國", "陸股", "china", "beijing", "北京", "人行", "pboc", "港股", "hong kong"]),
    ("日本", ["日本", "日股", "japan", "boj", "日銀", "nikkei", "日圓", "yen"]),
    ("歐洲", ["歐洲", "歐股", "europe", "ecb", "歐央", "eurozone", "germany", "德國", "uk", "英國", "france", "法國"]),
    ("韓國", ["韓國", "韓股", "korea", "kospi", "三星", "samsung", "海力士", "hynix"]),
    ("中東", ["中東", "伊朗", "以色列", "iran", "israel", "saudi", "沙烏地", "opec", "紅海", "gaza"]),
]


def _region(title: str, lang: str) -> str:
    t = " " + title.lower() + " "
    best, hits = None, 0
    for name, kws in REGIONS:
        n = sum(1 for k in kws if (re.search(r"(?<![a-z])" + re.escape(k.strip()) + r"(?![a-z])", t) if k[0].isascii() else k in t))
        if n > hits:
            best, hits = name, n
    return best or ("台灣" if lang == "zh" and ("台" in title) else "全球")


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
    cats = []
    for tg in tags:
        for c in THEME_CAT.get(tg["theme"], []):
            if c not in cats:
                cats.append(c)
    item["cats"] = cats
    item["region"] = _region(item["title"], item.get("lang", ""))
    item["id"] = hashlib.md5((item["title"] + item.get("source", "")).encode("utf-8")).hexdigest()[:10]
    return item


def collect(max_age_hours: int = 168, limit: int = 600) -> tuple[list[dict], list[dict], list[str]]:
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
