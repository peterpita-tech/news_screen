"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const LV = { 0: "lv0", 1: "lv1", 2: "lv2" };
let D = null;
let isLocal = false;
const state = {
  group: "all", newsQ: "", theme: null, cat: "all", span: "7d", mine: false, saved: false, ev: null, evLimit: 120, view: "news", fMine: false,
  preset: "all", market: "all", exch: "all", asset: "all", sector: "all", fTheme: "all", chain: "all", pos: "all", q: "", sort: "score", desc: true, page: 0,
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
  D.newsSyms = {};
  for (const n of D.news) for (const t of n.tags) {
    const set = (D.newsSyms[t.theme] = D.newsSyms[t.theme] || new Set());
    for (const k of ["mk_benefit", "mk_hurt", "mk_related"]) for (const x of n[k] || []) set.add(x);
  }
  const c = D.counts;
  $("#updated").innerHTML = `更新 <b>${esc(D.generated_at_tpe)}</b>（台北）· 新聞 ${c.news} 則`;
  let b = "";
  if (D.demo) b += `<div class="banner">⚠ 目前為<b>示範資料</b>（隨機模擬行情與範例新聞），非真實市場數據。實際使用請執行 <code>python app.py</code> 或由 GitHub Actions 產生。</div>`;
  if (D.error_count) b += `<div class="banner err">部分資料來源抓取失敗 ${D.error_count} 筆（其餘資料正常顯示）。<details class="errs"><summary>查看明細</summary>${D.errors.map(esc).join("<br>")}</details></div>`;
  $("#banners").innerHTML = b;
  renderOverview();
  renderScenario();
  renderMonitor();
  renderNews();
  renderScreener();
  loadMarket();
  route();
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
  $("#grpFilter").innerHTML = groups.map(([k, n]) => `<button data-g="${k}" class="${state.group === k ? "on" : ""}">${esc(n)}</button>`).join("");
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
      <td>${esc(r.metric)}${r.auto ? '<span class="badge auto">自動</span>' : r.manual ? '<span class="badge man">手動</span>' : ""}<div class="src">${esc(r.source)}</div></td>
      <td class="r"><div class="val num">${esc(r.display)}</div><div class="small" style="white-space:nowrap">${esc(r.asof || "")}</div></td>
      <td>${spark(r.spark, 100, 28, "var(--green)")}</td>
      <td><span class="thr">${esc(r.threshold)}</span>${r.note ? `<div class="small">${esc(r.note)}</div>` : ""}</td>
      <td>${lvSpan(r.level, r.status)}${r.signal ? `<div class="signal">◆ ${esc(r.signal)}</div>` : ""}</td>
      <td class="act" title="${esc(allActs)}">${esc(act)}${r.signal_action ? `<div class="signal">◆ ${esc(r.signal_action)}</div>` : ""}</td>
      <td class="prod">${esc(r.products)}</td></tr>`;
  }
  $("#indTbl").innerHTML = h + "</tbody>";
}

// ---------------------------------------------------------------- 市場事件（新聞）
const CATS = ["總經", "公司", "政策", "能源", "科技", "地緣"];
const store = {
  get(k) { try { return new Set(JSON.parse(localStorage.getItem(k) || "[]")); } catch (_) { return new Set(); } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify([...v])); } catch (_) { /* ignore */ } },
};
let WATCH = store.get("watchlist");
let SAVED = store.get("savedNews");
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 1800);
}
function toggleWatch(sym) {
  WATCH.has(sym) ? WATCH.delete(sym) : WATCH.add(sym);
  store.set("watchlist", WATCH);
  toast(WATCH.has(sym) ? `已加入自選：${nameOf(sym)}` : `已移出自選：${nameOf(sym)}`);
}
const starBtn = (sym) => `<button class="star ${WATCH.has(sym) ? "on" : ""}" data-star="${esc(sym)}" title="加入 / 移出自選">${WATCH.has(sym) ? "★" : "☆"}</button>`;
const newsSyms = (n) => [...n.benefit, ...n.hurt, ...(n.related || []), ...(n.mk_benefit || []), ...(n.mk_hurt || []), ...(n.mk_related || [])];
function rowOf(sym) {
  if (!D._rowIdx || D._rowIdxN !== allRows().length) {
    D._rowIdx = Object.fromEntries(allRows().map((r) => [r.symbol, r]));
    D._rowIdxN = allRows().length;
  }
  return D._rowIdx[sym];
}
function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("zh-TW", { timeZone: "Asia/Taipei", year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) + " GMT+8";
}
function agoShort(iso) {
  if (!iso) return "";
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return m < 60 ? `${m}m` : m < 1440 ? `${Math.round(m / 60)}h` : `${Math.round(m / 1440)}d`;
}
function newsFiltered(ignoreCat) {
  const now = Date.now();
  const midnight = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Taipei" })).setHours(0, 0, 0, 0) - (new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Taipei" })).getTime() - now);
  const since = state.span === "today" ? midnight : state.span === "24h" ? now - 864e5 : now - 7 * 864e5;
  let items = D.news.filter((n) => !n.time || new Date(n.time).getTime() >= since);
  if (!ignoreCat && state.cat !== "all") items = items.filter((n) => (n.cats || []).includes(state.cat));
  if (state.theme) items = items.filter((n) => n.tags.some((t) => t.theme === state.theme));
  if (state.mine) items = items.filter((n) => newsSyms(n).some((x) => WATCH.has(x)));
  if (state.saved) items = items.filter((n) => SAVED.has(n.id));
  if (state.newsQ) {
    const q = state.newsQ.toLowerCase();
    items = items.filter((n) => n.title.toLowerCase().includes(q) || newsSyms(n).some((x) => x.toLowerCase() === q || nameOf(x).toLowerCase().includes(q)));
  }
  return items;
}
function renderNews() {
  $("#timePills").innerHTML = [["today", "今日"], ["24h", "24H"], ["7d", "7D"]].map(([k, n]) => `<button data-span="${k}" class="${state.span === k ? "on" : ""}">${n}</button>`).join("");
  $("#mineOnly").checked = state.mine;
  $("#savedBtn").classList.toggle("on", state.saved);
  const base = newsFiltered(true);
  const cnt = (c) => (c === "all" ? base.length : base.filter((n) => (n.cats || []).includes(c)).length);
  $("#catTabs").innerHTML = [["all", "全部"], ...CATS.map((c) => [c, c])].map(([k, n]) => `<button data-cat="${k}" class="${state.cat === k ? "on" : ""}">${n}<span class="c">${cnt(k)}</span></button>`).join("") +
    (state.theme ? `<button class="on" data-theme="">主題：${esc(D.theme_names[state.theme] || state.theme)} ✕</button>` : "");
  const items = newsFiltered(false);
  $("#evCount").textContent = items.length;
  if (!items.some((n) => n.id === state.ev)) state.ev = items[0] ? items[0].id : null;
  $("#evItems").innerHTML = items.length ? items.slice(0, state.evLimit).map((n) => {
    const fresh = n.time && Date.now() - new Date(n.time).getTime() < 2 * 3600e3;
    const t0 = n.tags[0];
    const lead = [...(n.mk_benefit || []), ...n.benefit].slice(0, 2).map(nameOf).join("、");
    return `<div class="ev ${n.id === state.ev ? "sel" : ""}" data-ev="${n.id}">
      <div class="ev-top"><div class="ev-title">${esc(n.title)}</div><div class="ev-time">${agoShort(n.time)}<span class="dot ${fresh ? "fresh" : ""}"></span></div></div>
      <div class="ev-meta">${esc((n.cats && n.cats[0]) || "其他")} · ${esc(n.region || "全球")}${SAVED.has(n.id) ? " · 已收藏" : ""}</div>
      <div class="ev-sub">${t0 ? `${esc(t0.name)} <span class="${t0.dir > 0 ? "up" : t0.dir < 0 ? "down" : ""}">${t0.dir > 0 ? "▲" : t0.dir < 0 ? "▼" : "·"}</span>` : esc(n.source)}${lead ? ` · ${esc(lead)}` : ""}</div>
    </div>`;
  }).join("") + (items.length > state.evLimit ? `<button class="ev-more" data-more="1">顯示更多（${items.length - state.evLimit}）</button>` : "")
    : `<div class="ev-empty">沒有符合條件的事件${state.mine ? "（自選清單可在全市場篩選或事件內點 ☆ 加入）" : ""}</div>`;
  renderDetail();
  renderSide();
}
function relRows(n) {
  const out = [];
  const add = (list, role) => list.forEach((s) => { if (!out.some((x) => x.s === s)) out.push({ s, role }); });
  add(n.benefit, "b"); add(n.mk_benefit || [], "b"); add(n.hurt, "h"); add(n.mk_hurt || [], "h"); add(n.related || [], "r"); add(n.mk_related || [], "r");
  return out.slice(0, 24);
}
function renderDetail() {
  const n = D.news.find((x) => x.id === state.ev);
  if (!n) { $("#evDetail").innerHTML = `<div class="ev-empty">請從左側選擇一則事件</div>`; return; }
  const ups = n.tags.filter((t) => t.dir > 0), downs = n.tags.filter((t) => t.dir < 0);
  const names = (l) => l.slice(0, 4).map(nameOf).join("、");
  const ben = [...n.benefit, ...(n.mk_benefit || [])], hurt = [...n.hurt, ...(n.mk_hurt || [])];
  let summary = n.tags.length
    ? `此事件歸類為「${n.tags.map((t) => t.name).join("、")}」` + (ups.length ? `，判定 ${ups.map((t) => t.name).join("、")} 驅動因子上升` : "") + (downs.length ? `，${downs.map((t) => t.name).join("、")} 驅動因子下降` : "") + "。"
    : "此事件未歸入既有主題，僅依標題點名連結相關標的。";
  if (ben.length) summary += ` 受惠：${names(ben)}${ben.length > 4 ? " 等" : ""}。`;
  if (hurt.length) summary += ` 受壓：${names(hurt)}${hurt.length > 4 ? " 等" : ""}。`;
  const rows = relRows(n);
  const roleTxt = { b: "受惠", h: "受壓", r: "相關" };
  const indMap = Object.fromEntries(D.indicators.map((r) => [r.key, r]));
  const inds = n.indicators.map((k) => indMap[k]).filter(Boolean);
  const same = D.news.filter((x) => x.id !== n.id && x.tags.some((t) => n.tags.some((u) => u.theme === t.theme))).slice(0, 6);
  $("#evDetail").innerHTML = `
    <div class="dt-head">
      <div style="flex:1;min-width:0">
        <div class="dt-label"><b>${esc((n.cats && n.cats[0]) || "其他")}</b><span>${esc(n.region || "全球")}</span>${(n.cats || []).slice(1).map((c) => `<span>· ${esc(c)}</span>`).join("")}</div>
        <h2 class="dt-title">${esc(n.title)}</h2>
        <div class="dt-time">${esc(fmtTime(n.time))} · ${esc(n.source)} · ${n.time ? ago(n.time) : ""}</div>
      </div>
      <div class="dt-actions">
        <button class="icon-btn ${SAVED.has(n.id) ? "on" : ""}" data-save="${n.id}" title="收藏"><svg viewBox="0 0 24 24" width="17" height="17"><path d="M6 3h12v18l-6-4-6 4z" fill="${SAVED.has(n.id) ? "currentColor" : "none"}" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg></button>
        <button class="icon-btn" data-share="${n.id}" title="複製連結"><svg viewBox="0 0 24 24" width="17" height="17"><circle cx="18" cy="5" r="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="6" cy="12" r="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="18" cy="19" r="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8.2 10.8l7.6-4.4M8.2 13.2l7.6 4.4" stroke="currentColor" stroke-width="1.8"/></svg></button>
        <a class="icon-btn" href="${esc(n.link)}" target="_blank" rel="noopener noreferrer" title="閱讀原文"><svg viewBox="0 0 24 24" width="17" height="17"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></a>
      </div>
    </div>
    <hr class="dt-hr">
    <div class="impact">
      <h3>影響判讀</h3>
      <p>${esc(summary)}</p>
      ${n.tags.length ? `<div class="drv">${n.tags.map((t) => `<span class="drv-tag" data-theme="${t.theme}">${esc(t.name)} <span class="${t.dir > 0 ? "up" : t.dir < 0 ? "down" : "small"}">${t.dir > 0 ? "▲ 上升" : t.dir < 0 ? "▼ 下降" : "· 方向不明"}</span></span>`).join("")}</div>` : ""}
      <a class="cta" href="${esc(n.link)}" target="_blank" rel="noopener noreferrer">閱讀原文 ↗</a>
    </div>
    ${rows.length ? `<div class="dt-sec"><h4>相關標的</h4><table class="mini-tbl"><thead><tr><th></th><th>標的</th><th>市場</th><th>影響</th><th class="r">最新價</th><th class="r">1日</th><th class="r">新聞分數</th><th class="r">綜合分數</th></tr></thead><tbody>
      ${rows.map(({ s, role }) => { const r = rowOf(s) || {}; return `<tr><td>${starBtn(s)}</td><td><b data-sym="${esc(s)}" style="cursor:pointer">${esc(nameOf(s))}</b> <span class="small">${esc(s)}</span></td><td class="small">${esc(r.market || "")}</td>
        <td><span class="role ${role}">${roleTxt[role]}</span></td><td class="r num">${fmtPrice(r.last)}</td><td class="r num">${fmtPct(r.chg1d, 2)}</td>
        <td class="r num">${r.news ? `<span class="${r.news > 0 ? "up" : "down"}">${r.news > 0 ? "+" : ""}${r.news}</span>` : "—"}</td><td class="r num">${r.score == null ? "—" : r.score.toFixed(0)}</td></tr>`; }).join("")}
    </tbody></table></div>` : ""}
    ${inds.length ? `<div class="dt-sec"><h4>連動監控指標</h4><div class="ind-cards">${inds.map((r) => `<div class="ind-card" data-ind="${r.key}"><div class="n">${esc(r.label)}</div><div class="v num">${esc(r.display)}</div>${lvSpan(r.level, r.status)}<div class="small">${esc(r.metric)}</div></div>`).join("")}</div></div>` : ""}
    ${same.length ? `<div class="dt-sec"><h4>同主題事件</h4><ul class="rel-news">${same.map((x) => `<li data-ev="${x.id}"><span class="t">${esc(x.title)}</span><span class="small">${agoShort(x.time)}</span></li>`).join("")}</ul></div>` : ""}`;
}
function renderSide() {
  const base = newsFiltered(true);
  const cnt = {};
  for (const n of base) for (const t of n.tags) cnt[t.theme] = (cnt[t.theme] || 0) + 1;
  const heat = Object.entries(cnt).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const mx = Math.max(1, ...heat.map((x) => x[1]));
  const ov = D.overview.slice(0, 8);
  const alerts = D.indicators.filter((r) => (r.level || 0) >= 1).sort((a, b) => b.level - a.level).slice(0, 6);
  const watch = [...WATCH].slice(0, 12);
  $("#evSide").innerHTML = `
    <div class="side-box"><h4>主題熱度<a data-theme="">全部</a></h4>${heat.map(([k, c]) => {
      const th = D.themes.find((t) => t.id === k) || {};
      return `<div class="heat" data-theme="${k}"><span class="hn">${esc(D.theme_names[k] || k)}</span><span class="${th.dir > 0 ? "up" : th.dir < 0 ? "down" : "small"}">${th.dir > 0 ? "▲" : th.dir < 0 ? "▼" : "·"}</span><span class="hb"><i style="width:${(c / mx * 100).toFixed(0)}%"></i></span><span class="hc">${c}</span></div>`;
    }).join("") || '<div class="small">尚無資料</div>'}</div>
    <div class="side-box"><h4>市場脈動<a data-goto="overview">更多</a></h4>${ov.map((r) => `<div class="tick" data-sym="${esc(r.symbol)}"><b>${esc(r.name)}</b><span class="num">${fmtPrice(r.last)} ${fmtPct(r.chg1d, 2)}</span></div>`).join("")}</div>
    <div class="side-box"><h4>指標警戒<a data-goto="monitor">全部</a></h4>${alerts.map((r) => `<div class="alert-row" data-ind="${r.key}">${lvSpan(r.level, "")}<span class="an">${esc(r.label)}</span><span class="num small">${esc(r.display)}</span></div>`).join("") || '<div class="small">目前無警戒</div>'}</div>
    <div class="side-box"><h4>我的自選<a data-goto="screener">管理</a></h4>${watch.length ? watch.map((s) => { const r = rowOf(s) || {}; return `<div class="tick" data-sym="${esc(s)}"><b>${esc(nameOf(s))}</b><span class="num">${fmtPrice(r.last)} ${fmtPct(r.chg1d, 2)}</span></div>`; }).join("") : '<div class="small">在事件或篩選表點 ☆ 加入自選，開啟「只看自選」即只顯示相關事件。</div>'}</div>`;
}

// ---------------------------------------------------------------- 分頁（view）路由
function setView(v, push = true) {
  state.view = v;
  document.querySelectorAll(".view").forEach((el) => (el.hidden = el.id !== "view-" + v));
  document.querySelectorAll("#views a").forEach((a) => a.classList.toggle("on", a.dataset.view === v));
  if (push) history.replaceState(null, "", "#" + v + (v === "news" && state.ev ? "/" + state.ev : ""));
  window.scrollTo(0, 0);
}
function route() {
  const [v, id] = (location.hash.slice(1) || "news").split("/");
  if (id) state.ev = id;
  if (v === "news" && id) renderNews();
  setView(["news", "monitor", "scenario", "screener", "overview"].includes(v) ? v : "news", false);
}

// ---------------------------------------------------------------- 跨資產＋台美全市場篩選
let M = null;
const PAGE = 100;
const ZS = { 台灣: "https://peterpita-tech.github.io/Peterpita/tw/", 美國: "https://peterpita-tech.github.io/Peterpita/" };
async function loadMarket() {
  try {
    const r = await fetch("market.json?t=" + Date.now(), { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    M = await r.json();
    for (const x of M.rows) if (!D.names[x.symbol]) D.names[x.symbol] = x.name;
  } catch (e) {
    M = { rows: [], error: e.message };
  }
  renderScreener();
  renderNews();
}
const allRows = () => (M ? D.screener.concat(M.rows) : D.screener);
const PRESETS = [
  ["all", "全部", () => true],
  ["score", "綜合前 50", null],
  ["momentum", "強勢動能", (r) => (r.above200 && r.chg3m > 10) || r.zscore >= 85],
  ["newsUp", "新聞受惠", (r) => r.news > 0],
  ["newsDown", "新聞受壓", (r) => r.news < 0],
  ["mention", "新聞點名", (r) => r.mentions > 0],
  ["chain", "供應鏈標的", (r) => r.chain && r.chain.length],
  ["aboveMA", "站上月線", (r) => r.aboveMA === true],
  ["overbought", "超買警戒", (r) => r.bias240 > 25 || r.rsi14 > 75 || r.z >= 2.5],
  ["oversold", "超跌（RSI<30）", (r) => r.rsi14 != null && r.rsi14 < 30],
  ["nearHigh", "接近 52 週高點", (r) => r.from_high != null && r.from_high > -3],
];
const COLS = [
  ["symbol", "代號"], ["name", "名稱"], ["market", "市場"], ["sector", "產業 / 供應鏈"],
  ["last", "最新價", "r"], ["chg1d", "1日", "r"], ["chg1m", "1月", "r"], ["chg3m", "3月", "r"], ["ytd", "今年", "r"],
  ["bias240", "年線乖離", "r"], ["biasMA", "月線乖離", "r"], ["rsi14", "RSI", "r"], ["winPct", "獲利比例", "r"], ["zscore", "籌碼強勢", "r"],
  ["news", "新聞分數", "r"], ["score", "綜合分數", "r"], ["spark", "走勢 / 連結"],
];
const SORT_TEXT = ["symbol", "name", "market", "sector"];

function renderScreener() {
  const rows = allRows();
  const uniq = (arr) => [...new Set(arr.filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b), "zh-Hant"));
  const opt = (sel, vals, cur, allLabel) => {
    sel.innerHTML = `<option value="all">${allLabel}</option>` + vals.map((v) => `<option value="${esc(v[0] ?? v)}" ${cur === (v[0] ?? v) ? "selected" : ""}>${esc(v[1] ?? v)}</option>`).join("");
  };
  const mkts = uniq(rows.map((r) => r.market));
  opt($("#fMarket"), mkts, state.market, "全部市場");
  opt($("#fExch"), uniq(rows.filter((r) => state.market === "all" || r.market === state.market).map((r) => r.exch)), state.exch, "全部交易所");
  opt($("#fAsset"), uniq(rows.map((r) => r.asset)), state.asset, "全部類別");
  opt($("#fSector"), uniq(rows.filter((r) => state.market === "all" || r.market === state.market).map((r) => r.sector)), state.sector, "全部產業");
  opt($("#fTheme"), Object.entries(D.theme_names), state.fTheme, "全部新聞主題");
  opt($("#fChain"), uniq(rows.flatMap((r) => (r.chain || []).map((c) => c.theme))), state.chain, "全部供應鏈");
  opt($("#fPos"), ["上游", "中游", "下游", "相關"], state.pos, "全部位置");
  $("#fQ").value = state.q;
  $("#presetSeg").innerHTML = PRESETS.map(([k, n]) => `<button data-preset="${k}" class="${state.preset === k ? "on" : ""}">${esc(n)}</button>`).join("");
  const mm = D.market_meta || {};
  const meta = mm.meta || {};
  $("#scrNote").innerHTML = (M && M.error ? `<span class="lv lv2">全市場資料載入失敗：${esc(M.error)}</span><br>` : "") +
    `跨資產（約 180 檔，含指數、ETF、債券、商品、外匯）：綜合分數 = 動能百分位（1M / 3M / 6M）× 0.7 + 新聞分數百分位 × 0.3，站上 200 日線加 5 分。` +
    `台美全市場（${mm.count ?? "—"} 檔；台股 ${esc(meta.台股?.date || "—")}、美股 ${esc(meta.美股?.date || "—")}）：綜合分數 = <a href="${ZS.美國}" target="_blank" rel="noopener">籌碼結構掃描</a>強勢分數 × 0.7 + 新聞分數百分位 × 0.3；台股供應鏈位置來自 <a href="${esc(mm.chain_link || "#")}" target="_blank" rel="noopener">semi_value_chain</a>。` +
    `新聞分數：主題規則判定受惠 +1 / 受壓 −1、標題直接點名 ±1、供應鏈傳導 ±0.5（24 小時內 ×1.5）。`;
  drawScreenerTable();
}

