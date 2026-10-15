/* shared.js — construtores de gráficos e componentes comuns aos quatro ativos.
   Cada página chama mountCommon(d, cfg) para registrar os cards padrão presentes no HTML. */
import { tokens, register, rerender, fmt, ax, mk, tableYears, tableRows, countUpOnView, spark, onThemeChange, reducedMotion } from './viz.js';

export const sum = a => a.reduce((x, y) => x + (y || 0), 0);
export const last = a => a[a.length - 1];
export const pctOf = (a, b) => (b ? +(a / b * 100).toFixed(1) : null);
export const CAT_COLOR = t => ({ universidade: t.series[0], empresa: t.series[1], instituto_pesquisa: t.series[2], pessoa_fisica: t.series[3], governo: t.series[4], pessoa_fisica_provavel: t.series[3], nao_classificado: t.deemph, nao_identificado: t.deemph });
export const CAT_LABEL = { universidade: 'Universidades', empresa: 'Empresas', instituto_pesquisa: 'Institutos de pesquisa', pessoa_fisica: 'Pessoas físicas', governo: 'Governo', nao_identificado: 'Não identificado (sigilo)', pessoa_fisica_provavel: 'Pessoas físicas (provável)', nao_classificado: 'Não classificado' };
// rótulos de eixo temporal: o leitor precisa saber de que data se trata
export const X = {
  deposito: 'Ano de depósito (protocolo do pedido no INPI)',
  safra: 'Safra: ano de depósito do pedido',
  concessao: 'Ano de publicação da concessão na RPI',
  registro: 'Ano de publicação do registro na RPI',
  despacho: 'Ano de publicação do despacho na RPI',
  decisao: 'Ano de publicação da primeira decisão na RPI',
  fimAno: 'Situação ao fim de cada ano',
  decorrido: 'Anos decorridos desde o protocolo do pedido',
};

