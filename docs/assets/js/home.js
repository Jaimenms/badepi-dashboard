/* home.js — página inicial: índice dos ativos e comparativos. */
import { initTheme, register, mountAll, fmt, ax, mk, tableYears, tableRows, countUp, countUpOnView } from './viz.js';
import { chrome, heroCanvas, reveals, navSpy, loadError, tip, X, pctOf, setText } from './shared.js';

chrome({ active: 'home', sub: 'v12', sections: [['ativos', 'Ativos'], ['comparativo', 'Comparativo'], ['sobre', 'Sobre']] });
initTheme(document.getElementById('theme-toggle'));
const ICON = { patentes: '⚙️', marcas: '™️', desenho_industrial: '🎨', indicacao_geografica: '📍' };
const COLOR = { patentes: 'var(--s1)', marcas: 'var(--s2)', desenho_industrial: 'var(--s3)', indicacao_geografica: 'var(--s7)' };
const DESC = { patentes: 'Invenções e modelos de utilidade: 702 mil pedidos, tempo de concessão, campos tecnológicos, inventores.',
  marcas: 'O maior volume do INPI: 5 milhões de pedidos, classes de Nice, oposições, registros vigentes.',
  desenho_industrial: 'A forma dos produtos: 158 mil pedidos, registro em meses, prorrogações, classes de Locarno.',
  indicacao_geografica: 'Territórios reconhecidos: 254 pedidos, 157 IGs registradas, explorador completo.' };

