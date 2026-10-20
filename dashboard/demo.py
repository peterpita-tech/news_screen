"""離線示範資料（--demo）：隨機漫步行情與範例新聞，僅供版面預覽與測試，非真實行情。"""
from __future__ import annotations

import hashlib
import math
import random
from datetime import datetime, timedelta, timezone

BASE = {"^GSPC": 6700, "^NDX": 24500, "^SOX": 6800, "^TWII": 26500, "^N225": 46000, "^KS11": 3500,
        "^HSI": 26000, "000001.SS": 3800, "^STOXX50E": 5600, "^VIX": 17, "DX-Y.NYB": 97.5, "BZ=F": 66,
        "GC=F": 3900, "BTC-USD": 118000, "TWD=X": 30.4, "JPY=X": 150, "2330.TW": 1400, "CRWV": 130}


def _rng(key):
    return random.Random(int(hashlib.md5(key.encode()).hexdigest()[:8], 16))


def _dates(n):
    d, out = datetime.now(), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.strftime("%Y-%m-%d"))
        d -= timedelta(days=1)
    return out[::-1]


def yahoo_history(sym):
    rng = _rng(sym)
    n = 500
    drift = rng.uniform(-0.0004, 0.0014)
    vol = 0.006 if sym.startswith(("^", "DX", "TWD", "JPY", "EUR", "CNY", "CHF")) else rng.uniform(0.01, 0.028)
    end = BASE.get(sym, rng.uniform(20, 600))
    xs = [1.0]
    for _ in range(n - 1):
        xs.append(xs[-1] * math.exp(drift + vol * rng.gauss(0, 1)))
    scale = end / xs[-1]
    return {"symbol": sym, "name": sym, "currency": "USD", "dates": _dates(n), "close": [x * scale for x in xs]}


FRED_LEVEL = {"EFFR": (4.1, 0.01), "DGS1": (3.6, 0.02), "DGS2": (3.5, 0.03), "DGS10": (4.15, 0.04),
              "T5YIE": (2.4, 0.02), "T10Y2Y": (0.62, 0.03), "BAMLH0A0HYM2": (2.95, 0.04)}


def fred_series(sid):
    rng = _rng(sid)
    if sid == "CPIAUCSL":
        v, out = 300.0, []
        for i in range(36):
            v *= 1 + rng.uniform(0.0015, 0.0032)
            out.append(((datetime.now() - timedelta(days=30 * (36 - i))).strftime("%Y-%m-01"), v))
        return out
    if sid == "SAHMREALTIME":
        return [((datetime.now() - timedelta(days=30 * (24 - i))).strftime("%Y-%m-01"), round(0.1 + 0.01 * i, 2)) for i in range(24)]
    if sid in ("NCBEILQ027S", "GDP"):
        base = 64_000_000 if sid == "NCBEILQ027S" else 31_000
        return [((datetime.now() - timedelta(days=91 * (8 - i))).strftime("%Y-%m-01"), base * (1 + 0.01 * i)) for i in range(8)]
    lvl, vol = FRED_LEVEL[sid]
    dates = _dates(600)
    xs = [lvl]
    for _ in dates[1:]:
        xs.append(xs[-1] + vol * rng.gauss(0, 1) * 0.5)
    shift = lvl - xs[-1]
    return [(d, x + shift) for d, x in zip(dates, xs)]


HEADLINES = [
    ("Nvidia shares surge as hyperscaler capex guidance raised again", "en"),
    ("Google TPU8 demand boosts Broadcom and MediaTek orders", "en"),
    ("Oil prices fall as ceasefire talks progress in Middle East", "en"),
    ("Fed officials signal rate cuts likely by year-end, Treasury yields drop", "en"),
    ("Gold hits record high as investors seek safe haven", "en"),
    ("China unveils new stimulus to support property market", "en"),
    ("Tariff escalation fears weigh on Asian exporters", "en"),
    ("Micron jumps on strong HBM memory pricing", "en"),
    ("Credit spreads widen as private credit concerns grow", "en"),
    ("Bank of Japan holds rates, yen weakens; Nikkei climbs", "en"),
    ("台積電法說上修全年資本支出 AI伺服器需求強勁", "zh"),
    ("台股加權指數創新高 年線乖離擴大", "zh"),
    ("新台幣升值 外資匯入半導體", "zh"),
    ("聯準會降息預期升溫 美債殖利率走低", "zh"),
    ("油價重挫 航空股受惠", "zh"),
    ("重電族群受惠AI電力需求 華城、士電走高", "zh"),
    ("CoreWeave債務疑慮升溫 AI雲端信用利差擴大", "zh"),
    ("美光、海力士記憶體報價上修 南亞科大漲", "zh"),
]


def news_items():
    now = datetime.now(timezone.utc)
    body = ["（示範內文）這是一段模擬的新聞內文節錄，用來預覽點選標題後直接顯示內文的版面。實際部署時會抓取原始報導的前幾段文字。",
            "第二段示範內文：系統只保留前 4 段、約 700 字的節錄，並附上來源與原文連結，完整內容請點「閱讀原文」。"]
    return [{"title": t, "link": "https://example.com/demo", "source": "示範資料", "lang": lang,
             "time": (now - timedelta(minutes=37 * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "summary": "", "body": body if i % 3 != 2 else []}
            for i, (t, lang) in enumerate(HEADLINES)]


def market():
    rng = _rng("market")
    rows = []
    names = [("2330", "台積電", "上市"), ("3131", "弘塑", "上櫃"), ("3037", "欣興", "上市"), ("8070", "長華", "上市"),
             ("2454", "聯發科", "上市"), ("6664", "群翊", "上櫃")]
    for code, name, mkt in names:
        rows.append({"code": code, "name": name, "mkt": mkt, "region": "台股", "sector": "Semiconductors",
                     "close": round(rng.uniform(50, 1500), 1), "chg": round(rng.gauss(0, 2), 2),
                     "biasMA": round(rng.gauss(2, 6), 2), "winPct": round(rng.uniform(20, 90), 1),
                     "z": round(rng.gauss(0, 1.2), 2), "score": round(rng.uniform(5, 99), 1),
                     "chain": [{"theme": "CoWoS", "group": "先進封裝", "pos": rng.choice(["上游", "中游", "下游", "相關"])}]})
    for code, name, mkt, sec in [("NVDA", "NVIDIA Corp", "NASDAQ", "Technology"), ("AAPL", "Apple Inc", "NASDAQ", "Technology"),
                                 ("JPM", "JPMorgan Chase", "NYSE", "Finance"), ("XOM", "Exxon Mobil", "NYSE", "Energy")]:
        rows.append({"code": code, "name": name, "mkt": mkt, "region": "美股", "sector": sec, "mcap": rng.uniform(1e11, 4e12),
                     "close": round(rng.uniform(50, 900), 2), "chg": round(rng.gauss(0, 2), 2),
                     "biasMA": round(rng.gauss(2, 6), 2), "winPct": round(rng.uniform(20, 90), 1),
                     "z": round(rng.gauss(0, 1.2), 2), "score": round(rng.uniform(5, 99), 1)})
    return {"rows": rows, "meta": {"美股": {"date": "demo"}, "台股": {"date": "demo"}},
            "chain_link": "https://peterpita-tech.github.io/semi_value_chain/web/", "chain_matched": 6,
            "sources": {"美股": "https://peterpita-tech.github.io/Peterpita/", "台股": "https://peterpita-tech.github.io/Peterpita/tw/"}}
