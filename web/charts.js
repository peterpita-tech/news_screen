"use strict";
/* 流動性動態圖表：純 SVG，無外部套件。
   每個 panel 由多張共用時間軸的子圖組成（單一 y 軸），滑鼠 / 觸控十字線同步，下方資訊框顯示該日各序列數值。 */
const LQ = { data: null, range: {}, open: {}, hover: {} };
const RANGES = [["3M", 92], ["6M", 183], ["1Y", 366], ["2Y", 731], ["3Y", 1100], ["10Y", 3660]];

function lqEsc(s) { return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
const toT = (d) => Date.parse(d + "T00:00:00Z");
function fmtV(v, unit) {
  if (v == null || isNaN(v)) return "—";
  const a = Math.abs(v);
  const s = a >= 1000 || unit === "bp" ? v.toLocaleString("en-US", { maximumFractionDigits: 0 }) : a >= 100 ? v.toFixed(1) : v.toFixed(2);
  return unit === "%" ? s + "%" : unit === "bp" ? s + " bp" : unit === "倍" ? s + "x" : unit ? s + " " + unit : s;
}
function niceTicks(lo, hi, n = 4) {
  const span = hi - lo || 1, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) || mag * 10;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}
function valueAt(data, t) { // 該日或之前最近一筆
  let lo = 0, hi = data.length - 1, ans = -1;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (data[m][2] <= t) { ans = m; lo = m + 1; } else hi = m - 1; }
  return ans < 0 ? null : data[ans];
}

// 圖表組：資料鍵 → 容器
const SETS = { liquidity: ["panels", "#lqPanels"], monitor: ["monitor", "#monCharts"], overview: ["overview", "#ovCharts"] };
LQ.byId = {};
LQ.loading = null;

function loadCharts(set = "liquidity") {
  const box = $(SETS[set][1]);
  if (LQ.data) return renderSet(set);
  if (box && !box.innerHTML) box.innerHTML = '<div class="ev-empty">圖表資料載入中…</div>';
  LQ.loading = LQ.loading || fetch("charts.json?t=" + Date.now(), { cache: "no-store" }).then((r) => {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }).then((d) => {
    LQ.data = d;
    for (const k of Object.values(SETS).map((x) => x[0])) for (const p of d[k] || []) {
      LQ.byId[p.id] = p;
      for (const ch of p.charts) for (const s of ch.series) for (const pt of s.data) pt[2] = toT(pt[0]);
    }
  });
  LQ.loading.then(() => renderSet(set), (e) => { if (box) box.innerHTML = `<div class="ev-empty">圖表資料載入失敗：${lqEsc(e.message)}</div>`; });
}
const renderLiquidity = () => renderSet("liquidity");

function legendHtml(p) {
  return p.charts.flatMap((ch) => ch.series.map((s) => {
    const last = s.data[s.data.length - 1];
    let extra = "";
    if (ch.index && p._geo) {
      const base = valueAt(s.data, p._geo.tMin) || s.data[0];
      if (base && last) { const chg = (last[1] / base[1] - 1) * 100; extra = ` <span class="${chg >= 0 ? "up" : "down"}">${chg >= 0 ? "+" : ""}${chg.toFixed(1)}%</span>`; }
    }
    return `<span class="lg"><i class="sw ${s.type}" style="background:${s.color}"></i>${lqEsc(s.name)} <b class="num">${fmtV(last && last[1], ch.unit)}</b>${extra}<span class="d">（${lqEsc(last ? last[0].slice(5).replace("-", "/") : "")}）</span></span>`;
  })).join("");
}

