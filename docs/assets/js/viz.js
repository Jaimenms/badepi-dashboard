/* viz.js — tokens de tema, base ECharts, registro de gráficos, vista em tabela e contadores.
   Sem dependências além do ECharts global (carregado via CDN). */

export const SERIES_LIGHT = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
export const SERIES_DARK  = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'];
export const SEQ = ['#cde2fb', '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6', '#256abf', '#1c5cab', '#184f95', '#104281', '#0d366b'];
export const SEQ_DARK = ['#184f95', '#1c5cab', '#256abf', '#2a78d6', '#3987e5', '#5598e7', '#6da7ec', '#86b6ef', '#9ec5f4', '#b7d3f6', '#cde2fb'];
export const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

const root = document.documentElement;
const themeListeners = new Set();

export function isDark() {
  const t = root.getAttribute('data-theme');
  if (t) return t === 'dark';
  return matchMedia('(prefers-color-scheme: dark)').matches;
}
export function setTheme(mode) {           // 'light' | 'dark' | null (sistema)
  if (mode) root.setAttribute('data-theme', mode); else root.removeAttribute('data-theme');
  try { mode ? localStorage.setItem('badepi-theme', mode) : localStorage.removeItem('badepi-theme'); } catch (e) { /* armazenamento indisponível */ }
  themeListeners.forEach(fn => fn(isDark()));
}
export function initTheme(toggleBtn) {
  try { const saved = localStorage.getItem('badepi-theme'); if (saved) root.setAttribute('data-theme', saved); } catch (e) { /* ignora */ }
  const paint = () => { if (toggleBtn) toggleBtn.innerHTML = isDark() ? '☀️ <span>Claro</span>' : '🌙 <span>Escuro</span>'; };
  paint();
  toggleBtn?.addEventListener('click', () => { setTheme(isDark() ? 'light' : 'dark'); paint(); });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (!root.getAttribute('data-theme')) { paint(); themeListeners.forEach(fn => fn(isDark())); } });
}
export function onThemeChange(fn) { themeListeners.add(fn); }

// Cada página de ativo usa uma rotação da mesma paleta validada (o par novo que surge, vermelho↔azul,
// passa nas seis checagens em ambos os modos). Patentes usa a ordem de referência.
const ROTACAO = { marcas: 1, desenhos: 2, programas: 5, indicacoes: 6 };
const rotate = (arr, k) => arr.map((_, i) => arr[(i + k) % arr.length]);
export function tokens() {
  const cs = getComputedStyle(root);
  const v = n => cs.getPropertyValue(n).trim();
  const dark = isDark();
  const k = ROTACAO[root.dataset.asset] || 0;
  return {
    dark, surface: v('--surface'), page: v('--page'), ink: v('--ink'), ink2: v('--ink-2'), muted: v('--muted'),
    grid: v('--grid'), axis: v('--axis'), accent: v('--accent'), good: v('--good'),
    series: rotate(dark ? SERIES_DARK : SERIES_LIGHT, k), deemph: v('--deemph'), seq: dark ? SEQ_DARK : SEQ,
    font: '"Inter", system-ui, -apple-system, "Segoe UI", sans-serif',
  };
}

/* ---------- formatação pt-BR ---------- */
const nfInt = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const fmt = {
  int: n => (n == null || Number.isNaN(n)) ? '–' : nfInt.format(n),
  dec1: n => (n == null || Number.isNaN(n)) ? '–' : nf1.format(n),
  dec2: n => (n == null || Number.isNaN(n)) ? '–' : nf2.format(n),
  pct: n => (n == null || Number.isNaN(n)) ? '–' : nf1.format(n) + '%',
  anos: n => (n == null || Number.isNaN(n)) ? '–' : nf1.format(n) + ' anos',
  compact: n => {
    if (n == null) return '';
    const a = Math.abs(n);
    if (a >= 1e6) return nf1.format(n / 1e6).replace(',0', '') + ' mi';
    if (a >= 1e4) return nfInt.format(Math.round(n / 1e3)) + ' mil';
    if (a >= 1e3) return nf1.format(n / 1e3).replace(',0', '') + ' mil';
    return nfInt.format(n);
  },
  signed: n => (n == null) ? '–' : (n > 0 ? '+' : '') + nf1.format(n) + '%',
};

