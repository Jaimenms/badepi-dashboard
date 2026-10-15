/* patentes.js — dashboard de patentes: carrega a gold, monta os cards comuns (shared.js) e os específicos. */
import { initTheme, tokens, register, mountAll, fmt, ax, mk, tableYears, tableRows, countUpOnView } from './viz.js';
import { chrome, heroCanvas, heroStats, kpiTiles, setText, footerInfo, mountCommon, reveals, navSpy, loadJson, loadError, wireControls, tip, hbarOption, hbar2Option, X, pctOf, last } from './shared.js';

const FILES = ['resumo', 'serie_depositos', 'serie_decisoes', 'situacao_coorte', 'tempo_concessao', 'campos_tec', 'ipc_secoes', 'uf', 'paises', 'depositantes', 'municipios', 'genero', 'funil', 'impacto', 'ciclo_vida', 'transicoes'];
chrome({ active: 'patentes', sub: 'v12 · patentes', sections: [['panorama', 'Panorama'], ['impacto', 'Impacto'], ['jornada', 'Jornada'], ['quem', 'Quem'], ['onde', 'Onde'], ['tecnologias', 'Tecnologias'], ['genero', 'Gênero'], ['metodo', 'Método']] });
initTheme(document.getElementById('theme-toggle'));

function kpis(d) {
  const k = d.resumo.kpis, sd = d.serie_depositos, dc = d.serie_decisoes, imp = d.impacto, tc = d.tempo_concessao, ano = d.resumo.ano_ultimo;
  kpiTiles([
    { label: `Pedidos em ${ano}`, value: k.pedidos_ultimo_ano, delta: k.pedidos_variacao_pct, spark: sd.total },
    { label: 'Pedidos efetivos (2000–2025)', value: k.pedidos_efetivos, sub: `${fmt.int(k.pedidos_numeracao_anulada)} com numeração anulada ficam fora`, spark: sd.efetivos },
    { label: `Concessões em ${ano}`, value: k.concessoes_ultimo_ano, delta: k.concessoes_variacao_pct, spark: dc.concessoes },
    { label: 'Patentes vigentes', value: k.patentes_vigentes, sub: 'concedidas e dentro do prazo', spark: d.funil.vigentes },
    { label: 'Tempo mediano até a concessão', value: k.tempo_concessao_mediana_ultimo_ano, decimals: 1, suffix: ' anos', sub: `era ${fmt.dec1(k.tempo_concessao_pior_mediana)} em ${k.tempo_concessao_pior_ano}`, spark: tc.por_ano.map(x => x.mediana) },
    { label: 'Pedidos sem decisão', value: k.backlog_atual, sub: `pico de ${fmt.compact(k.backlog_pico)} em ${k.backlog_pico_ano}`, spark: imp.backlog_fim_ano },
    { label: `Residentes em ${ano}`, value: k.share_residentes_ultimo_ano, decimals: 1, suffix: '%', sub: `média 2000–${ano}: ${fmt.pct(k.share_residentes_total)}`, spark: sd.residente.map((v, i) => pctOf(v, sd.total[i])) },
    { label: 'Mulheres entre inventores', value: k.share_mulheres_inventoras_ultimo_ano, decimals: 1, suffix: '%', sub: `${fmt.pct(k.share_mulheres_inventoras_primeiro_ano)} em 2000 · residentes`, spark: d.genero.share_f_inventores },
  ]);
}
function bigNumbers(d) {
  const k = d.resumo.kpis, imp = d.impacto, ano = d.resumo.ano_ultimo;
  document.getElementById('big-tempo').dataset.count = k.tempo_concessao_mediana_ultimo_ano;
  setText('big-tempo-ano', ano); setText('big-tempo-sub', `Em ${k.tempo_concessao_pior_ano}, o pior ano, a mediana era de ${fmt.dec1(k.tempo_concessao_pior_mediana)} anos: uma redução de ${fmt.pct((1 - k.tempo_concessao_mediana_ultimo_ano / k.tempo_concessao_pior_mediana) * 100)}.`);
  document.getElementById('big-backlog').dataset.count = k.backlog_atual;
  setText('big-backlog-ano', ano); setText('big-backlog-sub', `${fmt.pct((1 - k.backlog_atual / k.backlog_pico) * 100)} abaixo do pico de ${fmt.int(k.backlog_pico)} pedidos em ${k.backlog_pico_ano}.`);
  document.getElementById('big-vigentes').dataset.count = k.patentes_vigentes;
  setText('big-vigentes-sub', `${fmt.int(imp.vigentes.residentes)} de titulares residentes (${fmt.pct(pctOf(imp.vigentes.residentes, imp.vigentes.total))}) e ${fmt.int(imp.vigentes.nao_residentes)} de não residentes.`);
  document.getElementById('big-res').dataset.count = k.share_residentes_ultimo_ano;
  setText('big-res-ano', ano); setText('big-res-sub', `A média de 2000 a ${ano} é ${fmt.pct(k.share_residentes_total)}. O último ano é parcial para pedidos PCT (não residentes), o que infla a parcela.`);
  countUpOnView(document.getElementById('impacto'));
}