export function tip(params, { total = false, fmtv = fmt.int } = {}) {
  const ps = params.filter(p => p.value != null && p.seriesName && !String(p.seriesName).startsWith('_'));
  const head = `<div style="font-weight:700;margin-bottom:4px">${params[0].axisValueLabel ?? params[0].name}</div>`;
  const rows = ps.map(p => `<div style="display:flex;justify-content:space-between;gap:18px"><span>${p.marker} ${p.seriesName}</span><b>${fmtv(Array.isArray(p.value) ? p.value[1] : p.value)}</b></div>`);
  const tot = total ? `<div style="border-top:1px solid rgba(128,128,128,.3);margin-top:4px;padding-top:4px;display:flex;justify-content:space-between"><span>Total</span><b>${fmtv(sum(ps.map(p => Array.isArray(p.value) ? p.value[1] : p.value)))}</b></div>` : '';
  return head + rows.join('') + tot;
}
export function hbarOption(t, names, values, { color, fmtv = fmt.int, width = 190, max, fontSize } = {}) {
  return {
    grid: { left: 8, right: 56, top: 8, bottom: 6, containLabel: true },
    tooltip: { trigger: 'item', formatter: p => `<b>${p.name}</b><br>${fmtv(p.value)}` },
    xAxis: ax.val(t, { formatter: v => (fmtv === fmt.pct ? v + '%' : fmt.compact(v)), max }),
    yAxis: ax.catY(t, names, { width, fontSize }),
    series: [mk.hbar('valor', values, color || t.series[0], t, { label: { show: true, position: 'right', color: t.ink2, fontSize: 12, formatter: p => fmtv(p.value) } })],
  };
}
export function hbar2Option(t, rows, { fmtv = fmt.int, width = 220, max, fontSize = 11.5 } = {}) {
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
export function hexA(hex, a) { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; }

/* ---------- hero: rede de partículas ---------- */
export function heroCanvas() {
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

/* ---------- KPIs (tiles) e números do hero ---------- */
export function heroStats(kpis) {
  document.querySelectorAll('[data-kpi]').forEach(el => { el.dataset.count = kpis[el.dataset.kpi] ?? 0; });
  countUpOnView(document.querySelector('.hero') || document);
}
export function kpiTiles(tiles, hostId = 'kpis') {
  const t = tokens(); const row = document.getElementById(hostId); if (!row) return;
  row.innerHTML = tiles.map((x, i) => `<div class="tile reveal"><div class="label">${x.label}</div><div class="value" data-count="${x.value ?? 0}" data-decimals="${x.decimals || 0}" data-suffix="${x.suffix || ''}">–</div>
    <div class="delta">${x.delta != null ? `<span class="${x.delta >= 0 ? 'up' : 'down'}">${x.delta >= 0 ? '▲' : '▼'} ${fmt.signed(x.delta)}</span> vs. ano anterior` : (x.sub || '')}</div>${x.spark ? `<div class="spark" id="${hostId}-spark-${i}"></div>` : ''}</div>`).join('');
  countUpOnView(row);
  tiles.forEach((x, i) => { if (x.spark) spark(document.getElementById(`${hostId}-spark-${i}`), x.spark, t.series[0], t); });
}
export function setText(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }
export function footerInfo(resumo) {
  const ger = new Date(resumo.gerado_em);
  setText('gerado', `BADEPI ${resumo.badepi_version} · referência ${new Date(resumo.data_referencia + 'T12:00:00').toLocaleDateString('pt-BR')} · painel gerado em ${ger.toLocaleDateString('pt-BR')}`);
}

/* ---------- construtores comuns ---------- */
const SIT_GROUPS = (termo) => [
  [`${termo === 'registro' ? 'Registrada' : 'Concedida'} e vigente`, ['Concedida (vigente)']],
  [`${termo === 'registro' ? 'Registrada' : 'Concedida'}, hoje extinta ou expirada`, ['Concedida (prazo expirado)', 'Extinta', 'Anulada']],
  ['Deferida (aguarda pagamento)', ['Deferida']],
  ['Em andamento', ['Em andamento']],
  ['Indeferida', ['Indeferida']],
  ['Arquivada', ['Arquivada']],
  ['Retirada / desistência', ['Retirada']],
  ['Numeração anulada (depósito não efetivado)', ['Numeração anulada']],
];

export function mountCommon(d, cfg) {
  const anos = d.serie_depositos.anos; const termo = cfg.termo || 'concessão'; const ano = d.resumo.ano_ultimo;
  const xConc = termo === 'registro' ? X.registro : X.concessao;
  const tempo = d.tempo_concessao || d.tempo_registro;

  register('dep-origem', ({ t }) => ({ option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { total: true }) }, xAxis: ax.time(t, anos, X.deposito, { boundaryGap: true }), yAxis: ax.val(t),
    series: [mk.stackBar('Residentes', d.serie_depositos.residente, t.series[0], t), mk.stackBar('Não residentes', d.serie_depositos.nao_residente, t.series[1], t)] },
    table: tableYears(anos, { Residentes: d.serie_depositos.residente, 'Não residentes': d.serie_depositos.nao_residente, Total: d.serie_depositos.total }) }));

  register('dep-categoria', ({ t }) => {
    const s = d.serie_depositos; const cats = ['empresa', 'pessoa_fisica', 'universidade', 'instituto_pesquisa', 'governo', 'nao_identificado'].filter(c => sum(s.categoria_residente[c] || []) > 0);
    const colors = CAT_COLOR(t);
    return { option: { legend: { type: 'scroll' }, grid: { top: 48 }, tooltip: { trigger: 'axis', formatter: p => tip(p, { total: true }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t),
      series: cats.map(c => mk.area(CAT_LABEL[c], s.categoria_residente[c], colors[c])) }, table: tableYears(anos, Object.fromEntries(cats.map(c => [CAT_LABEL[c], s.categoria_residente[c]]))) };
  });

  register('imp-tempo', ({ t }) => {
    const rows = tempo.por_ano; const xs = rows.map(r => r.ano);
    const p25 = rows.map(r => r.p25), band = rows.map(r => +(r.p75 - r.p25).toFixed(2)), med = rows.map(r => r.mediana);
    return { option: {
      tooltip: { trigger: 'axis', formatter: ps => { const r = rows[ps[0].dataIndex]; return `<b>${r.ano}</b> · ${fmt.int(r.n)} ${termo === 'registro' ? 'registros' : 'concessões'}<br>mediana <b>${fmt.anos(r.mediana)}</b><br>quartis: ${fmt.dec1(r.p25)} – ${fmt.dec1(r.p75)} anos<br>residentes ${fmt.anos(r.mediana_residentes)} · não residentes ${fmt.anos(r.mediana_nao_residentes)}`; } },
      xAxis: ax.time(t, xs, xConc), yAxis: ax.val(t, { formatter: v => v + ' a', min: 0 }),
      series: [
        { name: '_p25', type: 'line', data: p25, stack: 'band', lineStyle: { opacity: 0 }, showSymbol: false, silent: true, areaStyle: { opacity: 0 } },
        { name: '_band', type: 'line', data: band, stack: 'band', lineStyle: { opacity: 0 }, showSymbol: false, silent: true, areaStyle: { color: t.series[0], opacity: .14 } },
        mk.line('Mediana', med, t.series[0], { markPoint: { symbol: 'circle', symbolSize: 36, itemStyle: { color: t.series[0] }, label: { color: '#fff', fontSize: 11, fontWeight: 700, formatter: p => fmt.dec1(p.value) }, data: [{ type: 'max', name: 'pior ano' }, { name: 'último', coord: [xs.length - 1, last(med)], value: last(med) }] } }),
      ] },
      table: tableRows([`Ano de ${termo}`, 'N', 'Mediana (anos)', 'P25', 'P75', 'Residentes', 'Não residentes'], rows.map(r => [r.ano, r.n, r.mediana, r.p25, r.p75, r.mediana_residentes, r.mediana_nao_residentes])) };
  });

  register('imp-backlog', ({ t }) => {
    const b = (d.impacto || d.backlog).backlog_fim_ano;
    return { option: { tooltip: { trigger: 'axis', formatter: p => tip(p) }, xAxis: ax.time(t, anos, X.fimAno), yAxis: ax.val(t),
      series: [mk.line('Pedidos sem decisão', b, t.series[0], { areaStyle: { color: t.series[0], opacity: .15 }, markPoint: { symbol: 'circle', symbolSize: 40, itemStyle: { color: t.series[0] }, label: { color: '#fff', fontSize: 10, fontWeight: 700, formatter: p => fmt.compact(p.value) }, data: [{ type: 'max' }, { coord: [anos.length - 1, last(b)], value: last(b) }] } })] },
      table: tableYears(anos, { 'Pedidos sem decisão ao fim do ano': b }) };
  });

  register('imp-concessoes', ({ t }) => {
    const dc = d.serie_decisoes; const nres = dc.concessoes.map((v, i) => v - dc.concessoes_residentes[i]);
    return { option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { total: true }) }, xAxis: ax.time(t, anos, xConc, { boundaryGap: true }), yAxis: ax.val(t),
      series: [mk.stackBar('Residentes', dc.concessoes_residentes, t.series[0], t), mk.stackBar('Não residentes', nres, t.series[1], t)] },
      table: tableYears(anos, { Residentes: dc.concessoes_residentes, 'Não residentes': nres, Total: dc.concessoes, Indeferimentos: dc.indeferimentos }) };
  });

  register('sit-coorte', ({ t, state }) => {
    const sc = d.situacao_coorte; const src = state.view === 'res' ? sc.por_coorte_residentes : state.view === 'nres' ? sc.por_coorte_nao_residentes : sc.por_coorte;
    const groups = SIT_GROUPS(termo).filter(([, keys]) => keys.some(k => src[k] && sum(src[k]) > 0));
    const counts = groups.map(([, keys]) => anos.map((_, i) => sum(keys.map(k => (src[k] || [])[i] || 0))));
    const totals = anos.map((_, i) => sum(counts.map(c => c[i]))); const pcts = counts.map(c => c.map((v, i) => pctOf(v, totals[i])));
    return { option: { legend: { type: 'scroll' }, grid: { top: 52 },
      tooltip: { trigger: 'axis', formatter: ps => { const i = ps[0].dataIndex; return `<div style="font-weight:700;margin-bottom:4px">${anos[i]} · ${fmt.int(totals[i])} pedidos</div>` + ps.map(p => `<div style="display:flex;justify-content:space-between;gap:18px"><span>${p.marker} ${p.seriesName}</span><b>${fmt.int(counts[p.seriesIndex][i])} (${fmt.pct(p.value)})</b></div>`).join(''); } },
      xAxis: ax.time(t, anos, X.safra, { boundaryGap: true }), yAxis: ax.val(t, { formatter: v => v + '%', max: 100 }),
      series: groups.map(([name], k) => mk.stackBar(name, pcts[k], t.series[k], t)) },
      table: tableRows(['Safra', ...groups.map(g => g[0]), 'Total'], anos.map((a, i) => [a, ...counts.map(c => c[i]), totals[i]])) };
  }, { state: { view: 'todos' } });

  register('funil', ({ t, state }) => {
    const f = d.funil; const i = anos.indexOf(state.ano ?? 2015);
    const keys = ['depositados', 'publicados', 'examinados', 'decididos', 'concedidos', 'vigentes'].filter(k => f[k]);
    const vals = keys.map(k => f[k][i]); const base = vals[0] || 1;
    const ramp = t.dark ? [t.seq[0], t.seq[2], t.seq[4], t.seq[6], t.seq[8], t.seq[10]] : [t.seq[3], t.seq[5], t.seq[7], t.seq[9], t.seq[11], t.seq[12]];
    return { option: { grid: { left: 8, right: 70, top: 6, bottom: 6, containLabel: true },
      tooltip: { trigger: 'item', formatter: p => `<b>${p.name}</b><br>${fmt.int(p.value)} pedidos · ${fmt.pct(pctOf(p.value, base))} da safra` },
      xAxis: ax.val(t, { show: false, max: base }), yAxis: ax.catY(t, f.etapas, { width: 150 }),
      series: [{ type: 'bar', data: vals.map((v, k) => ({ value: v, itemStyle: { color: ramp[k], borderRadius: [0, 4, 4, 0] } })), barCategoryGap: '28%', label: { show: true, position: 'right', color: t.ink2, fontSize: 12, formatter: p => `${fmt.compact(p.value)} · ${fmt.pct(pctOf(p.value, base))}` } }] },
      table: tableRows(['Etapa', `Pedidos (safra ${anos[i]})`, '% da safra'], keys.map((k, j) => [f.etapas[j], vals[j], pctOf(vals[j], base)])) };
  }, { state: { ano: 2015 } });

  register('eventos', ({ t }) => {
    const ev = d.serie_decisoes.eventos_pedidos_distintos || {}; const EV = cfg.eventos || [['exigencia', 'Exigências'], ['deferimento', 'Deferimentos'], ['indeferimento', 'Indeferimentos'], ['concessao', termo === 'registro' ? 'Registros' : 'Concessões'], ['arquivamento', 'Arquivamentos'], ['extincao', 'Extinções']];
    const EVk = EV.filter(([k]) => ev[k]);
    return { option: { legend: { type: 'scroll' }, grid: { top: 48 }, tooltip: { trigger: 'axis', formatter: p => tip(p) }, xAxis: ax.time(t, anos, X.despacho), yAxis: ax.val(t),
      series: EVk.map(([k, n], i) => mk.area(n, ev[k], t.series[i])) }, table: tableYears(anos, Object.fromEntries(EVk.map(([k, n]) => [n, ev[k]]))) };
  });

  register('tempo-hist', ({ t }) => {
    const h = tempo.histograma_recente; const labels = h.bins.map((b, i) => (i === h.bins.length - 1 ? `${b}+` : `${b}–${b + 1}`));
    const per = tempo.periodo_recente; setText('tempo-hist-sub', `${termo === 'registro' ? 'Registros' : 'Patentes'} de ${per[0]} a ${per[1]}, por anos entre o protocolo e a ${termo}`);
    if (tempo.por_via_recente) setText('tempo-via-note', tempo.por_via_recente.map(v => `${v.grupo}: mediana de ${fmt.anos(v.mediana)} (${fmt.int(v.n)})`).join(' · ') + '.');
    return { option: { tooltip: { trigger: 'axis', formatter: p => `<b>${p[0].name} anos</b><br>${fmt.int(p[0].value)}` }, xAxis: ax.time(t, labels, X.decorrido, { boundaryGap: true, axisLabel: { interval: 1 } }), yAxis: ax.val(t), series: [mk.bar(termo === 'registro' ? 'Registros' : 'Patentes', h.n, t.series[0], t)] },
      table: tableRows(['Anos decorridos', 'N'], labels.map((l, i) => [l, h.n[i]])) };
  });

  register('ciclo', ({ t, state }) => {
    const cv = d.ciclo_vida; const src = state.ano === 'todos' || !cv.por_ano[state.ano] ? cv.todos : cv.por_ano[state.ano];
    const passos = cv.passos; const colors = [t.series[3], t.series[0], t.series[2], t.series[6], t.series[7], t.series[1], t.series[4]];
    const excl = cv.excluidos_numeracao_anulada ? ` · ${fmt.int(cv.excluidos_numeracao_anulada)} pedidos com numeração anulada (depósito não efetivado) ficam fora` : '';
    setText('ciclo-sub', (state.ano === 'todos' ? `Todas as safras (${anos[0]}–${anos[anos.length - 1]}), só pedidos já observáveis em cada ponto` : `Safra ${state.ano}: ${fmt.int(src.n_observados[0])} pedidos`) + excl);
    return { option: { legend: { type: 'scroll' }, grid: { top: 52 },
      tooltip: { trigger: 'axis', formatter: ps => { const i = ps[0].dataIndex; return `<div style="font-weight:700;margin-bottom:4px">${passos[i]} anos após o protocolo · ${fmt.int(src.n_observados[i])} pedidos observáveis</div>` + ps.map(p => `<div style="display:flex;justify-content:space-between;gap:18px"><span>${p.marker} ${p.seriesName}</span><b>${fmt.pct(p.value)}</b></div>`).join(''); } },
      xAxis: ax.time(t, passos.map(p => (Number.isInteger(p) ? String(p) : '')), X.decorrido, { axisLabel: { interval: 1 } }), yAxis: ax.val(t, { formatter: v => v + '%', max: 100 }),
      series: cv.estados.map((e, k) => mk.area(e, src.estados[e], colors[k])) },
      table: tableRows(['Anos decorridos', 'Observáveis', ...cv.estados.map(e => e + ' (%)')], passos.map((p, i) => [p, src.n_observados[i], ...cv.estados.map(e => src.estados[e][i])])) };
  }, { state: { ano: 'todos' } });

  register('transicoes', ({ t, state }) => {
    const tr = d.transicoes; const de = state.de ?? anos[0], ate = state.ate ?? last(anos); const minW = state.min ?? 50;
    const acc = new Map();
    for (let a = de; a <= ate; a++) for (const [i, j, n] of (tr.por_ano[String(a)] || [])) { const k = i + '-' + j; acc.set(k, (acc.get(k) || 0) + n); }
    const edges = [...acc.entries()].map(([k, n]) => { const [i, j] = k.split('-').map(Number); return { i, j, n }; }).filter(e => e.n >= minW && e.i !== e.j);
    const used = new Set(edges.flatMap(e => [e.i, e.j])); const maxN = Math.max(1, ...edges.map(e => e.n));
    const grp = ev => (['deposito', 'publicacao', 'pct_fase_nacional'].includes(ev) ? 0 : ['exigencia', 'parecer', 'anuencia_anvisa', 'sobrestamento', 'oposicao'].includes(ev) ? 1 : ['deferimento', 'concessao', 'prorrogacao'].includes(ev) ? 2 : ['indeferimento', 'arquivamento', 'extincao', 'desistencia_retirada', 'anulacao', 'patente_anulada', 'numeracao_anulada'].includes(ev) ? 3 : ['recurso', 'recurso_provido', 'recurso_negado', 'nulidade'].includes(ev) ? 4 : 5);
    const GRP = ['Entrada e publicação', 'Exame, exigências e oposição', 'Decisão favorável', 'Decisão desfavorável / extinção', 'Recursos e nulidade', 'Petições e outros'];
    const gcol = [t.series[0], t.series[3], t.series[2], t.series[7], t.series[6], t.deemph];
    const inFlow = new Map(); edges.forEach(e => inFlow.set(e.j, (inFlow.get(e.j) || 0) + e.n));
    const nodes = tr.nos.map((n, k) => ({ id: String(k), name: n.id, value: inFlow.get(k) || 0, descricao: n.descricao, category: grp(n.evento),
      symbolSize: used.has(k) ? 10 + 34 * Math.sqrt((inFlow.get(k) || 1) / maxN) : 0, label: { show: used.has(k), fontSize: 10.5, color: t.ink }, itemStyle: { opacity: used.has(k) ? 1 : 0 } }));
    const links = edges.map(e => ({ source: String(e.i), target: String(e.j), value: e.n, lineStyle: { width: 1 + 9 * Math.sqrt(e.n / maxN), curveness: 0.25, opacity: 0.45, color: gcol[nodes[e.i].category] } }));
    setText('transicoes-sub', `${fmt.int(used.size)} despachos e ${fmt.int(links.length)} transições com ${fmt.int(minW)}+ ocorrências em pedidos depositados de ${de} a ${ate}`);
    return { option: { legend: { data: GRP, type: 'scroll' }, grid: undefined,
      tooltip: { formatter: p => (p.dataType === 'edge' ? `<b>${nodes[+p.data.source].name}</b> → <b>${nodes[+p.data.target].name}</b><br>${fmt.int(p.data.value)} transições` : `<b>${p.data.name}</b> ${p.data.descricao ? '· ' + p.data.descricao : ''}<br>${fmt.int(p.data.value)} chegadas · ${GRP[p.data.category]}`) },
      series: [{ type: 'graph', layout: 'force', roam: true, draggable: true, data: nodes, links, categories: GRP.map((n, i) => ({ name: n, itemStyle: { color: gcol[i] } })),
        force: { repulsion: 420, gravity: 0.12, edgeLength: [40, 160], friction: 0.2 }, edgeSymbol: ['none', 'arrow'], edgeSymbolSize: 7,
        label: { show: true, position: 'right', formatter: p => p.data.name }, emphasis: { focus: 'adjacency', lineStyle: { opacity: 0.9, width: 4 } }, lineStyle: { color: 'source' },
        animationDurationUpdate: reducedMotion ? 0 : 800 }] },
      table: tableRows(['De', 'Para', 'Transições', 'Descrição (de)', 'Descrição (para)'], edges.sort((a, b) => b.n - a.n).slice(0, 300).map(e => [tr.nos[e.i].id, tr.nos[e.j].id, e.n, tr.nos[e.i].descricao, tr.nos[e.j].descricao])) };
  }, { state: { de: anos[0], ate: last(anos), min: 50 } });

  register('race', ({ t, state }) => {
    const frames = d.depositantes.corrida_residentes; const fi = state.i ?? frames.length - 1; const frame = frames[fi]; const cc = CAT_COLOR(t);
    return { option: { grid: { left: 8, right: 70, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: 'item', formatter: p => `<b>${p.name}</b><br>${fmt.int(p.value)} pedidos acumulados até ${frame.ano}` },
      xAxis: ax.val(t, { position: 'top' }),
      yAxis: { type: 'category', inverse: true, max: 11, data: frame.itens.map(i => i.nome), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.ink2, width: 230, overflow: 'truncate', fontSize: 12 }, animationDuration: 300, animationDurationUpdate: 300 },
      series: [{ type: 'bar', realtimeSort: true, data: frame.itens.map(i => ({ value: i.valor, itemStyle: { color: cc[i.categoria] || t.deemph, borderRadius: [0, 4, 4, 0] } })), barMaxWidth: 24, label: { show: true, position: 'right', valueAnimation: true, color: t.ink2, fontSize: 12, formatter: p => fmt.int(p.value) } }],
      graphic: [{ type: 'text', right: 28, bottom: 18, style: { text: String(frame.ano), font: '800 48px Inter, system-ui, sans-serif', fill: t.grid } }],
      animationDuration: 0, animationDurationUpdate: reducedMotion ? 0 : 950, animationEasing: 'linear', animationEasingUpdate: 'linear' },
      table: tableRows(['Depositante', 'Categoria', `Pedidos acumulados até ${frame.ano}`], frame.itens.map(i => [i.nome, CAT_LABEL[i.categoria] || i.categoria, i.valor])),
      after: (chart, r) => {
        if (r.player) return; r.player = { timer: null };
        const btn = r.card.querySelector('.btn-play'); if (!btn) return;
        const stop = () => { clearInterval(r.player.timer); r.player.timer = null; btn.textContent = '▶ Reproduzir'; };
        btn.addEventListener('click', () => {
          if (r.player.timer) return stop();
          let i = (r.state.i == null || r.state.i >= frames.length - 1) ? 0 : r.state.i + 1; btn.textContent = '⏸ Pausar';
          const step = () => { r.state.i = i; rerender('race', {}); if (++i >= frames.length) stop(); };
          step(); r.player.timer = setInterval(step, reducedMotion ? 400 : 1100);
        });
      } };
  }, { state: {} });

  register('top-dep', ({ t, state }) => {
    const list = d.depositantes[state.view || 'top_geral'] || []; const rows = list.slice(0, 15);
    return { option: { ...hbarOption(t, rows.map(r => r.nome), rows.map(r => r.total), { width: 150 }), tooltip: { trigger: 'item', formatter: p => { const r = rows[p.dataIndex]; return `<b>${r.nome}</b><br>${r.pais_nome} · ${CAT_LABEL[r.categoria] || r.categoria}<br>${fmt.int(r.total)} pedidos · ${fmt.int(r.concedidos)} ${termo === 'registro' ? 'registrados' : 'concedidos'}<br>${fmt.int(r.ultimo_ano)} em ${ano}`; } } },
      table: tableRows(['Depositante', 'País', 'Categoria', 'Pedidos', termo === 'registro' ? 'Registrados' : 'Concedidos', `Em ${ano}`], list.map(r => [r.nome, r.pais_nome, CAT_LABEL[r.categoria] || r.categoria, r.total, r.concedidos, r.ultimo_ano])) };
  }, { state: { view: 'top_geral' } });

  register('paises-bar', ({ t }) => {
    const ps = d.paises.paises; const top = ps.filter(p => p.pais !== 'OUTROS').slice(0, 12); const outros = ps.find(p => p.pais === 'OUTROS'); const rows = [...top, ...(outros ? [outros] : [])];
    return { option: { ...hbarOption(t, rows.map(r => r.nome), rows.map(r => r.total), { width: 150 }), series: [{ type: 'bar', data: rows.map(r => ({ value: r.total, itemStyle: { color: r.pais === 'BR' ? t.series[0] : t.deemph, borderRadius: [0, 4, 4, 0] } })), barMaxWidth: 22, label: { show: true, position: 'right', color: t.ink2, fontSize: 12, formatter: p => fmt.int(p.value) } }],
      tooltip: { trigger: 'item', formatter: p => { const r = rows[p.dataIndex]; return `<b>${r.nome}</b><br>${fmt.int(r.total)} pedidos · ${fmt.int(r.concedidos)} ${termo === 'registro' ? 'registrados' : 'concedidos'}`; } } },
      table: tableRows(['País', 'Pedidos', termo === 'registro' ? 'Registrados' : 'Concedidos'], ps.map(r => [r.nome, r.total, r.concedidos])) };
  });
  register('paises-linhas', ({ t }) => {
    const top = d.paises.paises.filter(p => p.pais !== 'OUTROS' && p.pais !== 'BR').slice(0, 6);
    return { option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t), series: top.map((p, i) => mk.line(p.nome, p.serie, t.series[i])) },
      table: tableYears(anos, Object.fromEntries(top.map(p => [p.nome, p.serie]))) };
  });

  if (d.geo && d.uf) {
    const ufByCode = Object.fromEntries(d.uf.ufs.map(u => [String(u.codigo_ibge), u]));
    d.geo.features.forEach(f => { const u = ufByCode[String(f.properties.codarea)]; f.properties.name = u ? u.uf : f.properties.codarea; });
    echarts.registerMap('BR', d.geo);
    const METRIC = { total: `Pedidos ${anos[0]}–${last(anos)}`, concedidos: termo === 'registro' ? 'Registros' : 'Patentes concedidas', vigentes: 'Vigentes', ultimo_ano: `Pedidos em ${ano}` };
    register('mapa', ({ t, state }) => {
      const m = state.view || 'total'; const ufs = d.uf.ufs; const vals = ufs.map(u => u[m]);
      return { option: {
        tooltip: { trigger: 'item', formatter: p => { const u = ufs.find(x => x.uf === p.name); if (!u) return p.name; const top = (u.top_campos || u.top || []).map(c => c.nome).join(' · '); return `<b>${u.nome}</b> (${u.regiao})<br>${fmt.int(u.total)} pedidos · ${fmt.int(u.concedidos)} ${termo === 'registro' ? 'registrados' : 'concedidos'} · ${fmt.int(u.vigentes)} vigentes<br>${fmt.int(u.ultimo_ano)} em ${ano}${top ? `<br><span style="color:${t.muted}">${top}</span>` : ''}`; } },
        visualMap: { type: 'continuous', min: 0, max: Math.max(...vals), inRange: { color: t.seq }, orient: 'horizontal', left: 'center', bottom: 0, itemWidth: 12, itemHeight: 160, text: ['mais', 'menos'], textStyle: { color: t.ink2, fontSize: 12 }, formatter: v => fmt.compact(v) },
        series: [{ type: 'map', map: 'BR', name: METRIC[m], roam: false, aspectScale: 0.92, layoutCenter: ['50%', '47%'], layoutSize: '92%', data: ufs.map((u, i) => ({ name: u.uf, value: vals[i] })), itemStyle: { borderColor: t.surface, borderWidth: 1 }, label: { show: true, color: t.ink, fontSize: 10, formatter: p => p.name }, emphasis: { label: { show: true, color: t.ink, fontWeight: 700 }, itemStyle: { borderColor: t.ink, borderWidth: 1.5 } }, select: { disabled: true } }] },
        table: tableRows(['UF', 'Região', 'Pedidos', termo === 'registro' ? 'Registrados' : 'Concedidos', 'Vigentes', `Em ${ano}`], ufs.map(u => [`${u.uf} – ${u.nome}`, u.regiao, u.total, u.concedidos, u.vigentes, u.ultimo_ano])) };
    }, { state: { view: 'total' } });
    register('regioes', ({ t }) => ({ option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { total: true }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t), series: d.uf.regioes.map((r, i) => mk.area(r.regiao, r.serie, t.series[i])) }, table: tableYears(anos, Object.fromEntries(d.uf.regioes.map(r => [r.regiao, r.serie]))) }));
    register('uf-ranking', ({ t }) => { const rows = [...d.uf.ufs].sort((a, b) => b.total - a.total); return { option: hbarOption(t, rows.map(r => r.nome), rows.map(r => r.total), { width: 150 }), table: tableRows(['UF', 'Pedidos', termo === 'registro' ? 'Registrados' : 'Concedidos', 'Vigentes'], rows.map(r => [r.nome, r.total, r.concedidos, r.vigentes])) }; });
  }
  if (d.municipios) register('municipios', ({ t }) => {
    const rows = d.municipios.municipios.slice(0, 20);
    return { option: { ...hbarOption(t, rows.map(r => `${r.cidade} (${r.uf})`), rows.map(r => r.total), { width: 170 }), tooltip: { trigger: 'item', formatter: p => { const r = rows[p.dataIndex]; return `<b>${r.cidade} (${r.uf})</b><br>${fmt.int(r.total)} pedidos · ${fmt.int(r.concedidos)} ${termo === 'registro' ? 'registrados' : 'concedidos'}<br>${fmt.int(r.ultimo_ano)} em ${ano}`; } } },
      table: tableRows(['Município', 'UF', 'Pedidos', termo === 'registro' ? 'Registrados' : 'Concedidos', `Em ${ano}`], d.municipios.municipios.map(r => [r.cidade, r.uf, r.total, r.concedidos, r.ultimo_ano])) };
  });
  if (d.genero && d.genero.share_f_depositantes) register('gen-dep', ({ t }) => ({ option: { tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.pct }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t, { formatter: v => v + '%', min: 0 }),
    series: [mk.line('Depositantes pessoa física mulheres (%)', d.genero.share_f_depositantes, t.series[0], { areaStyle: { color: t.series[0], opacity: .12 } })] },
    table: tableYears(anos, { 'Mulheres (%)': d.genero.share_f_depositantes, 'Mulheres (n)': d.genero.depositantes_pf.F, 'Homens (n)': d.genero.depositantes_pf.M }) }));
}

