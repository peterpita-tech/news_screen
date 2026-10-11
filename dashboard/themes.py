"""新聞主題規則：關鍵字偵測主題 → 判斷驅動因子方向（升/降）→ 對應全球受惠 / 受壓標的與相關監控指標。

up_benefit：驅動因子「上升 / 正面」時受惠的標的；驅動因子「下降 / 負面」時角色互換。
"""

UP_WORDS = [
    "surge", "soar", "jump", "rally", "spike", "climb", "rise", "rises", "rising", "gain", "record", "high",
    "beat", "boost", "strong", "upgrade", "raise", "raises", "hike", "hikes", "accelerat", "expand", "escalat",
    "漲", "飆", "攀升", "走高", "創高", "新高", "上修", "強勁", "擴大", "升溫", "加速", "大增", "暴增", "升息", "激增", "看好",
]
DOWN_WORDS = [
    "plunge", "slump", "drop", "fall", "falls", "tumble", "sink", "slide", "decline", "low", "miss", "cut",
    "cuts", "weak", "downgrade", "slow", "ease", "eases", "cool", "ceasefire", "truce", "delay", "shrink",
    "跌", "重挫", "下滑", "走低", "下修", "疲弱", "放緩", "降溫", "停火", "延後", "砍單", "減少", "萎縮", "降息", "崩", "看淡",
]

