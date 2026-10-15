/* desenhos.js — dashboard de desenho industrial. */
import { initTheme, register, mountAll, fmt, ax, mk, tableYears, tableRows, countUpOnView } from './viz.js';
import { chrome, heroCanvas, heroStats, kpiTiles, setText, footerInfo, mountCommon, reveals, navSpy, loadJson, loadError, wireControls, tip, hbarOption, hbar2Option, X, pctOf } from './shared.js';

const FILES = ['resumo', 'serie_depositos', 'serie_decisoes', 'situacao_coorte', 'tempo_registro', 'classes', 'uf', 'paises', 'depositantes', 'municipios', 'genero', 'funil', 'backlog', 'ciclo_vida', 'transicoes'];
chrome({ active: 'desenhos', sub: 'v12 · desenhos industriais', sections: [['panorama', 'Panorama'], ['jornada', 'Jornada'], ['quem', 'Quem'], ['onde', 'Onde'], ['classes', 'Classes'], ['metodo', 'Método']] });
initTheme(document.getElementById('theme-toggle'));

function kpis(d) {
  const k = d.resumo.kpis, sd = d.serie_depositos, dc = d.serie_decisoes, ano = d.resumo.ano_ultimo;
  kpiTiles([
    { label: `Pedidos em ${ano}`, value: k.pedidos_ultimo_ano, delta: k.pedidos_variacao_pct, spark: sd.total },
    { label: `Registros em ${ano}`, value: k.concessoes_ultimo_ano, delta: k.concessoes_variacao_pct, spark: dc.concessoes },
    { label: 'Registros vigentes', value: k.vigentes, sub: 'registrados, não extintos, até 25 anos', spark: d.funil.vigentes },
    { label: 'Tempo mediano até o registro', value: k.tempo_concessao_mediana_ultimo_ano, decimals: 1, suffix: ' anos', sub: `era ${fmt.dec1(k.tempo_concessao_pior_mediana)} em ${k.tempo_concessao_pior_ano}`, spark: d.tempo_registro.por_ano.map(x => x.mediana) },
    { label: `Residentes em ${ano}`, value: k.share_residentes_ultimo_ano, decimals: 1, suffix: '%', sub: `média 2000–${ano}: ${fmt.pct(k.share_residentes_total)}`, spark: sd.residente.map((v, i) => pctOf(v, sd.total[i])) },
    { label: `Via Haia em ${ano}`, value: k.share_haia_ultimo_ano, decimals: 1, suffix: '%', sub: 'designações do Brasil pelo Acordo', spark: sd.via['Via Haia'].map((v, i) => pctOf(v, sd.total[i])) },
    { label: 'Pessoas físicas (residentes)', value: k.share_pf_residentes, decimals: 1, suffix: '%', sub: 'parcela dos pedidos de residentes' },
  ]);
  document.getElementById('big-tempo').dataset.count = k.tempo_concessao_mediana_ultimo_ano; setText('big-tempo-ano', ano);
  setText('big-tempo-sub', `Em ${k.tempo_concessao_pior_ano} a mediana era de ${fmt.dec1(k.tempo_concessao_pior_mediana)} anos.`);
  document.getElementById('big-vigentes').dataset.count = k.vigentes; setText('big-vigentes-sub', `${fmt.int(k.vigentes_residentes)} de titulares residentes (${fmt.pct(pctOf(k.vigentes_residentes, k.vigentes))}).`);
  document.getElementById('big-prorr').dataset.count = k.registros_prorrogados; setText('big-prorr-sub', `${fmt.pct(pctOf(k.registros_prorrogados, k.concessoes_total))} dos ${fmt.int(k.concessoes_total)} registros concedidos desde 2000.`);
  document.getElementById('big-pf').dataset.count = k.share_pf_residentes; setText('big-pf-sub', 'O desenho industrial é o ativo mais usado por inventores individuais e pequenos negócios.');
  countUpOnView(document.getElementById('jornada'));
}
function charts(d) {
  const anos = d.serie_depositos.anos; const s = d.serie_depositos;
  mountCommon(d, { termo: 'registro', eventos: [['deposito', 'Depósitos notificados'], ['exigencia', 'Exigências'], ['concessao', 'Registros'], ['prorrogacao', 'Prorrogações'], ['extincao', 'Extinções'], ['nulidade', 'Nulidade (processos)']] });
  register('dep-haia', ({ t }) => { const share = s.via['Via Haia'].map((v, i) => pctOf(v, s.total[i]));
    return { option: { tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.pct }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t, { formatter: v => v + '%', min: 0 }), series: [mk.line('Via Haia (%)', share, t.series[0], { areaStyle: { color: t.series[0], opacity: .12 } })] }, table: tableYears(anos, { 'Via Haia': s.via['Via Haia'], 'Via direta': s.via.Direta, 'Divididos': s.via['Dividido (provável)'], '% Haia': share }) }; });
  register('dep-autores', ({ t }) => ({ option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.dec2 }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t, { formatter: v => fmt.dec1(v), min: 0 }), series: [mk.line('Autores por pedido', s.media_autores, t.series[0]), mk.line('Depositantes por pedido', s.media_depositantes, t.series[1])] }, table: tableYears(anos, { 'Autores por pedido': s.media_autores, 'Depositantes por pedido': s.media_depositantes }) }));
  const cls = d.classes.classes;
  register('classes-bar', ({ t }) => { const rows = [...cls].sort((a, b) => b.total - a.total);
    return { option: hbar2Option(t, rows.map(r => ({ name: `${r.classe} · ${r.nome}`, value: r.total })), { width: 230 }), table: tableRows(['Classe', 'Nome', 'Pedidos', 'Registrados', 'Residentes'], rows.map(r => [r.classe, r.nome, r.total, r.registrados, r.residentes])) }; });
  register('classes-res', ({ t }) => { const rows = [...cls].sort((a, b) => b.total - a.total).slice(0, 12).map(r => ({ ...r, share: pctOf(r.residentes, r.total) })).sort((a, b) => b.share - a.share);
    return { option: hbarOption(t, rows.map(r => r.nome), rows.map(r => r.share), { fmtv: fmt.pct, width: 170, max: 100 }), table: tableRows(['Classe', 'Residentes (%)', 'Pedidos'], rows.map(r => [r.nome, r.share, r.total])) }; });
  register('classes-linhas', ({ t }) => { const top = [...cls].sort((a, b) => b.total - a.total).slice(0, 8);
    return { option: { legend: { type: 'scroll' }, grid: { top: 48 }, tooltip: { trigger: 'axis', formatter: p => tip(p) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t), series: top.map((c, i) => mk.line(c.nome, c.serie, t.series[i])) }, table: tableYears(anos, Object.fromEntries(top.map(c => [c.nome, c.serie]))) }; });
  wireControls('transicoes');
}
Promise.all([loadJson('./data/desenho_industrial/', FILES), fetch('./data/geo/br_uf.json').then(r => r.json())]).then(([d, geo]) => {
  d.geo = geo; heroStats(d.resumo.kpis); footerInfo(d.resumo); heroCanvas(); kpis(d); charts(d); mountAll({ d }); reveals(); navSpy();
}).catch(loadError);