function charts(d) {
  const anos = d.serie_depositos.anos; const ano = d.resumo.ano_ultimo;
  mountCommon(d, { termo: 'concessão', eventos: [['exigencia', 'Exigências'], ['parecer', 'Pareceres técnicos'], ['deferimento', 'Deferimentos'], ['indeferimento', 'Indeferimentos'], ['concessao', 'Concessões'], ['arquivamento', 'Arquivamentos']] });

  register('dep-serie', ({ t, state }) => {
    const s = d.serie_depositos; let cols;
    if (state.view === 'natureza') cols = { 'Patente de invenção (PI)': s.natureza.PI, 'Modelo de utilidade (MU)': s.natureza.MU, 'Certificado de adição (CA)': s.natureza.CA };
    else if (state.view === 'via') cols = { 'Via PCT': s.via.PCT, 'Via direta': s.via.Direta };
    else cols = { Residentes: s.residente, 'Não residentes': s.nao_residente };
    const names = Object.keys(cols);
    return { option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { total: true }) }, xAxis: ax.time(t, anos, X.deposito, { boundaryGap: true }), yAxis: ax.val(t), series: names.map((n, i) => mk.stackBar(n, cols[n], t.series[i], t)) },
      table: tableYears(anos, { ...cols, Total: s.total }) };
  }, { state: { view: 'origem' } });
  register('dep-inventores', ({ t }) => ({ option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.dec2 }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t, { formatter: v => fmt.dec1(v), min: 0 }),
    series: [mk.line('Inventores por pedido', d.serie_depositos.media_inventores, t.series[0]), mk.line('Depositantes por pedido', d.serie_depositos.media_depositantes, t.series[1])] },
    table: tableYears(anos, { 'Inventores por pedido': d.serie_depositos.media_inventores, 'Depositantes por pedido': d.serie_depositos.media_depositantes }) }));
  register('dep-prioridade', ({ t }) => { const s = d.serie_depositos; const share = s.com_prioridade.map((v, i) => pctOf(v, s.total[i]));
    return { option: { tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.pct }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t, { formatter: v => v + '%', max: 100, min: 0 }), series: [mk.line('Com prioridade (%)', share, t.series[0], { areaStyle: { color: t.series[0], opacity: .12 } })] },
      table: tableYears(anos, { 'Pedidos com prioridade': s.com_prioridade, Total: s.total, '% com prioridade': share }) }; });

  register('imp-vigentes-setor', ({ t }) => { const rows = [...d.impacto.vigentes.por_setor].sort((a, b) => b.n - a.n); return { option: hbarOption(t, rows.map(r => r.setor), rows.map(r => r.n), { width: 210 }), table: tableRows(['Setor', 'Patentes vigentes'], rows.map(r => [r.setor, r.n])) }; });
  register('imp-cresc', ({ t }) => {
    const all = d.impacto.crescimento_campos; const rows = [...all.slice(0, 7), ...all.slice(-7)].sort((a, b) => b.variacao_pct - a.variacao_pct);
    return { option: { grid: { left: 8, right: 60, top: 8, bottom: 6, containLabel: true },
      tooltip: { trigger: 'item', formatter: p => { const r = rows[p.dataIndex]; return `<b>${r.nome}</b><br>${r.setor}<br>média 2011–15: ${fmt.dec1(r.media_2011_2015)} / ano<br>média 2021–25: ${fmt.dec1(r.media_2021_2025)} / ano<br><b>${fmt.signed(r.variacao_pct)}</b>`; } },
      xAxis: ax.val(t, { formatter: v => v + '%' }), yAxis: ax.catY(t, rows.map(r => r.nome), { width: 220 }),
      series: [{ type: 'bar', data: rows.map(r => ({ value: r.variacao_pct, itemStyle: { color: r.variacao_pct >= 0 ? t.series[0] : t.series[7], borderRadius: r.variacao_pct >= 0 ? [0, 4, 4, 0] : [4, 0, 0, 4] } })), barMaxWidth: 20, label: { show: true, position: 'right', color: t.ink2, fontSize: 12, formatter: p => fmt.signed(p.value) } }] },
      table: tableRows(['Campo', 'Setor', 'Média 2011–2015', 'Média 2021–2025', 'Variação (%)'], all.map(r => [r.nome, r.setor, r.media_2011_2015, r.media_2021_2025, r.variacao_pct])) };
  });
  register('imp-academia', ({ t }) => ({ option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.pct }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t, { formatter: v => v + '%', min: 0 }),
    series: [mk.line('Universidades + institutos de pesquisa', d.impacto.share_academia_residentes, t.series[0]), mk.line('Só universidades', d.impacto.share_universidades_residentes, t.series[1])] },
    table: tableYears(anos, { 'Universidades + institutos (%)': d.impacto.share_academia_residentes, 'Só universidades (%)': d.impacto.share_universidades_residentes, 'Pedidos com nome conhecido (%)': d.impacto.share_residentes_identificados }) }));
  register('imp-regional-sp', ({ t }) => ({ option: { tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.pct }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t, { formatter: v => v + '%', min: 0 }), series: [mk.line('SP (%)', d.impacto.share_sp_residentes, t.series[0], { areaStyle: { color: t.series[0], opacity: .12 } })] }, table: tableYears(anos, { 'Parcela de SP (%)': d.impacto.share_sp_residentes, 'Sudeste + Sul (%)': d.impacto.share_sudeste_sul_residentes }) }));
  register('imp-regional-ufs', ({ t }) => ({ option: { tooltip: { trigger: 'axis', formatter: p => tip(p) }, xAxis: ax.time(t, anos, X.deposito, { boundaryGap: true }), yAxis: ax.val(t, { formatter: v => v, minInterval: 1 }), series: [mk.bar('UFs com 50+ pedidos', d.impacto.ufs_com_50_ou_mais, t.series[0], t)] }, table: tableYears(anos, { 'UFs com 50+ pedidos': d.impacto.ufs_com_50_ou_mais }) }));
  register('imp-prioritario', ({ t }) => ({ option: { tooltip: { trigger: 'axis', formatter: p => tip(p) }, xAxis: ax.time(t, anos, X.despacho, { boundaryGap: true }), yAxis: ax.val(t), series: [mk.bar('Pedidos com trâmite prioritário', d.impacto.tramite_prioritario_pedidos, t.series[0], t)] }, table: tableYears(anos, { 'Pedidos com trâmite prioritário': d.impacto.tramite_prioritario_pedidos, 'Ofertas de licença': d.impacto.oferta_licenca_pedidos, 'Transferências/alterações': d.impacto.transferencias_pedidos }) }));

  const campoNome = {}; d.campos_tec.setores.forEach(s => s.campos.forEach(c => { campoNome[c.campo_tec] = c.nome; }));
  register('tempo-setor', ({ t }) => {
    const rows = [...d.tempo_concessao.por_setor_recente].sort((a, b) => a.mediana - b.mediana); const vias = [...d.tempo_concessao.por_via_recente].sort((a, b) => a.mediana - b.mediana);
    const lab = { show: true, position: 'right', color: t.ink2, fontSize: 12, formatter: p => fmt.anos(p.value) };
    return { option: { title: [{ text: 'Por setor tecnológico', left: 0, top: 0, textStyle: { fontSize: 12.5, fontWeight: 600, color: t.ink2 } }, { text: 'Por via de entrada', left: 0, top: '66%', textStyle: { fontSize: 12.5, fontWeight: 600, color: t.ink2 } }],
      grid: [{ left: 8, right: 60, top: 28, height: '50%', containLabel: true }, { left: 8, right: 60, top: '76%', bottom: 4, containLabel: true }],
      tooltip: { trigger: 'item', formatter: p => `<b>${p.name}</b><br>mediana ${fmt.anos(p.value)}` },
      xAxis: [{ ...ax.val(t, { formatter: v => v + ' a', max: 8 }), gridIndex: 0 }, { ...ax.val(t, { formatter: v => v + ' a', max: 8 }), gridIndex: 1 }],
      yAxis: [{ ...ax.catY(t, rows.map(r => r.grupo), { width: 210 }), gridIndex: 0 }, { ...ax.catY(t, vias.map(v => v.grupo === 'PCT' ? 'Via PCT' : 'Via direta'), { width: 210 }), gridIndex: 1 }],
      series: [{ ...mk.hbar('valor', rows.map(r => r.mediana), t.series[0], t, { label: lab }), xAxisIndex: 0, yAxisIndex: 0 }, { ...mk.hbar('valor', vias.map(v => v.mediana), t.series[0], t, { label: lab }), xAxisIndex: 1, yAxisIndex: 1 }] },
      table: tableRows(['Grupo', 'Mediana (anos)', 'Concessões'], [...rows.map(r => [r.grupo, r.mediana, r.n]), ...vias.map(v => [v.grupo, v.mediana, v.n])]) };
  });
  register('tempo-campo', ({ t }) => { const rows = [...d.tempo_concessao.por_campo_recente].filter(r => r.n >= 50).sort((a, b) => a.mediana - b.mediana);
    return { option: hbar2Option(t, rows.map(r => ({ name: campoNome[r.grupo], value: r.mediana })), { fmtv: fmt.anos, width: 200 }), table: tableRows(['Campo', 'Mediana (anos)', 'Concessões'], rows.map(r => [campoNome[r.grupo], r.mediana, r.n])) }; });

  register('treemap', ({ t }) => {
    const data = d.campos_tec.setores.map((s, i) => ({ name: s.setor, value: s.total, itemStyle: { color: t.series[i] }, children: s.campos.map(c => ({ name: c.nome, value: c.total, campo: c })) }));
    return { option: { tooltip: { formatter: p => { const c = p.data.campo; return c ? `<b>${c.nome}</b><br>${fmt.int(c.total)} pedidos · ${fmt.int(c.concedidos)} concedidos<br>${fmt.pct(pctOf(c.residentes, c.total))} de residentes` : `<b>${p.name}</b><br>${fmt.int(p.value)} pedidos`; } },
      series: [{ type: 'treemap', data, roam: false, nodeClick: false, breadcrumb: { show: false }, width: '100%', height: '100%', top: 0, left: 0, right: 0, bottom: 0,
        label: { show: true, formatter: p => `${p.name}\n${fmt.compact(p.value)}`, fontSize: 12, color: '#fff', padding: 6, overflow: 'truncate' },
        upperLabel: { show: true, height: 28, color: '#fff', fontWeight: 700, fontSize: 13, formatter: p => `${p.name}  ·  ${fmt.compact(p.value)}` },
        levels: [{ itemStyle: { gapWidth: 4, borderWidth: 0 }, upperLabel: { show: false } }, { itemStyle: { borderWidth: 3, gapWidth: 3, borderColorSaturation: 0.75 }, upperLabel: { show: true, height: 28, color: '#fff', fontWeight: 700 } }, { colorSaturation: [0.5, 0.85], itemStyle: { borderColor: t.surface, borderWidth: 1, gapWidth: 2 } }] }] },
      table: tableRows(['Setor', 'Campo', 'Pedidos', 'Concedidos', 'Residentes'], d.campos_tec.setores.flatMap(s => s.campos.map(c => [s.setor, c.nome, c.total, c.concedidos, c.residentes]))) };
  });
  register('setores-area', ({ t }) => ({ option: { legend: { type: 'scroll' }, grid: { top: 48 }, tooltip: { trigger: 'axis', formatter: p => tip(p, { total: true }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t), series: d.campos_tec.setores.map((s, i) => mk.area(s.setor, s.serie, t.series[i])) }, table: tableYears(anos, Object.fromEntries(d.campos_tec.setores.map(s => [s.setor, s.serie]))) }));
  const allCampos = d.campos_tec.setores.flatMap(s => s.campos.map(c => ({ ...c, setor: s.setor })));
  register('campo-res', ({ t }) => { const sorted = allCampos.map(c => ({ ...c, share: pctOf(c.residentes, c.total) })).sort((a, b) => b.share - a.share); const rows = [...sorted.slice(0, 10), ...sorted.slice(-5)];
    return { option: hbarOption(t, rows.map(r => r.nome), rows.map(r => r.share), { fmtv: fmt.pct, width: 230, max: 100 }), table: tableRows(['Campo', 'Setor', 'Residentes (%)', 'Pedidos'], sorted.map(r => [r.nome, r.setor, r.share, r.total])) }; });
  const top8 = [...allCampos].sort((a, b) => b.total - a.total).slice(0, 8);
  const host = document.getElementById('campos-mult');
  host.innerHTML = top8.map(c => `<article class="card col-3 keep reveal" data-chart="campo-${c.campo_tec}"><header><div class="titles"><h3 style="font-size:14px">${c.nome}</h3><p class="sub">${fmt.int(c.total)} pedidos · ${c.setor}</p></div><div class="actions"><button class="icon-btn btn-table">Tabela</button></div></header><div class="chart" style="height:170px"></div><div class="table-view hidden"></div></article>`).join('');
  top8.forEach(c => register(`campo-${c.campo_tec}`, ({ t }) => ({ option: { legend: {}, grid: { left: 4, right: 22, top: 30, bottom: 4, containLabel: true }, tooltip: { trigger: 'axis', formatter: p => tip(p) }, xAxis: ax.time(t, anos, 'Ano de depósito', { axisLabel: { showMinLabel: true, showMaxLabel: true, interval: anos.length - 2 } }), yAxis: ax.val(t, { splitNumber: 3 }), series: [mk.line('Todos', c.serie, t.series[0], { areaStyle: { color: t.series[0], opacity: .12 } }), mk.line('Residentes', c.serie_residentes, t.series[1])] }, table: tableYears(anos, { Pedidos: c.serie, Residentes: c.serie_residentes, Concessões: c.serie_concessoes }) })));

  register('gen-share', ({ t }) => ({ option: { legend: {}, tooltip: { trigger: 'axis', formatter: p => tip(p, { fmtv: fmt.pct }) }, xAxis: ax.time(t, anos, X.deposito), yAxis: ax.val(t, { formatter: v => v + '%', min: 0 }),
    series: [mk.line('Inventoras (% dos inventores)', d.genero.share_f_inventores, t.series[0]), mk.line('Depositantes PF mulheres (%)', d.genero.share_f_depositantes, t.series[1])] },
    table: tableYears(anos, { 'Inventoras (%)': d.genero.share_f_inventores, 'Inventoras (n)': d.genero.inventores.F, 'Inventores (n)': d.genero.inventores.M, 'Depositantes PF mulheres (%)': d.genero.share_f_depositantes }) }));
  register('gen-setor', ({ t }) => { const rows = [...d.genero.share_f_por_setor].sort((a, b) => b.share_f - a.share_f); return { option: hbarOption(t, rows.map(r => r.setor), rows.map(r => r.share_f), { fmtv: fmt.pct, width: 210, max: 60 }), table: tableRows(['Setor', 'Inventoras (%)', 'Menções'], rows.map(r => [r.setor, r.share_f, r.n])) }; });
  register('gen-campo', ({ t }) => { const rows = [...d.genero.share_f_por_campo].filter(r => r.n >= 200).sort((a, b) => b.share_f - a.share_f); return { option: hbar2Option(t, rows.map(r => ({ name: campoNome[r.campo_tec], value: r.share_f })), { fmtv: fmt.pct, width: 220, max: 60 }), table: tableRows(['Campo', 'Inventoras (%)', 'Menções'], rows.map(r => [campoNome[r.campo_tec], r.share_f, r.n])) }; });
  wireControls('transicoes');
}

Promise.all([loadJson('./data/patentes/', FILES), fetch('./data/geo/br_uf.json').then(r => r.json())]).then(([d, geo]) => {
  d.geo = geo;
  heroStats(d.resumo.kpis); footerInfo(d.resumo); heroCanvas(); kpis(d); bigNumbers(d); charts(d);
  const lbl = document.querySelector('[data-kpi="pedidos_total"]')?.nextElementSibling; if (lbl) lbl.textContent = `pedidos de patente (2000–2025) · ${fmt.int(d.resumo.kpis.pedidos_efetivos)} efetivos`;
  mountAll({ d }); reveals(); navSpy();
}).catch(loadError);
