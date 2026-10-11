"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const LV = { 0: "lv0", 1: "lv1", 2: "lv2" };
let D = null;
let isLocal = false;
const state = {
  group: "all", lang: "all", dir: "all", newsQ: "", theme: null,
  preset: "all", market: "all", asset: "all", fTheme: "all", q: "", sort: "score", desc: true,
};

// ---------------------------------------------------------------- utils
function fmtPrice(v) {
  if (v == null) return "—";
  const a = Math.abs(v);
  const d = a >= 1000 ? 0 : a >= 100 ? 1 : a >= 1 ? 2 : 4;
  return v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}
function fmtPct(v, d = 1) {
  if (v == null) return '<span class="small">—</span>';
  const cls = v > 0 ? "up" : v < 0 ? "down" : "";
  return `<span class="${cls}">${v > 0 ? "+" : ""}${v.toFixed(d)}%</span>`;
}
function spark(vals, w = 110, h = 28, color) {
  if (!vals || vals.length < 2) return "";
  const min = Math.min(...vals), max = Math.max(...vals), rng = max - min || 1;
  const pts = vals.map((v, i) => `${(i / (vals.length - 1) * (w - 2) + 1).toFixed(1)},${(h - 2 - (v - min) / rng * (h - 4)).toFixed(1)}`).join(" ");
  const c = color || (vals[vals.length - 1] >= vals[0] ? "var(--up)" : "var(--down)");
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline fill="none" stroke="${c}" stroke-width="1.6" stroke-linejoin="round" points="${pts}"/></svg>`;
}
function ago(iso) {
  if (!iso) return "";
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 60) return `${Math.max(m, 0)} 分鐘前`;
  if (m < 1440) return `${Math.round(m / 60)} 小時前`;
  return `${Math.round(m / 1440)} 天前`;
}
const nameOf = (s) => (D.names && D.names[s]) || s;
function tickerChips(list, cls) {
  return (list || []).map((s) => `<span class="chip ${cls}" data-sym="${esc(s)}" title="${esc(s)}">${esc(nameOf(s))}</span>`).join("");
}
function lvSpan(level, text) {
  const c = level == null ? "lvn" : LV[level];
  return `<span class="lv ${c}">${esc(text)}</span>`;
}

// ---------------------------------------------------------------- load
async function load() {
  try {
    const r = await fetch("data.json?t=" + Date.now(), { cache: "no-store" });
    if (r.status === 503) { setTimeout(load, 3000); return; }
    if (!r.ok) throw new Error("HTTP " + r.status);
    D = await r.json();
    render();
  } catch (e) {
    $("#loading").textContent = "資料載入失敗：" + e.message + "（若為本機版，請確認 app.py 視窗仍在執行）";
  }
}
async function detectLocal() {
  try {
    const r = await fetch("api/status", { cache: "no-store" });
    if (r.ok) { isLocal = true; $("#refreshBtn").hidden = false; }
  } catch (_) { /* 靜態版（GitHub Pages） */ }
}
async function doRefresh() {
  const btn = $("#refreshBtn");
  btn.disabled = true; btn.textContent = "更新中…";
  const before = D && D.generated_at;
  await fetch("api/refresh", { method: "POST" });
  const poll = async () => {
    const s = await (await fetch("api/status", { cache: "no-store" })).json();
    if (s.busy) return setTimeout(poll, 2500);
    await load();
    btn.disabled = false; btn.textContent = "重新整理";
    if (D && D.generated_at === before && s.error) alert("更新失敗：" + s.error);
  };
  setTimeout(poll, 2500);
}

// ---------------------------------------------------------------- render
function render() {
  $("#loading").hidden = true;
  document.querySelectorAll("main section").forEach((s) => (s.hidden = false));
  const c = D.counts;
  $("#updated").innerHTML = `更新：<b>${esc(D.generated_at_tpe)}</b>（台北）｜標的 ${c.tickers}｜新聞 ${c.news} 則`;
  let b = "";
  if (D.demo) b += `<div class="banner">⚠ 目前為<b>示範資料</b>（隨機模擬行情與範例新聞），非真實市場數據。實際使用請執行 <code>python app.py</code> 或由 GitHub Actions 產生。</div>`;
  if (D.error_count) b += `<div class="banner err">部分資料來源抓取失敗 ${D.error_count} 筆（其餘資料正常顯示）。<details class="errs"><summary>查看明細</summary>${D.errors.map(esc).join("<br>")}</details></div>`;
  $("#banners").innerHTML = b;
  renderOverview();
  renderScenario();
  renderMonitor();
  renderNews();
  renderScreener();
}

function renderOverview() {
  $("#ovGrid").innerHTML = D.overview.map((r) => `
    <div class="card ov" data-sym="${esc(r.symbol)}">
      <div class="n">${esc(r.name)}</div>
      <div class="v num">${fmtPrice(r.last)}</div>
      <div class="c num">${fmtPct(r.chg1d, 2)} <span class="small">1日</span>　${fmtPct(r.chg1m)} <span class="small">1月</span></div>
      ${spark(r.spark, 150, 30)}
    </div>`).join("");
}

function renderScenario() {
  const S = D.scenario;
  const best = S.scenarios.find((s) => s.id === S.best);
  const nRes = Object.values(S.resonance).filter((x) => x.triggered).length;
  const anyData = S.scenarios.some((s) => s.total > 0);
  $("#verdict").innerHTML = !anyData ? `<span class="lv lvn">資料不足</span>　指標資料尚未取得，無法判讀情境。`
    : S.regime_confirmed
    ? `<span class="lv lv2">體制切換確認</span>　三大維度同時出現警戒訊號，最接近：<b>${esc(best.name)}</b>（符合 ${best.met}/${best.total} 項）→ 依下表調整配置。`
    : `<span class="lv ${nRes >= 2 ? "lv1" : "lv0"}">共振 ${nRes}/3 維度</span>　尚未達體制切換條件，維持基準配置並觀察；目前條件最接近：<b>${esc(best.name)}</b>（符合 ${best.met}/${best.total} 項可得指標）。`;
  $("#resGrid").innerHTML = Object.values(S.resonance).map((r) => `
    <div class="card res">
      <h4>${lvSpan(r.triggered ? 1 : 0, r.triggered ? "有警戒" : "無警戒")}　${esc(r.name)}</h4>
      <div class="small">可得指標 ${r.available}/${r.total}</div>
      ${r.alerts.length ? `<ul>${r.alerts.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>` : ""}
    </div>`).join("");
  $("#scGrid").innerHTML = S.scenarios.map((s) => `
    <div class="card sc ${s.id === S.best ? "best" : ""}">
      <h3>${esc(s.name)}</h3><div class="en">${esc(s.en)}</div>
      <div class="meter"><i style="width:${s.score}%"></i></div>
      <div class="small">條件符合 <b>${s.met}</b> / ${s.total}（${s.score}%）｜衍生品：${esc(s.hedge)}</div>
      <div class="conds">${s.details.map((d) => `<span class="cond ${d.state}">${esc(d.label)}</span>`).join("")}</div>
    </div>`).join("");
  const cols = [S.baseline, ...S.scenarios];
  let h = `<thead><tr><th>資產類別</th>${cols.map((c, i) => `<th class="r ${i && c.id === S.best ? "hl" : ""}">${esc(c.name)}</th>`).join("")}</tr></thead><tbody>`;
  S.alloc_rows.forEach((row, ri) => {
    h += `<tr><td class="facet">${esc(row)}</td>${cols.map((c, i) => {
      const diff = i ? c.alloc[ri] - S.baseline.alloc[ri] : 0;
      const d = diff ? ` <span class="small">(${diff > 0 ? "+" : ""}${diff})</span>` : "";
      return `<td class="r ${i && c.id === S.best ? "hl" : ""}"><b>${c.alloc[ri]}%</b>${d}<div class="small">${esc(c.tools[ri])}</div></td>`;
    }).join("")}</tr>`;
  });
  h += `<tr><td class="facet">衍生品對沖</td>${cols.map((c, i) => `<td class="r ${i && c.id === S.best ? "hl" : ""}">${esc(c.hedge)}</td>`).join("")}</tr></tbody>`;
  $("#allocTbl").innerHTML = h;
}

function renderMonitor() {
  const groups = [["all", "全部"], ...D.groups, ["alert", "僅警戒"]];
  $("#grpFilter").innerHTML = `<div class="seg">${groups.map(([k, n]) => `<button data-g="${k}" class="${state.group === k ? "on" : ""}">${esc(n)}</button>`).join("")}</div>`;
  const gname = Object.fromEntries(D.groups);
  let rows = D.indicators;
  if (state.group === "alert") rows = rows.filter((r) => (r.level || 0) >= 1);
  else if (state.group !== "all") rows = rows.filter((r) => r.group === state.group);
  const order = Object.fromEntries(D.groups.map(([k], i) => [k, i]));
  rows = [...rows].sort((a, b) => order[a.group] - order[b.group]);
  let h = `<thead><tr><th>監控面向</th><th>核心監控指標</th><th class="r">最新值</th><th>走勢</th><th>分級觸發門檻</th><th>狀態</th><th>量化建議動作（占投組）</th><th>推薦商品 / 工具</th></tr></thead><tbody>`;
  for (const r of rows) {
    const act = r.level != null ? (r.actions[r.level] || r.actions[0] || "") : "—";
    const allActs = Object.entries(r.actions).map(([k, v]) => `${{ 0: "正常", 1: "一級", 2: "二級" }[k]}：${v}`).join("\n");
    h += `<tr class="${r.level >= 1 ? "row-lv" + r.level : ""}">
      <td class="facet">${esc(r.label)}<small>${esc(gname[r.group] || "")}</small></td>
      <td>${esc(r.metric)}${r.manual ? '<span class="badge man">手動</span>' : ""}<div class="src">${esc(r.source)}</div></td>
      <td class="r"><div class="val num">${esc(r.display)}</div><div class="small" style="white-space:nowrap">${esc(r.asof || "")}</div></td>
      <td>${spark(r.spark, 100, 28, "var(--green)")}</td>
      <td><span class="thr">${esc(r.threshold)}</span>${r.note ? `<div class="small">${esc(r.note)}</div>` : ""}</td>
      <td>${lvSpan(r.level, r.status)}${r.signal ? `<div class="signal">◆ ${esc(r.signal)}</div>` : ""}</td>
      <td class="act" title="${esc(allActs)}">${esc(act)}${r.signal_action ? `<div class="signal">◆ ${esc(r.signal_action)}</div>` : ""}</td>
      <td class="prod">${esc(r.products)}</td></tr>`;
  }
  $("#indTbl").innerHTML = h + "</tbody>";
}

function renderNews() {
  const langs = [["all", "全部"], ["zh", "中文"], ["en", "英文"]];
  $("#langSeg").innerHTML = langs.map(([k, n]) => `<button data-lang="${k}" class="${state.lang === k ? "on" : ""}">${n}</button>`).join("");
  const dirs = [["all", "全部"], ["up", "▲ 驅動上升"], ["down", "▼ 驅動下降"]];
  $("#dirSeg").innerHTML = dirs.map(([k, n]) => `<button data-dir="${k}" class="${state.dir === k ? "on" : ""}">${n}</button>`).join("");
  const maxC = Math.max(1, ...D.themes.map((t) => t.count));
  $("#themeList").innerHTML = `<div class="th-row ${state.theme ? "" : "sel"}" data-theme=""><div class="top"><span class="nm">全部主題</span><span class="cnt">${D.news.length} 則</span></div></div>` +
    D.themes.map((t) => `
    <div class="th-row ${state.theme === t.id ? "sel" : ""}" data-theme="${t.id}">
      <div class="top"><span class="nm">${esc(t.name)}</span>
        <span class="${t.dir > 0 ? "up" : t.dir < 0 ? "down" : "small"}" style="font-weight:800">${t.dir > 0 ? "▲" : t.dir < 0 ? "▼" : "—"}</span>
        <span class="cnt">${t.count} 則（▲${t.up} ▼${t.down}）</span></div>
      <div class="hbar"><i style="width:${(t.count / maxC * 100).toFixed(0)}%"></i></div>
      ${t.benefit.length ? `<div class="chips"><span class="lbl">受惠</span>${tickerChips(t.benefit.slice(0, 8), "b")}</div>` : ""}
      ${t.hurt.length ? `<div class="chips"><span class="lbl">受壓</span>${tickerChips(t.hurt.slice(0, 8), "h")}</div>` : ""}
    </div>`).join("");
  let items = D.news;
  if (state.theme) items = items.filter((n) => n.tags.some((t) => t.theme === state.theme));
  if (state.lang !== "all") items = items.filter((n) => n.lang === state.lang);
  if (state.dir !== "all") {
    const want = state.dir === "up" ? 1 : -1;
    items = items.filter((n) => n.tags.some((t) => t.dir === want && (!state.theme || t.theme === state.theme)));
  }
  if (state.newsQ) { const q = state.newsQ.toLowerCase(); items = items.filter((n) => n.title.toLowerCase().includes(q)); }
  const tagged = D.news.filter((n) => n.tags.length).length;
  $("#newsMeta").textContent = `近 72 小時 ${D.news.length} 則，已歸類主題 ${tagged} 則；顯示 ${Math.min(items.length, 200)} 則`;
  const indName = Object.fromEntries(D.indicators.map((r) => [r.key, r.metric]));
  $("#newsList").innerHTML = items.slice(0, 200).map((n) => `
    <div class="nw">
      <div class="m">${esc(n.source)}・${ago(n.time)}${n.tags.map((t) => ` <span class="tag">${esc(t.name)} <span class="d ${t.dir > 0 ? "up" : t.dir < 0 ? "down" : ""}">${t.dir > 0 ? "▲" : t.dir < 0 ? "▼" : "·"}</span></span>`).join("")}</div>
      <a class="t" href="${esc(n.link)}" target="_blank" rel="noopener noreferrer">${esc(n.title)}</a>
      ${n.benefit.length ? `<div class="chips"><span class="lbl">受惠</span>${tickerChips(n.benefit, "b")}</div>` : ""}
      ${n.hurt.length ? `<div class="chips"><span class="lbl">受壓</span>${tickerChips(n.hurt, "h")}</div>` : ""}
      ${n.related && n.related.length ? `<div class="chips"><span class="lbl">相關</span>${tickerChips(n.related, "")}</div>` : ""}
      ${n.indicators.length ? `<div class="chips"><span class="lbl">監控</span>${n.indicators.map((k) => `<span class="chip i" data-ind="${k}">${esc(indName[k] || k)}</span>`).join("")}</div>` : ""}
    </div>`).join("") || `<div class="nw small">沒有符合條件的新聞</div>`;
}

const PRESETS = [
  ["all", "全部", () => true],
  ["score", "綜合前 30", null],
  ["momentum", "強勢動能", (r) => r.above200 && r.chg3m > 10],
  ["newsUp", "新聞受惠", (r) => r.news > 0],
  ["newsDown", "新聞受壓", (r) => r.news < 0],
  ["overbought", "超買警戒（乖離>25% 或 RSI>75）", (r) => r.bias240 > 25 || r.rsi14 > 75],
  ["oversold", "超跌（RSI<30）", (r) => r.rsi14 != null && r.rsi14 < 30],
  ["nearHigh", "接近 52 週高點", (r) => r.from_high != null && r.from_high > -3],
  ["breakdown", "跌破 200 日線", (r) => r.above200 === false],
];
const COLS = [
  ["symbol", "代號"], ["name", "名稱"], ["market", "市場"], ["sector", "產業 / 主題"],
  ["last", "最新價", "r"], ["chg1d", "1日", "r"], ["chg1m", "1月", "r"], ["chg3m", "3月", "r"], ["ytd", "今年", "r"],
  ["bias240", "年線乖離", "r"], ["rsi14", "RSI", "r"], ["from_high", "距52週高", "r"],
  ["news", "新聞分數", "r"], ["score", "綜合分數", "r"], ["spark", "近 3 月走勢"],
];

function renderScreener() {
  const uniq = (k) => [...new Set(D.screener.map((r) => r[k]))];
  const opt = (sel, vals, cur, allLabel) => {
    sel.innerHTML = `<option value="all">${allLabel}</option>` + vals.map((v) => `<option value="${esc(v[0] ?? v)}" ${cur === (v[0] ?? v) ? "selected" : ""}>${esc(v[1] ?? v)}</option>`).join("");
  };
  opt($("#fMarket"), uniq("market"), state.market, "全部市場");
  opt($("#fAsset"), uniq("asset"), state.asset, "全部類別");
  opt($("#fTheme"), Object.entries(D.theme_names), state.fTheme, "全部主題");
  $("#fQ").value = state.q;
  $("#presetSeg").innerHTML = PRESETS.map(([k, n]) => `<button data-preset="${k}" class="${state.preset === k ? "on" : ""}">${esc(n)}</button>`).join("");
  drawScreenerTable();
}

function drawScreenerTable() {
  let rows = D.screener.slice();
  const p = PRESETS.find((x) => x[0] === state.preset);
  if (p && p[2]) rows = rows.filter(p[2]);
  if (state.market !== "all") rows = rows.filter((r) => r.market === state.market);
  if (state.asset !== "all") rows = rows.filter((r) => r.asset === state.asset);
  if (state.fTheme !== "all") rows = rows.filter((r) => r.themes.includes(state.fTheme));
  if (state.q) {
    const q = state.q.toLowerCase();
    rows = rows.filter((r) => [r.symbol, r.name, r.sector, r.market].some((x) => String(x).toLowerCase().includes(q)));
  }
  const k = state.sort, sgn = state.desc ? -1 : 1;
  rows.sort((a, b) => {
    const x = a[k], y = b[k];
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return (typeof x === "string" ? x.localeCompare(y, "zh-Hant") : x - y) * sgn;
  });
  if (state.preset === "score") rows = rows.filter((r) => r.score != null).sort((a, b) => b.score - a.score).slice(0, 30);
  $("#scrMeta").textContent = `篩選結果 ${rows.length} / ${D.screener.length} 檔`;
  let h = `<thead><tr>${COLS.map(([key, n, cls]) => `<th class="sort ${cls || ""}" data-sort="${key}">${n}${state.sort === key ? `<span class="arr">${state.desc ? "▼" : "▲"}</span>` : ""}</th>`).join("")}</tr></thead><tbody>`;
  for (const r of rows) {
    const bias = r.bias240 == null ? "—" : `<span class="${r.bias240 > 35 ? "lv2" : r.bias240 > 25 ? "lv1" : ""}" style="font-weight:${r.bias240 > 25 ? 800 : 400}">${r.bias240 > 0 ? "+" : ""}${r.bias240.toFixed(1)}%</span>`;
    const rsi = r.rsi14 == null ? "—" : `<span style="font-weight:${r.rsi14 > 70 || r.rsi14 < 30 ? 800 : 400}" class="${r.rsi14 > 70 ? "lv1" : r.rsi14 < 30 ? "lv0" : ""}">${r.rsi14.toFixed(0)}</span>`;
    const news = r.news ? `<span class="${r.news > 0 ? "up" : "down"}" style="font-weight:700">${r.news > 0 ? "+" : ""}${r.news}</span>` : '<span class="small">0</span>';
    h += `<tr>
      <td class="num"><b>${esc(r.symbol)}</b></td><td>${esc(r.name)}</td><td>${esc(r.market)}</td>
      <td class="small">${esc(r.sector)}</td>
      <td class="r num">${fmtPrice(r.last)}</td><td class="r num">${fmtPct(r.chg1d, 2)}</td><td class="r num">${fmtPct(r.chg1m)}</td>
      <td class="r num">${fmtPct(r.chg3m)}</td><td class="r num">${fmtPct(r.ytd)}</td>
      <td class="r num">${bias}</td><td class="r num">${rsi}</td><td class="r num">${fmtPct(r.from_high)}</td>
      <td class="r num">${news}</td><td class="r num"><b>${r.score == null ? "—" : r.score.toFixed(0)}</b></td>
      <td>${spark(r.spark, 100, 24)}</td></tr>`;
  }
  $("#scrTbl").innerHTML = h + "</tbody>";
}

function gotoTicker(sym) {
  Object.assign(state, { preset: "all", market: "all", asset: "all", fTheme: "all", q: sym });
  renderScreener();
  $("#screener").scrollIntoView();
}

// ---------------------------------------------------------------- events
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-sym],[data-g],[data-lang],[data-dir],[data-theme],[data-preset],[data-sort],[data-ind]");
  if (!t || !D) return;
  const ds = t.dataset;
  if (ds.sym) return gotoTicker(ds.sym);
  if (ds.g) { state.group = ds.g; return renderMonitor(); }
  if (ds.lang) { state.lang = ds.lang; return renderNews(); }
  if (ds.dir) { state.dir = ds.dir; return renderNews(); }
  if (ds.theme !== undefined) { state.theme = ds.theme || null; return renderNews(); }
  if (ds.preset) { state.preset = ds.preset; return renderScreener(); }
  if (ds.ind) { state.group = "all"; renderMonitor(); return $("#monitor").scrollIntoView(); }
  if (ds.sort) {
    if (state.sort === ds.sort) state.desc = !state.desc;
    else { state.sort = ds.sort; state.desc = !["symbol", "name", "market", "sector"].includes(ds.sort); }
    return drawScreenerTable();
  }
});
$("#fMarket").addEventListener("change", (e) => { state.market = e.target.value; drawScreenerTable(); });
$("#fAsset").addEventListener("change", (e) => { state.asset = e.target.value; drawScreenerTable(); });
$("#fTheme").addEventListener("change", (e) => { state.fTheme = e.target.value; drawScreenerTable(); });
$("#fQ").addEventListener("input", (e) => { state.q = e.target.value.trim(); drawScreenerTable(); });
$("#fReset").addEventListener("click", () => { Object.assign(state, { preset: "all", market: "all", asset: "all", fTheme: "all", q: "" }); renderScreener(); });
$("#newsQ").addEventListener("input", (e) => { state.newsQ = e.target.value.trim(); renderNews(); });
$("#refreshBtn").addEventListener("click", doRefresh);

function applyColor(mode) {
  document.documentElement.dataset.color = mode;
  $("#colorBtn").textContent = mode === "us" ? "綠漲紅跌" : "紅漲綠跌";
  try { localStorage.setItem("colorMode", mode); } catch (_) { /* ignore */ }
}
$("#colorBtn").addEventListener("click", () => applyColor(document.documentElement.dataset.color === "us" ? "tw" : "us"));
try { applyColor(localStorage.getItem("colorMode") || "tw"); } catch (_) { applyColor("tw"); }

// 導覽列目前區段高亮
const io = new IntersectionObserver((ents) => {
  ents.forEach((en) => {
    if (en.isIntersecting) document.querySelectorAll("#tabs a").forEach((a) => a.classList.toggle("active", a.getAttribute("href") === "#" + en.target.id));
  });
}, { rootMargin: "-40% 0px -55% 0px" });
document.querySelectorAll("main section").forEach((s) => io.observe(s));

detectLocal();
load();
// 靜態版每 10 分鐘自動重新讀取最新 data.json
setInterval(load, 10 * 60 * 1000);