/* ---------- animações e navegação ---------- */
export function reveals() {
  if (reducedMotion || !window.gsap || !window.ScrollTrigger) return;
  gsap.registerPlugin(ScrollTrigger);
  gsap.utils.toArray('.reveal').forEach(el => gsap.from(el, { opacity: 0, y: 26, duration: .8, ease: 'power2.out', scrollTrigger: { trigger: el, start: 'top 90%', once: true } }));
  gsap.from('.hero h1', { opacity: 0, y: 24, duration: .9, ease: 'power3.out' });
  gsap.from('.hero .lead, .hero .cta', { opacity: 0, y: 18, duration: .9, delay: .15, ease: 'power3.out', stagger: .1 });
  gsap.from('.hero-stat', { opacity: 0, y: 18, duration: .8, delay: .35, stagger: .08, ease: 'power3.out' });
}
export function navSpy() {
  const links = [...document.querySelectorAll('nav.primary a[href^="#"]')];
  const io = new IntersectionObserver(entries => { entries.forEach(e => { if (e.isIntersecting) links.forEach(l => l.classList.toggle('active', l.getAttribute('href') === '#' + e.target.id)); }); }, { rootMargin: '-40% 0px -55% 0px' });
  document.querySelectorAll('section.block[id]').forEach(s => io.observe(s));
}
export async function loadJson(base, files) {
  const out = {};
  await Promise.all(files.map(async f => { const r = await fetch(base + f + '.json'); if (!r.ok) throw new Error(f); out[f] = await r.json(); }));
  return out;
}
export function loadError(err) {
  console.error(err);
  const row = document.getElementById('kpis'); if (row) row.innerHTML = `<div class="tile"><div class="label">Não foi possível carregar os dados</div><div class="delta">${err.message}. Rode <code>uv run badepi gold</code> para gerar os JSON em docs/data/.</div></div>`;
}

