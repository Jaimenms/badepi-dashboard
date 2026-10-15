/* app.js — dashboard de patentes (BADEPI v12). Carrega os JSON da camada gold e monta os gráficos. */
import { initTheme, tokens, register, mountAll, rerender, fmt, ax, mk, tableYears, tableRows, countUp, countUpOnView, spark, onThemeChange, reducedMotion } from './viz.js';

const BASE = './data/patentes/';
const FILES = ['resumo', 'serie_depositos', 'serie_decisoes', 'situacao_coorte', 'tempo_concessao', 'campos_tec', 'ipc_secoes', 'uf', 'paises', 'depositantes', 'municipios', 'genero', 'funil', 'impacto'];
let d = null;

async function loadAll() {
  const [geo, ...rest] = await Promise.all([
    fetch('./data/geo/br_uf.json').then(r => r.json()),
    ...FILES.map(f => fetch(BASE + f + '.json').then(r => { if (!r.ok) throw new Error(f); return r.json(); })),
  ]);
  const out = Object.fromEntries(FILES.map((f, i) => [f, rest[i]]));
  out.geo = geo;
  return out;
}

/* ---------- helpers ---------- */
const sum = a => a.reduce((x, y) => x + (y || 0), 0);
const last = a => a[a.length - 1];
const pctOf = (a, b) => (b ? +(a / b * 100).toFixed(1) : null);
const CAT_COLOR = t => ({ universidade: t.series[0], empresa: t.series[1], instituto_pesquisa: t.series[2], pessoa_fisica: t.series[3], governo: t.series[4], pessoa_fisica_provavel: t.series[3], nao_classificado: t.deemph, nao_identificado: t.deemph });
const CAT_LABEL = { universidade: 'Universidades', empresa: 'Empresas', instituto_pesquisa: 'Institutos de pesquisa', pessoa_fisica: 'Pessoas físicas', governo: 'Governo', nao_identificado: 'Não identificado (sigilo)' };
function tip(params, { total = false, fmtv = fmt.int } = {}) {
  const ps = params.filter(p => p.value != null && p.seriesName && !String(p.seriesName).startsWith('_'));
  const head = `<div style="font-weight:700;margin-bottom:4px">${params[0].axisValueLabel ?? params[0].name}</div>`;
  const rows = ps.map(p => `<div style="display:flex;justify-content:space-between;gap:18px"><span>${p.marker} ${p.seriesName}</span><b>${fmtv(Array.isArray(p.value) ? p.value[1] : p.value)}</b></div>`);
  const tot = total ? `<div style="border-top:1px solid rgba(128,128,128,.3);margin-top:4px;padding-top:4px;display:flex;justify-content:space-between"><span>Total</span><b>${fmtv(sum(ps.map(p => Array.isArray(p.value) ? p.value[1] : p.value)))}</b></div>` : '';
  return head + rows.join('') + tot;
}
function hbarOption(t, names, values, { color, fmtv = fmt.int, width = 190, max, fontSize } = {}) {
  return {
    grid: { left: 8, right: 56, top: 8, bottom: 6, containLabel: true },
    tooltip: { trigger: 'item', formatter: p => `<b>${p.name}</b><br>${fmtv(p.value)}` },
    xAxis: ax.val(t, { formatter: v => (fmtv === fmt.pct ? v + '%' : fmt.compact(v)), max }),
    yAxis: ax.catY(t, names, { width, fontSize }),
    series: [mk.hbar('valor', values, color || t.series[0], t, { label: { show: true, position: 'right', color: t.ink2, fontSize: 12, formatter: p => fmtv(p.value) } })],
  };
}
function hbar2Option(t, rows, { fmtv = fmt.int, width = 220, max, fontSize = 11.5 } = {}) {
  const half = Math.ceil(rows.length / 2); const parts = [rows.slice(0, half), rows.slice(half)];
  const xfmt = v => (fmtv === fmt.pct ? v + '%' : fmt.compact(v));
  return {
    grid: [{ left: 8, right: '55%', top: 8, bottom: 6, containLabel: true }, { left: '53%', right: 56, top: 8, bottom: 6, containLabel: true }],
    tooltip: { trigger: 'item', formatter: p => `<b>${p.name}</b><br>${fmtv(p.value)}` },
    xAxis: parts.map((_, i) => ({ ...ax.val(t, { formatter: xfmt, max }), gridIndex: i })),
    yAxis: parts.map((pr, i) => ({ ...ax.catY(t, pr.map(r => r.name), { width, fontSize }), gridIndex: i })),
    series: parts.map((pr, i) => ({ ...mk.hbar('valor', pr.map(r => r.value), t.series[0], t, { label: { show: true, position: 'right', color: t.ink2, fontSize: 11.5, formatter: p => fmtv(p.value) } }), xAxisIndex: i, yAxisIndex: i })),
  };
}
function hexA(hex, a) { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; }

