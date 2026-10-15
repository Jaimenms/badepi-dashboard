/* marcas.js — dashboard de marcas. */
import { initTheme, register, mountAll, fmt, ax, mk, tableYears, tableRows, countUpOnView } from './viz.js';
import { chrome, heroCanvas, heroStats, kpiTiles, setText, footerInfo, mountCommon, reveals, navSpy, loadJson, loadError, wireControls, tip, hbar2Option, X, pctOf } from './shared.js';

const FILES = ['resumo', 'serie_depositos', 'serie_decisoes', 'situacao_coorte', 'tempo_registro', 'classes', 'uf', 'paises', 'depositantes', 'municipios', 'genero', 'funil', 'backlog', 'ciclo_vida', 'transicoes'];
chrome({ active: 'marcas', sub: 'v12 · marcas', sections: [['panorama', 'Panorama'], ['jornada', 'Jornada'], ['quem', 'Quem'], ['onde', 'Onde'], ['classes', 'Classes'], ['metodo', 'Método']] });
initTheme(document.getElementById('theme-toggle'));

function kpis(d) {
  const k = d.resumo.kpis, sd = d.serie_depositos, dc = d.serie_decisoes, ano = d.resumo.ano_ultimo;
  kpiTiles([
    { label: `Pedidos em ${ano}`, value: k.pedidos_ultimo_ano, delta: k.pedidos_variacao_pct, spark: sd.total },
    { label: `Registros em ${ano}`, value: k.concessoes_ultimo_ano, delta: k.concessoes_variacao_pct, spark: dc.concessoes },
    { label: 'Registros vigentes', value: k.vigentes, sub: 'registrados e não extintos', spark: d.funil.vigentes },
    { label: 'Tempo mediano até o registro', value: k.tempo_concessao_mediana_ultimo_ano, decimals: 1, suffix: ' anos', sub: `era ${fmt.dec1(k.tempo_concessao_pior_mediana)} em ${k.tempo_concessao_pior_ano}`, spark: d.tempo_registro.por_ano.map(x => x.mediana) },
    { label: 'Pedidos em tramitação', value: k.backlog_atual, sub: `${fmt.compact(d.situacao_coorte.por_coorte['Em andamento'][d.situacao_coorte.anos.length - 1])} deles são pedidos de ${ano}`, spark: d.backlog.backlog_fim_ano },
    { label: `Residentes em ${ano}`, value: k.share_residentes_ultimo_ano, decimals: 1, suffix: '%', sub: `média 2000–${ano}: ${fmt.pct(k.share_residentes_total)}`, spark: sd.residente.map((v, i) => pctOf(v, sd.total[i])) },
    { label: `Via Madri em ${ano}`, value: k.share_madri_ultimo_ano, decimals: 1, suffix: '%', sub: 'designações do Brasil pelo Protocolo', spark: sd.via.Madri.map((v, i) => pctOf(v, sd.total[i])) },
  ]);
  document.getElementById('big-tempo').dataset.count = k.tempo_concessao_mediana_ultimo_ano; setText('big-tempo-ano', ano);
  setText('big-tempo-sub', `Em ${k.tempo_concessao_pior_ano} a mediana era de ${fmt.dec1(k.tempo_concessao_pior_mediana)} anos.`);
  document.getElementById('big-backlog').dataset.count = k.backlog_atual; setText('big-backlog-ano', ano);
  const em2025 = d.situacao_coorte.por_coorte['Em andamento'][d.situacao_coorte.anos.length - 1];
  setText('big-backlog-sub', `${fmt.int(em2025)} (${fmt.pct(pctOf(em2025, k.backlog_atual))}) são pedidos de ${ano} ainda no prazo normal de publicação, oposição e exame; o estoque antigo caiu de ${fmt.compact(Math.max(...d.backlog.backlog_fim_ano.slice(0, 20)))} para ${fmt.compact(d.backlog.backlog_fim_ano[18])} entre 2005 e 2018.`);
  document.getElementById('big-vigentes').dataset.count = k.vigentes; setText('big-vigentes-sub', `${fmt.int(k.vigentes_residentes)} de titulares residentes (${fmt.pct(pctOf(k.vigentes_residentes, k.vigentes))}).`);
  document.getElementById('big-opos').dataset.count = k.share_oposicao; setText('big-opos-sub', `Oposições apresentadas após a publicação do pedido (notificação de oposição), 2000–${ano}.`);
  countUpOnView(document.getElementById('jornada'));
}
function charts(d) {
  const anos = d.serie_depositos.anos;
  mountCommon(d, { termo: 'registro', eventos: [['publicacao', 'Publicações'], ['oposicao', 'Oposições'], ['exigencia', 'Exigências'], ['deferimento', 'Deferimentos'], ['indeferimento', 'Indeferimentos'], ['concessao', 'Registros'], ['arquivamento', 'Arquivamentos'], ['extincao', 'Extinções']] });
  const s = d.serie_depositos;
  register('dep-natureza', ({ t }) => { const cols = Object.fromEntries(Object.entries(s.natureza).filter(([, v]) => v.some(x => x))); const names = Object.keys(cols);
    return { option: { legend: { type: 'scroll' }, grid: { top: 48 }, tooltip: { trigger: 'axis', formatter: p => tip(p, { total: true }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t), series: names.map((n, i) => mk.area(n, cols[n], t.series[i])) }, table: tableYears(anos, cols) }; });
  register('dep-apresentacao', ({ t }) => { const names = Object.keys(s.apresentacao);
    return { option: { legend: { type: 'scroll' }, grid: { top: 48 }, tooltip: { trigger: 'axis', formatter: p => tip(p, { total: true }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t), series: names.map((n, i) => mk.area(n, s.apresentacao[n], t.series[i])) }, table: tableYears(anos, s.apresentacao) }; });
  register('dep-madri', ({ t }) => { const share = s.via.Madri.map((v, i) => pctOf(v, s.total[i]));
    return { option: { tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.pct }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t, { formatter: v => v + '%', min: 0 }), series: [mk.line('Via Madri (%)', share, t.series[0], { areaStyle: { color: t.series[0], opacity: .12 } })] }, table: tableYears(anos, { 'Via Madri': s.via.Madri, 'Via direta': s.via.Direta, '% Madri': share }) }; });
  const cls = d.classes.classes;
  register('classes-bar', ({ t }) => { const rows = [...cls].sort((a, b) => b.total - a.total);
    return { option: hbar2Option(t, rows.map(r => ({ name: `${r.classe} · ${r.nome}`, value: r.total })), { width: 230 }), table: tableRows(['Classe', 'Nome', 'Tipo', 'Pedidos', 'Registrados', 'Residentes'], rows.map(r => [r.classe, r.nome, r.tipo, r.total, r.registrados, r.residentes])) }; });
  register('classes-ps', ({ t }) => ({ option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { total: true }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t), series: [mk.area('Produtos (classes 1–34)', d.classes.produtos_vs_servicos.Produto, t.series[0]), mk.area('Serviços (classes 35–45)', d.classes.produtos_vs_servicos['Serviço'], t.series[1])] }, table: tableYears(anos, { Produtos: d.classes.produtos_vs_servicos.Produto, Serviços: d.classes.produtos_vs_servicos['Serviço'] }) }));
  register('classes-linhas', ({ t }) => { const top = [...cls].sort((a, b) => b.total - a.total).slice(0, 8);
    return { option: { legend: { type: 'scroll' }, grid: { top: 48 }, tooltip: { trigger: 'axis', formatter: p => tip(p) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t), series: top.map((c, i) => mk.line(`${c.classe} · ${c.nome}`, c.serie, t.series[i])) }, table: tableYears(anos, Object.fromEntries(top.map(c => [`${c.classe} · ${c.nome}`, c.serie]))) }; });
  wireControls('transicoes');
}
Promise.all([loadJson('./data/marcas/', FILES), fetch('./data/geo/br_uf.json').then(r => r.json())]).then(([d, geo]) => {
  d.geo = geo; heroStats(d.resumo.kpis); footerInfo(d.resumo); heroCanvas(); kpis(d); charts(d); mountAll({ d }); reveals(); navSpy();
}).catch(loadError);