function renderSet(set) {
  const [key, sel] = SETS[set];
  const box = $(sel);
  if (!box || !LQ.data) return;
  const ps = LQ.data[key] || [];
  if (set === "liquidity") $("#lqMeta").textContent = `資料時間 ${LQ.data.generated_at}（FRED、multpl.com、Yahoo Finance）`;
  if (!ps.length) { box.innerHTML = '<div class="ev-empty">尚無圖表資料</div>'; return; }
  box.innerHTML = ps.map((p) => {
    if (LQ.open[p.id] === undefined) LQ.open[p.id] = true;
    if (!LQ.range[p.id]) LQ.range[p.id] = p.years >= 10 ? "10Y" : "1Y";
    const ranges = RANGES.filter(([k, d]) => d <= (p.years || 3) * 366 + 10);
    return `<section class="lq-panel ${LQ.open[p.id] ? "open" : ""}" id="lq-${p.id}">
      <header class="lq-hd" data-lqtoggle="${p.id}"><span class="lq-no">${p.no}</span><h3>${lqEsc(p.title)}</h3>
        <span class="lq-sub">${lqEsc(p.subtitle)}</span><span class="lq-caret">⌃</span></header>
      <div class="lq-body">
        ${p.kpis && p.kpis.length ? `<div class="lq-kpis">${p.kpis.map((k) => `<div class="lq-kpi"><div class="n">${lqEsc(k.label)}</div><div class="v num">${lqEsc(k.value)}</div><div class="s">${lqEsc(k.asof || "")}${k.src ? " · " + lqEsc(k.src.replace(/^手動：/, "")) : ""}</div></div>`).join("")}</div>` : ""}
        <div class="lq-ranges">${ranges.map(([k]) => `<button data-lqrange="${p.id}:${k}" class="${LQ.range[p.id] === k ? "on" : ""}">${k}</button>`).join("")}</div>
        <div class="lq-charts" data-panel="${p.id}">${p.charts.map((ch, i) => `${ch.title ? `<div class="lq-ctitle" id="lqc-${lqEsc(ch.key || "")}"><i class="sw" style="background:${ch.series[0].color}"></i>${lqEsc(ch.title)} <b class="num">${(() => { const l = ch.series[0].data[ch.series[0].data.length - 1]; return l ? fmtV(l[1], ch.unit) + `<em>（${l[0]}）</em>` : ""; })()}</b>${ch.refs && ch.refs.length ? `<span>${ch.refs.map((r) => `<i class="ref-sw lv${r.lv}"></i>${lqEsc(r.label)}`).join("")}</span>` : ""}</div>` : ""}<div class="lq-chart" data-ci="${i}" style="height:${ch.height}px"></div>`).join("")}</div>
        ${p.charts.some((c) => c.title) ? "" : `<div class="lq-legend" id="lql-${p.id}">${legendHtml(p)}</div>`}
        <div class="lq-info" id="lqi-${p.id}"><span class="small">將游標移到圖上查看各日數值</span></div>
        ${p.defs && p.defs.length ? `<details class="lq-defs"><summary>由上到下點開看定義</summary>${p.defs.map((d) => `<p><b>${lqEsc(d.term)}</b>：${lqEsc(d.text)}</p>`).join("")}</details>` : ""}
      </div></section>`;
  }).join("");
  for (const p of ps) if (LQ.open[p.id]) drawPanel(p);
}