function filteredRows() {
  let rows = allRows();
  const p = PRESETS.find((x) => x[0] === state.preset);
  if (p && p[2]) rows = rows.filter(p[2]);
  if (state.fMine) rows = rows.filter((r) => WATCH.has(r.symbol));
  if (state.market !== "all") rows = rows.filter((r) => r.market === state.market);
  if (state.exch !== "all") rows = rows.filter((r) => r.exch === state.exch);
  if (state.asset !== "all") rows = rows.filter((r) => r.asset === state.asset);
  if (state.sector !== "all") rows = rows.filter((r) => r.sector === state.sector);
  if (state.fTheme !== "all") rows = rows.filter((r) => (r.themes || []).includes(state.fTheme) || (D.newsSyms[state.fTheme] || new Set()).has(r.symbol));
  if (state.chain !== "all" || state.pos !== "all") rows = rows.filter((r) => (r.chain || []).some((c) => (state.chain === "all" || c.theme === state.chain) && (state.pos === "all" || c.pos === state.pos)));
  if (state.q) {
    const q = state.q.toLowerCase();
    const exact = rows.filter((r) => r.symbol.toLowerCase() === q);
    rows = exact.length ? exact : rows.filter((r) => [r.symbol, r.name, r.sector].some((x) => String(x ?? "").toLowerCase().includes(q)));
  }
  const k = state.sort, sgn = state.desc ? -1 : 1;
  rows = rows.slice().sort((a, b) => {
    const x = a[k], y = b[k];
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return (typeof x === "string" ? x.localeCompare(y, "zh-Hant") : x - y) * sgn;
  });
  if (state.preset === "score") rows = rows.filter((r) => r.score != null).sort((a, b) => b.score - a.score).slice(0, 50);
  return rows;
}

