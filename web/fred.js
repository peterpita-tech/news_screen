"use strict";
/* FRED 圖表：從預載序列（fred.json）任選組合，前端即時轉換與繪圖；本機版可即時抓任意代號。 */
const FR = { cat: null, sel: [], t: "raw", f: "raw", q: "", custom: {}, msg: "" };
const FR_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"];
const FR_MAX = 6;
const FR_T = [["raw", "原始值"], ["yoy", "年增率 %"], ["ch1", "年變動（差值）"], ["idx", "指數化＝100"]];
const FR_F = [["raw", "原始頻率"], ["m", "月平均"], ["q", "季平均"]];

function frSeries(id) { return (FR.cat && FR.cat.series[id]) || FR.custom[id]; }

async function loadFred() {
  if (FR.cat) return renderFred();
  $("#frChart").innerHTML = '<div class="ev-empty">FRED 序列載入中…</div>';
  try {
    const r = await fetch("fred.json?t=" + Date.now(), { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    FR.cat = await r.json();
  } catch (e) {
    FR.cat = { series: {}, cats: [] };
    FR.msg = "預載序列載入失敗：" + e.message;
  }
  frFromHash();
  if (!FR.sel.length) ["UNRATE", "CPIAUCSL", "FEDFUNDS"].forEach((id) => frSeries(id) && frAdd(id, true));
  renderFred();
}

function frFromHash() {
  const q = (location.hash.split("?")[1] || "");
  const p = new URLSearchParams(q);
  if (p.get("t")) FR.t = p.get("t");
  if (p.get("f")) FR.f = p.get("f");
  (p.get("s") || "").split(",").filter(Boolean).forEach((id) => frSeries(id) && frAdd(id, true));
}
function frToHash() {
  const p = new URLSearchParams({ s: FR.sel.map((x) => x.id).join(","), t: FR.t, f: FR.f });
  history.replaceState(null, "", "#fred?" + p.toString());
}

function frAdd(id, silent) {
  id = id.toUpperCase();
  if (FR.sel.some((x) => x.id === id)) return;
  if (FR.sel.length >= FR_MAX) { if (!silent) toast(`最多同時 ${FR_MAX} 條序列`); return; }
  const used = new Set(FR.sel.map((x) => x.color));
  FR.sel.push({ id, color: FR_COLORS.find((c) => !used.has(c)) }); // 顏色跟著序列走，不因增刪重排
}
function frRemove(id) { FR.sel = FR.sel.filter((x) => x.id !== id); }

async function frCustom(id) {
  id = id.trim().toUpperCase();
  if (!id) return;
  if (frSeries(id)) { frAdd(id); return renderFred(); }
  if (!/^[A-Z0-9_]{2,40}$/.test(id)) return toast("代號格式不正確");
  FR.msg = `正在即時查詢 ${id}…`; renderFred();
  try {
    if (typeof isLocal !== "undefined" && isLocal) {
      const r = await fetch("api/fred?id=" + encodeURIComponent(id));
      const d = await r.json();
      if (!r.ok || d.error) throw new Error(d.error || "HTTP " + r.status);
      FR.custom[id] = d;
    } else {
      // 靜態版：嘗試直接向 FRED 取 CSV（多數瀏覽器會因跨網域限制失敗）
      const r = await fetch(`https://fred.stlouisfed.org/graph/fredgraph.csv?id=${id}&cosd=1990-01-01`);
      if (!r.ok) throw new Error("HTTP " + r.status);
      const rows = (await r.text()).trim().split("\n").slice(1).map((l) => l.split(",")).filter((x) => x[1] && x[1] !== ".");
      if (!rows.length) throw new Error("無資料");
      FR.custom[id] = { name: id, cat: "即時查詢", unit: "", freq: "", data: rows.map((x) => [x[0], +x[1]]) };
    }
    frAdd(id); FR.msg = "";
  } catch (e) {
    FR.msg = typeof isLocal !== "undefined" && isLocal
      ? `查詢 ${id} 失敗：${e.message}（請確認代號存在於 fred.stlouisfed.org）`
      : `線上版無法即時抓取未預載的序列 ${id}（瀏覽器跨網域限制）。請把「${id}」加到 repo 的 config/fred_extra.json，下次自動更新（約 30 分鐘內）就會出現；或在本機執行 app.py 即可即時查詢任何代號。`;
  }
  renderFred();
}

// ---------------------------------------------------------------- 轉換
function frAgg(data, f) {
  if (f === "raw") return data;
  const key = (d) => f === "m" ? d.slice(0, 7) : d.slice(0, 4) + "Q" + (Math.floor((+d.slice(5, 7) - 1) / 3) + 1);
  const g = new Map();
  for (const [d, v] of data) { const k = key(d); if (!g.has(k)) g.set(k, [d, 0, 0]); const a = g.get(k); a[1] += v; a[2]++; }
  return [...g.values()].map(([d, s, n]) => [f === "m" ? d.slice(0, 7) + "-01" : d.slice(0, 5) + String((Math.floor((+d.slice(5, 7) - 1) / 3)) * 3 + 1).padStart(2, "0") + "-01", s / n]);
}
function frTransform(data, t) {
  if (t === "raw" || t === "idx") return data;
  const pts = data.map(([d, v]) => [d, v, toT(d)]);
  const out = [];
  for (const p of pts) {
    const prev = valueAt(pts, p[2] - 365 * 864e5 + 3 * 864e5);
    if (!prev || p[2] - prev[2] < 300 * 864e5) continue;
    out.push([p[0], t === "yoy" ? (prev[1] ? (p[1] / prev[1] - 1) * 100 : null) : p[1] - prev[1]]);
  }
  return out.filter((x) => x[1] != null && isFinite(x[1]));
}

function renderFred() {
  const box = $("#frPicker");
  if (!box || !FR.cat) return;
  const cats = FR.cat.cats || [];
  const q = FR.q.toLowerCase();
  const list = Object.entries(FR.cat.series).filter(([id, s]) => (!FR.cat_ || s.cat === FR.cat_) &&
    (!q || id.toLowerCase().includes(q) || s.name.toLowerCase().includes(q)));
  box.innerHTML = `
    <div class="fr-search"><input id="frQ" value="${lqEsc(FR.q)}" placeholder="搜尋序列（名稱或代號）"><span class="small">${list.length} / ${Object.keys(FR.cat.series).length}</span></div>
    <div class="fr-cats"><button data-frcat="" class="${!FR.cat_ ? "on" : ""}">全部</button>${cats.map((c) => `<button data-frcat="${lqEsc(c)}" class="${FR.cat_ === c ? "on" : ""}">${lqEsc(c)}</button>`).join("")}</div>
    <div class="fr-list">${list.map(([id, s]) => {
      const on = FR.sel.some((x) => x.id === id);
      return `<div class="fr-item ${on ? "on" : ""}" data-fradd="${id}"><span class="fr-id">${id}</span><span class="fr-nm">${lqEsc(s.name)}</span><span class="fr-meta">${lqEsc(s.freq || "")}${s.unit ? " · " + lqEsc(s.unit) : ""}</span><span class="fr-plus">${on ? "✓" : "＋"}</span></div>`;
    }).join("") || '<div class="small" style="padding:10px">沒有符合的序列，可在上方「輸入任意 FRED 代號」。</div>'}</div>
    <form class="fr-custom" id="frCustomForm"><input id="frCustomId" placeholder="輸入任意 FRED 代號，如 NAPM"><button class="solid" type="submit">加入</button></form>`;
  $("#frQ").addEventListener("input", (e) => { FR.q = e.target.value; const pos = e.target.selectionStart; renderFred(); const el = $("#frQ"); el.focus(); el.setSelectionRange(pos, pos); });
  $("#frCustomForm").addEventListener("submit", (e) => { e.preventDefault(); frCustom($("#frCustomId").value); });
  $("#frControls").innerHTML = `
    <div class="fr-sel">${FR.sel.map((x) => { const s = frSeries(x.id) || {}; return `<span class="fr-chip"><i style="background:${x.color}"></i>${lqEsc(s.name || x.id)} <em>${x.id}</em><button data-frrm="${x.id}" title="移除">✕</button></span>`; }).join("") || '<span class="small">從左側點選序列加入圖表（最多 6 條）</span>'}</div>
    <div class="fr-opts"><span class="lab">轉換</span>${FR_T.map(([k, n]) => `<button data-frt="${k}" class="${FR.t === k ? "on" : ""}">${n}</button>`).join("")}
      <span class="lab">頻率</span>${FR_F.map(([k, n]) => `<button data-frf="${k}" class="${FR.f === k ? "on" : ""}">${n}</button>`).join("")}
      <button class="ghost" data-frcsv="1">下載 CSV</button></div>
    ${FR.msg ? `<div class="banner">${lqEsc(FR.msg)}</div>` : ""}`;
  frToHash();
  renderFredChart();
}

function frBuildPanel() {
  const unitOf = (s) => FR.t === "yoy" ? "%" : FR.t === "idx" ? "指數化" : (s.unit || "");
  const groups = new Map();
  for (const x of FR.sel) {
    const s = frSeries(x.id);
    if (!s) continue;
    // 本身就是 % 的序列（利率、失業率…）算年增率沒有意義，改顯示年變動（百分點）
    const pctSeries = FR.t === "yoy" && s.unit === "%";
    const data = frTransform(frAgg(s.data, FR.f), pctSeries ? "ch1" : FR.t);
    if (!data.length) continue;
    const u = pctSeries ? "百分點（年變動）" : unitOf(s) + (FR.t === "ch1" ? " 變動" : "");
    if (!groups.has(u)) groups.set(u, []);
    groups.get(u).push({ name: `${s.name}（${x.id}）`, color: x.color, type: "line", data: data.map(([d, v]) => [d, v, toT(d)]) });
  }
  const charts = [...groups.entries()].map(([u, series]) => ({
    unit: u === "指數化" ? "" : u.startsWith("百分點") ? "百分點" : u.replace(" 變動", ""), index: FR.t === "idx", height: groups.size > 1 ? 220 : 340, series,
    title: groups.size > 1 ? `單位：${u || "—"}` : "", key: "",
  }));
  const allT = charts.flatMap((c) => c.series.flatMap((s) => [s.data[0][2], s.data[s.data.length - 1][2]]));
  const years = allT.length ? Math.max(1, (Math.max(...allT) - Math.min(...allT)) / (365 * 864e5)) : 3;
  return { id: "fredx", no: "F", title: "自訂 FRED 圖表", subtitle: FR_T.find((t) => t[0] === FR.t)[1] + " · " + FR_F.find((f) => f[0] === FR.f)[1] + (groups.size > 1 ? " · 不同單位分開繪製" : ""),
    years: Math.min(years, 40), charts, defs: [] };
}

function renderFredChart() {
  const box = $("#frChart");
  if (!box || !FR.cat) return;
  const p = frBuildPanel();
  if (!p.charts.length) { box.innerHTML = '<div class="ev-empty">尚未選擇序列</div>'; return; }
  LQ.byId.fredx = p;
  LQ.open.fredx = true;
  const allowed = RANGES.filter(([k, d]) => d <= p.years * 366 + 10).map((r) => r[0]);
  if (!LQ.range.fredx || !allowed.includes(LQ.range.fredx)) LQ.range.fredx = allowed.includes("10Y") ? "10Y" : allowed[allowed.length - 1] || "1Y";
  if (p.years > 20 && !allowed.includes("全部")) RANGES.find((r) => r[0] === "全部")[1] = Math.ceil(p.years * 366 + 20);
  box.innerHTML = panelHtml(p);
  // 單一單位時以 legend 顯示；多單位時每張子圖標題列單位、legend 仍顯示全部
  const lg = document.getElementById("lql-fredx");
  if (!lg) box.querySelector(".lq-charts").insertAdjacentHTML("afterend", `<div class="lq-legend" id="lql-fredx"></div>`);
  drawPanel(p);
}

function frCsv() {
  const cols = FR.sel.map((x) => x.id).filter(frSeries);
  const maps = cols.map((id) => new Map(frTransform(frAgg(frSeries(id).data, FR.f), FR.t)));
  const dates = [...new Set(maps.flatMap((m) => [...m.keys()]))].sort();
  const lines = ["date," + cols.join(","), ...dates.map((d) => [d, ...maps.map((m) => m.has(d) ? m.get(d) : "")].join(","))];
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
  a.download = `fred_${cols.join("_")}_${FR.t}.csv`;
  a.click();
}

document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-fradd],[data-frrm],[data-frcat],[data-frt],[data-frf],[data-frcsv]");
  if (!t) return;
  const d = t.dataset;
  if (d.fradd) { FR.sel.some((x) => x.id === d.fradd) ? frRemove(d.fradd) : frAdd(d.fradd); FR.msg = ""; }
  else if (d.frrm) frRemove(d.frrm);
  else if (d.frcat !== undefined) FR.cat_ = d.frcat || null;
  else if (d.frt) FR.t = d.frt;
  else if (d.frf) FR.f = d.frf;
  else if (d.frcsv) return frCsv();
  renderFred();
});
