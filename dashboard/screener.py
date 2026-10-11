"""全市場技術面 / 動能篩選指標計算。"""
from __future__ import annotations

import math
from datetime import datetime


def pct(a, b):
    return (a / b - 1) * 100 if a is not None and b else None


def sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


def rsi(xs, n=14):
    if len(xs) <= n:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = xs[i] - xs[i - 1]
        gains += max(d, 0); losses += max(-d, 0)
    ag, al = gains / n, losses / n
    for i in range(n + 1, len(xs)):
        d = xs[i] - xs[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def ann_vol(xs, n=20):
    if len(xs) <= n:
        return None
    r = [math.log(xs[i] / xs[i - 1]) for i in range(len(xs) - n, len(xs)) if xs[i - 1] > 0]
    if len(r) < 2:
        return None
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252) * 100


def spark(xs, n=60, points=30):
    s = xs[-n:]
    if len(s) <= points:
        return [round(x, 4) for x in s]
    step = (len(s) - 1) / (points - 1)
    return [round(s[round(i * step)], 4) for i in range(points)]


def metrics(hist: dict) -> dict:
    c, d = hist["close"], hist["dates"]
    last = c[-1]
    year = datetime.now().year
    ytd_base = next((c[i - 1] for i in range(1, len(d)) if d[i].startswith(str(year)) and not d[i - 1].startswith(str(year))), None)
    ma200, ma240 = sma(c, 200), sma(c, 240)
    hi52 = max(c[-252:])
    return {
        "last": last,
        "asof": d[-1],
        "chg1d": pct(last, c[-2]) if len(c) > 1 else None,
        "chg5d": pct(last, c[-6]) if len(c) > 5 else None,
        "chg1m": pct(last, c[-22]) if len(c) > 21 else None,
        "chg3m": pct(last, c[-64]) if len(c) > 63 else None,
        "chg6m": pct(last, c[-127]) if len(c) > 126 else None,
        "chg1y": pct(last, c[-253]) if len(c) > 252 else None,
        "ytd": pct(last, ytd_base),
        "above200": (last > ma200) if ma200 else None,
        "bias240": pct(last, ma240),
        "rsi14": rsi(c[-120:]),
        "from_high": pct(last, hi52),
        "vol20": ann_vol(c),
        "spark": spark(c),
    }


def _pct_rank(values: dict[str, float]) -> dict[str, float]:
    items = sorted((v, k) for k, v in values.items() if v is not None)
    n = len(items)
    return {k: (i / (n - 1) * 100 if n > 1 else 50) for i, (v, k) in enumerate(items)}


def score_all(rows: list[dict]) -> None:
    """綜合分數 = 動能百分位（1M/3M/6M 平均）×0.7 + 新聞分數百分位 ×0.3，站上 200MA 加 5 分。"""
    tradable = [r for r in rows if r["asset"] not in ("指數",)]
    ranks = {k: _pct_rank({r["symbol"]: r.get(k) for r in tradable}) for k in ("chg1m", "chg3m", "chg6m")}
    news_vals = {r["symbol"]: r.get("news") or 0 for r in tradable}
    nz = {k: v for k, v in news_vals.items() if v}
    news_rank = _pct_rank(nz)
    for r in rows:
        s = r["symbol"]
        parts = [ranks[k][s] for k in ranks if s in ranks[k]]
        mom = sum(parts) / len(parts) if parts else None
        r["momentum"] = round(mom, 1) if mom is not None else None
        if mom is None:
            r["score"] = None
            continue
        nr = news_rank.get(s, 50.0)
        sc = mom * 0.7 + nr * 0.3 + (5 if r.get("above200") else 0)
        r["score"] = round(min(sc, 100), 1)