function drawScreenerTable() {
  const rows = filteredRows();
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  state.page = Math.min(state.page, pages - 1);
  const view = rows.slice(state.page * PAGE, (state.page + 1) * PAGE);
  $("#scrMeta").textContent = `篩選結果 ${rows.length} / ${allRows().length} 檔${M ? "" : "（全市場載入中…）"}`;
  let h = `<thead><tr>${COLS.map(([key, n, cls]) => `<th class="sort ${cls || ""}" data-sort="${key}">${n}${state.sort === key ? `<span class="arr">${state.desc ? "▼" : "▲"}</span>` : ""}</th>`).join("")}</tr></thead><tbody>`;
  const numCell = (v, f) => (v == null ? '<span class="small">—</span>' : f(v));
  for (const r of view) {
    const bias = numCell(r.bias240, (v) => `<span class="${v > 35 ? "lv2" : v > 25 ? "lv1" : ""}" style="font-weight:${v > 25 ? 800 : 400}">${v > 0 ? "+" : ""}${v.toFixed(1)}%</span>`);
    const rsi = numCell(r.rsi14, (v) => `<span style="font-weight:${v > 70 || v < 30 ? 800 : 400}" class="${v > 70 ? "lv1" : v < 30 ? "lv0" : ""}">${v.toFixed(0)}</span>`);
    const news = r.news ? `<span class="${r.news > 0 ? "up" : "down"}" style="font-weight:700">${r.news > 0 ? "+" : ""}${r.news}</span>${r.mentions ? `<span class="small" title="標題直接點名次數"> ·${r.mentions}</span>` : ""}` : '<span class="small">0</span>';
    const chain = (r.chain || []).slice(0, 3).map((c) => `<span class="pos pos-${esc(c.pos)}" title="${esc(c.group)}">${esc(c.theme)}·${esc(c.pos)}</span>`).join("") + ((r.chain || []).length > 3 ? `<span class="small">+${r.chain.length - 3}</span>` : "");
    const links = r.full ? `<a class="lnk" href="${ZS[r.market] || ZS.美國}" target="_blank" rel="noopener">籌碼</a>` + (r.chain && r.chain.length ? `<a class="lnk" href="${esc((D.market_meta || {}).chain_link || "#")}" target="_blank" rel="noopener">供應鏈</a>` : "") : "";
    h += `<tr>
      <td class="num" style="white-space:nowrap">${starBtn(r.symbol)}<b>${esc(r.symbol)}</b></td><td>${esc(r.name)}</td><td>${esc(r.market)}${r.exch ? `<div class="small">${esc(r.exch)}</div>` : ""}</td>
      <td class="small">${esc(r.sector)}${chain ? `<div>${chain}</div>` : ""}</td>
      <td class="r num">${fmtPrice(r.last)}</td><td class="r num">${fmtPct(r.chg1d, 2)}</td><td class="r num">${fmtPct(r.chg1m)}</td>
      <td class="r num">${fmtPct(r.chg3m)}</td><td class="r num">${fmtPct(r.ytd)}</td>
      <td class="r num">${bias}</td><td class="r num">${fmtPct(r.biasMA)}</td><td class="r num">${rsi}</td>
      <td class="r num">${numCell(r.winPct, (v) => v.toFixed(0) + "%")}</td><td class="r num">${numCell(r.zscore, (v) => v.toFixed(0))}</td>
      <td class="r num">${news}</td><td class="r num"><b>${r.score == null ? "—" : r.score.toFixed(0)}</b></td>
      <td>${r.spark ? spark(r.spark, 90, 22) : ""}${links}</td></tr>`;
  }
  $("#scrTbl").innerHTML = h + "</tbody>";
  $("#scrPager").innerHTML = pages > 1 ? `<span class="small">第 ${state.page + 1} / ${pages} 頁</span>
    <button data-pg="0" ${state.page === 0 ? "disabled" : ""}>« 第一頁</button><button data-pg="${state.page - 1}" ${state.page === 0 ? "disabled" : ""}>‹ 上一頁</button>
    <button data-pg="${state.page + 1}" ${state.page >= pages - 1 ? "disabled" : ""}>下一頁 ›</button><button data-pg="${pages - 1}" ${state.page >= pages - 1 ? "disabled" : ""}>最末頁 »</button>` : "";
}

