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
    "ndc_signal": ("景氣燈號 分", "zh", 45, [["燈"]], _ndc),
    "ism_pmi": ("ISM manufacturing PMI", "en", 40, [["ISM"], ["PMI", "manufactur"]], _ism),
    "spx_fwd_pe": ("S&P 500 forward P/E ratio", "en", 21, [["forward", "P/E"], ["forward", "PE"]], _fwd_pe),
    "margin_ratio": ("大盤融資維持率", "zh", 10, [["維持率"]], _pct_in(100, 220)),
    "foreign_futures_net_oi": ("外資 台指期 淨空單 口", "zh", 7, [["外資"]], _fut_oi),
    "export_orders_yoy": ("外銷訂單 年增", "zh", 45, [["外銷訂單"]], _export),
}


def _match_title(t: str, must: list[list[str]]) -> bool:
    tl = t.lower()
    return any(all(w.lower() in tl for w in grp) for grp in must)


def search_values(errors: list[str]) -> dict:
    out = {}
    for key, (q, lang, days, must, fn) in SEARCH.items():
        try:
            for it in _search(q, lang, days):
                if not _match_title(it["title"], must):
                    continue
                v = fn(it["title"])
                if v is None:
                    continue
                out[key] = {"value": v, "asof": (it["time"] or "")[:10] or None, "auto": True,
                            "note": f"自動搜尋：{it['title']}（{it['source']}）", "link": it["link"]}
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
    if len(pts) < 8:
        raise ValueError(f"{sym} 季度資本支出不足 8 季")
    return pts


def _ttm_yoy(pts):
    last4 = sum(v for _, v in pts[-4:])
    prev4 = sum(v for _, v in pts[-8:-4])
    return (last4 / prev4 - 1) * 100, pts[-1][0], last4


def capex_values(errors: list[str]) -> dict:
    out = {}
    try:
        yoy, d, ttm = _ttm_yoy(_quarterly_capex("TSM"))
        out["tsmc_capex_yoy"] = {"value": round(yoy, 1), "asof": d, "auto": True,
                                 "note": f"自動：台積電近四季實際資本支出年增率（TTM {ttm / 1e9:,.1f}B，Yahoo 財報）"}
    except Exception as e:  # noqa: BLE001
        errors.append(f"台積電資本支出：{str(e)[:100]}")
    try:
        cur = prev = 0.0
        dates = []
        for s in ("MSFT", "GOOGL", "AMZN", "META"):
            pts = _quarterly_capex(s)
            cur += sum(v for _, v in pts[-4:])
            prev += sum(v for _, v in pts[-8:-4])
            dates.append(pts[-1][0])
        out["csp_capex_revision"] = {"value": round((cur / prev - 1) * 100, 1), "asof": max(dates), "auto": True,
                                     "note": f"自動：四大 CSP 近四季實際資本支出合計年增率（TTM {cur / 1e9:,.0f}B，Yahoo 財報）"}
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