/* ---------- base ECharts ---------- */
export function base(t) {
  return {
    color: t.series,
    textStyle: { fontFamily: t.font, color: t.ink2 },
    animationDuration: reducedMotion ? 0 : 900,
    animationDurationUpdate: reducedMotion ? 0 : 600,
    animationEasing: 'cubicOut',
    grid: { left: 8, right: 18, top: 36, bottom: 6, containLabel: true },
    tooltip: {
      backgroundColor: t.surface, borderColor: t.grid, borderWidth: 1, padding: [8, 12],
      textStyle: { color: t.ink, fontSize: 13, fontFamily: t.font }, extraCssText: 'box-shadow: 0 8px 24px -8px rgba(0,0,0,.25); border-radius: 10px;',
      valueFormatter: v => fmt.int(v),
    },
  };
}
// legenda só quando o gráfico tem 2+ séries (uma série é nomeada pelo título do card)
export const legendDefaults = t => ({ top: 0, left: 0, icon: 'circle', itemWidth: 9, itemHeight: 9, itemGap: 14, textStyle: { color: t.ink2, fontSize: 12.5 } });
export const ax = {
  cat: (t, data, extra = {}) => ({ type: 'category', data, boundaryGap: extra.boundaryGap ?? false, axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false }, axisLabel: { color: t.muted, hideOverlap: true, ...(extra.axisLabel || {}) }, ...extra }),
  // eixo temporal com o significado da data explícito (ex.: "Ano de depósito (protocolo no INPI)")
  time: (t, data, name, extra = {}) => ({ type: 'category', data, boundaryGap: extra.boundaryGap ?? false, name, nameLocation: 'middle', nameGap: 30,
    nameTextStyle: { color: t.muted, fontSize: 11.5, fontWeight: 600 }, axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false },
    axisLabel: { color: t.muted, hideOverlap: true, ...(extra.axisLabel || {}) }, ...extra }),
  val: (t, extra = {}) => ({ type: 'value', splitNumber: 4, splitLine: { lineStyle: { color: t.grid } }, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.muted, hideOverlap: true, formatter: extra.formatter || fmt.compact }, ...extra }),
  catY: (t, data, extra = {}) => ({ type: 'category', data, inverse: true, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.ink2, width: extra.width || 180, overflow: 'truncate', fontSize: extra.fontSize || 12.5, interval: 0 }, ...extra }),
};
export const mk = {
  line: (name, data, color, extra = {}) => ({ name, type: 'line', data, showSymbol: false, symbol: 'circle', symbolSize: 8, lineStyle: { width: 2, color }, itemStyle: { color }, emphasis: { focus: 'series' }, ...extra }),
  area: (name, data, color, extra = {}) => ({ name, type: 'line', data, stack: 'total', showSymbol: false, symbol: 'circle', symbolSize: 8, lineStyle: { width: 1, color }, itemStyle: { color }, areaStyle: { color, opacity: 0.82 }, emphasis: { focus: 'series' }, ...extra }),
  bar: (name, data, color, t, extra = {}) => ({ name, type: 'bar', data, itemStyle: { color, borderRadius: [4, 4, 0, 0] }, barMaxWidth: 30, emphasis: { focus: 'series' }, ...extra }),
  stackBar: (name, data, color, t, extra = {}) => ({ name, type: 'bar', data, stack: 'total', itemStyle: { color, borderColor: t.surface, borderWidth: 1 }, barMaxWidth: 30, emphasis: { focus: 'series' }, ...extra }),
  hbar: (name, data, color, t, extra = {}) => ({ name, type: 'bar', data, itemStyle: { color, borderRadius: [0, 4, 4, 0] }, barMaxWidth: 22, label: { show: true, position: 'right', color: t.ink2, fontSize: 12, formatter: p => fmt.int(p.value) }, ...extra }),
};
export function deepMerge(a, b) {
  const out = Array.isArray(a) ? [...a] : { ...a };
  for (const k of Object.keys(b || {})) {
    const av = out[k], bv = b[k];
    out[k] = (av && bv && typeof av === 'object' && typeof bv === 'object' && !Array.isArray(av) && !Array.isArray(bv)) ? deepMerge(av, bv) : bv;
  }
  return out;
}

