"""自動補值：原本需手動輸入的指標，改由定期搜尋取得。
- 新聞搜尋：Google News RSS 標題中以正則擷取數值（景氣燈號、ISM、預估本益比、融資維持率、外資期貨、外銷訂單、CDS）
- 財報：Yahoo Finance 季度資本支出（台積電、四大 CSP 近四季合計年增率）
- 代理：CoreWeave 股價 1 個月跌幅
回傳 {key: {"value","asof","note","auto": True}}；抓不到的就不回傳，維持手動值或「待輸入」。
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
from datetime import datetime

from . import fetchers


def _search(q: str, lang: str, days: int) -> list[dict]:
    qq = urllib.parse.quote(f"{q} when:{days}d")
    if lang == "zh":
        url = f"https://news.google.com/rss/search?q={qq}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    else:
        url = f"https://news.google.com/rss/search?q={qq}&hl=en-US&gl=US&ceid=US:en"
    items = fetchers.rss_items(url, "Google News", lang)
    items.sort(key=lambda x: x["time"] or "", reverse=True)
    return items


def _num(s: str) -> float:
    return float(s.replace(",", ""))


# key: (查詢字串, 語言, 回溯天數, 標題必須包含的字（任一組全部包含）, 擷取函式)
def _ndc(t):
    m = re.search(r"(\d{1,2})\s*分", t)
    v = _num(m.group(1)) if m else None
    return v if v and 9 <= v <= 45 else None


def _pct_in(lo, hi):
    def f(t):
        for m in re.finditer(r"(\d{2,3}(?:\.\d+)?)\s*%", t):
            v = _num(m.group(1))
            if lo <= v <= hi:
                return v
        return None
    return f


def _ism(t):
    for m in re.finditer(r"(\d{2}\.\d)", t):
        v = _num(m.group(1))
        if 35 <= v <= 65:
            return v
    return None


def _fwd_pe(t):
    for m in re.finditer(r"(\d{2}\.\d)\s*(?:x|times)?", t):
        v = _num(m.group(1))
        if 12 <= v <= 30:
            return v
    return None


def _fut_oi(t):
    m = re.search(r"淨空單?[^\d]{0,6}([\d,]{4,7})\s*口", t)
    if m:
        return -_num(m.group(1))
    m = re.search(r"淨多單?[^\d]{0,6}([\d,]{4,7})\s*口", t)
    return _num(m.group(1)) if m else None


def _export(t):
    m = re.search(r"年(增|減)\s*([\d.]+)\s*%", t)
    if not m:
        return None
    v = _num(m.group(2))
    return v if m.group(1) == "增" else -v


def _cds(t):
    m = re.search(r"(\d{2,3}(?:\.\d+)?)\s*(?:個)?基點", t) or re.search(r"(\d{2,3})\s*bp", t, re.I)
    return _num(m.group(1)) if m else None


SEARCH = {
    # key: ([查詢字串…], 語言, 回溯天數, 標題必含字組, 排除字, 擷取函式, 需檢查資料月份)
    "ndc_signal": (["景氣燈號 分", "景氣對策信號 分"], "zh", 45, [["燈"], ["信號"]], [], _ndc, True),
    "ism_pmi": (["ISM manufacturing PMI", "ISM manufacturing index"], "en", 40, [["ISM", "manufactur"]],
                ["non-manufacturing", "services", "nonmanufacturing"], _ism, False),
    "spx_fwd_pe": (["S&P 500 forward P/E ratio", "forward 12-month P/E ratio S&P 500", "S&P 500 forward PE FactSet"],
                   "en", 30, [["forward", "P/E"], ["forward", "PE"], ["forward", "price-to-earnings"]], [], _fwd_pe, False),
    "margin_ratio": (["大盤融資維持率", "融資維持率 大盤", "整體融資維持率"], "zh", 14, [["維持率"]], [], _pct_in(100, 220), False),
    "foreign_futures_net_oi": (["外資 台指期 淨空單 口", "外資 期貨 淨空單", "外資台指期 空單 口數", "外資 淨多單 台指期"],
                               "zh", 7, [["外資"]], [], _fut_oi, False),
    "export_orders_yoy": (["外銷訂單 年增", "外銷訂單 年減"], "zh", 45, [["外銷訂單"]], [], _export, True),
}


def _month_ok(title: str, published: str) -> bool:
    """標題提到「N月」時，須為發布日前 1～2 個月的資料，避免抓到舊月份的回顧報導。"""
    m = re.search(r"(\d{1,2})\s*月", title)
    if not m:
        return True
    try:
        pub = datetime.strptime(published[:10], "%Y-%m-%d") if published else datetime.now()
    except ValueError:
        pub = datetime.now()
    month = int(m.group(1))
    ok = {((pub.month - k - 1) % 12) + 1 for k in (0, 1, 2)}  # 當月、前 1、前 2 個月
    return month in ok


def search_values(errors: list[str]) -> dict:
    out = {}
    for key, (queries, lang, days, must, exclude, fn, check_month) in SEARCH.items():
        try:
            seen, items = set(), []
            for q in queries:
                for it in _search(q, lang, days):
                    if it["title"] not in seen:
                        seen.add(it["title"]); items.append(it)
                if any(_match_title(i["title"], must) for i in items):
                    break
            items.sort(key=lambda x: x["time"] or "", reverse=True)
            for it in items:
                t = it["title"]
                if not _match_title(t, must) or any(x.lower() in t.lower() for x in exclude):
                    continue
                if check_month and not _month_ok(t, it["time"]):
                    continue
                v = fn(t)
                if v is None:
                    continue
                out[key] = {"value": v, "asof": (it["time"] or "")[:10] or None, "auto": True,
                            "note": f"自動搜尋：{t}（{it['source']}）", "link": it["link"]}
                break
        except Exception as e:  # noqa: BLE001
            errors.append(f"自動搜尋 {key}：{str(e)[:100]}")
    return out


# ---------------------------------------------------------------- 資本支出（Yahoo 財報）
def _quarterly_capex(sym: str) -> list[tuple[str, float]]:
    now = int(time.time())
    url = ("https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/"
           f"{urllib.parse.quote(sym)}?type=quarterlyCapitalExpenditure&period1={now - 4 * 366 * 86400}&period2={now}")
    data = json.loads(fetchers.http_get(url, retries=1))
    pts = []
    for res in data.get("timeseries", {}).get("result", []):
        for p in res.get("quarterlyCapitalExpenditure") or []:
            if p and p.get("reportedValue"):
                pts.append((p["asOfDate"], abs(float(p["reportedValue"]["raw"]))))
    pts.sort()
    if len(pts) < 5:
        raise ValueError(f"{sym} 季度資本支出不足 5 季（取得 {len(pts)} 季）")
    return pts


def _ttm_yoy(pts):
    """有 8 季取近四季合計年增率；Yahoo 常只給 5 季，則取最新一季對去年同季。回傳 (yoy, 日期, 基準值, 說明)。"""
    if len(pts) >= 8:
        cur, prev = sum(v for _, v in pts[-4:]), sum(v for _, v in pts[-8:-4])
        return (cur / prev - 1) * 100, pts[-1][0], cur, "近四季合計"
    cur, prev = pts[-1][1], pts[-5][1]
    return (cur / prev - 1) * 100, pts[-1][0], cur, "最新一季對去年同季"


def capex_values(errors: list[str]) -> dict:
    out = {}
    try:
        yoy, d, base, how = _ttm_yoy(_quarterly_capex("TSM"))
        out["tsmc_capex_yoy"] = {"value": round(yoy, 1), "asof": d, "auto": True,
                                 "note": f"自動：台積電實際資本支出年增率（{how}，{base / 1e9:,.1f}B，Yahoo 財報）"}
    except Exception as e:  # noqa: BLE001
        errors.append(f"台積電資本支出：{str(e)[:100]}")
    try:
        cur = prev = 0.0
        dates, hows = [], set()
        for s in ("MSFT", "GOOGL", "AMZN", "META"):
            pts = _quarterly_capex(s)
            n = 4 if len(pts) >= 8 else 1
            cur += sum(v for _, v in pts[-n:])
            prev += sum(v for _, v in pts[-2 * n:-n]) if n == 4 else pts[-5][1]
            dates.append(pts[-1][0])
            hows.add("近四季合計" if n == 4 else "最新一季對去年同季")
        out["csp_capex_revision"] = {"value": round((cur / prev - 1) * 100, 1), "asof": max(dates), "auto": True,
                                     "note": f"自動：四大 CSP 實際資本支出合計年增率（{'／'.join(sorted(hows))}，{cur / 1e9:,.0f}B，Yahoo 財報）"}
    except Exception as e:  # noqa: BLE001
        errors.append(f"CSP 資本支出：{str(e)[:100]}")
    return out


def proxy_values(yahoo: dict) -> dict:
    """CoreWeave CDS 無公開來源 → 以 CRWV 股價距 3 個月高點跌幅換算代理分數（跌 20% ≈ +150bp、跌 40% ≈ +350bp）。"""
    out = {}
    h = yahoo.get("CRWV")
    if h and len(h["close"]) > 63:
        c = h["close"]
        dd = (c[-1] / max(c[-63:]) - 1) * 100
        proxy = max(0.0, -dd) * 8.75  # 40% 跌幅 → 350
        out["coreweave_cds_bp"] = {"value": round(proxy), "asof": h["dates"][-1], "auto": True,
                                   "note": f"代理：CRWV 距 3 個月高點 {dd:+.1f}%，換算信用壓力分數（非真實 CDS）"}
    return out


def collect(yahoo: dict, errors: list[str]) -> dict:
    out = {}
    out.update(proxy_values(yahoo))
    out.update(capex_values(errors))
    out.update(search_values(errors))
    return out


def merge(manual: dict, auto: dict) -> dict:
    """手動值與自動值取資料日期較新者；手動未填則用自動值。"""
    merged = dict(manual)
    for k, a in auto.items():
        m = manual.get(k) or {}
        if m.get("value") is None or (a.get("asof") or "") > (m.get("asof") or ""):
            merged[k] = {**a, "note": a["note"]}
    return merged
