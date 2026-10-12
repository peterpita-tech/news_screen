"""監控指標：依《全球總經與台美股量化監控體系》PDF 與季度檢視表的分級觸發門檻計算狀態。

level：0 = 正常、1 = 一級 / 警戒、2 = 二級 / 危機、None = 無資料（待手動輸入）。
自動來源：FRED（免 key CSV）、Yahoo Finance；無免費公開來源者讀 config/manual_indicators.json。
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from .screener import sma, spark

GROUPS = [
    ("macro", "總經 / 利率"),
    ("credit", "信用 / 流動性"),
    ("us", "美股評價"),
    ("tw", "台股動能 / 籌碼"),
    ("ai", "AI / 科技專項"),
    ("geo", "地緣 / 外匯 / 商品"),
]

# 多因子共振三大維度（PDF 第五章）
DIMENSIONS = {
    "macro": "總體環境維度",
    "valuation": "評價與市場動能維度",
    "credit": "信貸與流動性維度",
    "geo": "地緣 / 外生衝擊",
}


def _f(v, d=2):
    return None if v is None else round(v, d)


def lvl_above(v, l1, l2):
    if v is None:
        return None
    return 2 if v > l2 else 1 if v > l1 else 0


def lvl_below(v, l1, l2):
    if v is None:
        return None
    return 2 if v < l2 else 1 if v < l1 else 0


class Ctx:
    def __init__(self, yahoo: dict, fred: dict, manual: dict):
        self.yahoo, self.fred, self.manual = yahoo, fred, manual

    def fred_vals(self, sid, days=None):
        s = self.fred.get(sid) or []
        if days:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            s = [x for x in s if x[0] >= cutoff]
        return s

    def fred_last(self, sid):
        s = self.fred.get(sid) or []
        return (s[-1][1], s[-1][0]) if s else (None, None)

    def yh(self, sym):
        return self.yahoo.get(sym)

    def man(self, key):
        m = self.manual.get(key) or {}
        return m.get("value"), m.get("asof"), m.get("note", "")


def _fred_at(series, days_ago):
    """回傳約 days_ago 天前的值。"""
    if not series:
        return None
    target = (datetime.strptime(series[-1][0], "%Y-%m-%d") - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    prior = [v for d, v in series if d <= target]
    return prior[-1] if prior else None


def _base(key, group, dim, label, metric, unit, threshold, actions, products, source):
    return {"key": key, "group": group, "dim": dim, "label": label, "metric": metric, "unit": unit,
            "threshold": threshold, "actions": actions, "products": products, "source": source,
            "value": None, "display": "—", "asof": None, "level": None, "status": "無資料", "spark": [],
            "note": "", "signal": "", "signal_action": "", "manual": source.startswith("手動")}


STATUS = {0: "正常", 1: "一級警戒", 2: "二級危機", None: "無資料"}


def _finish(row, value, asof, level, fmt="{:.2f}", status=None, spark_vals=None, note=""):
    row["value"] = _f(value, 4)
    row["display"] = "—" if value is None else fmt.format(value)
    row["asof"] = asof
    row["level"] = level
    row["status"] = status or STATUS[level]
    if row["manual"] and value is None:
        row["status"] = "待輸入"
    if note and note.startswith(("自動", "代理")):
        row["auto"] = True
    if spark_vals:
        row["spark"] = spark_vals
    if note:
        row["note"] = note
    return row


def build(ctx: Ctx) -> list[dict]:
    rows = []
    add = rows.append

    # ---------------------------------------------------------------- 總經 / 利率
    r = _base("fed_pivot", "macro", "macro", "利率週期（轉向）", "Fed 聲明 / SOFR 期貨隱含路徑（代理：2×(EFFR−1Y)）", "bp",
              "轉向：定價未來 12 個月降息 ≥50bp",
              {1: "7–10 年公債／高評級 IG 債增持 5–8%；降低貨幣基金 5–8%", 0: "維持中性存續期"},
              "基金：富達全球優質債券、NB 策略收益｜ETF：LQD、BND、IEF", "FRED:EFFR,DGS1")
    effr, d1 = ctx.fred_last("EFFR")
    y1, _ = ctx.fred_last("DGS1")
    v = max(0.0, (effr - y1) * 2 * 100) if effr is not None and y1 is not None else None
    lv = None if v is None else (1 if v >= 50 else 0)
    add(_finish(r, v, d1, lv, "{:.0f} bp", status={1: "轉向觸發", 0: "未觸發"}.get(lv),
                note="市場隱含降息幅度以 1 年期公債殖利率相對有效聯邦資金利率推估；正式版可改接 CME FedWatch。"))

    r = _base("cpi_yoy", "macro", "macro", "通膨與貨幣政策", "美國 CPI 年增率", "%",
              "偏鷹：≥3.8%｜降溫：≤3.2%",
              {2: "偏鷹：股票降至中性、增持短債", 1: "觀察：維持配置、留意核心通膨", 0: "降溫：長債加碼 5%"},
              "美元貨幣市場基金、短天期投資級債基金、LQD、BND", "FRED:CPIAUCSL")
    s = ctx.fred_vals("CPIAUCSL")
    yoy = [(s[i][0], (s[i][1] / s[i - 12][1] - 1) * 100) for i in range(12, len(s))]
    v, d = (yoy[-1][1], yoy[-1][0]) if yoy else (None, None)
    lv = None if v is None else (2 if v >= 3.8 else 0 if v <= 3.2 else 1)
    add(_finish(r, v, d, lv, "{:.2f}%", status={2: "偏鷹", 1: "觀察", 0: "降溫"}.get(lv),
                spark_vals=[round(x[1], 2) for x in yoy[-24:]]))

    r = _base("us10y", "macro", "macro", "利率週期（通膨）", "美國 10 年期公債殖利率", "%",
              "一級：突破 5.0%｜二級：突破 5.35% 並維持 5 日（布局線 ≥5.5%、停利線 ≤4.9%）",
              {2: "限制長天期加碼，配置 0–3 個月國庫券 5–10%、浮動利率票券", 1: "每升 25bp 加碼債券 3%", 0: "跌破 4.9% 停利 1/3；常態配置"},
              "基金：百達美元短期貨幣、富蘭克林美元短期票券｜ETF：SGOV、BIL、USO、DBA、COPX｜私募：Muzinich MLoan", "FRED:DGS10")
    s = ctx.fred_vals("DGS10", 400)
    v, d = (s[-1][1], s[-1][0]) if s else (None, None)
    lv = None
    if v is not None:
        last5 = [x[1] for x in s[-5:]]
        lv = 2 if len(last5) == 5 and min(last5) > 5.35 else 1 if v > 5.0 else 0
    sig = "已達布局線（≥5.5%），可階梯式買入鎖定利息" if v and v >= 5.5 else "低於停利線 4.9%（持有長債者可停利 1/3）" if v and v <= 4.9 else ""
    add(_finish(r, v, d, lv, "{:.2f}%", spark_vals=spark([x[1] for x in s], 250, 40)))
    r["signal"] = sig
    if v and v >= 5.5:
        r["signal_action"] = "每升 25bp 階梯式加碼債券 3%，鎖定長期利息收益"

    r = _base("bei5", "macro", "macro", "通膨預期", "5 年期平衡通膨率（BEI）", "%",
              "補充：>2.6% 警戒｜>3.0% 通膨預期失錨",
              {2: "增配 TIPS、原物料，縮短存續期", 1: "留意長端殖利率熊陡風險", 0: "通膨預期穩定"},
              "ETF：TIP、DBA、COPX", "FRED:T5YIE")
    s = ctx.fred_vals("T5YIE", 400)
    v, d = (s[-1][1], s[-1][0]) if s else (None, None)
    add(_finish(r, v, d, lvl_above(v, 2.6, 3.0), "{:.2f}%", spark_vals=spark([x[1] for x in s], 250, 40)))

    r = _base("sahm", "macro", "macro", "勞動市場", "薩姆規則衰退指標（Sahm Rule）", "%",
              "安全 <0.30%｜警戒 ≥0.35%｜衰退確認 ≥0.50%",
              {2: "整體權益曝險調降至防禦水準，配置長天期優質公債", 1: "降低循環股，提高防禦比重", 0: "就業穩定"},
              "ETF：TLT、IEF、XLV、XLU", "FRED:SAHMREALTIME")
    s = ctx.fred_vals("SAHMREALTIME")
    v, d = (s[-1][1], s[-1][0]) if s else (None, None)
    lv = None if v is None else (2 if v >= 0.5 else 1 if v >= 0.35 else 0)
    add(_finish(r, v, d, lv, "{:.2f}%", spark_vals=[x[1] for x in s[-24:]]))

    r = _base("curve_10y2y", "macro", "macro", "殖利率曲線", "10Y−2Y 殖利率利差", "bp",
              "平穩 >+50bp｜警戒：倒掛 <0bp｜危機：牛陡解除倒掛（2Y 三個月降 >50bp 且利差轉正 >+30bp）",
              {2: "牛陡：提防衰退引發權益急跌，增配長債與現金", 1: "倒掛：限制性政策承壓，降低高 Beta",
               0: "熊陡時降低長久期權益配置，增配抗通膨商品"},
              "ETF：TLT、IEF、SHY、GLD", "FRED:T10Y2Y,DGS2")
    s = ctx.fred_vals("T10Y2Y", 800)
    v, d = (s[-1][1] * 100, s[-1][0]) if s else (None, None)
    lv = None
    if v is not None:
        inverted_recent = any(x[1] < 0 for x in s[-260:])
        s2 = ctx.fred_vals("DGS2", 200)
        y2_drop = (_fred_at(s2, 90) or s2[-1][1]) - s2[-1][1] if s2 else 0
        if inverted_recent and v > 30 and y2_drop > 0.5:
            lv, st = 2, "牛陡解除倒掛"
        elif v < 0:
            lv, st = 1, "倒掛"
        else:
            lv, st = 0, "正常"
        r["status"] = st
    add(_finish(r, v, d, lv, "{:+.0f} bp", status=r["status"] if lv is not None else None,
                spark_vals=spark([x[1] * 100 for x in s], 500, 40)))

    r = _base("ism_pmi", "macro", "macro", "產出週期", "ISM 製造業 PMI", "",
              "正常 50–58｜警戒 <48｜實質收縮 <45",
              {2: "降低週期股與工業股，轉入公用事業、醫療保健", 1: "減碼循環股", 0: "維持配置"},
              "ETF：XLU、XLV、XLP", "手動（ISM 不開放免費 API）")
    v, d, note = ctx.man("ism_pmi")
    add(_finish(r, v, d, lvl_below(v, 48, 45), "{:.1f}", note=note))

    # ---------------------------------------------------------------- 信用 / 流動性
    r = _base("hy_oas", "credit", "credit", "信用利差", "ICE BofA 美國高收益債 OAS（30 日變動）", "bp",
              "警戒：>450bp 或 30 日擴大 >75bp｜危機：突破 520bp",
              {2: "非投等債降至 0，轉入 1–5 年優質 IG 債或短端公債", 1: "減碼非投資等級債 5–8%（或減半）",
               0: "正常：可維持高收益債息收配置"},
              "基金：東方匯理美元短期債、富達全球優質債券｜ETF：SHY｜私募：DNCA 阿爾法債券（IR02）", "FRED:BAMLH0A0HYM2")
    s = ctx.fred_vals("BAMLH0A0HYM2", 800)
    v, d = (s[-1][1] * 100, s[-1][0]) if s else (None, None)
    chg30 = (v - _fred_at(s, 30) * 100) if s and _fred_at(s, 30) is not None else None
    lv = None if v is None else (2 if v > 520 else 1 if v > 450 or (chg30 or 0) > 75 else 0)
    add(_finish(r, v, d, lv, "{:.0f} bp", spark_vals=spark([x[1] * 100 for x in s], 250, 40),
                note=f"30 日變動 {chg30:+.0f}bp" if chg30 is not None else ""))

    r = _base("vix", "credit", "credit", "市場情緒", "VIX 波動率指數", "",
              "正常 12–18｜定價分歧 22–28｜恐慌拋售 >35",
              {2: "融資出清時逐步回補超跌權值股", 1: "突破 28 時買入價外 Put 避險", 0: "低波動，無需額外避險"},
              "選擇權避險、USMV", "Yahoo:^VIX")
    h = ctx.yh("^VIX")
    v, d = (h["close"][-1], h["dates"][-1]) if h else (None, None)
    lv = None if v is None else (2 if v > 35 else 1 if v >= 22 else 0)
    add(_finish(r, v, d, lv, "{:.1f}", spark_vals=spark(h["close"], 120, 40) if h else None))

    r = _base("margin_ratio", "credit", "credit", "台股信用槓桿", "台股大盤融資維持率", "%",
              "正常 160–175%｜追繳壓力 <140%｜系統性斷頭 <130%",
              {2: "跌破 130% 且融資單日大減逾百億時準備左側抄底", 1: "降低中小型高融資股", 0: "正常"},
              "國泰台灣高股息、台灣貨幣市場基金", "手動（證交所 / 券商資訊）")
    v, d, note = ctx.man("margin_ratio")
    add(_finish(r, v, d, lvl_below(v, 140, 130), "{:.1f}%", note=note))

    # ---------------------------------------------------------------- 美股評價
    r = _base("spx_pe", "us", "valuation", "美股評價", "S&P 500 預估 P/E", "x",
              "一級：P/E >21x｜二級：P/E >22.5x 或 ERP <0.5% 持續 10 日",
              {2: "獲利了結 5–10%，轉入短期無風險資產或保本型 PGN", 1: "停止追高、提高品質因子", 0: "維持配置"},
              "基金：聯博優化波動股票、駿利亨德森平衡｜結構型：PGN-Digital｜私募：百達總報酬泰坦（IP02）",
              "手動（FactSet / Yardeni 週報）")
    pe, d, note = ctx.man("spx_fwd_pe")
    add(_finish(r, pe, d, lvl_above(pe, 21, 22.5), "{:.1f}x", note=note))

    r = _base("erp", "us", "valuation", "股權風險溢酬", "ERP = 1/預估P/E − 10Y 殖利率", "%",
              "正常 2.5–4.5%｜警戒 <1.0%｜危機 <0.5% 或轉負",
              {2: "降低權益 Beta，獲利了結 10–20%，轉入優質 IG 債與短存續期現金", 1: "降低高估值成長股比重",
               0: "ERP ≥3.0% 時可重啟左側建倉"},
              "IG 債基金、SGOV", "計算：手動 P/E + FRED:DGS10")
    y10, d10 = ctx.fred_last("DGS10")
    v = (100 / pe - y10) if pe and y10 is not None else None
    add(_finish(r, v, d10 if v is not None else None, lvl_below(v, 1.0, 0.5), "{:.2f}%"))

    r = _base("buffett", "us", "valuation", "長期估值錨", "巴菲特指標（美國非金融企業股權市值 / GDP，代理）", "%",
              "正常 100–140%｜過熱 >170%｜歷史極端 >200%",
              {2: "停止全面被動大盤配置，轉向低波動、價值防禦或提高現金", 1: "提高低波動因子比重", 0: "正常"},
              "ETF：USMV、XLP｜聯博優化波動股票", "FRED:NCBEILQ027S,GDP")
    eq, deq = ctx.fred_last("NCBEILQ027S")
    gdp, _ = ctx.fred_last("GDP")
    v = (eq / 1000 / gdp * 100) if eq and gdp else None
    add(_finish(r, v, deq, lvl_above(v, 170, 200), "{:.0f}%", note="季資料，Fed Z.1 股權市值 ÷ 名目 GDP"))

    # ---------------------------------------------------------------- 台股
    r = _base("taiex_bias", "tw", "valuation", "台股動能", "加權指數 240 日線（年線）乖離率", "%",
              "一級：乖離 >+25%｜二級：乖離 >+35%（正常 −10%～+15%）",
              {2: "累計減碼 10–15%，資金轉向台幣定存 / 短票", 1: "減碼台股高 Beta 基金 / ETF 5%", 0: "維持配置"},
              "基金：第一金台灣貨幣市場、兆豐寶鑽貨幣市場｜低 Beta 替代：國泰台灣高股息", "Yahoo:^TWII")
    h = ctx.yh("^TWII")
    v = d = None
    sp = None
    if h and len(h["close"]) >= 240:
        c = h["close"]
        v = (c[-1] / sma(c, 240) - 1) * 100
        d = h["dates"][-1]
        bias_series = [(c[i] / (sum(c[i - 239:i + 1]) / 240) - 1) * 100 for i in range(239, len(c))]
        sp = spark(bias_series, 250, 40)
    add(_finish(r, v, d, lvl_above(v, 25, 35), "{:+.1f}%", spark_vals=sp,
                note=f"加權指數 {h['close'][-1]:,.0f}" if h else ""))

    r = _base("ndc_signal", "tw", "macro", "台灣景氣", "國發會景氣對策信號（分數 9–45）", "分",
              "綠燈 23–31｜黃紅 32–37 / 黃藍 17–22｜紅燈 ≥38 / 藍燈 ≤16",
              {2: "紅燈：分批調節高估值電子股；藍燈：分批加碼台股 ETF 與權值股", 1: "黃紅／黃藍：留意景氣轉折",
               0: "綠燈：維持基準權重"},
              "0050、0056、台灣貨幣市場基金", "手動（國發會每月 27 日左右公布）")
    v, d, note = ctx.man("ndc_signal")
    lv = None
    st = None
    if v is not None:
        if v >= 38: lv, st = 2, "紅燈（過熱）"
        elif v >= 32: lv, st = 1, "黃紅燈"
        elif v >= 23: lv, st = 0, "綠燈"
        elif v >= 17: lv, st = 1, "黃藍燈"
        else: lv, st = 2, "藍燈（低迷）"
    add(_finish(r, v, d, lv, "{:.0f} 分", status=st, note=note))

    r = _base("foreign_fut", "tw", "credit", "外資籌碼", "外資台指期淨未平倉（口，負值 = 淨空）", "口",
              "正常 ±15,000｜警戒淨空 >30,000｜極端淨空 >45,000",
              {2: "極端壓制：降低多頭部位，買入 Put 或反向 ETF 防禦", 1: "降低個股多頭部位", 0: "正常對沖"},
              "台指期 Put、反向 ETF", "手動（期交所三大法人）")
    v, d, note = ctx.man("foreign_futures_net_oi")
    lv = None if v is None else (2 if v < -45000 else 1 if v < -30000 else 0)
    add(_finish(r, v, d, lv, "{:+,.0f}", note=note))

    r = _base("export_orders", "tw", "macro", "外銷動能", "外銷訂單年增率", "%",
              "正常 5–15%｜放緩 0–3%｜轉負且連續 3 個月 <−5%",
              {2: "減持景氣循環股（塑化、鋼鐵、面板），增持電信、公共事業", 1: "留意出口動能", 0: "正常"},
              "中華電、XLU", "手動（經濟部統計處）")
    v, d, note = ctx.man("export_orders_yoy")
    lv = None if v is None else (2 if v < -5 else 1 if v < 3 else 0)
    add(_finish(r, v, d, lv, "{:+.1f}%", note=note))

    # ---------------------------------------------------------------- AI 專項
    r = _base("coreweave_cds", "ai", "credit", "AI 信用風險", "CoreWeave CDS（相較基準，bp）", "bp",
              "緩解 <+150bp｜觀察 +150～+350bp｜信用警戒 >+350bp",
              {2: "新興雲端曝險減半", 1: "暫停加碼 AI 雲端", 0: "信用緩解：可維持配置"},
              "全球大型科技股基金、半導體 ETF、台灣科技主題基金", "手動（Bloomberg / 券商報價）")
    v, d, note = ctx.man("coreweave_cds_bp")
    lv = None if v is None else (2 if v > 350 else 1 if v >= 150 else 0)
    h = ctx.yh("CRWV")
    proxy = ""
    if h and len(h["close"]) > 22 and not note.startswith("代理"):
        proxy = f"代理：CRWV 股價 1 個月 {(h['close'][-1] / h['close'][-22] - 1) * 100:+.1f}%"
    add(_finish(r, v, d, lv, "{:+.0f} bp", note=(note + " " + proxy).strip()))

    r = _base("csp_capex", "ai", "macro", "AI 需求", "四大 CSP 資本支出年增率（近四季合計）", "%",
              "需求擴張：年增 >0｜放緩：≤0｜需求轉弱：衰退 >10%",
              {2: "科技股降至中性", 1: "觀察：指引持平", 0: "需求上修：拉回分批加碼"},
              "SMH、台灣科技主題基金", "手動（法說會）")
    v, d, note = ctx.man("csp_capex_revision")
    lv = None if v is None else (2 if v < -10 else 1 if v <= 0 else 0)
    add(_finish(r, v, d, lv, "{:+.1f}%", note=note))

    r = _base("tsmc_capex", "ai", "macro", "台積電資本支出", "台積電資本支出年增率（近四季）", "%",
              "正常：年增 >5%｜警戒：0–5%｜危機：下調 >10%",
              {2: "調降半導體設備、特化與封測部位，轉入傳產高股息或貨幣型", 1: "觀察供應鏈訂單", 0: "維持供應鏈配置"},
              "2330、SMH、台灣科技主題基金", "手動（台積電法說會）")
    v, d, note = ctx.man("tsmc_capex_yoy")
    lv = None if v is None else (2 if v < -10 else 1 if v <= 5 else 0)
    add(_finish(r, v, d, lv, "{:+.1f}%", note=note))

    # ---------------------------------------------------------------- 地緣 / 外匯 / 商品
    r = _base("brent", "geo", "geo", "大宗商品與地緣", "Brent 現貨 / 中東航運保費", "USD",
              "停火確認：Brent 跌破 70 美元且低於 200 日均線｜補充：>90 警戒、>100 滯脹風險",
              {2: "滯脹衝擊：增配能源、黃金，降低高 Beta 本幣權益", 1: "油價偏高：留意通膨回升",
               0: "油價溫和：維持配置"},
              "基金：摩根歐洲策略股息、景順環球消費趨勢、摩根新興市場本地貨幣債｜ETF：XLY、VWO", "Yahoo:BZ=F")
    h = ctx.yh("BZ=F")
    v = d = None
    if h:
        v, d = h["close"][-1], h["dates"][-1]
        ma = sma(h["close"], 200)
        if ma and v < 70 and v < ma:
            r["signal"] = "停火確認條件成立（<70 且低於 200MA）"
            r["signal_action"] = "減持產油國主權債與能源高收益債 3–5%；加碼歐股 3%、非必需消費 2%、原油進口國主權債 3%"
        r["note"] = f"200 日均線 {ma:.1f}" if ma else ""
    add(_finish(r, v, d, lvl_above(v, 90, 100), "{:.2f}", spark_vals=spark(h["close"], 250, 40) if h else None,
                note=r["note"]))

    r = _base("twd_vol", "geo", "geo", "重大地緣危機", "台幣波動率衝擊（代理 1M NDF：5 日實現波動週變化 z 值）", "σ",
              "重大地緣：軍事封鎖 / 嚴重制裁且 NDF 波動率單週飆升 ≥3σ",
              {2: "減碼高 Beta 本幣權益 10%：黃金、美元現金、瑞郎提高至 12–15%", 1: "觀察：預備避險", 0: "正常"},
              "基金：富蘭克林黃金、貝萊德世界黃金｜黃金存摺｜ETF：GLD、IAU｜停泊：法巴貨幣型（IR01）", "Yahoo:TWD=X")
    h = ctx.yh("TWD=X")
    v = d = None
    if h and len(h["close"]) > 270:
        c = h["close"]
        rets = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
        rv = []
        for i in range(4, len(rets)):
            w = rets[i - 4:i + 1]
            m = sum(w) / 5
            rv.append(math.sqrt(sum((x - m) ** 2 for x in w) / 4) * math.sqrt(252) * 100)
        jumps = [rv[i] - rv[i - 5] for i in range(5, len(rv))]
        hist = jumps[-255:-5]
        mu = sum(hist) / len(hist)
        sd = math.sqrt(sum((x - mu) ** 2 for x in hist) / (len(hist) - 1)) or 1
        v, d = (jumps[-1] - mu) / sd, h["dates"][-1]
        r["note"] = f"USD/TWD {c[-1]:.3f}，5 日實現波動 {rv[-1]:.1f}%"
    add(_finish(r, v, d, lvl_above(v, 2, 3), "{:+.1f}σ", note=r["note"]))

    r = _base("tw_cds", "geo", "geo", "台灣主權風險", "台灣主權 CDS（5Y，bp）", "bp",
              "補充：較基準急升 >+20bp 警戒｜>+40bp 危機",
              {2: "啟動極端風險對沖：黃金、能源提高至 25%", 1: "降低高 Beta 電子外銷股", 0: "正常"},
              "GLD、IAU、美元現金", "手動（Bloomberg / 券商報價）")
    v, d, note = ctx.man("tw_cds_change_bp")
    add(_finish(r, v, d, lvl_above(v, 20, 40), "{:+.0f} bp", note=note))

    r = _base("dxy", "geo", "geo", "外匯趨勢", "美元指數週線 / 美債美日 2 年利差", "",
              "一級：DXY 跌破 98 且破年線｜二級：確認跌破 94",
              {2: "降純美元資產 5–10%，回補台幣、歐元與經常帳盈餘新興貨幣", 1: "開始降低純美元資產",
               0: "美元維持強勢：維持美元資產"},
              "基金：第一金台灣貨幣市場、路博邁新興市場本地貨幣債｜歐元：DNCA 阿爾法債券（IR03）｜ETF：VEU", "Yahoo:DX-Y.NYB")
    h = ctx.yh("DX-Y.NYB")
    v = d = None
    lv = None
    if h:
        v, d = h["close"][-1], h["dates"][-1]
        ma = sma(h["close"], 250)
        lv = 2 if v < 94 else 1 if (v < 98 and ma and v < ma) else 0
        r["note"] = f"年線 {ma:.2f}" if ma else ""
    add(_finish(r, v, d, lv, "{:.2f}", spark_vals=spark(h["close"], 250, 40) if h else None, note=r["note"]))

    r = _base("gold", "geo", "geo", "避險資產", "黃金期貨（補充）", "USD",
              "補充：1 個月漲幅 >8% 代表避險需求急升｜>15% 極端",
              {2: "地緣 / 滯脹定價中，避免追高、分批調節", 1: "避險需求升溫", 0: "正常"},
              "GLD、IAU、黃金存摺", "Yahoo:GC=F")
    h = ctx.yh("GC=F")
    v = d = None
    lv = None
    if h and len(h["close"]) > 22:
        v, d = h["close"][-1], h["dates"][-1]
        m1 = (v / h["close"][-22] - 1) * 100
        lv = lvl_above(m1, 8, 15)
        r["note"] = f"1 個月 {m1:+.1f}%"
    add(_finish(r, v, d, lv, "{:,.0f}", spark_vals=spark(h["close"], 250, 40) if h else None, note=r["note"]))

    return rows


def breadth_row(rows_screen: list[dict]) -> dict:
    """全市場廣度：篩選池內可交易標的站上 200 日均線比例。"""
    r = _base("breadth", "us", "valuation", "全市場廣度", "全球篩選池站上 200 日均線比例（補充）", "%",
              "過熱 >85%｜偏弱 <30%｜極弱 <20%",
              {2: "市場普遍跌破長期均線：降低 Beta、留意超跌反彈", 1: "廣度偏離：留意追高或轉弱", 0: "健康"},
              "—", "計算：Yahoo 全市場篩選池")
    vals = [x["above200"] for x in rows_screen if x.get("above200") is not None and x["asset"] != "指數"]
    v = sum(vals) / len(vals) * 100 if vals else None
    lv = None if v is None else (2 if v < 20 else 1 if v < 30 or v > 85 else 0)
    return _finish(r, v, datetime.now().strftime("%Y-%m-%d") if v is not None else None, lv, "{:.0f}%",
                   note=f"樣本 {len(vals)} 檔")
