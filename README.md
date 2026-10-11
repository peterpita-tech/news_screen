# 全球新聞與指標監控儀表板（news_screen）

情境分析║全球新聞 → 主題 → 受惠 / 受壓標的，加上總經、信用、美股評價、台股動能、AI 專項、地緣外匯的**分級觸發監控**，以及**全市場篩選**（美、台、日、韓、港陸、歐、新興市場個股＋產業 / 國家 / 債券 / 商品 ETF、期貨、外匯、加密）。

版面採黑字淺色系、深綠表頭、金褐色面向標籤，比照季度檢視表的樣式。

## 功能

| 區塊 | 內容 |
|---|---|
| 市場概況 | S&P 500、那斯達克 100、費半、台灣加權、日經、KOSPI、恆生、上證、STOXX50、VIX、DXY、布蘭特、黃金、比特幣 |
| 情境判讀 | PDF 第四章的四種情境（軟著陸 / 過熱估值壓縮 / 衰退去槓桿 / 地緣滯脹），逐條比對條件；第五章的**多因子共振**（總體、評價動能、信貸流動性三個維度）；各情境的資產配置建議表 |
| 指標監控 | 26 項指標，各列出分級門檻、目前狀態（正常 / 一級 / 二級）、量化建議動作與推薦商品，可依面向篩選或「只看警戒」 |
| 新聞衝擊 | 抓取 Google News（中英文）、CNBC、MarketWatch、Yahoo Finance、鉅亨網近 72 小時的新聞，用 20 個主題規則判斷驅動方向（▲ / ▼），推導全球受惠 / 受壓標的與相關監控指標 |
| 全市場篩選 | 約 180 檔跨市場標的：1日 / 1月 / 3月 / 今年報酬、年線乖離、RSI、距 52 週高點、新聞分數、綜合分數；內建強勢動能、新聞受惠 / 受壓、超買、超跌、接近新高、跌破 200 日線等預設篩選 |

### 監控指標與資料來源

| 面向 | 指標 | 來源 |
|---|---|---|
| 總經 / 利率 | Fed 轉向（2×(EFFR−1Y) 推估 12 個月降息幅度）、CPI 年增率、10Y 殖利率（5.0% / 5.35% 持續 5 日）、5Y BEI、薩姆規則、10Y−2Y（倒掛 / 牛陡）、ISM PMI | FRED（ISM 為手動） |
| 信用 / 流動性 | 高收益債 OAS（>450bp 或 30 日擴大 >75bp / >520bp）、VIX、台股融資維持率 | FRED、Yahoo（融資維持率為手動） |
| 美股評價 | 預估 P/E（21x / 22.5x）、ERP = 1/PE − 10Y、巴菲特指標（Fed Z.1 股權市值 / GDP）、全市場站上 200MA 比例 | 手動 P/E＋FRED、篩選池計算 |
| 台股 | 加權指數年線乖離（+25% / +35%）、國發會景氣燈號、外資台指期淨未平倉、外銷訂單 | Yahoo（其餘為手動） |
| AI 專項 | CoreWeave CDS（附 CRWV 股價作代理）、四大 CSP 資本支出修正、台積電資本支出 | 手動 |
| 地緣 / 外匯 | Brent（停火確認：<70 且低於 200MA）、台幣波動衝擊（5 日實現波動週變化 z 值，作為 1M NDF 波動率的代理，≥3σ）、台灣 CDS、DXY（<98 且破年線 / <94）、黃金 | Yahoo（CDS 為手動） |

沒有免費公開 API 的指標，請編輯 [`config/manual_indicators.json`](config/manual_indicators.json)：`value` 填數值、`asof` 填資料日期。儀表板上這些指標會標示「手動」；尚未填寫的顯示「待輸入」，不列入情境判讀。

## 使用方式

### 1. 本機執行（Windows）

需要 Python 3.10 以上，**不必安裝任何套件**，只用標準函式庫。

```
git clone https://github.com/peterpita-tech/news_screen.git
雙擊 start_dashboard.bat
```

或在命令列執行：

```
python app.py                # http://localhost:8763，預設每 15 分鐘自動更新
python app.py --interval 5   # 自訂更新間隔（分鐘）
python app.py --demo         # 離線示範資料，用來預覽版面
```

本機版右上角有「重新整理」按鈕，可立即重抓資料。

### 2. GitHub Pages（線上版，自動更新）

`.github/workflows/pages.yml` 每 2 小時抓一次資料，產生靜態網站並發布。首次使用需要：

1. GitHub repo → **Settings → Pages → Build and deployment → Source** 選 **GitHub Actions**
2. **Actions** 分頁 → 「更新儀表板並發布 GitHub Pages」→ **Run workflow**
3. 網址：`https://peterpita-tech.github.io/news_screen/`

> GitHub 預設只允許從預設分支部署 Pages。如果部署被擋，請到 Settings → Environments → github-pages 加入要部署的分支，或把分支合併到預設分支。

### 3. 測試

```
python -m unittest discover tests
```

## 擴充

- **增加篩選標的**：在 `dashboard/universe.py` 的 `UNIVERSE` 加一行 `(Yahoo 代號, 中文名, 市場, 類別, 產業)`
- **增加新聞主題 / 受惠股**：在 `dashboard/themes.py` 的 `THEMES` 加入關鍵字與 `up_benefit` / `up_hurt` 清單
- **調整門檻**：在 `dashboard/indicators.py` 修改各指標；情境條件在 `dashboard/scenarios.py`

## 專案結構

```
app.py                 本機伺服器（port 8763）
build_static.py        產生 GitHub Pages 靜態網站
start_dashboard.bat    Windows 一鍵啟動
config/manual_indicators.json  手動指標
dashboard/
  fetchers.py   Yahoo / FRED / RSS / 鉅亨抓取
  universe.py   全市場篩選池
  themes.py     新聞主題 → 受惠 / 受壓規則
  news.py       新聞抓取、去重、標註
  indicators.py 監控指標與分級門檻
  scenarios.py  情境矩陣與多因子共振
  screener.py   技術面 / 動能指標
  build.py      彙整輸出 JSON
  demo.py       離線示範資料
web/            前端（index.html / app.js / style.css）
tests/          離線測試
```

## 免責聲明

新聞主題與受惠標的由關鍵字規則自動判讀，代理指標（Fed 隱含路徑、台幣 NDF 波動、巴菲特指標）是公開資料的近似值。本專案僅供研究參考，不構成任何投資建議。
