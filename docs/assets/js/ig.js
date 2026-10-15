/* ig.js — dashboard de indicações geográficas + explorador. */
import { initTheme, register, mountAll, fmt, ax, mk, tableYears, tableRows } from './viz.js';
import { chrome, heroCanvas, heroStats, kpiTiles, footerInfo, mountCommon, reveals, navSpy, loadJson, loadError, tip, X, pctOf } from './shared.js';

const FILES = ['resumo', 'serie_depositos', 'serie_decisoes', 'situacao_coorte', 'tempo_registro', 'uf', 'paises', 'wipo', 'lista', 'funil', 'ciclo_vida'];
chrome({ active: 'indicacoes', sub: 'v12 · indicações geográficas', sections: [['panorama', 'Panorama'], ['jornada', 'Jornada'], ['onde', 'Onde'], ['explorador', 'Explorador'], ['metodo', 'Método']] });
initTheme(document.getElementById('theme-toggle'));
const esc = s => String(s ?? '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

function kpis(d) {
  const k = d.resumo.kpis, sd = d.serie_depositos, dc = d.serie_decisoes, ano = d.resumo.ano_ultimo;
  kpiTiles([
    { label: `Pedidos em ${ano}`, value: k.pedidos_ultimo_ano, delta: k.pedidos_variacao_pct, spark: sd.total },
    { label: `Registros em ${ano}`, value: k.concessoes_ultimo_ano, delta: k.concessoes_variacao_pct, spark: dc.concessoes },
    { label: 'IGs registradas', value: k.registradas, sub: `${fmt.int(k.estrangeiras_registradas)} estrangeiras reconhecidas no Brasil` },
    { label: 'Tempo mediano até o registro', value: k.tempo_registro_mediana_recente, decimals: 1, suffix: ' anos', sub: 'registros do último ano com dados', spark: d.tempo_registro.por_ano.map(x => x.mediana) },
    { label: 'Pedidos registrados', value: k.share_concedidos, decimals: 1, suffix: '%', sub: 'de todos os pedidos desde 2000' },
    { label: 'Residentes', value: k.share_residentes_total, decimals: 1, suffix: '%', sub: 'dos pedidos, 2000–2025' },
  ]);
}
function charts(d) {
  const anos = d.serie_depositos.anos; const s = d.serie_depositos;
  mountCommon(d, { termo: 'registro' });
  register('dep-tipo', ({ t }) => ({ option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { total: true }) }, xAxis: ax.time(t, anos, X.deposito, { boundaryGap: true }), yAxis: ax.val(t, { minInterval: 1, formatter: v => v }), series: [mk.stackBar('Indicação de procedência', s.tipo.IP, t.series[0], t), mk.stackBar('Denominação de origem', s.tipo.DO, t.series[1], t)] }, table: tableYears(anos, { 'Indicação de procedência': s.tipo.IP, 'Denominação de origem': s.tipo.DO }) }));
  register('dep-wipo', ({ t }) => { const names = Object.keys(s.wipo); return { option: { legend: { type: 'scroll' }, grid: { top: 48 }, tooltip: { trigger: 'axis', formatter: p => tip(p, { total: true }) }, xAxis: ax.time(t, anos, X.deposito, { boundaryGap: true }), yAxis: ax.val(t, { minInterval: 1, formatter: v => v }), series: names.map((n, i) => mk.stackBar(n, s.wipo[n], t.series[i], t)) }, table: tableYears(anos, s.wipo) }; });
  register('wipo-bar', ({ t }) => { const rows = d.wipo.categorias;
    return { option: { legend: {}, grid: { left: 8, right: 40, top: 32, bottom: 6, containLabel: true }, tooltip: { trigger: 'axis', formatter: p => tip(p) }, xAxis: ax.val(t, { formatter: v => v }), yAxis: ax.catY(t, rows.map(r => r.classificacao_wipo), { width: 190 }),
      series: [{ name: 'Pedidos', type: 'bar', data: rows.map(r => r.total), itemStyle: { color: t.deemph, borderRadius: [0, 4, 4, 0] }, barMaxWidth: 16 }, { name: 'Registradas', type: 'bar', data: rows.map(r => r.registradas), itemStyle: { color: t.series[0], borderRadius: [0, 4, 4, 0] }, barMaxWidth: 16, label: { show: true, position: 'right', color: t.ink2, fontSize: 12 } }] },
      table: tableRows(['Categoria', 'Pedidos', 'Registradas'], rows.map(r => [r.classificacao_wipo, r.total, r.registradas])) }; });
  explorer(d);
}
function explorer(d) {
  const itens = d.lista.itens; const ufs = [...new Set(itens.map(i => i.uf_origem).filter(Boolean))].sort(); const wipos = [...new Set(itens.map(i => i.classificacao_wipo).filter(Boolean))].sort();
  document.getElementById('ex-uf').innerHTML += ufs.map(u => `<option value="${u}">${u}</option>`).join('');
  document.getElementById('ex-wipo').innerHTML += wipos.map(u => `<option value="${esc(u)}">${esc(u)}</option>`).join('');
  const tag = s => s === 'Concedida' ? '<span class="tag ok">Registrada</span>' : s === 'Em andamento' ? '<span class="tag warn">Em andamento</span>' : `<span class="tag bad">${esc(s)}</span>`;
  const norm = v => String(v ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const render = () => {
    const q = norm(document.getElementById('ex-q').value), tipo = document.getElementById('ex-tipo').value, sit = document.getElementById('ex-sit').value, uf = document.getElementById('ex-uf').value, wipo = document.getElementById('ex-wipo').value;
    const rows = itens.filter(i => (!tipo || i.tipo_atual === tipo) && (!sit || i.situacao === sit) && (!uf || i.uf_origem === uf) && (!wipo || i.classificacao_wipo === wipo)
      && (!q || norm([i.nome_ig, i.classe_produto_servico, i.cidade, i.nome, i.uf_nome, i.pais_nome].join(' ')).includes(q)));
    document.getElementById('ex-count').textContent = `${rows.length} de ${itens.length} pedidos`;
    document.getElementById('ex-table').innerHTML = `<table><thead><tr><th>Indicação geográfica</th><th>Espécie</th><th>Categoria</th><th>UF / país</th><th>Depositante</th><th>Ano</th><th>Situação</th><th>Registro</th></tr></thead><tbody>${rows.map(i => `<tr><td><b>${esc(i.nome_ig)}</b></td><td>${esc(i.tipo_atual)}</td><td>${esc(i.classificacao_wipo)}</td><td>${esc(i.uf_origem || i.pais_nome)}</td><td>${esc(i.nome)}${i.cidade ? ` <span style="color:var(--muted)">· ${esc(i.cidade)}</span>` : ''}</td><td class="num">${i.ano}</td><td>${tag(i.situacao)}</td><td class="num">${i.dt_concessao ? new Date(i.dt_concessao + 'T12:00:00').toLocaleDateString('pt-BR') : '–'}</td></tr>`).join('')}</tbody></table>`;
  };
  ['ex-q', 'ex-tipo', 'ex-sit', 'ex-uf', 'ex-wipo'].forEach(id => document.getElementById(id).addEventListener('input', render));
  render();
}
Promise.all([loadJson('./data/indicacao_geografica/', FILES), fetch('./data/geo/br_uf.json').then(r => r.json())]).then(([d, geo]) => {
  d.geo = geo; heroStats(d.resumo.kpis); footerInfo(d.resumo); heroCanvas(); kpis(d); charts(d); mountAll({ d }); reveals(); navSpy();
}).catch(loadError);
