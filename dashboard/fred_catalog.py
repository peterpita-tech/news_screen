"""FRED 圖表頁的預載序列：建置時抓取，前端可任意組合、轉換（年增率 / 年變動 / 指數化）並即時畫圖。
要加新序列：在 config/fred_extra.json 列出 FRED 代號（或直接加到下面清單），下次更新就會納入。
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from . import fetchers

ROOT = Path(__file__).resolve().parent.parent
EXTRA_PATH = ROOT / "config" / "fred_extra.json"

# (代號, 中文名稱, 分類, 單位)
CATALOG = [
    # 利率 / 貨幣政策
    ("FEDFUNDS", "聯邦資金利率（月）", "利率", "%"), ("DFF", "聯邦資金有效利率（日）", "利率", "%"),
    ("SOFR", "擔保隔夜融資利率 SOFR", "利率", "%"), ("IORB", "準備金利率 IORB", "利率", "%"),
    ("DFEDTARU", "聯邦資金目標區間上限", "利率", "%"), ("DFEDTARL", "聯邦資金目標區間下限", "利率", "%"),
    ("DGS1MO", "美債 1 個月", "利率", "%"), ("DGS3MO", "美債 3 個月", "利率", "%"), ("DGS6MO", "美債 6 個月", "利率", "%"),
    ("DGS1", "美債 1 年", "利率", "%"), ("DGS2", "美債 2 年", "利率", "%"), ("DGS5", "美債 5 年", "利率", "%"),
    ("DGS7", "美債 7 年", "利率", "%"), ("DGS10", "美債 10 年", "利率", "%"), ("DGS20", "美債 20 年", "利率", "%"),
    ("DGS30", "美債 30 年", "利率", "%"), ("T10Y2Y", "10Y−2Y 利差", "利率", "%"), ("T10Y3M", "10Y−3M 利差", "利率", "%"),
    ("DFII10", "10 年期實質殖利率（TIPS）", "利率", "%"), ("MORTGAGE30US", "30 年房貸利率", "利率", "%"),
    ("DPRIME", "銀行基本放款利率", "利率", "%"),
    # 通膨
    ("CPIAUCSL", "CPI 指數", "通膨", "指數"), ("CPILFESL", "核心 CPI 指數", "通膨", "指數"),
    ("PCEPI", "PCE 物價指數", "通膨", "指數"), ("PCEPILFE", "核心 PCE 物價指數", "通膨", "指數"),
    ("PPIFIS", "PPI 最終需求", "通膨", "指數"), ("T5YIE", "5 年期平衡通膨率", "通膨", "%"),
    ("T10YIE", "10 年期平衡通膨率", "通膨", "%"), ("T5YIFR", "5 年後 5 年期通膨預期", "通膨", "%"),
    ("MICH", "密大 1 年通膨預期", "通膨", "%"),
    # 就業
    ("UNRATE", "失業率", "就業", "%"), ("U6RATE", "U-6 廣義失業率", "就業", "%"),
    ("PAYEMS", "非農就業人數", "就業", "千人"), ("ICSA", "初領失業救濟金", "就業", "人"),
    ("CCSA", "續領失業救濟金", "就業", "人"), ("CIVPART", "勞動參與率", "就業", "%"),
    ("EMRATIO", "就業人口比", "就業", "%"), ("JTSJOL", "JOLTS 職缺數", "就業", "千人"),
    ("CES0500000003", "平均時薪", "就業", "美元"), ("SAHMREALTIME", "薩姆規則指標", "就業", "%"),
    # 經濟成長
    ("GDP", "名目 GDP", "成長", "十億美元"), ("GDPC1", "實質 GDP", "成長", "十億美元"),
    ("A191RL1Q225SBEA", "實質 GDP 季增年率", "成長", "%"), ("GDPNOW", "亞特蘭大 Fed GDPNow", "成長", "%"),
    ("INDPRO", "工業生產指數", "成長", "指數"), ("TCU", "產能利用率", "成長", "%"),
    ("RSAFS", "零售銷售", "成長", "百萬美元"), ("DGORDER", "耐久財訂單", "成長", "百萬美元"),
    ("PCE", "個人消費支出", "成長", "十億美元"), ("PI", "個人所得", "成長", "十億美元"),
    ("PSAVERT", "個人儲蓄率", "成長", "%"), ("CFNAI", "芝加哥 Fed 全國活動指數", "成長", "指數"),
    ("USREC", "NBER 衰退期間（1＝衰退）", "成長", ""),
    # 房市
    ("HOUST", "新屋開工", "房市", "千戶"), ("PERMIT", "建築許可", "房市", "千戶"),
    ("HSN1F", "新屋銷售", "房市", "千戶"), ("EXHOSLUSM495S", "成屋銷售", "房市", "戶"),
    ("CSUSHPISA", "Case-Shiller 全國房價指數", "房市", "指數"), ("MSPUS", "新屋銷售中位價", "房市", "美元"),
    # 信心 / 金融條件
    ("UMCSENT", "密大消費者信心", "信心", "指數"), ("STLFSI4", "聖路易 Fed 金融壓力指數", "信心", "指數"),
    ("NFCI", "芝加哥 Fed 金融條件指數", "信心", "指數"),
    # 貨幣 / 流動性
    ("M2SL", "M2 貨幣供給", "流動性", "十億美元"), ("WALCL", "Fed 總資產", "流動性", "百萬美元"),
    ("WRESBAL", "銀行準備金", "流動性", "十億美元"), ("RRPONTSYD", "ON RRP 使用量", "流動性", "十億美元"),
    ("WTREGEN", "財政部一般帳戶 TGA", "流動性", "十億美元"), ("RPONTSYD", "SRF / 附買回操作量", "流動性", "十億美元"),
    ("BOGMBASE", "貨幣基數", "流動性", "百萬美元"), ("TOTBKCR", "銀行信用", "流動性", "十億美元"),
    # 信用
    ("BAMLH0A0HYM2", "高收益債 OAS", "信用", "%"), ("BAMLH0A3HYC", "CCC 級高收益債 OAS", "信用", "%"),
    ("BAMLC0A0CM", "投資級債 OAS", "信用", "%"), ("BAA10Y", "Baa 公司債 − 10Y", "信用", "%"),
    ("AAA10Y", "Aaa 公司債 − 10Y", "信用", "%"), ("DRTSCILM", "銀行緊縮工商放款比例（SLOOS）", "信用", "%"),
    # 金融市場
    ("SP500", "S&P 500", "市場", "點"), ("NASDAQCOM", "那斯達克綜合指數", "市場", "點"),
    ("DJIA", "道瓊工業指數", "市場", "點"), ("VIXCLS", "VIX 波動率指數", "市場", ""),
    # 匯率
    ("DTWEXBGS", "美元廣義指數", "匯率", "指數"), ("DEXTAUS", "新台幣 / 美元", "匯率", "TWD"),
    ("DEXJPUS", "日圓 / 美元", "匯率", "JPY"), ("DEXUSEU", "美元 / 歐元", "匯率", "USD"),
    ("DEXCHUS", "人民幣 / 美元", "匯率", "CNY"), ("DEXKOUS", "韓元 / 美元", "匯率", "KRW"),
    # 能源 / 商品
    ("DCOILWTICO", "WTI 原油", "商品", "美元"), ("DCOILBRENTEU", "Brent 原油", "商品", "美元"),
    ("DHHNGSP", "Henry Hub 天然氣", "商品", "美元"), ("GASREGW", "美國汽油零售價", "商品", "美元"),
    ("PCOPPUSDM", "國際銅價", "商品", "美元"),
    # 財政
    ("GFDEBTN", "聯邦政府債務", "財政", "百萬美元"), ("GFDEGDQ188S", "聯邦債務占 GDP", "財政", "%"),
    ("FYFSD", "聯邦財政盈餘 / 赤字（年）", "財政", "百萬美元"),
]

DAILY_START = "2014-01-01"
LONG_START = "1990-01-01"


def extra_ids() -> list[str]:
    try:
        d = json.loads(EXTRA_PATH.read_text(encoding="utf-8"))
        return [str(x).strip().upper() for x in d.get("series", []) if str(x).strip()]
    except (OSError, ValueError):
        return []


def _freq(data) -> str:
    if len(data) < 3:
        return ""
    gaps = sorted((datetime.strptime(data[i][0], "%Y-%m-%d") - datetime.strptime(data[i - 1][0], "%Y-%m-%d")).days
                  for i in range(max(1, len(data) - 40), len(data)))
    g = gaps[len(gaps) // 2]
    return "日" if g <= 3 else "週" if g <= 8 else "月" if g <= 35 else "季" if g <= 100 else "年"


def build(errors: list[str], get=None) -> dict:
    get = get or (lambda sid, start: fetchers.fred_series(sid, start))
    meta = {c[0]: {"name": c[1], "cat": c[2], "unit": c[3]} for c in CATALOG}
    for sid in extra_ids():
        meta.setdefault(sid, {"name": sid, "cat": "自訂", "unit": ""})

    def one(sid):
        try:
            data = get(sid, LONG_START)
            if _freq(data) in ("日", "週"):
                data = [x for x in data if x[0] >= DAILY_START]
            return sid, data, None
        except Exception as e:  # noqa: BLE001
            return sid, None, e

    out = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for sid, data, err in ex.map(one, list(meta)):
            if err or not data:
                errors.append(f"FRED 圖表 {sid}：{str(err)[:80] if err else '無資料'}")
                continue
            out[sid] = {**meta[sid], "freq": _freq(data), "data": [[d, float(f"{v:.6g}")] for d, v in data]}
    return {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "series": out,
            "cats": list(dict.fromkeys(m["cat"] for m in meta.values()))}
