"""彙整所有資料 → 單一 JSON（前端 web/index.html 讀取）。"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import autofill, fetchers, indicators, market, news, scenarios, screener
from .themes import THEMES
from .universe import META, OVERVIEW, UNIVERSE

ROOT = Path(__file__).resolve().parent.parent
MANUAL_PATH = ROOT / "config" / "manual_indicators.json"

FRED_IDS = ["EFFR", "DGS1", "DGS2", "DGS10", "CPIAUCSL", "T5YIE", "SAHMREALTIME", "T10Y2Y",
            "BAMLH0A0HYM2", "NCBEILQ027S", "GDP"]

TPE = timezone(timedelta(hours=8))


def load_manual() -> dict:
    try:
        return json.loads(MANUAL_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _yahoo_all(get, errors):
    out = {}
    syms = [u[0] for u in UNIVERSE]

    def one(s):
        try:
            return s, get(s)
        except Exception as e:  # noqa: BLE001
            return s, e

    with ThreadPoolExecutor(max_workers=10) as ex:
        for s, res in ex.map(one, syms):
            if isinstance(res, Exception):
                errors.append(f"行情 {s}：{str(res)[:100]}")
            else:
                out[s] = res
    return out


def _fred_all(get, errors):
    out = {}

    def one(s):
        try:
            return s, get(s)
        except Exception as e:  # noqa: BLE001
            return s, e

    with ThreadPoolExecutor(max_workers=6) as ex:
        for s, res in ex.map(one, FRED_IDS):
            if isinstance(res, Exception):
                errors.append(f"FRED {s}：{str(res)[:100]}")
            else:
                out[s] = res
    return out


def collect(demo: bool = False) -> dict:
    t0 = time.time()
    errors: list[str] = []
    if demo:
        from . import demo as dm
        yahoo = {s: dm.yahoo_history(s) for s, *_ in UNIVERSE}
        fred = {s: dm.fred_series(s) for s in FRED_IDS}
        news_items = [news.tag_item(i) for i in dm.news_items()]
        theme_sum = news.summarize(news_items)
        mk = dm.market()
    else:
        with ThreadPoolExecutor(max_workers=4) as ex:
            fy = ex.submit(_yahoo_all, fetchers.yahoo_history, errors)
            ff = ex.submit(_fred_all, fetchers.fred_series, errors)
            fn = ex.submit(news.collect)
            fm = ex.submit(market.collect, errors)
            yahoo, fred = fy.result(), ff.result()
            news_items, theme_sum, nerr = fn.result()
            errors.extend(nerr)
            mk = fm.result()

    # FRED 失敗時，10 年期殖利率以 Yahoo ^TNX 備援
    if "DGS10" not in fred and "^TNX" in yahoo:
        h = yahoo["^TNX"]
        fred["DGS10"] = list(zip(h["dates"], h["close"]))
        errors.append("FRED DGS10 改用 Yahoo ^TNX 備援")

    manual = load_manual()
    if not demo:
        manual = autofill.merge(manual, autofill.collect(yahoo, errors))
    market.news_mentions(mk["rows"], news_items)
    nscore = news.ticker_news_scores(news_items)

    # 標的 → 相關主題
    sym_themes: dict[str, list[str]] = {}
    for th in THEMES:
        for s in th["up_benefit"] + th["up_hurt"]:
            sym_themes.setdefault(s, []).append(th["id"])

    rows = []
    for sym, h in yahoo.items():
        if len(h["close"]) < 30:
            continue
        m = META[sym]
        row = {"symbol": sym, **m, "currency": h.get("currency", ""), **screener.metrics(h),
               "news": round(nscore.get(sym, 0), 1), "themes": sym_themes.get(sym, [])}
        rows.append(row)
    screener.score_all(rows)
    for r in rows:
        for k, v in list(r.items()):
            if isinstance(v, float):
                r[k] = round(v, 4 if k == "last" else 2)

    ctx = indicators.Ctx(yahoo, fred, manual)
    ind_rows = indicators.build(ctx)
    ind_rows.append(indicators.breadth_row(rows))
    sc = scenarios.evaluate(ind_rows)

    by_sym = {r["symbol"]: r for r in rows}
    overview = [by_sym[s] for s in OVERVIEW if s in by_sym]

    now = datetime.now(timezone.utc)
    return {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_at_tpe": now.astimezone(TPE).strftime("%Y-%m-%d %H:%M"),
        "demo": demo,
        "elapsed_sec": round(time.time() - t0, 1),
        "counts": {"tickers": len(rows), "universe": len(UNIVERSE), "news": len(news_items), "market": len(mk["rows"]),
                   "fred": len(fred), "fred_total": len(FRED_IDS)},
        "groups": indicators.GROUPS,
        "indicators": ind_rows,
        "scenario": sc,
        "overview": overview,
        "screener": rows,
        "themes": theme_sum,
        "theme_names": {t["id"]: t["name"] for t in THEMES},
        "news": news_items,
        "market": mk,
        "names": {s: m["name"] for s, m in META.items()},
        "manual_asof": {k: v.get("asof") for k, v in manual.items() if isinstance(v, dict)},
        "errors": errors[:80],
        "error_count": len(errors),
    }


def write_all(folder: Path, data: dict) -> None:
    """data.json（主資料）＋ market.json（台美全市場，體積大、前端延遲載入）。"""
    data = dict(data)
    mk = data.pop("market", None) or {"rows": []}
    data["market_meta"] = {k: v for k, v in mk.items() if k != "rows"} | {"count": len(mk["rows"])}
    write(folder / "market.json", mk)
    write(folder / "data.json", data)


def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)