THEMES = [
    {
        "id": "ai_semis", "name": "AI / 半導體需求",
        "kw": ["nvidia", "ai chip", "semiconductor", "chipmaker", "gpu", "tpu", "hbm", "data center", "datacenter",
               "tsmc", "broadcom", "asic", "hyperscaler", "capex", "輝達", "半導體", "晶片", "台積電", "ai伺服器",
               "資料中心", "算力", "先進製程", "cowos", "tpu8", "聯發科", "博通"],
        "up_benefit": ["NVDA", "AVGO", "TSM", "2330.TW", "2454.TW", "3443.TW", "3661.TW", "2382.TW", "2317.TW",
                       "6669.TW", "3711.TW", "ASML.AS", "8035.T", "6857.T", "AMAT", "SMH", "^SOX", "000660.KS"],
        "up_hurt": [],
        "indicators": ["csp_capex", "tsmc_capex", "coreweave_cds", "taiex_bias"],
    },
    {
        "id": "memory", "name": "記憶體 / HBM 報價",
        "kw": ["memory", "dram", "nand", "hbm", "micron", "sk hynix", "samsung electronics", "記憶體", "美光",
               "海力士", "三星", "南亞科", "華邦"],
        "up_benefit": ["MU", "000660.KS", "005930.KS", "2408.TW", "2344.TW"],
        "up_hurt": [],
        "indicators": ["csp_capex"],
    },
    {
        "id": "ai_power", "name": "AI 電力 / 散熱 / 核能",
        "kw": ["power grid", "electricity demand", "nuclear", "uranium", "cooling", "transformer", "utility",
               "電力", "電網", "核電", "核能", "散熱", "重電", "變壓器", "鈾"],
        "up_benefit": ["VRT", "ETN", "GEV", "CEG", "VST", "CCJ", "URA", "2308.TW", "3017.TW", "1519.TW",
                       "1503.TW", "6501.T"],
        "up_hurt": [],
        "indicators": ["csp_capex"],
    },
    {
        "id": "ai_credit", "name": "AI 雲端信用風險",
        "kw": ["coreweave", "neocloud", "ai bubble", "ai debt", "gpu financing", "ai spending", "ai泡沫",
               "雲端債務", "資本支出下修"],
        "up_benefit": [],
        "up_hurt": ["CRWV", "NVDA", "ORCL", "SMH"],
        "indicators": ["coreweave_cds", "csp_capex", "hy_oas"],
    },
    {
        "id": "fed_rates", "name": "Fed 降息 / 利率",
        "kw": ["federal reserve", "fed ", "fomc", "powell", "rate cut", "rate hike", "interest rate", "treasury yield",
               "bond yield", "聯準會", "fed", "鮑爾", "降息", "升息", "利率", "美債殖利率", "公債殖利率"],
        # 方向定義：「利率上升」為 up
        "up_benefit": ["JPM", "XLF", "SGOV", "BIL", "8306.T"],
        "up_hurt": ["TLT", "IEF", "LQD", "BND", "VNQ", "IWM", "^RUT", "NEE"],
        "indicators": ["fed_pivot", "us10y", "curve_10y2y", "erp"],
        "invert_words": ["cut", "cuts", "降息", "dovish", "鴿"],  # 這些字代表利率下降
    },
    {
        "id": "inflation", "name": "通膨 / CPI",
        "kw": ["inflation", "cpi", "pce", "consumer prices", "breakeven", "stagflation", "通膨", "物價", "消費者物價",
               "停滯性通膨", "滯脹"],
        "up_benefit": ["TIP", "GLD", "DBA", "COPX", "XLE", "USO"],
        "up_hurt": ["TLT", "IEF", "QQQ", "^NDX"],
        "indicators": ["cpi_yoy", "bei5", "us10y"],
    },
    {
        "id": "oil_mideast", "name": "油價 / 中東情勢",
        "kw": ["oil", "crude", "brent", "opec", "iran", "israel", "red sea", "strait of hormuz", "houthi", "gaza",
               "原油", "油價", "布蘭特", "中東", "伊朗", "以色列", "紅海", "荷莫茲", "胡塞", "石油輸出國"],
        "up_benefit": ["XOM", "CVX", "SHEL.L", "0883.HK", "XLE", "USO", "BZ=F", "CL=F", "1301.TW"],
        "up_hurt": ["DAL", "2610.TW", "XLY", "EWJ", "INDA", "EWT"],
        "indicators": ["brent", "cpi_yoy"],
    },
    {
        "id": "taiwan_geo", "name": "台海 / 地緣風險",
        "kw": ["taiwan strait", "blockade", "pla", "military drill", "sanction", "geopolit", "invasion", "war ",
               "台海", "封鎖", "共軍", "軍演", "制裁", "地緣", "戰爭", "解放軍"],
        "up_benefit": ["GLD", "IAU", "GC=F", "LMT", "RTX", "NOC", "ITA", "RHM.DE", "7011.T", "012450.KS", "CHF=X"],
        "up_hurt": ["^TWII", "EWT", "2330.TW", "TSM", "0050.TW"],
        "indicators": ["tw_cds", "twd_vol", "vix"],
    },
    {
        "id": "dollar", "name": "美元 / 匯率",
        "kw": ["dollar", "dxy", "currency", "yen", "yuan", "forex", "new taiwan dollar", "美元", "匯率", "台幣",
               "新台幣", "日圓", "人民幣", "升值", "貶值"],
        # up = 美元走強
        "up_benefit": ["DX-Y.NYB", "SGOV"],
        "up_hurt": ["EEM", "VWO", "VEU", "GLD", "EMB", "EWT", "EWY"],
        "indicators": ["dxy", "twd_vol"],
    },
    {
        "id": "china", "name": "中國經濟 / 刺激政策",
        "kw": ["china", "beijing", "pboc", "stimulus", "property", "chinese economy", "中國", "陸股", "人行",
               "刺激", "房地產", "北京", "港股"],
        "up_benefit": ["FXI", "KWEB", "0700.HK", "9988.HK", "3690.HK", "1211.HK", "BHP", "VALE", "FCX", "COPX", "HG=F"],
        "up_hurt": [],
        "indicators": [],
    },
    {
        "id": "tariff", "name": "關稅 / 貿易戰",
        "kw": ["tariff", "trade war", "export control", "trade deal", "duties", "關稅", "貿易戰", "出口管制",
               "貿易協議", "232條款", "301"],
        # up = 關稅升級
        "up_benefit": ["GLD", "XLP", "USMV"],
        "up_hurt": ["AAPL", "TSM", "2330.TW", "2317.TW", "FXI", "EWT", "7203.T", "005380.KS", "XLY"],
        "indicators": ["vix", "dxy"],
    },
    {
        "id": "japan", "name": "日本 / 日銀",
        "kw": ["bank of japan", "boj", "nikkei", "japan", "日銀", "日本央行", "日經", "日股"],
        "up_benefit": ["EWJ", "^N225", "8306.T", "8058.T", "7203.T"],
        "up_hurt": [],
        "indicators": [],
    },
    {
        "id": "recession", "name": "衰退 / 就業",
        "kw": ["recession", "jobless", "unemployment", "payroll", "layoff", "labor market", "ism", "pmi",
               "衰退", "失業", "非農", "裁員", "就業", "採購經理人"],
        # up = 衰退風險升高
        "up_benefit": ["TLT", "IEF", "XLU", "XLV", "XLP", "GLD", "USMV"],
        "up_hurt": ["IWM", "XLI", "CAT", "XLF", "HYG", "^RUT"],
        "indicators": ["sahm", "ism_pmi", "curve_10y2y", "hy_oas"],
    },
    {
        "id": "credit", "name": "信用 / 違約",
        "kw": ["credit spread", "default", "junk bond", "high yield", "private credit", "bankruptcy", "liquidity",
               "信用利差", "違約", "高收益債", "垃圾債", "私募信貸", "破產", "流動性"],
        # up = 信用風險升高
        "up_benefit": ["SHY", "SGOV", "IEF", "GLD"],
        "up_hurt": ["HYG", "XLF", "IWM", "JPM", "GS"],
        "indicators": ["hy_oas", "coreweave_cds"],
    },
    {
        "id": "gold", "name": "黃金 / 避險",
        "kw": ["gold", "bullion", "safe haven", "precious metal", "黃金", "金價", "避險", "貴金屬"],
        "up_benefit": ["GLD", "IAU", "GC=F", "NEM", "SLV"],
        "up_hurt": [],
        "indicators": ["vix", "dxy"],
    },
    {
        "id": "defense", "name": "國防支出",
        "kw": ["defense spending", "defence", "nato", "military budget", "missile", "drone", "國防", "軍工",
               "北約", "飛彈", "無人機"],
        "up_benefit": ["LMT", "RTX", "NOC", "ITA", "RHM.DE", "7011.T", "012450.KS"],
        "up_hurt": [],
        "indicators": [],
    },
    {
        "id": "pharma", "name": "減重藥 / 醫療",
        "kw": ["glp-1", "obesity", "weight-loss", "eli lilly", "novo nordisk", "fda", "減重", "禮來", "諾和諾德", "藥"],
        "up_benefit": ["LLY", "NOVO-B.CO", "XLV"],
        "up_hurt": [],
        "indicators": [],
    },
    {
        "id": "crypto", "name": "加密資產",
        "kw": ["bitcoin", "crypto", "ethereum", "stablecoin", "比特幣", "加密貨幣", "穩定幣", "以太幣"],
        "up_benefit": ["BTC-USD", "IBIT", "COIN"],
        "up_hurt": [],
        "indicators": [],
    },
    {
        "id": "shipping", "name": "航運 / 運價",
        "kw": ["shipping", "freight", "container rates", "suez", "panama canal", "航運", "運價", "貨櫃", "蘇伊士", "scfi"],
        "up_benefit": ["2603.TW"],
        "up_hurt": ["COST", "WMT"],
        "indicators": ["brent"],
    },
    {
        "id": "ev_auto", "name": "電動車 / 汽車",
        "kw": ["electric vehicle", " ev ", "tesla", "byd", "automaker", "電動車", "特斯拉", "比亞迪", "車廠"],
        "up_benefit": ["TSLA", "1211.HK", "7203.T", "005380.KS"],
        "up_hurt": [],
        "indicators": [],
    },
]
