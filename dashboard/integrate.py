"""把台美全市場（籌碼結構掃描＋供應鏈）整合進跨資產篩選與新聞衝擊。

- 全市場列轉成跨資產篩選的欄位格式，代號統一用 Yahoo 格式（美股 NVDA、台股 2330.TW / 6664.TWO）
- 與跨資產篩選池重複者合併為一列（保留技術面欄位，補上籌碼與供應鏈欄位）
- 新聞連結全市場：
  1. 直接提及：中文標題含台股公司名、英文標題含美股公司名或代號（市值 ≥ 50 億美元，避免誤判）
  2. 供應鏈傳導：新聞主題 → semi_value_chain 主題 / 產業 → 台股供應鏈公司（權重 0.5）
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .themes import DOWN_WORDS, UP_WORDS

# 新聞主題 → (供應鏈主題, 台股產業)
THEME_CHAIN = {
    "ai_semis": (["CoWoS", "AI 伺服器", "NVIDIA", "資料中心", "CPO", "矽光子", "ABF 載板", "EUV"],
                 ["Semiconductors", "Semiconductor Equipment & Materials"]),
    "memory": (["HBM"], []),
    "ai_power": (["資料中心"], ["Electrical Equipment & Parts"]),
    "ai_credit": (["AI 伺服器", "NVIDIA"], []),
    "ev_auto": (["電動車", "Tesla"], ["Auto Parts"]),
    "shipping": ([], ["Marine Shipping"]),
    "defense": ([], ["Aerospace & Defense"]),
    "tariff": (["Apple"], []),
    "apple": (["Apple"], []),
    "satellite": (["低軌衛星", "5G"], []),
}
POS_RANK = {"上游": 0, "中游": 1, "下游": 2, "相關": 3}
US_STOP = {"american", "first", "united", "general", "international", "global", "target", "public", "national",
           "energy", "bank", "capital", "the", "new", "world", "china", "us", "u.s.", "federal", "western", "southern",
           "northern", "eastern", "pacific", "atlantic", "digital", "real", "advanced", "applied", "standard", "royal",
           "smart", "health", "home", "service", "simon", "texas", "carrier", "progressive", "visa", "oracle"}
US_SUFFIX = re.compile(r"\b(inc|corp|corporation|co|company|holdings?|group|plc|ltd|limited|class [a-c]|common stock|"
                       r"ordinary shares|n\.?v\.?|s\.?a\.?|incorporated|technologies|platforms)\b\.?", re.I)


def symbol_of(r: dict) -> str:
    if r["region"] == "台股":
        return r["code"] + (".TWO" if r.get("mkt") == "上櫃" else ".TW")
    return r["code"]


def to_screen_rows(mk_rows: list[dict]) -> list[dict]:
    out = []
    for r in mk_rows:
        out.append({
            "symbol": symbol_of(r), "code": r["code"], "name": r.get("name", ""),
            "market": "台灣" if r["region"] == "台股" else "美國", "exch": r.get("mkt", ""), "asset": "股票",
            "sector": r.get("sector") or "—", "last": r.get("close"), "chg1d": r.get("chg"),
            "biasMA": r.get("biasMA"), "winPct": r.get("winPct"), "z": r.get("z"), "zscore": r.get("score"),
            "aboveMA": r.get("aboveMA"), "chain": r.get("chain") or [], "mc": r.get("mc"), "mcap": r.get("mcap"),
            "full": True, "themes": [],
        })
    return out


def merge_dups(cross: list[dict], mk: list[dict]) -> list[dict]:
    """跨資產列若與全市場重複，補上籌碼與供應鏈欄位；回傳去重後的全市場列。"""
    by = {r["symbol"]: r for r in cross}
    rest = []
    for r in mk:
        c = by.get(r["symbol"])
        if c is None and r["market"] == "台灣":  # 上市/上櫃後綴不一致時以代號比對
            c = by.get(r["code"] + ".TW") or by.get(r["code"] + ".TWO")
        if c is None:
            rest.append(r)
            continue
        for k in ("biasMA", "winPct", "z", "zscore", "aboveMA", "chain", "exch", "mc", "mcap"):
            if r.get(k) not in (None, []):
                c[k] = r[k]
        c["full"] = True
    return rest


def _direction(title: str) -> int:
    t = " " + title.lower() + " "
    u = sum(1 for w in UP_WORDS if (re.search(r"\b" + re.escape(w), t) if w[0].isascii() else w in t))
    d = sum(1 for w in DOWN_WORDS if (re.search(r"\b" + re.escape(w), t) if w[0].isascii() else w in t))
    return 1 if u > d else -1 if d > u else 0


def _us_alias(name: str) -> str | None:
    n = US_SUFFIX.sub("", name).replace(",", " ").strip()
    words = [w for w in n.split() if w]
    if not words:
        return None
    first = words[0]
    if first.lower() in US_STOP or len(first) < 4:
        if len(words) < 2:
            return None
        first = words[0] + " " + words[1]
    return first


def link_news(cross: list[dict], mk: list[dict], items: list[dict], now=None) -> dict[str, dict]:
    """在每則新聞加上 mk_benefit / mk_hurt / mk_related（全市場代號），回傳各標的新聞統計。"""
    now = now or datetime.now(timezone.utc)
    allrows = cross + mk
    # 直接提及的比對表
    tw_names = [(r["name"], r["symbol"]) for r in allrows if r.get("market") == "台灣" and len(r.get("name", "")) >= 2]
    tw_names.sort(key=lambda x: -len(x[0]))
    us_alias = []
    for r in mk:
        if r["market"] != "美國" or (r.get("mcap") or 0) < 5e9:
            continue
        a = _us_alias(r.get("name", ""))
        if a:
            us_alias.append((re.compile(r"\b" + re.escape(a) + r"\b", re.I), r["symbol"]))
        if len(r["code"]) >= 3:
            us_alias.append((re.compile(r"(?<![A-Za-z$])\$?" + re.escape(r["code"]) + r"\b"), r["symbol"]))
    # 供應鏈傳導表
    chain_members: dict[str, list[dict]] = defaultdict(list)
    ind_members: dict[str, list[dict]] = defaultdict(list)
    for r in allrows:
        for c in r.get("chain") or []:
            chain_members[c["theme"]].append({"r": r, "pos": c["pos"]})
        if r.get("market") == "台灣" and r.get("sector"):
            ind_members[r["sector"]].append({"r": r, "pos": "相關"})

    stats: dict[str, dict] = defaultdict(lambda: {"news": 0.0, "mentions": 0})
    for it in items:
        try:
            age = now - datetime.strptime(it["time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            w = 1.5 if age < timedelta(hours=24) else 1.0
        except (KeyError, ValueError):
            w = 1.0
        title = it["title"]
        b, h, rel = [], [], []
        # 1. 直接提及
        mentioned = set()
        if it.get("lang") == "zh":
            for name, sym in tw_names:
                if name in title and not any(name in m for m in mentioned):
                    mentioned.add(name)
                    stats[sym]["mentions"] += 1
                    d = _direction(title)
                    (b if d > 0 else h if d < 0 else rel).append(sym)
                    stats[sym]["news"] += d * w
        else:
            seen = set()
            for rx, sym in us_alias:
                if sym not in seen and rx.search(title):
                    seen.add(sym)
                    stats[sym]["mentions"] += 1
                    d = _direction(title)
                    (b if d > 0 else h if d < 0 else rel).append(sym)
                    stats[sym]["news"] += d * w
        # 2. 供應鏈傳導
        for tg in it.get("tags", []):
            chains, inds = THEME_CHAIN.get(tg["theme"], ([], []))
            if not chains and not inds:
                continue
            members = {}
            for ch in chains:
                for m in chain_members.get(ch, []):
                    s = m["r"]["symbol"]
                    if s not in members or POS_RANK[m["pos"]] < POS_RANK[members[s]["pos"]]:
                        members[s] = m
            for ind in inds:
                for m in ind_members.get(ind, []):
                    members.setdefault(m["r"]["symbol"], m)
            d = tg["dir"]
            # ai_credit / tariff：主題「升溫」對供應鏈是利空
            if tg["theme"] in ("ai_credit", "tariff"):
                d = -d
            ranked = sorted(members.values(), key=lambda m: (POS_RANK[m["pos"]], -(m["r"].get("mc") or m["r"].get("mcap") or 0)))
            for m in ranked:
                stats[m["r"]["symbol"]]["news"] += 0.5 * d * w
            top = [m["r"]["symbol"] for m in ranked[:8]]
            (b if d > 0 else h if d < 0 else rel).extend(top)
        dedup = lambda xs: list(dict.fromkeys(xs))[:12]  # noqa: E731
        it["mk_benefit"], it["mk_hurt"] = dedup(b), dedup(h)
        it["mk_related"] = [s for s in dedup(rel) if s not in it["mk_benefit"] and s not in it["mk_hurt"]]
    return stats


def theme_market_leaders(themes: list[dict], items: list[dict]) -> None:
    """主題摘要加上全市場受惠 / 受壓前幾名（依該主題新聞出現次數）。"""
    for th in themes:
        bc, hc = defaultdict(int), defaultdict(int)
        for it in items:
            if not any(t["theme"] == th["id"] for t in it.get("tags", [])):
                continue
            for s in it.get("mk_benefit", []):
                bc[s] += 1
            for s in it.get("mk_hurt", []):
                hc[s] += 1
        th["mk_benefit"] = [s for s, _ in sorted(bc.items(), key=lambda x: -x[1])[:8]]
        th["mk_hurt"] = [s for s, _ in sorted(hc.items(), key=lambda x: -x[1])[:8]]


def score_full(mk: list[dict]) -> None:
    """全市場列綜合分數 = 籌碼強勢分數 × 0.7 + 新聞淨分數百分位 × 0.3（無新聞者以 50 計）。"""
    nz = sorted((r["news"], r["symbol"]) for r in mk if r.get("news"))
    n = len(nz)
    rank = {s: (i / (n - 1) * 100 if n > 1 else 50) for i, (_, s) in enumerate(nz)}
    for r in mk:
        if r.get("zscore") is None:
            r["score"] = None
            continue
        r["score"] = round(r["zscore"] * 0.7 + rank.get(r["symbol"], 50.0) * 0.3, 1)