function resetFilters(extra) {
  Object.assign(state, { preset: "all", market: "all", exch: "all", asset: "all", sector: "all", fTheme: "all", chain: "all", pos: "all", q: "", page: 0 }, extra || {});
}
function gotoTicker(sym) {
  resetFilters({ q: sym });
  renderScreener();
  setView("screener");
}

// ---------------------------------------------------------------- events
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-star],[data-save],[data-share],[data-ev],[data-more],[data-span],[data-cat],[data-goto],[data-view],[data-sym],[data-g],[data-theme],[data-preset],[data-sort],[data-ind],[data-pg]");
  if (!t || !D) return;
  const ds = t.dataset;
  if (ds.star) { e.stopPropagation(); toggleWatch(ds.star); renderNews(); return drawScreenerTable(); }
  if (ds.save) { SAVED.has(ds.save) ? SAVED.delete(ds.save) : SAVED.add(ds.save); store.set("savedNews", SAVED); toast(SAVED.has(ds.save) ? "已收藏" : "已取消收藏"); return renderNews(); }
  if (ds.share) {
    const url = location.href.split("#")[0] + "#news/" + ds.share;
    (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject()).then(() => toast("已複製連結"), () => prompt("複製此連結", url));
    return;
  }
  if (ds.ev) {
    state.ev = ds.ev; renderNews();
    history.replaceState(null, "", "#news/" + ds.ev);
    if (state.view !== "news") setView("news");
    if (window.innerWidth < 860) $("#evDetail").scrollIntoView();
    return;
  }
  if (ds.more) { state.evLimit += 120; return renderNews(); }
  if (ds.span) { state.span = ds.span; return renderNews(); }
  if (ds.cat) { state.cat = ds.cat; return renderNews(); }
  if (ds.view) { e.preventDefault(); return setView(ds.view); }
  if (ds.goto) return setView(ds.goto);
  if (ds.sym) return gotoTicker(ds.sym);
  if (ds.pg) { state.page = +ds.pg; drawScreenerTable(); return window.scrollTo(0, 0); }
  if (ds.g) { state.group = ds.g; return renderMonitor(); }
  if (ds.theme !== undefined) { state.theme = ds.theme || null; state.cat = "all"; renderNews(); return setView("news"); }
  if (ds.preset) { state.preset = ds.preset; state.page = 0; return renderScreener(); }
  if (ds.ind) { state.group = "all"; renderMonitor(); return setView("monitor"); }
  if (ds.sort) {
    if (state.sort === ds.sort) state.desc = !state.desc;
    else { state.sort = ds.sort; state.desc = !SORT_TEXT.includes(ds.sort); }
    state.page = 0;
    return drawScreenerTable();
  }
});
[["#fMarket", "market"], ["#fExch", "exch"], ["#fAsset", "asset"], ["#fSector", "sector"], ["#fTheme", "fTheme"], ["#fChain", "chain"], ["#fPos", "pos"]].forEach(([sel, key]) =>
  $(sel).addEventListener("change", (e) => { state[key] = e.target.value; state.page = 0; if (key === "market") { state.exch = "all"; state.sector = "all"; return renderScreener(); } drawScreenerTable(); }));
