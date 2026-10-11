"""跨市場情境矩陣（PDF 第四章）與多因子共振判定（PDF 第五章）。"""
from __future__ import annotations

ALLOC_ROWS = ["美股", "台股", "長天期公債／高評級 IG 債", "非投資等級債", "現金／超短期國庫券", "黃金與大宗商品"]
BASELINE = {"name": "基準配置（常態）", "alloc": [35, 25, 20, 10, 5, 5],
            "tools": ["S&P 500、大型權值", "台灣 50、半導體", "7–10 年 IG 債、LQD", "高收益債", "貨幣市場基金", "實體黃金、GLD"],
            "hedge": "無"}

SCENARIOS = [
    {
        "id": "goldilocks", "name": "情境一：常態擴張與軟著陸", "en": "Goldilocks Expansion",
        "alloc": [40, 30, 15, 10, 2, 3],
        "tools": ["科技巨頭、成長 ETF", "先進製程、AI 供應鏈", "投資級公司債基金", "獲取息收", "活存、短期商業本票", "黃金 ETF"],
        "hedge": "無需額外對沖",
        "conds": [
            ("ism_pmi", "ISM 50–55", lambda v: 50 <= v <= 55),
            ("cpi_yoy", "CPI ≤3.2%", lambda v: v <= 3.2),
            ("sahm", "Sahm <0.3%", lambda v: v < 0.3),
            ("ndc_signal", "景氣綠燈 23–31", lambda v: 23 <= v <= 31),
            ("erp", "ERP >1.5%", lambda v: v > 1.5),
            ("taiex_bias", "年線乖離 <20%", lambda v: v < 20),
            ("hy_oas", "HY OAS <400bp", lambda v: v < 400),
            ("vix", "VIX <20", lambda v: v < 20),
        ],
    },
    {
        "id": "overheat", "name": "情境二：市場過熱與估值壓縮", "en": "Valuation Compression & Bear Steepening",
        "alloc": [25, 15, 10, 5, 35, 10],
        "tools": ["價值股、低波動、PGN", "高股息 ETF、低 Beta", "1–3 年短期 IG 債", "利差警戒減碼", "SGOV、BIL、台幣短票", "原油 USO、銅 COPX"],
        "hedge": "建立台指期空單對沖 Beta",
        "conds": [
            ("spx_pe", "P/E >22.5x", lambda v: v > 22.5),
            ("erp", "ERP <0.5%", lambda v: v < 0.5),
            ("buffett", "巴菲特指標 >200%", lambda v: v > 200),
            ("taiex_bias", "年線乖離 >25%", lambda v: v > 25),
            ("ndc_signal", "景氣紅燈 ≥38", lambda v: v >= 38),
            ("us10y", "10Y >5.0%", lambda v: v > 5.0),
            ("breadth", "廣度 >85%", lambda v: v > 85),
        ],
    },
    {
        "id": "recession", "name": "情境三：景氣衰退與被動去槓桿", "en": "Recessionary Bear & Bull Steepening",
        "alloc": [20, 10, 40, 0, 25, 5],
        "tools": ["防禦板塊（公用、醫療）", "逆景氣藍燈分批買進金控", "TLT、IEF、美國公債 ETF", "全面清空", "SGOV、美元定存", "GLD、黃金基金"],
        "hedge": "S&P 500 深度價外 Put 對沖尾部風險",
        "conds": [
            ("sahm", "Sahm ≥0.5%", lambda v: v >= 0.5),
            ("ism_pmi", "ISM <45", lambda v: v < 45),
            ("curve_10y2y", "牛陡解除倒掛", None),  # 以 level==2 判定
            ("hy_oas", "HY OAS >520bp", lambda v: v > 520),
            ("margin_ratio", "融資維持率 <135%", lambda v: v < 135),
            ("csp_capex", "CSP 資本支出下修 >10%", lambda v: v < -10),
            ("vix", "VIX >35", lambda v: v > 35),
        ],
    },
    {
        "id": "stagflation", "name": "情境四：地緣衝突與滯脹衝擊", "en": "Geopolitical Stagflation Shock",
        "alloc": [20, 10, 10, 0, 35, 25],
        "tools": ["能源、國防、抗通膨題材", "內需公共事業、高現金流", "超短端國庫券、浮動利率票券", "全面清空", "美元現金、瑞郎", "GLD、IAU、能源期貨"],
        "hedge": "買入台指期 Put、台幣 NDF",
        "conds": [
            ("brent", "Brent >90", lambda v: v > 90),
            ("twd_vol", "台幣波動 ≥3σ", lambda v: v >= 3),
            ("tw_cds", "台灣 CDS 急升", lambda v: v > 20),
            ("cpi_yoy", "CPI ≥3.8%", lambda v: v >= 3.8),
            ("gold", "黃金急漲", None),  # level>=1
            ("vix", "VIX >28", lambda v: v > 28),
        ],
    },
]

# 多因子共振：三大獨立維度各至少一項跨越警戒才確認體制切換
RESONANCE = {
    "macro": ("總體環境維度", ["ism_pmi", "sahm", "curve_10y2y", "cpi_yoy", "csp_capex", "export_orders"]),
    "valuation": ("評價與市場動能維度", ["erp", "spx_pe", "buffett", "ndc_signal", "taiex_bias", "breadth"]),
    "credit": ("信貸與流動性維度", ["hy_oas", "coreweave_cds", "margin_ratio", "vix", "foreign_fut"]),
}


def evaluate(ind_rows: list[dict]) -> dict:
    by = {r["key"]: r for r in ind_rows}
    results = []
    for sc in SCENARIOS:
        met, total, details = 0, 0, []
        for key, label, fn in sc["conds"]:
            r = by.get(key)
            if not r or r["value"] is None:
                details.append({"label": label, "state": "na"})
                continue
            total += 1
            if fn is None:
                ok = (r["level"] or 0) >= (2 if key == "curve_10y2y" else 1)
            else:
                ok = bool(fn(r["value"]))
            met += ok
            details.append({"label": label, "state": "hit" if ok else "miss"})
        results.append({"id": sc["id"], "name": sc["name"], "en": sc["en"], "alloc": sc["alloc"], "tools": sc["tools"],
                        "hedge": sc["hedge"], "met": met, "total": total,
                        "score": round(met / total * 100) if total else 0, "details": details})
    best = max(results, key=lambda x: (x["score"], x["met"]))
    res = {}
    for dim, (name, keys) in RESONANCE.items():
        alerts = [by[k]["label"] + "｜" + by[k]["metric"] for k in keys if k in by and (by[k]["level"] or 0) >= 1]
        avail = sum(1 for k in keys if k in by and by[k]["level"] is not None)
        res[dim] = {"name": name, "alerts": alerts, "available": avail, "total": len(keys), "triggered": bool(alerts)}
    confirmed = all(v["triggered"] for v in res.values())
    return {"scenarios": results, "best": best["id"], "resonance": res, "regime_confirmed": confirmed,
            "alloc_rows": ALLOC_ROWS, "baseline": BASELINE}