/* ---------- hero ---------- */
function hero() {
  const k = d.resumo.kpis;
  document.querySelectorAll('[data-kpi]').forEach(el => { el.dataset.count = k[el.dataset.kpi] ?? 0; });
  countUpOnView(document.getElementById('hero-stats'));
  const ger = new Date(d.resumo.gerado_em);
  document.getElementById('gerado').textContent = `BADEPI ${d.resumo.badepi_version} · referência ${new Date(d.resumo.data_referencia + 'T12:00:00').toLocaleDateString('pt-BR')} · painel gerado em ${ger.toLocaleDateString('pt-BR')}`;
  heroCanvas();
}
function heroCanvas() {
  const cv = document.getElementById('hero-canvas'); if (!cv) return;
  const ctx = cv.getContext('2d'); const dpr = Math.min(2, devicePixelRatio || 1);
  let w = 0, h = 0, pts = [], raf = 0, color = tokens().series[0];
  const N = Math.min(90, Math.max(40, Math.round(innerWidth / 16)));
  const resize = () => { const r = cv.parentElement.getBoundingClientRect(); w = cv.width = Math.round(r.width * dpr); h = cv.height = Math.round(r.height * dpr); };
  const init = () => { pts = Array.from({ length: N }, () => ({ x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - .5) * .3 * dpr, vy: (Math.random() - .5) * .3 * dpr, r: (1.2 + Math.random() * 1.6) * dpr })); };
  const maxD = 140 * dpr;
  const draw = () => {
    ctx.clearRect(0, 0, w, h);
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i];
      if (!reducedMotion) { p.x += p.vx; p.y += p.vy; if (p.x < 0 || p.x > w) p.vx *= -1; if (p.y < 0 || p.y > h) p.vy *= -1; }
      for (let j = i + 1; j < pts.length; j++) {
        const q = pts[j], dx = p.x - q.x, dy = p.y - q.y, dd = dx * dx + dy * dy;
        if (dd < maxD * maxD) { ctx.strokeStyle = hexA(color, (1 - Math.sqrt(dd) / maxD) * .35); ctx.lineWidth = dpr; ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke(); }
      }
      ctx.fillStyle = hexA(color, .75); ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
    }
    if (!reducedMotion) raf = requestAnimationFrame(draw);
  };
  resize(); init(); draw();
  addEventListener('resize', () => { resize(); init(); if (reducedMotion) draw(); });
  onThemeChange(() => { color = tokens().series[0]; if (reducedMotion) draw(); });
  if (!reducedMotion) new IntersectionObserver(([e]) => { cancelAnimationFrame(raf); if (e.isIntersecting) raf = requestAnimationFrame(draw); }).observe(cv);
}

/* ---------- KPIs ---------- */
function kpis() {
  const k = d.resumo.kpis, sd = d.serie_depositos, dc = d.serie_decisoes, imp = d.impacto, tc = d.tempo_concessao, ano = d.resumo.ano_ultimo;
  const t = tokens();
  const tiles = [
    { label: `Pedidos em ${ano}`, value: k.pedidos_ultimo_ano, delta: k.pedidos_variacao_pct, spark: sd.total },
    { label: `Concessões em ${ano}`, value: k.concessoes_ultimo_ano, delta: k.concessoes_variacao_pct, spark: dc.concessoes },
    { label: 'Patentes vigentes', value: k.patentes_vigentes, sub: 'concedidas e dentro do prazo', spark: d.funil.vigentes },
    { label: 'Tempo mediano até a concessão', value: k.tempo_concessao_mediana_ultimo_ano, decimals: 1, suffix: ' anos', sub: `era ${fmt.dec1(k.tempo_concessao_pior_mediana)} em ${k.tempo_concessao_pior_ano}`, spark: tc.por_ano.map(x => x.mediana) },
    { label: 'Pedidos sem decisão', value: k.backlog_atual, sub: `pico de ${fmt.compact(k.backlog_pico)} em ${k.backlog_pico_ano}`, spark: imp.backlog_fim_ano },
    { label: `Residentes em ${ano}`, value: k.share_residentes_ultimo_ano, decimals: 1, suffix: '%', sub: `média 2000–${ano}: ${fmt.pct(k.share_residentes_total)}`, spark: sd.residente.map((v, i) => pctOf(v, sd.total[i])) },
    { label: 'Mulheres entre inventores', value: k.share_mulheres_inventoras_ultimo_ano, decimals: 1, suffix: '%', sub: `${fmt.pct(k.share_mulheres_inventoras_primeiro_ano)} em 2000 · residentes`, spark: d.genero.share_f_inventores },
  ];
  const row = document.getElementById('kpis');
  row.innerHTML = tiles.map((x, i) => `<div class="tile reveal"><div class="label">${x.label}</div><div class="value" data-count="${x.value}" data-decimals="${x.decimals || 0}" data-suffix="${x.suffix || ''}">–</div>
    <div class="delta">${x.delta != null ? `<span class="${x.delta >= 0 ? 'up' : 'down'}">${x.delta >= 0 ? '▲' : '▼'} ${fmt.signed(x.delta)}</span> vs. ano anterior` : (x.sub || '')}</div><div class="spark" id="spark-${i}"></div></div>`).join('');
  countUpOnView(row);
  tiles.forEach((x, i) => spark(document.getElementById(`spark-${i}`), x.spark, t.series[0], t));
}

/* ---------- números grandes (impacto) ---------- */
function bigNumbers() {
  const k = d.resumo.kpis, imp = d.impacto, ano = d.resumo.ano_ultimo;
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  document.getElementById('big-tempo').dataset.count = k.tempo_concessao_mediana_ultimo_ano;
  set('big-tempo-ano', ano); set('big-tempo-sub', `Em ${k.tempo_concessao_pior_ano}, o pior ano, a mediana era de ${fmt.dec1(k.tempo_concessao_pior_mediana)} anos: uma redução de ${fmt.pct((1 - k.tempo_concessao_mediana_ultimo_ano / k.tempo_concessao_pior_mediana) * 100)}.`);
  document.getElementById('big-backlog').dataset.count = k.backlog_atual;
  set('big-backlog-ano', ano); set('big-backlog-sub', `${fmt.pct((1 - k.backlog_atual / k.backlog_pico) * 100)} abaixo do pico de ${fmt.int(k.backlog_pico)} pedidos em ${k.backlog_pico_ano}.`);
  document.getElementById('big-vigentes').dataset.count = k.patentes_vigentes;
  set('big-vigentes-sub', `${fmt.int(imp.vigentes.residentes)} de titulares residentes (${fmt.pct(pctOf(imp.vigentes.residentes, imp.vigentes.total))}) e ${fmt.int(imp.vigentes.nao_residentes)} de não residentes.`);
  document.getElementById('big-res').dataset.count = k.share_residentes_ultimo_ano;
  set('big-res-ano', ano); set('big-res-sub', `A média de 2000 a ${ano} é ${fmt.pct(k.share_residentes_total)}. O último ano é parcial para pedidos PCT (não residentes), o que infla a parcela.`);
  countUpOnView(document.getElementById('impacto'));
}

