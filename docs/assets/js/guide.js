/* guide.js — página "Como usar": tabela da fonte, modelo de dados de todos os ativos (diagramas gerados), navegação. */
import { initTheme, fmt } from './viz.js';
import { chrome } from './shared.js';

chrome({ active: 'guia', sub: 'v12 · como usar', sections: [['fonte', 'Fonte'], ['arquitetura', 'Arquitetura'], ['rodar', 'Rodar'], ['modelo', 'Modelo de dados'], ['pandas', 'Pandas'], ['situacao', 'Método'], ['roadmap', 'Próximos ativos']] });
initTheme(document.getElementById('theme-toggle'));
const esc = s => String(s ?? '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const mb = b => (b >= 1e9 ? fmt.dec1(b / 1e9) + ' GB' : b >= 1e6 ? fmt.int(Math.round(b / 1e6)) + ' MB' : fmt.int(Math.round(b / 1e3)) + ' KB');

const DESC = {
  deposito: 'Fato principal: um pedido por linha, com título/nome, datas, via, origem (primeiro depositante), contagens e classificação principal.',
  situacao: 'Derivada: situação atual, marcos do processo (publicação, oposição, exigência, deferimento, indeferimento, concessão/registro, arquivamento, extinção, desistência, prorrogação), vigência e tempos.',
  depositante: 'Depositantes (titulares) de cada pedido, na ordem do pedido, com nome normalizado e categoria inferida.',
  inventor: 'Inventores de cada pedido, com domicílio; nomes sob sigilo marcados em anonimo.', autor: 'Autores do desenho (a fonte não traz nomes, só domicílio).',
  despacho: 'Despachos publicados na RPI com o evento derivado do código.', ipc: 'Classificações IPC (uma linha por símbolo) com seção/classe/subclasse e o campo tecnológico OMPI.',
  pct: 'Dados do pedido internacional PCT (número, escritório receptor, datas).', prioridade: 'Prioridades unionistas reivindicadas (número e país; datas ausentes na v12).',
  classe: 'Classificação do pedido (Nice para marcas, Locarno para desenhos).', classificacao: 'Classe de produto/serviço e categoria OMPI da indicação geográfica.',
  inventor_genero: 'BADEPI PI e Gênero: sexo provável de cada inventor residente.', depositante_genero: 'BADEPI PI e Gênero: sexo provável de depositantes pessoa física residentes.',
  dim_campo_tec: '35 campos tecnológicos da OMPI e seus 5 setores.', dim_despacho: 'Códigos de despacho observados, descrição (da fonte ou curada), evento derivado e contagem.',
  dim_pais: 'Códigos ISO-2 (e códigos de escritórios regionais usados pelo INPI) com nome em português.', dim_uf: 'Unidades da federação com nome, região e código IBGE.',
};
const describe = n => DESC[n] || DESC[n.replace(/^(ptn|mrc|di|ig)_/, '')] || '';

/* ---------- diagrama de relacionamentos gerado a partir de tabelas + relações ---------- */
function diagram(tabelas, relacoes) {
  const names = Object.keys(tabelas);
  const fact = names.find(n => n.endsWith('_deposito'));
  const dims = names.filter(n => n.startsWith('dim_'));
  const derived = relacoes.filter(r => r.para === fact && r.cardinalidade === '1:1').map(r => r.de).filter(n => names.includes(n));
  const children = names.filter(n => n !== fact && !dims.includes(n) && !derived.includes(n));
  const W = 960, bw = 200, bh = 52, gap = 14, top = 16;
  const col = { left: 16, mid: (W - bw) / 2, right: W - bw - 16 };
  const pos = {};
  children.forEach((n, i) => { pos[n] = { x: col.left, y: top + i * (bh + gap), kind: 'child' }; });
  dims.forEach((n, i) => { pos[n] = { x: col.right, y: top + i * (bh + gap), kind: 'dim' }; });
  pos[fact] = { x: col.mid, y: top, kind: 'fact' };
  derived.forEach((n, i) => { pos[n] = { x: col.mid, y: top + (i + 1) * (bh + gap + 26), kind: 'derived' }; });
  const H = Math.max(...Object.values(pos).map(p => p.y + bh)) + 16;
  const fill = { fact: 'var(--s1)', derived: 'var(--s7)', child: 'var(--surface-2)', dim: 'var(--surface-2)' };
  const ink = k => (k === 'fact' || k === 'derived' ? '#fff' : 'var(--ink)');
  const anchor = (a, b) => { // ponto de saída de a na direção de b
    const ca = { x: a.x + bw / 2, y: a.y + bh / 2 }, cb = { x: b.x + bw / 2, y: b.y + bh / 2 };
    if (Math.abs(ca.x - cb.x) < 1) return { x: ca.x, y: cb.y > ca.y ? a.y + bh : a.y };
    return { x: cb.x > ca.x ? a.x + bw : a.x, y: ca.y };
  };
  const edges = relacoes.filter(r => pos[r.de] && pos[r.para]).map(r => {
    const p1 = anchor(pos[r.de], pos[r.para]), p2 = anchor(pos[r.para], pos[r.de]);
    const mx = (p1.x + p2.x) / 2, my = (p1.y + p2.y) / 2; const key = r.chave.replace(/ → .*/, '');
    const w = key.length * 6.2 + 10;
    return `<path d="M${p1.x},${p1.y} C${mx},${p1.y} ${mx},${p2.y} ${p2.x},${p2.y}" fill="none" stroke="var(--axis)" stroke-width="1.4" marker-end="url(#arr)"/>
      <rect x="${mx - w / 2}" y="${my - 8}" width="${w}" height="16" rx="8" fill="var(--surface)" stroke="var(--border)"/><text x="${mx}" y="${my + 3.5}" text-anchor="middle" font-size="9.5" fill="var(--muted)">${esc(key)}</text>`;
  });
  const boxes = Object.entries(pos).map(([n, p]) => `<g><rect x="${p.x}" y="${p.y}" width="${bw}" height="${bh}" rx="10" fill="${fill[p.kind]}" stroke="${p.kind === 'dim' ? 'var(--axis)' : 'var(--border)'}" ${p.kind === 'dim' ? 'stroke-dasharray="4 3"' : ''}/>
    <text x="${p.x + bw / 2}" y="${p.y + 21}" text-anchor="middle" font-size="12.5" font-weight="700" fill="${ink(p.kind)}">${esc(n)}</text>
    <text x="${p.x + bw / 2}" y="${p.y + 38}" text-anchor="middle" font-size="10.5" fill="${ink(p.kind)}" opacity=".85">${fmt.int(tabelas[n].rows)} linhas · ${(tabelas[n].key || []).join(' + ') || '—'}</text></g>`);
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Diagrama de relacionamentos" font-family="Inter, system-ui, sans-serif" style="max-height:${H}px"><defs><marker id="arr" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="var(--axis)"/></marker></defs>${edges.join('')}${boxes.join('')}</svg>`;
}

function renderFonte(m) {
  const rows = m.ativos.map(a => {
    const nf = a.bronze ? a.bronze.files.length : 0; const sz = a.bronze ? a.bronze.files.reduce((s, f) => s + f.size, 0) : 0;
    const nt = a.silver ? Object.keys(a.silver.tabelas).length : 0; const rowsSilver = a.silver ? Object.values(a.silver.tabelas).filter(t => !t.path.startsWith('dim')).reduce((s, t) => s + t.rows, 0) : 0;
    const status = a.silver ? `<span class="tag ok">silver + painel</span>` : a.bronze ? `<span class="tag warn">bronze</span>` : `<span class="tag">—</span>`;
    return `<tr><td><b>${esc(a.label)}</b>${a.pagina ? ` · <a href="${a.pagina}">painel</a>` : ''}</td><td><a href="${a.url_fonte}" target="_blank" rel="noopener"><code>${esc(a.zip)}</code></a></td><td class="num">${nf ? `${nf} arquivos · ${mb(sz)}` : '–'}</td><td class="num">${nt ? `${nt} tabelas · ${fmt.int(rowsSilver)} linhas` : '–'}</td><td>${status}</td></tr>`;
  });
  document.getElementById('fonte-tabela').innerHTML = `<table><thead><tr><th>Ativo</th><th>Arquivo do INPI</th><th>Bronze (extraído)</th><th>Silver (parquet)</th><th>Status</th></tr></thead><tbody>${rows.join('')}</tbody></table>`;
}

function renderModelo(m) {
  const host = document.getElementById('modelo-ativos');
  host.innerHTML = m.ativos.filter(a => a.silver).map(a => {
    const s = a.silver; const tabelas = s.tabelas; const names = Object.keys(tabelas).sort((x, y) => rank(x) - rank(y) || x.localeCompare(y));
    const details = names.map(n => { const t = tabelas[n];
      const cols = Object.entries(t.columns).map(([c, ty]) => `<tr><td><code>${esc(c)}</code>${(t.key || []).includes(c) ? ' <span class="pill">chave</span>' : ''}</td><td>${esc(ty)}</td></tr>`).join('');
      return `<details class="table-def"${n.endsWith('_deposito') ? ' open' : ''}><summary><code>${esc(n)}</code><span class="meta">${fmt.int(t.rows)} linhas · ${Object.keys(t.columns).length} colunas${t.partitioned_by ? ' · particionada por ' + esc(t.partitioned_by) : ''} · <code>${esc(t.path)}</code></span></summary>
        <p class="prose" style="margin:8px 0 10px">${esc(describe(n))}</p><table class="model-table"><thead><tr><th>Coluna</th><th>Tipo</th></tr></thead><tbody>${cols}</tbody></table></details>`; }).join('');
    const rel = (s.relacoes || []).map(r => `<tr><td><code>${esc(r.de)}</code></td><td><code>${esc(r.para)}</code></td><td>${esc(r.chave)}</td><td>${esc(r.cardinalidade)}</td></tr>`).join('');
    const totalRows = names.reduce((x, n) => x + tabelas[n].rows, 0);
    return `<div class="card" style="margin-bottom:22px" id="modelo-${a.slug}"><header><div class="titles"><h3 style="font-size:20px">${esc(a.label)} <span class="pill">prefixo ${esc(a.prefix)}_</span></h3><p class="sub">${names.length} tabelas · ${fmt.int(totalRows)} linhas · pasta <code>data/silver/${esc(a.slug)}/</code> · referência ${esc(s.data_referencia)} · construída em ${new Date(s.built_at).toLocaleString('pt-BR')} · <a href="${a.pagina}">painel</a></p></div></header>
      ${diagram(tabelas, s.relacoes || [])}
      <h4 style="margin:14px 0 6px;font-size:15px">Tabelas e colunas</h4>${details}
      <h4 style="margin:18px 0 6px;font-size:15px">Relações</h4><table class="model-table"><thead><tr><th>De</th><th>Para</th><th>Chave</th><th>Cardinalidade</th></tr></thead><tbody>${rel}</tbody></table></div>`;
  }).join('');
}
const rank = n => (n.endsWith('_deposito') ? 0 : n.endsWith('_situacao') ? 1 : n.startsWith('dim_') ? 3 : 2);

fetch('./data/modelo_geral.json').then(r => r.json()).then(m => { renderFonte(m); renderModelo(m); })
  .catch(err => { document.getElementById('modelo-ativos').innerHTML = `<p class="prose">Não foi possível carregar <code>modelo_geral.json</code> (${esc(err.message)}). Rode <code>uv run badepi gold</code>.</p>`; });