function cards(c) {
  const host = document.getElementById('assets');
  host.innerHTML = c.ativos.map(a => { const k = a.kpis; const termo = a.termo_concessao === 'registro' ? 'registrados' : 'concedidas';
    return `<a class="asset-card reveal" href="${a.pagina}" style="--c:${COLOR[a.slug]}"><div class="icon">${ICON[a.slug]}</div><h3>${a.label}</h3>
      <div class="num"><span data-count="${k.pedidos_total}">0</span><small>pedidos desde 2000</small></div>
      <p style="margin:0;color:var(--ink-2);font-size:13.5px">${DESC[a.slug]}</p>
      <div class="facts"><span>Em 2025 <b>${fmt.int(k.pedidos_ultimo_ano)}</b> <span class="${(k.pedidos_variacao_pct ?? 0) >= 0 ? 'up' : 'down'}" style="color:${(k.pedidos_variacao_pct ?? 0) >= 0 ? 'var(--good)' : 'var(--s8)'}">${fmt.signed(k.pedidos_variacao_pct)}</span></span><span>${termo[0].toUpperCase() + termo.slice(1)} <b>${fmt.int(k.concessoes_total)}</b></span><span>Vigentes <b>${fmt.int(k.vigentes)}</b></span><span>Residentes <b>${fmt.pct(k.share_residentes_total)}</b></span><span>Tempo mediano <b>${a.tempo_mediana_recente != null ? fmt.anos(a.tempo_mediana_recente) : '–'}</b></span><span>Decididos a favor <b>${fmt.pct(k.share_concedidos)}</b></span></div>
      <div class="go">Abrir painel →</div></a>`; }).join('');
  countUpOnView(host);
  const tot = key => c.ativos.reduce((s, a) => s + (a.kpis[key] || 0), 0);
  document.getElementById('h-pedidos').dataset.count = tot('pedidos_total'); document.getElementById('h-concedidos').dataset.count = tot('concessoes_total');
  document.getElementById('h-vigentes').dataset.count = tot('vigentes'); document.getElementById('h-ultimo').dataset.count = tot('pedidos_ultimo_ano');
  countUpOnView(document.querySelector('.hero'));
  setText('gerado', `BADEPI v12 · comparativo gerado em ${new Date(c.gerado_em).toLocaleDateString('pt-BR')}`);
}
function charts(c) {
  const anos = c.anos; const A = c.ativos;
  register('cmp-indice', ({ t }) => ({ option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: v => fmt.dec1(v) }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t, { formatter: v => v, type: 'log', min: 50 }),
    series: A.map((a, i) => mk.line(a.label, a.serie_indice, t.series[i])) }, table: tableYears(anos, Object.fromEntries(A.map(a => [a.label + ' (índice)', a.serie_indice]))) }));
  register('cmp-residentes', ({ t }) => ({ option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.pct }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t, { formatter: v => v + '%', min: 0, max: 100 }),
    series: A.map((a, i) => mk.line(a.label, a.share_residentes_serie, t.series[i])) }, table: tableYears(anos, Object.fromEntries(A.map(a => [a.label + ' (%)', a.share_residentes_serie]))) }));
  register('cmp-tempo', ({ t }) => ({ option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.anos }) }, xAxis: ax.time(t, anos, 'Ano de publicação da concessão ou do registro na RPI'), yAxis: ax.val(t, { formatter: v => v + ' a', min: 0 }),
    series: A.map((a, i) => mk.line(a.label, anos.map(y => a.tempo_mediana_por_ano[String(y)] ?? null), t.series[i], { connectNulls: true })) }, table: tableYears(anos, Object.fromEntries(A.map(a => [a.label + ' (anos)', anos.map(y => a.tempo_mediana_por_ano[String(y)] ?? null)]))) }));
  const GROUPS = [['Concedida/registrada e vigente', ['Concedida (vigente)']], ['Concedida, hoje extinta ou expirada', ['Concedida (prazo expirado)', 'Extinta', 'Anulada']], ['Deferida', ['Deferida']], ['Em andamento', ['Em andamento']], ['Indeferida', ['Indeferida']], ['Arquivada', ['Arquivada']], ['Retirada', ['Retirada']], ['Numeração anulada', ['Numeração anulada']]];
  register('cmp-situacao', ({ t }) => { const vals = A.map(a => { const n = Object.values(a.situacao_total).reduce((x, y) => x + y, 0); return GROUPS.map(([, keys]) => pctOf(keys.reduce((s, k) => s + (a.situacao_total[k] || 0), 0), n)); });
    return { option: { legend: { type: 'scroll' }, grid: { left: 24, right: 16, top: 52, bottom: 6, containLabel: true }, tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.pct }) }, xAxis: ax.val(t, { formatter: v => v + '%', max: 100 }), yAxis: ax.catY(t, A.map(a => a.label), { width: 220, fontSize: 12 }),
      series: GROUPS.map(([name], k) => ({ name, type: 'bar', stack: 'total', data: vals.map(v => v[k]), itemStyle: { color: t.series[k], borderColor: t.surface, borderWidth: 1 }, barMaxWidth: 34 })) },
      table: tableRows(['Ativo', ...GROUPS.map(g => g[0] + ' (%)')], A.map((a, i) => [a.label, ...vals[i]])) }; });
  register('cmp-funil', ({ t }) => { const ET = [['publicados', 'Publicados'], ['decididos', 'Decididos no mérito'], ['concedidos', 'Concedidos / registrados'], ['vigentes', 'Vigentes hoje']];
    return { option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.pct }) }, xAxis: ax.cat(t, ET.map(e => e[1]), { boundaryGap: true }), yAxis: ax.val(t, { formatter: v => v + '%', max: 100 }),
      series: A.map((a, i) => mk.bar(a.label, ET.map(([k]) => (a.funil_total[k] == null ? null : pctOf(a.funil_total[k], a.funil_total.depositados))), t.series[i], t, { barGap: '10%' })) },
      table: tableRows(['Ativo', ...ET.map(e => e[1] + ' (%)')], A.map(a => [a.label, ...ET.map(([k]) => (a.funil_total[k] == null ? null : pctOf(a.funil_total[k], a.funil_total.depositados)))])) }; });
  const host = document.getElementById('cmp-mini');
  host.innerHTML = A.map(a => `<article class="card col-3 keep reveal" data-chart="mini-${a.slug}"><header><div class="titles"><h3 style="font-size:14px">${a.label}</h3><p class="sub">${fmt.int(a.kpis.pedidos_total)} pedidos</p></div><div class="actions"><button class="icon-btn btn-table">Tabela</button></div></header><div class="chart" style="height:170px"></div><div class="table-view hidden"></div></article>`).join('');
  A.forEach((a, i) => register(`mini-${a.slug}`, ({ t }) => ({ option: { grid: { left: 4, right: 22, top: 10, bottom: 4, containLabel: true }, tooltip: { trigger: 'axis', formatter: p => tip(p) }, xAxis: ax.time(t, anos, 'Ano de depósito', { axisLabel: { showMinLabel: true, showMaxLabel: true, interval: anos.length - 2 } }), yAxis: ax.val(t, { splitNumber: 3 }), series: [mk.line('Pedidos', a.serie_total, t.series[i], { areaStyle: { color: t.series[i], opacity: .12 } })] }, table: tableYears(anos, { Pedidos: a.serie_total }) })));
}
fetch('./data/comparativo.json').then(r => r.json()).then(c => { heroCanvas(); cards(c); charts(c); mountAll({ c }); reveals(); navSpy(); }).catch(loadError);