/* ---------- gráficos: panorama ---------- */
function charts() {
  const anos = d.serie_depositos.anos;

  register('dep-serie', ({ t, state }) => {
    const s = d.serie_depositos; let cols;
    if (state.view === 'natureza') cols = { 'Patente de invenção (PI)': s.natureza.PI, 'Modelo de utilidade (MU)': s.natureza.MU, 'Certificado de adição (CA)': s.natureza.CA };
    else if (state.view === 'via') cols = { 'Via PCT': s.via.PCT, 'Via direta': s.via.Direta };
    else cols = { 'Residentes': s.residente, 'Não residentes': s.nao_residente };
    const names = Object.keys(cols);
    return { option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { total: true }) }, xAxis: ax.cat(t, anos, { boundaryGap: true }), yAxis: ax.val(t), series: names.map((n, i) => mk.stackBar(n, cols[n], t.series[i], t)) },
      table: tableYears(anos, { ...cols, Total: s.total }) };
  }, { state: { view: 'origem' } });

  register('dep-categoria', ({ t }) => {
    const s = d.serie_depositos; const cats = ['empresa', 'pessoa_fisica', 'universidade', 'instituto_pesquisa', 'governo', 'nao_identificado'];
    const cols = Object.fromEntries(cats.map(c => [CAT_LABEL[c], s.categoria_residente[c]]));
    const colors = CAT_COLOR(t);
    return { option: { legend: { type: 'scroll' }, grid: { top: 48 }, tooltip: { trigger: 'axis', formatter: p => tip(p, { total: true }) }, xAxis: ax.cat(t, anos), yAxis: ax.val(t),
      series: cats.map(c => mk.area(CAT_LABEL[c], s.categoria_residente[c], colors[c])) }, table: tableYears(anos, cols) };
  });

  register('dep-inventores', ({ t }) => {
    const s = d.serie_depositos;
    return { option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.dec2 }) }, xAxis: ax.cat(t, anos), yAxis: ax.val(t, { formatter: v => fmt.dec1(v), min: 0 }),
      series: [mk.line('Inventores por pedido', s.media_inventores, t.series[0]), mk.line('Depositantes por pedido', s.media_depositantes, t.series[1])] },
      table: tableYears(anos, { 'Inventores por pedido': s.media_inventores, 'Depositantes por pedido': s.media_depositantes }) };
  });

  register('dep-prioridade', ({ t }) => {
    const s = d.serie_depositos; const share = s.com_prioridade.map((v, i) => pctOf(v, s.total[i]));
    return { option: { tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.pct }) }, xAxis: ax.cat(t, anos), yAxis: ax.val(t, { formatter: v => v + '%', max: 100, min: 0 }),
      series: [mk.line('Com prioridade (%)', share, t.series[0], { areaStyle: { color: t.series[0], opacity: .12 } })] },
      table: tableYears(anos, { 'Pedidos com prioridade': s.com_prioridade, 'Total': s.total, '% com prioridade': share }) };
  });

  /* ---------- impacto ---------- */
  register('imp-tempo', ({ t }) => {
    const rows = d.tempo_concessao.por_ano; const xs = rows.map(r => r.ano);
    const p25 = rows.map(r => r.p25), band = rows.map(r => +(r.p75 - r.p25).toFixed(2)), med = rows.map(r => r.mediana);
    return { option: {
      tooltip: { trigger: 'axis', formatter: ps => { const r = rows[ps[0].dataIndex]; return `<b>${r.ano}</b> · ${fmt.int(r.n)} concessões<br>mediana <b>${fmt.anos(r.mediana)}</b><br>quartis: ${fmt.dec1(r.p25)} – ${fmt.dec1(r.p75)} anos<br>residentes ${fmt.anos(r.mediana_residentes)} · não residentes ${fmt.anos(r.mediana_nao_residentes)}`; } },
      xAxis: ax.cat(t, xs), yAxis: ax.val(t, { formatter: v => v + ' a', min: 0 }),
      series: [
        { name: '_p25', type: 'line', data: p25, stack: 'band', lineStyle: { opacity: 0 }, showSymbol: false, silent: true, areaStyle: { opacity: 0 } },
        { name: '_band', type: 'line', data: band, stack: 'band', lineStyle: { opacity: 0 }, showSymbol: false, silent: true, areaStyle: { color: t.series[0], opacity: .14 } },
        mk.line('Mediana', med, t.series[0], { markPoint: { symbol: 'circle', symbolSize: 36, itemStyle: { color: t.series[0] }, label: { color: '#fff', fontSize: 11, fontWeight: 700, formatter: p => fmt.dec1(p.value) }, data: [{ type: 'max', name: 'pior ano' }, { name: 'último', coord: [xs.length - 1, last(med)], value: last(med) }] } }),
      ] },
      table: tableRows(['Ano de concessão', 'Concessões', 'Mediana (anos)', 'P25', 'P75', 'Residentes', 'Não residentes'], rows.map(r => [r.ano, r.n, r.mediana, r.p25, r.p75, r.mediana_residentes, r.mediana_nao_residentes])) };
  });

  register('imp-backlog', ({ t }) => {
    const b = d.impacto.backlog_fim_ano;
    return { option: { tooltip: { trigger: 'axis', formatter: p => tip(p) }, xAxis: ax.cat(t, anos), yAxis: ax.val(t),
      series: [mk.line('Pedidos sem decisão', b, t.series[0], { areaStyle: { color: t.series[0], opacity: .15 }, markPoint: { symbol: 'circle', symbolSize: 40, itemStyle: { color: t.series[0] }, label: { color: '#fff', fontSize: 10, fontWeight: 700, formatter: p => fmt.compact(p.value) }, data: [{ type: 'max' }, { coord: [anos.length - 1, last(b)], value: last(b) }] } })] },
      table: tableYears(anos, { 'Pedidos sem decisão ao fim do ano': b }) };
  });

  register('imp-concessoes', ({ t }) => {
    const dc = d.serie_decisoes; const nres = dc.concessoes.map((v, i) => v - dc.concessoes_residentes[i]);
    return { option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { total: true }) }, xAxis: ax.cat(t, anos, { boundaryGap: true }), yAxis: ax.val(t),
      series: [mk.stackBar('Residentes', dc.concessoes_residentes, t.series[0], t), mk.stackBar('Não residentes', nres, t.series[1], t)] },
      table: tableYears(anos, { 'Residentes': dc.concessoes_residentes, 'Não residentes': nres, 'Total': dc.concessoes, 'Indeferimentos': dc.indeferimentos }) };
  });

  register('imp-vigentes-setor', ({ t }) => {
    const rows = [...d.impacto.vigentes.por_setor].sort((a, b) => b.n - a.n);
    return { option: hbarOption(t, rows.map(r => r.setor), rows.map(r => r.n), { width: 210 }), table: tableRows(['Setor', 'Patentes vigentes'], rows.map(r => [r.setor, r.n])) };
  });

  register('imp-cresc', ({ t }) => {
    const all = d.impacto.crescimento_campos; const rows = [...all.slice(0, 7), ...all.slice(-7)].sort((a, b) => b.variacao_pct - a.variacao_pct);
    return { option: {
      grid: { left: 8, right: 60, top: 8, bottom: 6, containLabel: true },
      tooltip: { trigger: 'item', formatter: p => { const r = rows[p.dataIndex]; return `<b>${r.nome}</b><br>${r.setor}<br>média 2011–15: ${fmt.dec1(r.media_2011_2015)} / ano<br>média 2021–25: ${fmt.dec1(r.media_2021_2025)} / ano<br><b>${fmt.signed(r.variacao_pct)}</b>`; } },
      xAxis: ax.val(t, { formatter: v => v + '%' }), yAxis: ax.catY(t, rows.map(r => r.nome), { width: 220 }),
      series: [{ type: 'bar', data: rows.map(r => ({ value: r.variacao_pct, itemStyle: { color: r.variacao_pct >= 0 ? t.series[0] : t.series[7], borderRadius: r.variacao_pct >= 0 ? [0, 4, 4, 0] : [4, 0, 0, 4] } })), barMaxWidth: 20, label: { show: true, position: 'right', color: t.ink2, fontSize: 12, formatter: p => fmt.signed(p.value) } }] },
      table: tableRows(['Campo', 'Setor', 'Média 2011–2015', 'Média 2021–2025', 'Variação (%)'], all.map(r => [r.nome, r.setor, r.media_2011_2015, r.media_2021_2025, r.variacao_pct])) };
  });

  register('imp-academia', ({ t }) => {
    const imp = d.impacto;
    return { option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.pct }) }, xAxis: ax.cat(t, anos), yAxis: ax.val(t, { formatter: v => v + '%', min: 0 }),
      series: [mk.line('Universidades + institutos de pesquisa', imp.share_academia_residentes, t.series[0]), mk.line('Só universidades', imp.share_universidades_residentes, t.series[1])] },
      table: tableYears(anos, { 'Universidades + institutos (%)': imp.share_academia_residentes, 'Só universidades (%)': imp.share_universidades_residentes, 'Pedidos com nome conhecido (%)': imp.share_residentes_identificados }) };
  });

  register('imp-regional-sp', ({ t }) => ({ option: { tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.pct }) }, xAxis: ax.cat(t, anos), yAxis: ax.val(t, { formatter: v => v + '%', min: 0 }), series: [mk.line('SP (%)', d.impacto.share_sp_residentes, t.series[0], { areaStyle: { color: t.series[0], opacity: .12 } })] }, table: tableYears(anos, { 'Parcela de SP (%)': d.impacto.share_sp_residentes, 'Sudeste + Sul (%)': d.impacto.share_sudeste_sul_residentes }) }));
  register('imp-regional-ufs', ({ t }) => ({ option: { tooltip: { trigger: 'axis', formatter: p => tip(p) }, xAxis: ax.cat(t, anos, { boundaryGap: true }), yAxis: ax.val(t, { formatter: v => v, minInterval: 1 }), series: [mk.bar('UFs com 50+ pedidos', d.impacto.ufs_com_50_ou_mais, t.series[0], t)] }, table: tableYears(anos, { 'UFs com 50+ pedidos': d.impacto.ufs_com_50_ou_mais }) }));
  register('imp-prioritario', ({ t }) => ({ option: { tooltip: { trigger: 'axis', formatter: p => tip(p) }, xAxis: ax.cat(t, anos, { boundaryGap: true }), yAxis: ax.val(t), series: [mk.bar('Pedidos com trâmite prioritário', d.impacto.tramite_prioritario_pedidos, t.series[0], t)] }, table: tableYears(anos, { 'Pedidos com trâmite prioritário': d.impacto.tramite_prioritario_pedidos, 'Ofertas de licença': d.impacto.oferta_licenca_pedidos, 'Transferências/alterações': d.impacto.transferencias_pedidos }) }));

  /* ---------- jornada ---------- */
  const SIT_GROUPS = [
    ['Concedida e vigente', ['Concedida (vigente)']],
    ['Concedida, hoje extinta ou expirada', ['Concedida (prazo expirado)', 'Extinta', 'Anulada']],
    ['Deferida (aguarda carta-patente)', ['Deferida']],
    ['Em andamento', ['Em andamento']],
    ['Indeferida', ['Indeferida']],
    ['Arquivada', ['Arquivada']],
    ['Retirada / desistência', ['Retirada']],
  ];
  register('sit-coorte', ({ t, state }) => {
    const sc = d.situacao_coorte; const src = state.view === 'res' ? sc.por_coorte_residentes : state.view === 'nres' ? sc.por_coorte_nao_residentes : sc.por_coorte;
    const counts = SIT_GROUPS.map(([, keys]) => anos.map((_, i) => sum(keys.map(k => src[k][i]))));
    const totals = anos.map((_, i) => sum(counts.map(c => c[i])));
    const pcts = counts.map(c => c.map((v, i) => pctOf(v, totals[i])));
    return { option: { legend: { type: 'scroll' }, grid: { top: 52 },
      tooltip: { trigger: 'axis', formatter: ps => { const i = ps[0].dataIndex; return `<div style="font-weight:700;margin-bottom:4px">${anos[i]} · ${fmt.int(totals[i])} pedidos</div>` + ps.map(p => `<div style="display:flex;justify-content:space-between;gap:18px"><span>${p.marker} ${p.seriesName}</span><b>${fmt.int(counts[p.seriesIndex][i])} (${fmt.pct(p.value)})</b></div>`).join(''); } },
      xAxis: ax.cat(t, anos, { boundaryGap: true }), yAxis: ax.val(t, { formatter: v => v + '%', max: 100 }),
      series: SIT_GROUPS.map(([name], k) => mk.stackBar(name, pcts[k], t.series[k], t)) },
      table: tableRows(['Ano', ...SIT_GROUPS.map(g => g[0]), 'Total'], anos.map((a, i) => [a, ...counts.map(c => c[i]), totals[i]])) };
  }, { state: { view: 'todos' } });

  register('funil', ({ t, state }) => {
    const f = d.funil; const i = anos.indexOf(state.ano ?? 2015);
    const keys = ['depositados', 'publicados', 'examinados', 'decididos', 'concedidos', 'vigentes'];
    const vals = keys.map(k => f[k][i]); const base = vals[0] || 1;
    const ramp = t.dark ? [t.seq[0], t.seq[2], t.seq[4], t.seq[6], t.seq[8], t.seq[10]] : [t.seq[3], t.seq[5], t.seq[7], t.seq[9], t.seq[11], t.seq[12]];
    return { option: {
      grid: { left: 8, right: 70, top: 6, bottom: 6, containLabel: true },
      tooltip: { trigger: 'item', formatter: p => `<b>${p.name}</b><br>${fmt.int(p.value)} pedidos · ${fmt.pct(pctOf(p.value, base))} da safra` },
      xAxis: ax.val(t, { show: false, max: base }), yAxis: ax.catY(t, f.etapas, { width: 150 }),
      series: [{ type: 'bar', data: vals.map((v, k) => ({ value: v, itemStyle: { color: ramp[k], borderRadius: [0, 4, 4, 0] } })), barCategoryGap: '28%', label: { show: true, position: 'right', color: t.ink2, fontSize: 12, formatter: p => `${fmt.compact(p.value)} · ${fmt.pct(pctOf(p.value, base))}` } }] },
      table: tableRows(['Etapa', `Pedidos (${anos[i]})`, '% da safra'], keys.map((k, j) => [f.etapas[j], vals[j], pctOf(vals[j], base)])) };
  }, { state: { ano: 2015 } });

  register('eventos', ({ t }) => {
    const ev = d.serie_decisoes.eventos_pedidos_distintos; const EV = [['exigencia', 'Exigências'], ['parecer', 'Pareceres técnicos'], ['deferimento', 'Deferimentos'], ['indeferimento', 'Indeferimentos'], ['concessao', 'Concessões'], ['arquivamento', 'Arquivamentos']];
    return { option: { legend: { type: 'scroll' }, grid: { top: 48 }, tooltip: { trigger: 'axis', formatter: p => tip(p) }, xAxis: ax.cat(t, anos), yAxis: ax.val(t),
      series: EV.map(([k, n], i) => mk.area(n, ev[k], t.series[i])) }, table: tableYears(anos, Object.fromEntries(EV.map(([k, n]) => [n, ev[k]]))) };
  });

  register('tempo-hist', ({ t }) => {
    const h = d.tempo_concessao.histograma_recente; const labels = h.bins.map((b, i) => (i === h.bins.length - 1 ? `${b}+` : `${b}–${b + 1}`));
    const per = d.tempo_concessao.periodo_recente; document.getElementById('tempo-hist-sub').textContent = `Patentes concedidas de ${per[0]} a ${per[1]}, por anos desde o protocolo`;
    const via = d.tempo_concessao.por_via_recente; document.getElementById('tempo-via-note').textContent = via.map(v => `${v.via}: mediana de ${fmt.anos(v.mediana)} (${fmt.int(v.n)} concessões)`).join(' · ') + '.';
    return { option: { tooltip: { trigger: 'axis', formatter: p => `<b>${p[0].name} anos</b><br>${fmt.int(p[0].value)} patentes` }, xAxis: ax.cat(t, labels, { boundaryGap: true, axisLabel: { interval: 1 } }), yAxis: ax.val(t), series: [mk.bar('Patentes', h.n, t.series[0], t)] },
      table: tableRows(['Anos até a concessão', 'Patentes'], labels.map((l, i) => [l, h.n[i]])) };
  });

  register('tempo-setor', ({ t }) => {
    const rows = [...d.tempo_concessao.por_setor_recente].sort((a, b) => a.mediana - b.mediana);
    const vias = [...d.tempo_concessao.por_via_recente].sort((a, b) => a.mediana - b.mediana);
    const lab = { show: true, position: 'right', color: t.ink2, fontSize: 12, formatter: p => fmt.anos(p.value) };
    return { option: {
      title: [{ text: 'Por setor tecnológico', left: 0, top: 0, textStyle: { fontSize: 12.5, fontWeight: 600, color: t.ink2 } }, { text: 'Por via de entrada', left: 0, top: '66%', textStyle: { fontSize: 12.5, fontWeight: 600, color: t.ink2 } }],
      grid: [{ left: 8, right: 60, top: 28, height: '50%', containLabel: true }, { left: 8, right: 60, top: '76%', bottom: 4, containLabel: true }],
      tooltip: { trigger: 'item', formatter: p => `<b>${p.name}</b><br>mediana ${fmt.anos(p.value)}` },
      xAxis: [{ ...ax.val(t, { formatter: v => v + ' a', max: 8 }), gridIndex: 0 }, { ...ax.val(t, { formatter: v => v + ' a', max: 8 }), gridIndex: 1 }],
      yAxis: [{ ...ax.catY(t, rows.map(r => r.setor), { width: 210 }), gridIndex: 0 }, { ...ax.catY(t, vias.map(v => v.via === 'PCT' ? 'Via PCT' : 'Via direta'), { width: 210 }), gridIndex: 1 }],
      series: [{ ...mk.hbar('valor', rows.map(r => r.mediana), t.series[0], t, { label: lab }), xAxisIndex: 0, yAxisIndex: 0 }, { ...mk.hbar('valor', vias.map(v => v.mediana), t.series[0], t, { label: lab }), xAxisIndex: 1, yAxisIndex: 1 }] },
      table: tableRows(['Grupo', 'Mediana (anos)', 'Concessões'], [...rows.map(r => [r.setor, r.mediana, r.n]), ...vias.map(v => [v.via, v.mediana, v.n])]) };
  });
  const campoNome = {}; d.campos_tec.setores.forEach(s => s.campos.forEach(c => { campoNome[c.campo_tec] = c.nome; }));
  register('tempo-campo', ({ t }) => {
    const rows = [...d.tempo_concessao.por_campo_recente].filter(r => r.n >= 50).sort((a, b) => a.mediana - b.mediana);
    return { option: hbar2Option(t, rows.map(r => ({ name: campoNome[r.campo_tec], value: r.mediana })), { fmtv: fmt.anos, width: 200 }), table: tableRows(['Campo', 'Mediana (anos)', 'Concessões'], rows.map(r => [campoNome[r.campo_tec], r.mediana, r.n])) };
  });

  /* ---------- quem ---------- */
  register('race', ({ t, state }) => {
    const frames = d.depositantes.corrida_residentes; const fi = state.i ?? frames.length - 1; const frame = frames[fi]; const cc = CAT_COLOR(t);
    return { option: {
      grid: { left: 8, right: 70, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: 'item', formatter: p => `<b>${p.name}</b><br>${fmt.int(p.value)} pedidos acumulados até ${frame.ano}` },
      xAxis: ax.val(t, { position: 'top' }),
      yAxis: { type: 'category', inverse: true, max: 11, data: frame.itens.map(i => i.nome), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.ink2, width: 230, overflow: 'truncate', fontSize: 12 }, animationDuration: 300, animationDurationUpdate: 300 },
      series: [{ type: 'bar', realtimeSort: true, data: frame.itens.map(i => ({ value: i.valor, itemStyle: { color: cc[i.categoria] || t.deemph, borderRadius: [0, 4, 4, 0] } })), barMaxWidth: 24, label: { show: true, position: 'right', valueAnimation: true, color: t.ink2, fontSize: 12, formatter: p => fmt.int(p.value) } }],
      graphic: [{ type: 'text', right: 28, bottom: 18, style: { text: String(frame.ano), font: '800 48px Inter, system-ui, sans-serif', fill: t.grid } }],
      animationDuration: 0, animationDurationUpdate: reducedMotion ? 0 : 950, animationEasing: 'linear', animationEasingUpdate: 'linear' },
      table: tableRows(['Depositante', 'Categoria', `Pedidos acumulados até ${frame.ano}`], frame.itens.map(i => [i.nome, CAT_LABEL[i.categoria] || i.categoria, i.valor])),
      after: (chart, r) => {
        if (r.player) return; r.player = { timer: null };
        const btn = r.card.querySelector('.btn-play');
        const stop = () => { clearInterval(r.player.timer); r.player.timer = null; btn.textContent = '▶ Reproduzir'; };
        btn.addEventListener('click', () => {
          if (r.player.timer) return stop();
          let i = (r.state.i == null || r.state.i >= frames.length - 1) ? 0 : r.state.i + 1;
          btn.textContent = '⏸ Pausar';
          const step = () => { r.state.i = i; rerender('race', {}); if (++i >= frames.length) stop(); };
          step(); r.player.timer = setInterval(step, reducedMotion ? 400 : 1100);
        });
      } };
  }, { state: {} });

  register('top-dep', ({ t, state }) => {
    const list = d.depositantes[state.view || 'top_geral']; const rows = list.slice(0, 15);
    return { option: { ...hbarOption(t, rows.map(r => r.nome), rows.map(r => r.total), { width: 150 }), tooltip: { trigger: 'item', formatter: p => { const r = rows[p.dataIndex]; return `<b>${r.nome}</b><br>${r.pais_nome} · ${CAT_LABEL[r.categoria] || r.categoria}<br>${fmt.int(r.total)} pedidos · ${fmt.int(r.concedidos)} concedidos<br>${fmt.int(r.ultimo_ano)} em ${d.resumo.ano_ultimo}`; } } },
      table: tableRows(['Depositante', 'País', 'Categoria', 'Pedidos', 'Concedidos', `Em ${d.resumo.ano_ultimo}`], list.map(r => [r.nome, r.pais_nome, CAT_LABEL[r.categoria] || r.categoria, r.total, r.concedidos, r.ultimo_ano])) };
  }, { state: { view: 'top_geral' } });

  register('paises-bar', ({ t }) => {
    const ps = d.paises.paises; const top = ps.filter(p => p.pais !== 'OUTROS').slice(0, 12); const outros = ps.find(p => p.pais === 'OUTROS');
    const rows = [...top, ...(outros ? [outros] : [])];
    return { option: { ...hbarOption(t, rows.map(r => r.nome), rows.map(r => r.total), { width: 150 }), series: [{ type: 'bar', data: rows.map(r => ({ value: r.total, itemStyle: { color: r.pais === 'BR' ? t.series[0] : t.deemph, borderRadius: [0, 4, 4, 0] } })), barMaxWidth: 22, label: { show: true, position: 'right', color: t.ink2, fontSize: 12, formatter: p => fmt.int(p.value) } }],
      tooltip: { trigger: 'item', formatter: p => { const r = rows[p.dataIndex]; return `<b>${r.nome}</b><br>${fmt.int(r.total)} pedidos · ${fmt.int(r.concedidos)} concedidos<br>${fmt.pct(r.share_pct)} via PCT`; } } },
      table: tableRows(['País', 'Pedidos', 'Concedidos', '% via PCT'], ps.map(r => [r.nome, r.total, r.concedidos, r.share_pct])) };
  });

  register('paises-linhas', ({ t }) => {
    const top = d.paises.paises.filter(p => p.pais !== 'OUTROS').slice(0, 6);
    return { option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p) }, xAxis: ax.cat(t, anos), yAxis: ax.val(t), series: top.map((p, i) => mk.line(p.nome, p.serie, t.series[i])) },
      table: tableYears(anos, Object.fromEntries(top.map(p => [p.nome, p.serie]))) };
  });

  /* ---------- onde ---------- */
  const ufByCode = Object.fromEntries(d.uf.ufs.map(u => [String(u.codigo_ibge), u]));
  d.geo.features.forEach(f => { const u = ufByCode[String(f.properties.codarea)]; f.properties.name = u ? u.uf : f.properties.codarea; });
  echarts.registerMap('BR', d.geo);
  const METRIC = { total: 'Pedidos 2000–2025', concedidos: 'Patentes concedidas', vigentes: 'Patentes vigentes', ultimo_ano: `Pedidos em ${d.resumo.ano_ultimo}` };
  register('mapa', ({ t, state }) => {
    const m = state.view || 'total'; const ufs = d.uf.ufs; const vals = ufs.map(u => u[m]);
    return { option: {
      tooltip: { trigger: 'item', formatter: p => { const u = ufs.find(x => x.uf === p.name); if (!u) return p.name; return `<b>${u.nome}</b> (${u.regiao})<br>${fmt.int(u.total)} pedidos · ${fmt.int(u.concedidos)} concedidos · ${fmt.int(u.vigentes)} vigentes<br>${fmt.int(u.ultimo_ano)} em ${d.resumo.ano_ultimo}<br><span style="color:${t.muted}">${u.top_campos.map(c => c.nome).join(' · ')}</span>`; } },
      visualMap: { type: 'continuous', min: 0, max: Math.max(...vals), inRange: { color: t.seq }, orient: 'horizontal', left: 'center', bottom: 0, itemWidth: 12, itemHeight: 160, text: ['mais', 'menos'], textStyle: { color: t.ink2, fontSize: 12 }, formatter: v => fmt.compact(v) },
      series: [{ type: 'map', map: 'BR', name: METRIC[m], roam: false, aspectScale: 0.92, layoutCenter: ['50%', '47%'], layoutSize: '92%', data: ufs.map((u, i) => ({ name: u.uf, value: vals[i] })), itemStyle: { borderColor: t.surface, borderWidth: 1 }, label: { show: true, color: t.ink, fontSize: 10, formatter: p => p.name }, emphasis: { label: { show: true, color: t.ink, fontWeight: 700 }, itemStyle: { borderColor: t.ink, borderWidth: 1.5 } }, select: { disabled: true } }] },
      table: tableRows(['UF', 'Região', 'Pedidos', 'Concedidos', 'Vigentes', `Em ${d.resumo.ano_ultimo}`], ufs.map(u => [`${u.uf} – ${u.nome}`, u.regiao, u.total, u.concedidos, u.vigentes, u.ultimo_ano])) };
  }, { state: { view: 'total' } });

  register('regioes', ({ t }) => {
    const rg = d.uf.regioes;
    return { option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { total: true }) }, xAxis: ax.cat(t, anos), yAxis: ax.val(t), series: rg.map((r, i) => mk.area(r.regiao, r.serie, t.series[i])) }, table: tableYears(anos, Object.fromEntries(rg.map(r => [r.regiao, r.serie]))) };
  });
  register('municipios', ({ t }) => {
    const rows = d.municipios.municipios.slice(0, 20);
    return { option: { ...hbarOption(t, rows.map(r => `${r.cidade} (${r.uf})`), rows.map(r => r.total), { width: 170 }), tooltip: { trigger: 'item', formatter: p => { const r = rows[p.dataIndex]; return `<b>${r.cidade} (${r.uf})</b><br>${fmt.int(r.total)} pedidos · ${fmt.int(r.concedidos)} concedidos<br>${fmt.int(r.universidades)} de universidades · ${fmt.int(r.ultimo_ano)} em ${d.resumo.ano_ultimo}`; } } },
      table: tableRows(['Município', 'UF', 'Pedidos', 'Concedidos', 'De universidades', `Em ${d.resumo.ano_ultimo}`], d.municipios.municipios.map(r => [r.cidade, r.uf, r.total, r.concedidos, r.universidades, r.ultimo_ano])) };
  });
  register('uf-ranking', ({ t }) => {
    const rows = [...d.uf.ufs].sort((a, b) => b.total - a.total);
    return { option: hbarOption(t, rows.map(r => r.nome), rows.map(r => r.total), { width: 150 }), table: tableRows(['UF', 'Pedidos', 'Concedidos', 'Vigentes'], rows.map(r => [r.nome, r.total, r.concedidos, r.vigentes])) };
  });

  /* ---------- tecnologias ---------- */
  register('treemap', ({ t }) => {
    const data = d.campos_tec.setores.map((s, i) => ({ name: s.setor, value: s.total, itemStyle: { color: t.series[i] }, children: s.campos.map(c => ({ name: c.nome, value: c.total, campo: c })) }));
    return { option: {
      tooltip: { formatter: p => { const c = p.data.campo; return c ? `<b>${c.nome}</b><br>${fmt.int(c.total)} pedidos · ${fmt.int(c.concedidos)} concedidos<br>${fmt.pct(pctOf(c.residentes, c.total))} de residentes` : `<b>${p.name}</b><br>${fmt.int(p.value)} pedidos`; } },
      series: [{ type: 'treemap', data, roam: false, nodeClick: false, breadcrumb: { show: false }, width: '100%', height: '100%', top: 0, left: 0, right: 0, bottom: 0,
        label: { show: true, formatter: p => `${p.name}\n${fmt.compact(p.value)}`, fontSize: 12, color: '#fff', padding: 6, overflow: 'truncate' },
        upperLabel: { show: true, height: 28, color: '#fff', fontWeight: 700, fontSize: 13, formatter: p => `${p.name}  ·  ${fmt.compact(p.value)}` },
        levels: [
          { itemStyle: { gapWidth: 4, borderWidth: 0 }, upperLabel: { show: false } },
          { itemStyle: { borderWidth: 3, gapWidth: 3, borderColorSaturation: 0.75 }, upperLabel: { show: true, height: 28, color: '#fff', fontWeight: 700 } },
          { colorSaturation: [0.5, 0.85], itemStyle: { borderColor: t.surface, borderWidth: 1, gapWidth: 2 } },
        ] }] },
      table: tableRows(['Setor', 'Campo', 'Pedidos', 'Concedidos', 'Residentes'], d.campos_tec.setores.flatMap(s => s.campos.map(c => [s.setor, c.nome, c.total, c.concedidos, c.residentes]))) };
  });
  register('setores-area', ({ t }) => {
    const ss = d.campos_tec.setores;
    return { option: { legend: { type: 'scroll' }, grid: { top: 48 }, tooltip: { trigger: 'axis', formatter: p => tip(p, { total: true }) }, xAxis: ax.cat(t, anos), yAxis: ax.val(t), series: ss.map((s, i) => mk.area(s.setor, s.serie, t.series[i])) }, table: tableYears(anos, Object.fromEntries(ss.map(s => [s.setor, s.serie]))) };
  });
  const allCampos = d.campos_tec.setores.flatMap(s => s.campos.map(c => ({ ...c, setor: s.setor })));
  register('campo-res', ({ t }) => {
    const sorted = allCampos.map(c => ({ ...c, share: pctOf(c.residentes, c.total) })).sort((a, b) => b.share - a.share);
    const rows = [...sorted.slice(0, 10), ...sorted.slice(-5)];
    return { option: hbarOption(t, rows.map(r => r.nome), rows.map(r => r.share), { fmtv: fmt.pct, width: 230, max: 100 }), table: tableRows(['Campo', 'Setor', 'Residentes (%)', 'Pedidos'], sorted.map(r => [r.nome, r.setor, r.share, r.total])) };
  });
  // pequenos múltiplos: 8 maiores campos
  const top8 = [...allCampos].sort((a, b) => b.total - a.total).slice(0, 8);
  const host = document.getElementById('campos-mult');
  host.innerHTML = top8.map(c => `<article class="card col-3 keep reveal" data-chart="campo-${c.campo_tec}"><header><div class="titles"><h3 style="font-size:14px">${c.nome}</h3><p class="sub">${fmt.int(c.total)} pedidos · ${c.setor}</p></div><div class="actions"><button class="icon-btn btn-table">Tabela</button></div></header><div class="chart" style="height:150px"></div><div class="table-view hidden"></div></article>`).join('');
  top8.forEach(c => register(`campo-${c.campo_tec}`, ({ t }) => ({ option: { legend: {}, grid: { left: 4, right: 22, top: 30, bottom: 4, containLabel: true }, tooltip: { trigger: 'axis', formatter: p => tip(p) }, xAxis: ax.cat(t, anos, { axisLabel: { showMinLabel: true, showMaxLabel: true, interval: anos.length - 2 } }), yAxis: ax.val(t, { splitNumber: 3 }), series: [mk.line('Todos', c.serie, t.series[0], { areaStyle: { color: t.series[0], opacity: .12 } }), mk.line('Residentes', c.serie_residentes, t.series[1])] }, table: tableYears(anos, { 'Pedidos': c.serie, 'Residentes': c.serie_residentes, 'Concessões': c.serie_concessoes }) })));

  /* ---------- gênero ---------- */
  register('gen-share', ({ t }) => {
    const g = d.genero;
    return { option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.pct }) }, xAxis: ax.cat(t, anos), yAxis: ax.val(t, { formatter: v => v + '%', min: 0 }),
      series: [mk.line('Inventoras (% dos inventores)', g.share_f_inventores, t.series[0]), mk.line('Depositantes PF mulheres (%)', g.share_f_depositantes, t.series[1])] },
      table: tableYears(anos, { 'Inventoras (%)': g.share_f_inventores, 'Inventoras (n)': g.inventores.F, 'Inventores (n)': g.inventores.M, 'Depositantes PF mulheres (%)': g.share_f_depositantes }) };
  });
  register('gen-setor', ({ t }) => {
    const rows = [...d.genero.share_f_por_setor].sort((a, b) => b.share_f - a.share_f);
    return { option: hbarOption(t, rows.map(r => r.setor), rows.map(r => r.share_f), { fmtv: fmt.pct, width: 210, max: 60 }), table: tableRows(['Setor', 'Inventoras (%)', 'Menções'], rows.map(r => [r.setor, r.share_f, r.n])) };
  });
  register('gen-campo', ({ t }) => {
    const rows = [...d.genero.share_f_por_campo].filter(r => r.n >= 200).sort((a, b) => b.share_f - a.share_f);
    return { option: hbar2Option(t, rows.map(r => ({ name: campoNome[r.campo_tec], value: r.share_f })), { fmtv: fmt.pct, width: 220, max: 60 }), table: tableRows(['Campo', 'Inventoras (%)', 'Menções'], rows.map(r => [campoNome[r.campo_tec], r.share_f, r.n])) };
  });
}