function drawPanel(p) {
  const wrap = document.querySelector(`#lq-${p.id} .lq-charts`);
  if (!wrap) return;
  const days = RANGES.find((r) => r[0] === LQ.range[p.id])[1];
  const allT = p.charts.flatMap((ch) => ch.series.map((s) => s.data.length ? s.data[s.data.length - 1][2] : 0));
  const tMax = Math.max(...allT), tMin = tMax - days * 864e5;
  const W = wrap.clientWidth || 800, ML = 52, MR = 18;
  const x = (t) => ML + (t - tMin) / (tMax - tMin) * (W - ML - MR);
  p._geo = { tMin, tMax, ML, MR, W, x };
  p.charts.forEach((ch, ci) => {
    const el = wrap.querySelector(`[data-ci="${ci}"]`);
    const H = ch.height, MT = 10, MB = ci === p.charts.length - 1 || ch.title ? 24 : 8;
    let vis = ch.series.map((s) => s.data.filter((d) => d[2] >= tMin - 7 * 864e5));
    if (ch.index) { // 指數化：區間起點＝100
      vis = vis.map((pts) => { const b = pts.find((d) => d[2] >= tMin) || pts[0]; return b ? pts.map((d) => [d[0], d[1] / b[1] * 100, d[2], d[1]]) : pts; });
      ch._base = vis.map((pts) => (pts.find((d) => d[2] >= tMin) || [])[3]);
    }
    const vals = vis.flat().map((d) => d[1]).concat((ch.refs || []).map((r) => r.v));
    const isBar = ch.series.every((s) => s.type === "bar");
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (isBar) lo = Math.min(0, lo);
    if (!isFinite(lo)) { lo = 0; hi = 1; }
    const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.05 || 1;
    if (!isBar) lo -= pad;
    hi += pad;
    const y = (v) => MT + (1 - (v - lo) / (hi - lo)) * (H - MT - MB);
    ch._y = y; ch._H = H; ch._MT = MT; ch._MB = MB; ch._vis = vis;
    const ticks = niceTicks(lo, hi, H > 150 ? 4 : 3);
    let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${lqEsc(ch.series.map((s) => s.name).join("、"))}">`;
    svg += ticks.map((v) => `<line x1="${ML}" x2="${W - MR}" y1="${y(v)}" y2="${y(v)}" class="grid"/><text x="${ML - 6}" y="${y(v) + 4}" class="ax" text-anchor="end">${fmtV(v, ch.unit === "十億美元" ? "" : ch.unit).replace(" bp", "")}</text>`).join("");
    if (lo < 0 && hi > 0) svg += `<line x1="${ML}" x2="${W - MR}" y1="${y(0)}" y2="${y(0)}" class="zero"/>`;
    if (ch.index) svg += `<line x1="${ML}" x2="${W - MR}" y1="${y(100)}" y2="${y(100)}" class="zero"/>`;
    for (const r of ch.refs || []) svg += `<line x1="${ML}" x2="${W - MR}" y1="${y(r.v)}" y2="${y(r.v)}" class="ref lv${r.lv}"/><text x="${W - MR - 4}" y="${y(r.v) - 4}" class="reflab lv${r.lv}" text-anchor="end">${lqEsc(r.label)}</text>`;
    if (MB > 20) { // x 軸日期
      const n = Math.max(2, Math.min(6, Math.floor((W - ML - MR) / 110)));
      for (let i = 0; i <= n; i++) {
        const t = tMin + (tMax - tMin) * i / n, d = new Date(t);
        const lab = days > 400 ? `${d.getUTCFullYear()}/${String(d.getUTCMonth() + 1).padStart(2, "0")}` : `${String(d.getUTCMonth() + 1).padStart(2, "0")}/${String(d.getUTCDate()).padStart(2, "0")}`;
        svg += `<text x="${x(t)}" y="${H - 6}" class="ax" text-anchor="${i === 0 ? "start" : i === n ? "end" : "middle"}">${lab}</text>`;
      }
    }
    ch.series.forEach((s, si) => {
      const pts = vis[si];
      if (!pts.length) return;
      if (s.type === "bar") {
        const bw = Math.max(1.5, (W - ML - MR) / Math.max(pts.length, days * 0.7) * 0.7);
        svg += pts.filter((d) => d[1]).map((d) => `<rect x="${x(Math.max(d[2], tMin)) - bw / 2}" y="${Math.min(y(d[1]), y(0))}" width="${bw}" height="${Math.max(1, Math.abs(y(0) - y(d[1])))}" rx="1" fill="${s.color}" opacity=".75"/>`).join("");
      } else {
        let dstr = "";
        pts.forEach((d, i) => {
          const px = x(Math.max(d[2], tMin)), py = y(d[1]);
          if (i === 0) dstr += `M${px.toFixed(1)},${py.toFixed(1)}`;
          else dstr += s.type === "step" ? `H${px.toFixed(1)}V${py.toFixed(1)}` : `L${px.toFixed(1)},${py.toFixed(1)}`;
        });
        const last = pts[pts.length - 1];
        svg += `<path d="${dstr}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round"/>`;
        svg += `<circle cx="${x(last[2])}" cy="${y(last[1])}" r="4" fill="${s.color}" stroke="var(--chart-bg)" stroke-width="2"/>`;
      }
    });
    svg += `<g class="hov"></g><rect x="${ML}" y="0" width="${W - ML - MR}" height="${H}" fill="transparent" class="hit" data-hp="${p.id}"/></svg>`;
    el.innerHTML = svg;
  });
  const lg = document.getElementById("lql-" + p.id);
  if (lg) lg.innerHTML = legendHtml(p);
  if (LQ.hover[p.id]) hoverPanel(p, LQ.hover[p.id]);
}

