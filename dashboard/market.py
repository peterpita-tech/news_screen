"""台美全市場：串接 Peterpita 籌碼結構掃描（zsigma-us / zsigma-tw）已發布的全市場資料，
台股再合併 semi_value_chain 的產業與供應鏈（上 / 中 / 下游）分類。每個來源只需一次請求。"""
from __future__ import annotations

import json
import re

from . import fetchers

ZSIGMA_US = "https://peterpita-tech.github.io/Peterpita/"
ZSIGMA_TW = "https://peterpita-tech.github.io/Peterpita/tw/"
CHAIN_BASE = "https://peterpita-tech.github.io/semi_value_chain/web/"
CHAIN_INDEX = CHAIN_BASE + "data/index.json"
CHAIN_THEMES = CHAIN_BASE + "data/themes.json"

KEEP = ("code", "name", "mkt", "sector", "mcap", "close", "chg", "biasMA", "biasW", "winPct", "z", "conc", "score",
        "aboveMA")


def parse_zs_data(html: str) -> dict:
    """從籌碼結構掃描頁面取出內嵌的 window.ZS_DATA。"""
    i = html.find("window.ZS_DATA")
    if i < 0:
        raise ValueError("頁面中找不到 ZS_DATA")
    j = html.index("{", i)
    data, _ = json.JSONDecoder().raw_decode(html[j:])
    return data


def parse_chain(themes: list) -> dict[str, list[dict]]:
    """themes.json → {台股代號: [{"theme","group","pos"}]}；pos 為 上游 / 中游 / 下游 / 相關。"""
    out: dict[str, list[dict]] = {}
    for g in themes:
        for it in g.get("items", []):
            pos = "相關"
            for line in it.get("md", "").splitlines():
                m = re.match(r"^##\s*(上游|中游|下游|相關公司)", line)
                if m:
                    pos = m.group(1).replace("相關公司", "相關")
                    continue
                m = re.match(r"^-\s*\*\*(\d{4,6})\s", line)
                if m:
                    lst = out.setdefault(m.group(1), [])
                    if not any(x["theme"] == it["name"] for x in lst):
                        lst.append({"theme": it["name"], "group": g["group"], "pos": pos})
    return out


def _slim(r: dict, market: str) -> dict:
    o = {k: r.get(k) for k in KEEP if r.get(k) is not None}
    o["region"] = market
    return o


def collect(errors: list[str]) -> dict:
    rows, meta = [], {}
    for region, url in (("美股", ZSIGMA_US), ("台股", ZSIGMA_TW)):
        try:
            d = parse_zs_data(fetchers.http_get(url, timeout=40).decode("utf-8", "replace"))
            rows += [_slim(r, region) for r in d.get("rows", [])]
            meta[region] = {"date": d.get("date"), "total": d.get("total"), "intraday": d.get("intraday")}
        except Exception as e:  # noqa: BLE001
            errors.append(f"籌碼結構掃描（{region}）：{str(e)[:120]}")

    chain_n = 0
    try:
        idx = json.loads(fetchers.http_get(CHAIN_INDEX, timeout=40))
        themes = json.loads(fetchers.http_get(CHAIN_THEMES, timeout=40))
        info = {x["t"]: x for x in idx.get("rows", [])}
        chain = parse_chain(themes)
        for r in rows:
            if r["region"] != "台股":
                continue
            x = info.get(r["code"])
            if x:
                r["sector"] = x.get("ind") or r.get("sector")
                if x.get("pe") is not None:
                    r["pe"] = x["pe"]
                chain_n += 1
            if r["code"] in chain:
                r["chain"] = chain[r["code"]]
    except Exception as e:  # noqa: BLE001
        errors.append(f"semi_value_chain 供應鏈資料：{str(e)[:120]}")

    return {"rows": rows, "meta": meta, "chain_link": CHAIN_BASE, "chain_matched": chain_n,
            "sources": {"美股": ZSIGMA_US, "台股": ZSIGMA_TW}}


def news_mentions(rows: list[dict], news_items: list[dict]) -> None:
    """台股：中文新聞標題直接提到公司名稱（≥2 字）即計一次。"""
    zh = [n["title"] for n in news_items if n.get("lang") == "zh"]
    if not zh:
        return
    for r in rows:
        if r["region"] != "台股":
            continue
        name = r.get("name", "")
        if len(name) < 2:
            continue
        c = sum(1 for t in zh if name in t)
        if c:
            r["news"] = c