/* ---------- animações de rolagem ---------- */
function reveals() {
  if (reducedMotion || !window.gsap || !window.ScrollTrigger) return;
  gsap.registerPlugin(ScrollTrigger);
  gsap.utils.toArray('.reveal').forEach(el => gsap.from(el, { opacity: 0, y: 26, duration: .8, ease: 'power2.out', scrollTrigger: { trigger: el, start: 'top 90%', once: true } }));
  gsap.from('.hero h1', { opacity: 0, y: 24, duration: .9, ease: 'power3.out' });
  gsap.from('.hero .lead, .hero .cta', { opacity: 0, y: 18, duration: .9, delay: .15, ease: 'power3.out', stagger: .1 });
  gsap.from('.hero-stat', { opacity: 0, y: 18, duration: .8, delay: .35, stagger: .08, ease: 'power3.out' });
}
function navSpy() {
  const links = [...document.querySelectorAll('nav.primary a[href^="#"]')];
  const io = new IntersectionObserver(entries => { entries.forEach(e => { if (e.isIntersecting) links.forEach(l => l.classList.toggle('active', l.getAttribute('href') === '#' + e.target.id)); }); }, { rootMargin: '-40% 0px -55% 0px' });
  document.querySelectorAll('section.block[id]').forEach(s => io.observe(s));
}

/* ---------- boot ---------- */
initTheme(document.getElementById('theme-toggle'));
loadAll().then(data => {
  d = data;
  hero(); kpis(); bigNumbers(); charts();
  mountAll({ d });
  reveals(); navSpy();
}).catch(err => {
  console.error(err);
  const row = document.getElementById('kpis'); if (row) row.innerHTML = `<div class="tile"><div class="label">Não foi possível carregar os dados</div><div class="delta">${err.message}. Rode <code>uv run badepi gold</code> para gerar os JSON em docs/data/.</div></div>`;
});