/* ---------- cabeçalho e rodapé comuns ---------- */
export const PAGES = [
  { slug: 'home', label: 'Início', href: './' }, { slug: 'patentes', label: 'Patentes', href: 'patentes.html' }, { slug: 'marcas', label: 'Marcas', href: 'marcas.html' },
  { slug: 'desenhos', label: 'Desenhos', href: 'desenhos.html' }, { slug: 'indicacoes', label: 'Indicações geográficas', href: 'indicacoes.html' },
  { slug: 'programas', label: 'Programas', href: 'programas.html' }, { slug: 'guia', label: 'Como usar', href: 'como-usar.html' },
];
export function chrome({ active, sub = 'v12', sections = [] }) {
  const header = document.getElementById('topbar');
  if (header) header.innerHTML = `<div class="container"><a class="brand" href="./">BADEPI<small>${sub}</small></a>
    <nav class="primary" aria-label="Ativos">${PAGES.map(p => `<a href="${p.href}" class="${p.slug === active ? 'current' : ''}">${p.label}</a>`).join('')}</nav>
    <button class="icon-btn" id="theme-toggle" aria-label="Alternar tema">🌙 <span>Escuro</span></button></div>`;
  const sn = document.getElementById('subnav');
  if (sn && sections.length) sn.innerHTML = sections.map(([id, label]) => `<a href="#${id}">${label}</a>`).join('');
  const footer = document.getElementById('site-footer');
  if (footer) footer.innerHTML = `<div class="container"><div>Dados: <a href="https://www.gov.br/inpi/pt-br/inpi-data/dados-e-series-temporais/badepi" target="_blank" rel="noopener">BADEPI — INPI</a> · Malha: IBGE · Código: MIT · <a href="https://github.com/Jaimenms/badepi-dashboard" target="_blank" rel="noopener">GitHub</a></div><div id="gerado"></div>
    <div class="aviso-rodape">Projeto independente, sem vínculo com o INPI. Os números são derivados dos microdados do BADEPI por regras próprias e servem para ilustrar a base e observar tendências; estatísticas oficiais devem ser obtidas diretamente com o INPI (Anuário Estatístico e Indicadores de PI). Nosso agradecimento à equipe de tecnologia e estatística do INPI, que constrói e publica o BADEPI. <a href="./#aviso">Leia o aviso completo</a>.</div></div>`;
}
export function wireControls(id) {
  // ranges extras (data-key) dentro do card já são tratados em viz.js; aqui só sincroniza rótulos de/até
  const card = document.querySelector(`[data-chart="${id}"]`); if (!card) return;
  const de = card.querySelector('input[data-key="de"]'), ate = card.querySelector('input[data-key="ate"]');
  if (de && ate) { de.addEventListener('input', () => { if (+de.value > +ate.value) { ate.value = de.value; ate.dispatchEvent(new Event('input')); } }); ate.addEventListener('input', () => { if (+ate.value < +de.value) { de.value = ate.value; de.dispatchEvent(new Event('input')); } }); }
}