$("#fQ").addEventListener("input", (e) => { state.q = e.target.value.trim(); state.page = 0; drawScreenerTable(); });
$("#fMine").addEventListener("change", (e) => { state.fMine = e.target.checked; state.page = 0; drawScreenerTable(); });
$("#fReset").addEventListener("click", () => { resetFilters(); $("#fMine").checked = state.fMine = false; renderScreener(); });
$("#newsQ").addEventListener("input", (e) => { state.newsQ = e.target.value.trim(); renderNews(); });
$("#mineOnly").addEventListener("change", (e) => { state.mine = e.target.checked; renderNews(); });
$("#savedBtn").addEventListener("click", () => { state.saved = !state.saved; renderNews(); });
$("#refreshBtn").addEventListener("click", doRefresh);
window.addEventListener("hashchange", () => D && route());

function applyColor(mode) {
  document.documentElement.dataset.color = mode;
  $("#colorBtn").textContent = mode === "us" ? "綠漲紅跌" : "紅漲綠跌";
  try { localStorage.setItem("colorMode", mode); } catch (_) { /* ignore */ }
}
$("#colorBtn").addEventListener("click", () => applyColor(document.documentElement.dataset.color === "us" ? "tw" : "us"));
try { applyColor(localStorage.getItem("colorMode") || "tw"); } catch (_) { applyColor("tw"); }

detectLocal();
load();
// 靜態版每 10 分鐘自動重新讀取最新 data.json
setInterval(load, 10 * 60 * 1000);