function hoverPanel(p, t) {
  const g = p._geo;
  if (!g) return;
  t = Math.max(g.tMin, Math.min(g.tMax, t));
  LQ.hover[p.id] = t;
  const wrap = document.querySelector(`#lq-${p.id} .lq-charts`);
  const rows = [];
  let shown = null;
  p.charts.forEach((ch, ci) => {
    const el = wrap.querySelector(`[data-ci="${ci}"] .hov`);
    if (!el) return;
    let h = `<line x1="${g.x(t)}" x2="${g.x(t)}" y1="0" y2="${ch._H}" class="cross"/>`;
    ch.series.forEach((s, si) => {
      const d = valueAt(ch.index ? ch._vis[si] : s.data, t);
      if (!d) return;
      shown = shown && shown > d[0] ? shown : d[0];
      const val = ch.index ? `${fmtV(d[3], ch.unit)} <span class="${d[1] >= 100 ? "up" : "down"}">${d[1] >= 100 ? "+" : ""}${(d[1] - 100).toFixed(1)}%</span>` : fmtV(d[1], ch.unit);
      rows.push(`<span class="lg"><i class="sw ${s.type}" style="background:${s.color}"></i>${lqEsc(s.name)} <b class="num">${val}</b></span>`);
      if (s.type !== "bar") h += `<circle cx="${g.x(t)}" cy="${ch._y(d[1])}" r="4.5" fill="${s.color}" stroke="var(--chart-bg)" stroke-width="2"/>`;
    });
    el.innerHTML = h;
  });
  const d = new Date(t).toISOString().slice(0, 10);
  $(`#lqi-${p.id}`).innerHTML = `<div class="dt">${d}</div>${rows.join("")}`;
}

function lqPointer(e) {
  const hit = e.target.closest && e.target.closest("[data-hp]");
  if (!hit || !LQ.data) return;
  const p = LQ.byId[hit.dataset.hp];
  const g = p && p._geo;
  if (!g) return;
  const rect = hit.ownerSVGElement.getBoundingClientRect();
  const px = (e.touches ? e.touches[0].clientX : e.clientX) - rect.left;
  hoverPanel(p, g.tMin + (px - g.ML) / (g.W - g.ML - g.MR) * (g.tMax - g.tMin));
}
document.addEventListener("pointermove", lqPointer);
document.addEventListener("pointerdown", lqPointer);
document.addEventListener("click", (e) => {
  const tg = e.target.closest("[data-lqtoggle],[data-lqrange]");
  if (!tg || !LQ.data) return;
  const setOf = (id) => Object.keys(SETS).find((k) => (LQ.data[SETS[k][0]] || []).some((p) => p.id === id));
  if (tg.dataset.lqtoggle) { const id = tg.dataset.lqtoggle; LQ.open[id] = !LQ.open[id]; return renderSet(setOf(id)); }
  const [id, k] = tg.dataset.lqrange.split(":");
  LQ.range[id] = k; delete LQ.hover[id];
  renderSet(setOf(id));
});
let lqResize;
window.addEventListener("resize", () => { clearTimeout(lqResize); lqResize = setTimeout(() => LQ.data && SETS[state.view] && renderSet(state.view), 150); });
