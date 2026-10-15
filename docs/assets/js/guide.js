/* guide.js — página "Como usar": tema + modelo de dados a partir de modelo.json */
import { initTheme, fmt } from './viz.js';

initTheme(document.getElementById('theme-toggle'));

const DESC = {
  ptn_deposito: 'Fato principal: um pedido por linha, com título, datas, natureza, via, origem (primeiro depositante), contagens e classificação principal.',
  ptn_depositante: 'Depositantes (titulares) de cada pedido, na ordem do pedido. Categoria inferida do nome + tipo de pessoa.',
  ptn_inventor: 'Inventores de cada pedido, com domicílio; nomes sob sigilo marcados em anonimo.',
  ptn_despacho: 'Todos os despachos publicados na RPI, com o evento derivado do código. Particionada por ano de publicação.',
  ptn_ipc: 'Classificações IPC do pedido (uma linha por símbolo) com seção/classe/subclasse e o campo tecnológico OMPI.',
  ptn_pct: 'Dados do pedido internacional PCT (número, escritório receptor, datas de depósito e publicação OMPI).',
  ptn_prioridade: 'Prioridades unionistas reivindicadas (número e país). Datas ausentes na v12.',
  ptn_situacao: 'Derivada: situação atual, marcos do processo, vigência legal e tempos até decisão/concessão.',
  ptn_inventor_genero: 'BADEPI PI e Gênero: sexo provável de cada inventor residente (uma linha por menção).',
  ptn_depositante_genero: 'BADEPI PI e Gênero: sexo provável de depositantes pessoa física residentes.',
  dim_campo_tec: '35 campos tecnológicos da OMPI e seus 5 setores.',
  dim_despacho: 'Códigos de despacho observados, descrição mais frequente, evento derivado e contagem.',
  dim_pais: 'Códigos ISO-2 (e códigos de escritórios regionais usados pelo INPI) com nome em português.',
  dim_uf: 'Unidades da federação com nome, região e código IBGE.',
};
const esc = s => String(s ?? '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

fetch('./data/patentes/modelo.json').then(r => r.json()).then(m => {
  const host = document.getElementById('modelo-tabelas');
  const order = ['ptn_deposito', 'ptn_situacao', 'ptn_depositante', 'ptn_inventor', 'ptn_despacho', 'ptn_ipc', 'ptn_pct', 'ptn_prioridade', 'ptn_inventor_genero', 'ptn_depositante_genero', 'dim_campo_tec', 'dim_despacho', 'dim_pais', 'dim_uf'];
  const names = [...order.filter(n => m.tabelas[n]), ...Object.keys(m.tabelas).filter(n => !order.includes(n))];
  host.innerHTML = `<p class="prose">Construído em ${new Date(m.built_at).toLocaleString('pt-BR')} a partir do BADEPI ${esc(m.badepi_version)} (referência ${esc(m.data_referencia)}).</p>` + names.map(n => {
    const t = m.tabelas[n];
    const cols = Object.entries(t.columns).map(([c, ty]) => `<tr><td><code>${esc(c)}</code>${t.key.includes(c) ? ' <span class="pill">chave</span>' : ''}</td><td>${esc(ty)}</td></tr>`).join('');
    return `<details class="table-def"${n === 'ptn_deposito' ? ' open' : ''}><summary><code>${esc(n)}</code><span class="meta">${fmt.int(t.rows)} linhas · ${Object.keys(t.columns).length} colunas${t.partitioned_by ? ' · particionada por ' + esc(t.partitioned_by) : ''} · <code>${esc(t.path)}</code></span></summary>
      <p class="prose" style="margin:8px 0 10px">${esc(DESC[n] || '')}</p>
      <table class="model-table"><thead><tr><th>Coluna</th><th>Tipo</th></tr></thead><tbody>${cols}</tbody></table></details>`;
  }).join('');
}).catch(err => { document.getElementById('modelo-tabelas').innerHTML = `<p class="prose">Não foi possível carregar <code>modelo.json</code> (${esc(err.message)}). Rode <code>uv run badepi gold</code>.</p>`; });