/* ---------- registro de gráficos ---------- */
const registry = new Map();
let ctxRef = null;
export function register(id, build, opts = {}) {
  const card = document.querySelector(`[data-chart="${id}"]`);
  if (!card) return;
  registry.set(id, { id, card, build, opts, chart: null, last: null, tableOpen: false, state: opts.state || {} });
}
export function getState(id) { return registry.get(id)?.state; }
export function rerender(id, setOpts) { const r = registry.get(id); if (r && r.chart) render(r, setOpts || { replaceMerge: ['series', 'xAxis', 'yAxis', 'legend', 'visualMap', 'graphic'] }); }
function render(r, setOpts = { notMerge: true }) {
  const el = r.card.querySelector('.chart');
  const t = tokens();
  const res = r.build({ ...ctxRef, t, state: r.state });
  r.last = res;
  if (!r.chart) r.chart = echarts.init(el, null, { renderer: 'canvas' });
  const opt = deepMerge(base(t), res.option);
  const xs = Array.isArray(opt.xAxis) ? opt.xAxis : [opt.xAxis];
  if (xs.some(x => x && x.name) && opt.grid && !Array.isArray(opt.grid)) opt.grid.bottom = Math.max(opt.grid.bottom || 0, 30);
  if (res.option.legend) opt.legend = deepMerge(legendDefaults(t), res.option.legend); else opt.legend = { show: false };
  // em telas estreitas a legenda quebra em duas linhas: abre espaço acima do plot
  if (res.option.legend && innerWidth < 640 && opt.grid && !Array.isArray(opt.grid)) opt.grid.top = Math.max(opt.grid.top || 0, 64);
  r.chart.setOption(opt, setOpts);
  if (res.after) res.after(r.chart, r);
  if (r.tableOpen) renderTable(r);
}
function renderTable(r) {
  const host = r.card.querySelector('.table-view');
  const tb = r.last?.table; if (!host || !tb) return;
  const esc = s => String(s ?? '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const cell = v => typeof v === 'number' ? (Number.isInteger(v) ? fmt.int(v) : fmt.dec1(v)) : esc(v);
  host.innerHTML = `<table><thead><tr>${tb.columns.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${tb.rows.map(row => `<tr>${row.map((v, i) => `<td>${i === 0 ? esc(v) : cell(v)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
}
function wireCard(r) {
  const btn = r.card.querySelector('.btn-table');
  const chartEl = r.card.querySelector('.chart');
  const host = r.card.querySelector('.table-view');
  btn?.addEventListener('click', () => {
    r.tableOpen = !r.tableOpen;
    btn.textContent = r.tableOpen ? 'Gráfico' : 'Tabela';
    chartEl.classList.toggle('hidden', r.tableOpen);
    host.classList.toggle('hidden', !r.tableOpen);
    if (r.tableOpen) { if (!r.chart) render(r); renderTable(r); } else r.chart?.resize();
  });
  r.card.querySelectorAll('.seg').forEach(seg => {
    seg.addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return;
      seg.querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b));
      r.state[seg.dataset.key || 'view'] = b.dataset.value;
      if (!r.chart) render(r); else rerender(r.id);
    });
  });
  r.card.querySelectorAll('input[type=range][data-key]').forEach(inp => {
    const out = r.card.querySelector(`output[for="${inp.id}"]`);
    const apply = () => { r.state[inp.dataset.key] = Number(inp.value); if (out) out.value = inp.value; };
    if (out) out.value = inp.value;
    if (r.state[inp.dataset.key] === undefined) apply();   // um estado inicial vindo do register() (ex.: 'todos') prevalece
    inp.addEventListener('input', () => {
      apply(); r.card.querySelectorAll(`.seg[data-key="${inp.dataset.key}"] button`).forEach(b => b.classList.toggle('active', b.dataset.value === inp.value));
      if (!r.chart) render(r); else rerender(r.id, {});
    });
  });
}
export function mountAll(ctx) {
  ctxRef = ctx;
  const io = new IntersectionObserver(entries => {
    for (const e of entries) if (e.isIntersecting) { const r = registry.get(e.target.dataset.chart); if (r && !r.chart) render(r); io.unobserve(e.target); }
  }, { rootMargin: '160px 0px' });
  for (const r of registry.values()) { wireCard(r); io.observe(r.card); }
  let to; window.addEventListener('resize', () => { clearTimeout(to); to = setTimeout(() => registry.forEach(r => r.chart?.resize()), 120); });
  onThemeChange(() => registry.forEach(r => { if (r.chart) render(r, { notMerge: true }); }));
}

/* ---------- contadores animados ---------- */
export function countUp(el, to, { decimals = 0, suffix = '', prefix = '', duration = 1500 } = {}) {
  const f = v => decimals ? new Intl.NumberFormat('pt-BR', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(v) : fmt.int(Math.round(v));
  if (reducedMotion || to == null) { el.textContent = prefix + (to == null ? '–' : f(to)) + suffix; return; }
  const start = performance.now();
  const step = now => {
    const p = Math.min(1, (now - start) / duration); const e = 1 - Math.pow(1 - p, 3);
    el.textContent = prefix + f(to * e) + suffix;
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
export function countUpOnView(scope = document) {
  const io = new IntersectionObserver(entries => {
    for (const e of entries) if (e.isIntersecting) {
      const el = e.target; const d = el.dataset;
      if (Number(d.count) >= 1e6 && el.parentElement?.classList.contains('big')) el.parentElement.classList.add('long');
      countUp(el, Number(d.count), { decimals: Number(d.decimals || 0), suffix: d.suffix || '', prefix: d.prefix || '' });
      io.unobserve(el);
    }
  }, { threshold: 0.4 });
  scope.querySelectorAll('[data-count]').forEach(el => io.observe(el));
}

/* ---------- sparkline (tile) ---------- */
export function spark(el, data, color, t) {
  const c = echarts.init(el, null, { renderer: 'canvas' });
  c.setOption({
    animationDuration: reducedMotion ? 0 : 1200,
    grid: { left: 2, right: 2, top: 4, bottom: 2 },
    xAxis: { type: 'category', show: false, data: data.map((_, i) => i), boundaryGap: false },
    yAxis: { type: 'value', show: false, min: 'dataMin' },
    tooltip: { show: false },
    series: [{ type: 'line', data, showSymbol: false, lineStyle: { width: 1.5, color }, areaStyle: { color, opacity: 0.12 }, smooth: 0.2 }],
  });
  onThemeChange(() => c.setOption({ series: [{ lineStyle: { color: tokens().series[0] }, areaStyle: { color: tokens().series[0] } }] }));
  return c;
}

/* ---------- utilidades de tabela ---------- */
export function tableYears(anos, cols) {   // cols: {nome: array}
  const names = Object.keys(cols);
  return { columns: ['Ano', ...names], rows: anos.map((a, i) => [a, ...names.map(n => cols[n][i])]) };
}
export function tableRows(columns, rows) { return { columns, rows }; }
