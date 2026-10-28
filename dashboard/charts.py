"""流動性 / 利率 / 估值動態圖表資料（web/charts.js 繪製）。

每個 panel 由一到多張共用時間軸的子圖組成；同一張子圖只有一個 y 軸（不同量級拆成上下子圖）。
顏色依固定順序取自已驗證的類別色盤，不循環。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from . import fetchers

# 類別色盤（固定順序，已通過 validate_palette.js 檢查，背景 #f6f5f1）
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"]

CHART_FRED = ["IORB", "EFFR", "SOFR", "RRPONTSYAWARD", "DFEDTARU", "DFEDTARL", "RPONTSYD", "WALCL", "WTREGEN",
              "RRPONTSYD", "WRESBAL", "DGS3MO", "DGS2", "DGS10", "DGS30", "T10Y2Y", "BAMLH0A0HYM2", "BAMLC0A0CM", "VIXCLS"]
YEARS = 3


def _cut(series, years=YEARS):
    start = (datetime.now() - timedelta(days=365 * years + 10)).strftime("%Y-%m-%d")
    return [[d, round(v, 4)] for d, v in series if d >= start]


def _scale(series, k):
    return [[d, round(v * k, 4)] for d, v in series]


def _s(name, color, data, kind="line"):
    return {"name": name, "color": color, "type": kind, "data": data}


def multpl_table(path: str) -> list[tuple[str, float]]:
    """multpl.com 月表（S&P 500 本益比、Shiller CAPE）。"""
    page = fetchers.http_get(f"https://www.multpl.com/{path}/table/by-month", timeout=25).decode("utf-8", "replace")
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        txt = fetchers.clean_html(row)
        m = re.search(r"([A-Z][a-z]{2} \d{1,2}, \d{4})\s+(?:[^\d]*?)([\d,]+\.\d+)", txt)
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(1), "%b %d, %Y").strftime("%Y-%m-%d")
            out.append((d, float(m.group(2).replace(",", ""))))
        except ValueError:
            continue
    out.sort()
    if not out:
        raise RuntimeError(f"multpl {path}: 無資料")
    return out


def build(fred: dict, yahoo: dict, valuation: dict, fwd_pe: dict | None) -> dict:
    g = lambda k: fred.get(k) or []  # noqa: E731
    panels = []

    # 01 Fed 利率走廊
    panels.append({
        "id": "corridor", "no": "01", "title": "Fed 利率走廊", "subtitle": "SRF 動用量 × 利率走廊",
        "charts": [
            {"unit": "%", "height": 250, "series": [
                _s("準備金利率（IORB，走廊實質上緣）", C[0], _cut(g("IORB")), "step"),
                _s("聯邦資金有效利率（EFFR）", C[1], _cut(g("EFFR"))),
                _s("擔保隔夜融資利率（SOFR）", C[2], _cut(g("SOFR"))),
                _s("ON RRP 利率（走廊下緣）", C[3], _cut(g("RRPONTSYAWARD")), "step"),
                _s("SRF 利率（走廊名目上緣）", C[4], _cut(g("DFEDTARU")), "step"),
            ]},
            {"unit": "十億美元", "height": 90, "series": [
                _s("SRF 動用量", C[1], _cut(g("RPONTSYD")), "bar"),
            ]},
        ],
        "defs": [
            ("IORB", "Fed 付給銀行準備金的利率，銀行不會以低於此利率把資金借出，實務上是聯邦資金利率的上緣。"),
            ("EFFR", "銀行間無擔保隔夜拆借的加權平均利率，Fed 政策目標利率。"),
            ("SOFR", "以美國公債為擔保的隔夜附買回利率，反映短期美元資金的實際成本；高於 IORB 代表資金偏緊。"),
            ("ON RRP 利率", "貨幣基金等機構把資金存放在 Fed 的利率，構成走廊下緣。"),
            ("SRF 利率 / 動用量", "常備附買回工具：機構可用公債向 Fed 換取現金的利率（目標區間上限）。動用量放大＝市場資金緊張。"),
        ],
    })

    # 02 Fed 資產負債表與淨流動性
    walcl = {d: v / 1000 for d, v in g("WALCL")}  # 百萬 → 十億
    tga = dict(g("WTREGEN"))
    rrp = dict(g("RRPONTSYD"))
    net = []
    last_tga = last_rrp = None
    for d in sorted(set(walcl) | set(tga) | set(rrp)):
        last_tga = tga.get(d, last_tga)
        last_rrp = rrp.get(d, last_rrp)
        if d in walcl and last_tga is not None and last_rrp is not None:
            net.append((d, walcl[d] - last_tga - last_rrp))
    panels.append({
        "id": "netliq", "no": "02", "title": "Fed 淨流動性", "subtitle": "資產負債表 − TGA − ON RRP",
        "charts": [
            {"unit": "十億美元", "height": 220, "series": [
                _s("淨流動性（WALCL − TGA − ON RRP）", C[0], _cut(net)),
                _s("銀行準備金（WRESBAL）", C[1], _cut(g("WRESBAL"))),
            ]},
            {"unit": "十億美元", "height": 130, "series": [
                _s("財政部一般帳戶（TGA）", C[2], _cut(g("WTREGEN"))),
                _s("ON RRP 使用量", C[3], _cut(g("RRPONTSYD"))),
            ]},
        ],
        "defs": [
            ("淨流動性", "Fed 總資產扣除財政部存款（TGA）與逆回購（ON RRP），常用來衡量流入金融市場的美元流動性。"),
            ("TGA", "財政部在 Fed 的存款帳戶；發債補庫存時會從市場抽走流動性。"),
            ("ON RRP", "貨幣基金停放在 Fed 的閒置資金；下降代表資金回流市場。"),
            ("準備金", "銀行存放在 Fed 的準備金；過低時易發生資金市場壓力（如 2019 年 9 月）。"),
        ],
    })

    # 03 殖利率曲線
    panels.append({
        "id": "curve", "no": "03", "title": "美債殖利率曲線", "subtitle": "各天期殖利率 × 10Y−2Y 利差",
        "charts": [
            {"unit": "%", "height": 230, "series": [
                _s("3 個月", C[0], _cut(g("DGS3MO"))),
                _s("2 年", C[1], _cut(g("DGS2"))),
                _s("10 年", C[2], _cut(g("DGS10"))),
                _s("30 年", C[3], _cut(g("DGS30"))),
            ]},
            {"unit": "bp", "height": 110, "series": [
                _s("10Y − 2Y 利差", C[6], _cut(_scale(g("T10Y2Y"), 100))),
            ]},
        ],
        "defs": [
            ("10Y−2Y", "長短天期利差；倒掛（< 0）代表緊縮，倒掛結束後的牛陡常伴隨衰退與股市修正。"),
        ],
    })

    # 04 信用利差
    panels.append({
        "id": "credit", "no": "04", "title": "信用利差", "subtitle": "高收益債 × 投資級債 OAS",
        "charts": [
            {"unit": "bp", "height": 200, "series": [
                _s("高收益債 OAS", C[0], _cut(_scale(g("BAMLH0A0HYM2"), 100))),
            ]},
            {"unit": "bp", "height": 130, "series": [
                _s("投資級債 OAS", C[1], _cut(_scale(g("BAMLC0A0CM"), 100))),
            ]},
        ],
        "defs": [
            ("OAS", "選擇權調整利差：公司債相對美國公債的額外收益率。高收益債 > 450bp 警戒、> 520bp 危機。"),
        ],
    })

    # 05 S&P 500 估值
    pe = valuation.get("pe") or []
    cape = valuation.get("cape") or []
    y10 = dict(g("DGS10"))
    erp = []
    for d, v in pe:
        ys = [y for dd, y in g("DGS10") if dd <= d][-1:] if y10 else []
        if ys and v:
            erp.append((d, 100 / v - ys[0]))
    kpis = []
    if pe:
        kpis.append({"label": "本益比（TTM）", "value": f"{pe[-1][1]:.1f}x", "asof": pe[-1][0], "src": "multpl.com"})
    if fwd_pe and fwd_pe.get("value"):
        kpis.append({"label": "預估本益比（NTM）", "value": f"{float(fwd_pe['value']):.1f}x", "asof": fwd_pe.get("asof"),
                     "src": fwd_pe.get("note", "")})
    if cape:
        kpis.append({"label": "Shiller CAPE", "value": f"{cape[-1][1]:.1f}x", "asof": cape[-1][0], "src": "multpl.com"})
    if erp:
        kpis.append({"label": "盈餘殖利率 − 10Y", "value": f"{erp[-1][1]:+.2f}%", "asof": erp[-1][0], "src": "1/PE(TTM) − DGS10"})
    panels.append({
        "id": "valuation", "no": "05", "title": "S&P 500 估值", "subtitle": "本益比 × 預估本益比 × 股權風險溢酬",
        "kpis": kpis, "years": 10,
        "charts": [
            {"unit": "倍", "height": 220, "series": [
                _s("本益比（TTM）", C[0], _cut(pe, 10)),
                _s("Shiller CAPE", C[1], _cut(cape, 10)),
            ]},
            {"unit": "%", "height": 120, "series": [
                _s("盈餘殖利率 − 10Y（TTM 口徑）", C[2], _cut(erp, 10)),
            ]},
        ],
        "defs": [
            ("本益比（TTM）", "股價 ÷ 過去 12 個月實際每股盈餘。"),
            ("預估本益比（NTM）", "股價 ÷ 未來 12 個月分析師預估每股盈餘；> 21x 一級警訊、> 22.5x 二級警訊。"),
            ("Shiller CAPE", "股價 ÷ 過去 10 年經通膨調整的平均盈餘，衡量長期估值。"),
            ("盈餘殖利率 − 10Y", "股票盈餘殖利率減 10 年期美債殖利率；越低代表股票相對債券越貴。"),
        ],
    })

    # 06 風險情緒
    vix = _cut(g("VIXCLS"))
    dxy = yahoo.get("DX-Y.NYB")
    panels.append({
        "id": "risk", "no": "06", "title": "風險情緒", "subtitle": "VIX × 美元指數",
        "charts": [
            {"unit": "", "height": 180, "series": [_s("VIX 波動率指數", C[0], vix)]},
            {"unit": "", "height": 150, "series": [_s("美元指數 DXY", C[1], _cut(list(zip(dxy["dates"], dxy["close"])) if dxy else []))]},
        ],
        "defs": [
            ("VIX", "S&P 500 選擇權隱含波動率；22–28 定價分歧、> 35 恐慌拋售。"),
            ("DXY", "美元對一籃子主要貨幣；跌破 98 且破年線代表美元轉弱。"),
        ],
    })

    for p in panels:
        p["defs"] = [{"term": t, "text": x} for t, x in p["defs"]]
        for ch in p["charts"]:
            ch["series"] = [s for s in ch["series"] if s["data"]]
        p["charts"] = [ch for ch in p["charts"] if ch["series"]]
    return {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "panels": [p for p in panels if p["charts"]]}


# ---------------------------------------------------------------- 指標監控圖表（含分級門檻線）
def _yh(yahoo, sym):
    h = yahoo.get(sym)
    return list(zip(h["dates"], h["close"])) if h else []


def _ref(v, label, lv):
    return {"v": v, "label": label, "lv": lv}


def build_monitor(fred: dict, yahoo: dict) -> list[dict]:
    g = lambda k: fred.get(k) or []  # noqa: E731
    cpi = g("CPIAUCSL")
    cpi_yoy = [(cpi[i][0], (cpi[i][1] / cpi[i - 12][1] - 1) * 100) for i in range(12, len(cpi))]
    effr, y1 = dict(g("EFFR")), g("DGS1")
    pivot, last = [], None
    for d, v in y1:
        last = effr.get(d, last)
        if last is not None:
            pivot.append((d, max(0.0, (last - v) * 200)))
    eq, gdp = g("NCBEILQ027S"), dict(g("GDP"))
    buffett = [(d, v / 1000 / gdp[d] * 100) for d, v in eq if gdp.get(d)]
    tw = yahoo.get("^TWII")
    bias = []
    if tw and len(tw["close"]) > 240:
        c = tw["close"]
        bias = [(tw["dates"][i], (c[i] / (sum(c[i - 239:i + 1]) / 240) - 1) * 100) for i in range(239, len(c))]
    gold = _yh(yahoo, "GC=F")
    gold_m1 = [(gold[i][0], (gold[i][1] / gold[i - 21][1] - 1) * 100) for i in range(21, len(gold))]
    vix = g("VIXCLS") or _yh(yahoo, "^VIX")

    def ch(key, title, unit, data, color, refs, years=3, kind="line"):
        return {"key": key, "title": title, "unit": unit, "height": 170, "refs": refs,
                "series": [_s(title, color, _cut(data, years), kind)]}

    panels = [
        {"id": "m-macro", "no": "M1", "title": "總經 / 利率", "subtitle": "門檻線：橘＝一級警戒、紅＝二級危機",
         "charts": [
             ch("cpi_yoy", "美國 CPI 年增率", "%", cpi_yoy, C[0], [_ref(3.2, "降溫 3.2%", 0), _ref(3.8, "偏鷹 3.8%", 2)], 6),
             ch("us10y", "美國 10 年期公債殖利率", "%", g("DGS10"), C[1], [_ref(5.0, "一級 5.0%", 1), _ref(5.35, "二級 5.35%", 2)]),
             ch("fed_pivot", "隱含 12 個月降息幅度（2×(EFFR−1Y)）", "bp", pivot, C[2], [_ref(50, "轉向 50bp", 1)]),
             ch("bei5", "5 年期平衡通膨率", "%", g("T5YIE"), C[3], [_ref(2.6, "警戒 2.6%", 1), _ref(3.0, "失錨 3.0%", 2)]),
             ch("sahm", "薩姆規則衰退指標", "%", g("SAHMREALTIME"), C[4], [_ref(0.35, "警戒 0.35", 1), _ref(0.5, "衰退 0.50", 2)], 6),
             ch("curve_10y2y", "10Y−2Y 殖利率利差", "bp", _scale(g("T10Y2Y"), 100), C[6], [_ref(0, "倒掛 0", 1)]),
         ]},
        {"id": "m-credit", "no": "M2", "title": "信用 / 流動性", "subtitle": "高收益債利差與波動率",
         "charts": [
             ch("hy_oas", "ICE BofA 美國高收益債 OAS", "bp", _scale(g("BAMLH0A0HYM2"), 100), C[0], [_ref(450, "警戒 450", 1), _ref(520, "危機 520", 2)]),
             ch("vix", "VIX 波動率指數", "", vix, C[1], [_ref(22, "分歧 22", 1), _ref(35, "恐慌 35", 2)]),
         ]},
        {"id": "m-val", "no": "M3", "title": "美股評價 / 台股動能", "subtitle": "長期估值錨與年線乖離",
         "charts": [
             ch("buffett", "巴菲特指標（股權市值 / GDP）", "%", buffett, C[0], [_ref(170, "過熱 170%", 1), _ref(200, "極端 200%", 2)], 8),
             ch("taiex_bias", "台股加權指數 240 日乖離率", "%", bias, C[1], [_ref(25, "一級 +25%", 1), _ref(35, "二級 +35%", 2), _ref(-10, "−10%", 0)], 2),
         ]},
        {"id": "m-geo", "no": "M4", "title": "地緣 / 外匯 / 商品", "subtitle": "油價、美元與避險需求",
         "charts": [
             ch("brent", "Brent 原油期貨", "USD", _yh(yahoo, "BZ=F"), C[0], [_ref(70, "停火確認 70", 0), _ref(90, "警戒 90", 1), _ref(100, "滯脹 100", 2)], 2),
             ch("dxy", "美元指數 DXY", "", _yh(yahoo, "DX-Y.NYB"), C[1], [_ref(98, "一級 98", 1), _ref(94, "二級 94", 2)], 2),
             ch("gold", "黃金 1 個月漲幅", "%", gold_m1, C[2], [_ref(8, "升溫 8%", 1), _ref(15, "極端 15%", 2)], 2),
         ]},
    ]
    for p in panels:
        p["charts"] = [c for c in p["charts"] if c["series"][0]["data"]]
        p["defs"] = []
        p["years"] = max([8 if c["key"] == "buffett" else 6 if c["key"] in ("cpi_yoy", "sahm") else 3 for c in p["charts"]] or [3])
    return [p for p in panels if p["charts"]]


# ---------------------------------------------------------------- 市場概況圖表（指數化＝100）
def build_overview(yahoo: dict) -> list[dict]:
    from .universe import META

    def grp(pid, no, title, sub, syms):
        series = [_s(META.get(s, {}).get("name", s), C[i], _cut(_yh(yahoo, s), 2)) for i, s in enumerate(syms) if yahoo.get(s)]
        return {"id": pid, "no": no, "title": title, "subtitle": sub, "years": 2, "defs": [],
                "charts": [{"unit": "", "height": 300, "index": True, "series": series}]}

    panels = [
        grp("o-eq-a", "O1", "美國與台灣股市", "以區間起點＝100 指數化", ["^GSPC", "^NDX", "^SOX", "^TWII"]),
        grp("o-eq-b", "O2", "亞洲與歐洲股市", "以區間起點＝100 指數化", ["^N225", "^KS11", "^HSI", "000001.SS", "^STOXX50E", "^BSESN"]),
        grp("o-cmd", "O3", "商品與加密資產", "以區間起點＝100 指數化", ["BZ=F", "GC=F", "HG=F", "BTC-USD"]),
        grp("o-fx", "O4", "匯率", "以區間起點＝100 指數化（數值上升＝美元走強）", ["DX-Y.NYB", "TWD=X", "JPY=X", "CNY=X"]),
    ]
    return [p for p in panels if p["charts"][0]["series"]]
