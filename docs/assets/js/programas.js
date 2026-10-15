/* programas.js — dashboard de programas de computador. */
import { initTheme, register, mountAll, fmt, ax, mk, tableYears, tableRows } from './viz.js';
import { chrome, heroCanvas, heroStats, kpiTiles, footerInfo, mountCommon, reveals, navSpy, loadJson, loadError, tip, hbarOption, hbar2Option, X, pctOf } from './shared.js';

const FILES = ['resumo', 'serie_depositos', 'serie_decisoes', 'situacao_coorte', 'tempo_registro', 'tipos', 'autores', 'uf', 'paises', 'depositantes', 'municipios', 'genero', 'funil'];
chrome({ active: 'programas', sub: 'v12 · programas de computador', sections: [['panorama', 'Panorama'], ['tipos', 'Tipos'], ['jornada', 'Jornada'], ['quem', 'Quem'], ['onde', 'Onde'], ['metodo', 'Método']] });
initTheme(document.getElementById('theme-toggle'));

function kpis(d) {
  const k = d.resumo.kpis, sd = d.serie_depositos, ano = d.resumo.ano_ultimo;
  kpiTiles([
    { label: `Pedidos em ${ano}`, value: k.pedidos_ultimo_ano, delta: k.pedidos_variacao_pct, spark: sd.total },
    { label: 'Dias até o certificado', value: k.dias_ate_certificado_mediana_recente, decimals: 0, suffix: ' dias', sub: 'mediana, pedidos desde 2018' },
    { label: 'Universidades e institutos', value: k.share_academia, decimals: 1, suffix: '%', sub: 'dos pedidos, 2000–2025', spark: sd.categoria_residente.universidade.map((v, i) => pctOf(v + sd.categoria_residente.instituto_pesquisa[i], sd.total[i])) },
    { label: 'Pessoas físicas (residentes)', value: k.share_pf_residentes, decimals: 1, suffix: '%', sub: 'parcela dos pedidos de residentes', spark: sd.pf_pj['Pessoa física'].map((v, i) => pctOf(v, sd.total[i])) },
    { label: 'Autores por pedido', value: d.autores.media_por_pedido, decimals: 1, sub: `${fmt.int(d.autores.mencoes)} menções`, spark: sd.media_autores },
    { label: 'Tipos por pedido', value: d.tipos.media_tipos_por_pedido, decimals: 1, sub: `${fmt.int(d.tipos.mencoes)} menções`, spark: sd.media_tipos },
    { label: 'Mulheres entre depositantes PF', value: d.genero.share_f_depositantes ? d.genero.share_f_depositantes[d.genero.share_f_depositantes.length - 1] : null, decimals: 1, suffix: '%', sub: `em ${ano} · residentes`, spark: d.genero.share_f_depositantes },
  ]);
}
function charts(d) {
  const anos = d.serie_depositos.anos; const s = d.serie_depositos;
  mountCommon(d, { termo: 'registro', eventos: [['concessao', 'Certificados expedidos'], ['transferencia_alteracao', 'Transferências e alterações'], ['peticao', 'Petições'], ['extincao', 'Renúncias'], ['anulacao_retificacao', 'Anulações e retificações']] });
  register('dep-pfpj', ({ t }) => ({ option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { total: true }) }, xAxis: ax.time(t, anos, X.deposito, { boundaryGap: true }), yAxis: ax.val(t), series: [mk.stackBar('Pessoa jurídica', s.pf_pj['Pessoa jurídica'], t.series[0], t), mk.stackBar('Pessoa física', s.pf_pj['Pessoa física'], t.series[1], t)] }, table: tableYears(anos, s.pf_pj) }));
  register('dep-autores', ({ t }) => ({ option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.dec2 }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t, { formatter: v => fmt.dec1(v), min: 0 }), series: [mk.line('Autores por pedido', s.media_autores, t.series[0]), mk.line('Tipos por pedido', s.media_tipos, t.series[1])] }, table: tableYears(anos, { 'Autores por pedido': s.media_autores, 'Tipos por pedido': s.media_tipos }) }));
  register('prg-dias', ({ t }) => { const rows = d.tempo_registro.por_ano.filter(r => r.ano >= 2018); const xs = rows.map(r => r.ano); const dias = rows.map(r => Math.round(r.mediana * 365.25));
    return { option: { tooltip: { trigger: 'axis', formatter: ps => { const r = rows[ps[0].dataIndex]; return `<b>${r.ano}</b> · ${fmt.int(r.n)} certificados<br>mediana <b>${fmt.int(Math.round(r.mediana * 365.25))} dias</b> · quartis ${fmt.int(Math.round(r.p25 * 365.25))}–${fmt.int(Math.round(r.p75 * 365.25))}`; } }, xAxis: ax.time(t, xs, 'Ano de expedição do certificado (publicação na RPI)', { boundaryGap: true }), yAxis: ax.val(t, { formatter: v => v + ' d', min: 0 }), series: [mk.bar('Dias (mediana)', dias, t.series[0], t)] },
      table: tableRows(['Ano', 'Certificados', 'Mediana (dias)', 'P25', 'P75'], rows.map(r => [r.ano, r.n, Math.round(r.mediana * 365.25), Math.round(r.p25 * 365.25), Math.round(r.p75 * 365.25)])) }; });
  const g = d.tipos.grupos;
  register('tipos-grupos', ({ t }) => ({ option: hbarOption(t, g.map(x => x.nome), g.map(x => x.total), { width: 230 }), table: tableRows(['Grupo', 'Código', 'Menções', 'Pedidos'], g.map(x => [x.nome, x.grupo, x.total, x.pedidos])) }));
  register('tipos-area', ({ t }) => { const top = g.slice(0, 7); return { option: { legend: { type: 'scroll' }, grid: { top: 48 }, tooltip: { trigger: 'axis', formatter: p => tip(p) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t), series: top.map((x, i) => mk.area(x.nome, x.serie, t.series[i])) }, table: tableYears(anos, Object.fromEntries(top.map(x => [x.nome, x.serie]))) }; });
  register('tipos-top', ({ t }) => { const rows = d.tipos.tipos_top; return { option: hbar2Option(t, rows.map(r => ({ name: `${r.cd_tipo} · ${r.nome_tipo}`, value: r.n })), { width: 250 }), table: tableRows(['Código', 'Tipo', 'Grupo', 'Menções'], rows.map(r => [r.cd_tipo, r.nome_tipo, r.nome_grupo, r.n])) }; });
  register('autores-uf', ({ t }) => { const rows = d.autores.por_uf.slice(0, 27); const nomes = Object.fromEntries(d.uf.ufs.map(u => [u.uf, u.nome])); return { option: hbarOption(t, rows.map(r => nomes[r.uf] || r.uf), rows.map(r => r.n), { width: 150 }), table: tableRows(['UF', 'Menções a autores'], rows.map(r => [nomes[r.uf] || r.uf, r.n])) }; });
}
Promise.all([loadJson('./data/programa_computador/', FILES), fetch('./data/geo/br_uf.json').then(r => r.json())]).then(([d, geo]) => {
  d.geo = geo; heroStats(d.resumo.kpis); footerInfo(d.resumo); heroCanvas(); kpis(d); charts(d); mountAll({ d }); reveals(); navSpy();
}).catch(loadError);
