# CLAUDE.md — guia para evoluir o badepi-dashboard

Este arquivo orienta quem (pessoa ou agente) for continuar o projeto. Ele explica o que existe, como foi construído
e quais decisões não são óbvias a partir do código. Leia também o `README.md` e a página `docs/como-usar.html`.

## O que é

Pipeline medalhão em Python (uv + pandas + pyarrow, **sem DuckDB** por decisão do autor) sobre os microdados do
**BADEPI v12** do INPI, mais um site estático (GitHub Pages, pasta `docs/`) com um painel por ativo de PI e uma página
inicial comparativa. Ativos com painel: patentes, marcas, desenhos industriais, indicações geográficas, programas de
computador. Na bronze (só download/extração): contratos de tecnologia, topografias de circuito integrado, PI e Gênero
(esta última é cruzada com patentes, marcas, desenhos e programas).

Site: https://jaimenms.github.io/badepi-dashboard/ · Repo: `git@github.com:Jaimenms/badepi-dashboard.git`

## Comandos

```bash
uv sync                                   # ambiente
uv run badepi bronze [-s <ativo>]         # baixa e extrai os zips (manifesto com SHA-256)
uv run badepi silver [-s <ativo>] [--force]
uv run badepi gold   [-s <ativo>]         # JSON em data/gold e docs/data + comparativo + modelo_geral
uv run pytest -q                          # testes unitários (sem dados)
python -m http.server -d docs 8000        # site local
gh workflow run "Publicar GitHub Pages"   # publicação é MANUAL (sem Actions automáticas, por cota)
```

Slugs: `patentes`, `marcas`, `desenho_industrial`, `indicacao_geografica`, `programa_computador`, `contratos`,
`topografia_ci`, `pi_genero`. Marcas é pesado (19 M despachos): silver ~1,5 min / 6 GB RAM; gold ~7 min / 6,7 GB.

## Estrutura

```
src/badepi/
  config.py             fontes (token do inpidrive + nome do zip), versão, diretórios, silver_ready por ativo
  bronze.py             download validado (zipfile.testzip; o servidor não manda Content-Length) + extração + manifesto
  ioutil.py             TranscodingReader (UTF-8 com fallback cp1252 linha a linha), read/iter_badepi_csv, ParquetSink, read_parquet
  silver/common.py      pessoa_base, transform_depositante (categoria por regex), derive_situacao (genérica), dim_despacho_from_parts
  silver/<ativo>.py     transformações por ativo (ver "despachos" abaixo)
  gold/common.py        serie_base, serie_decisoes, situacao_coorte, tempo_concessao, uf, paises, depositantes (com corrida),
                        municipios, genero, funil, backlog, ciclo_vida, transicoes, kpis_base, modelo, write_blocks
  gold/<ativo>.py       monta os blocos JSON do ativo; gold/comparativo.py gera comparativo.json e modelo_geral.json
  reference/            campos_tec.csv (35 campos OMPI), ufs.csv, paises.csv
docs/
  index.html            índice dos ativos + comparativos + aviso            (home.js)
  patentes.html …       um painel por ativo                                 (patentes.js, marcas.js, desenhos.js, ig.js, programas.js)
  como-usar.html        guia: fonte, arquitetura, modelo de dados de TODOS os ativos (gerado), pandas, método (guide.js)
  assets/js/viz.js      tema claro/escuro, tokens, base ECharts, registro de cards, vista em tabela, contadores, sparklines
  assets/js/shared.js   construtores comuns (mountCommon), nav/rodapé injetados (chrome), hero, KPIs, helpers
  assets/css/style.css  tokens, layout, componentes, cores por ativo
  data/<ativo>/*.json   gold publicada (versionada no git); data/geo/br_uf.json (IBGE, qualidade mínima)
tests/                  helpers de limpeza, derivação de situação, mapeamentos de despacho
```

## Como os assets do site foram criados (processo usado pelo Claude)

1. **Perfil da fonte antes de qualquer código.** Cada zip foi aberto e inspecionado: cabeçalhos, encoding (`file` + decodificação
   linha a linha), contagens, valores distintos, cobertura das chaves entre tabelas, datas-sentinela, dicionários XLSX. Vários
   defeitos só aparecem assim (encoding misto no mesmo arquivo, `DT_PEDIDO_ORIGEM` repetindo o número, pedidos em sigilo sem
   nome, despachos de marcas sem descrição, despachos de programas cobrindo só 2017–2023).
2. **Silver com contrato comum.** Todo ativo produz `<prefixo>_deposito` (fato), `<prefixo>_situacao` (derivada), tabelas N:1 e
   dimensões, com nomes de coluna harmonizados (`no_pedido`, `ano`, `dt_entrada_inpi`, `residente`, `pais_origem`, `uf_origem`,
   `categoria_origem`, `depositante_principal`, `situacao`, `dt_publicado`, `dt_concessao`, …). Isso é o que permite a gold e o
   site serem compartilhados entre ativos. Ao criar um ativo novo, respeite esse contrato.
3. **Gold = JSON pequenos por bloco**, um arquivo por card ou grupo de cards (`serie_depositos`, `situacao_coorte`,
   `ciclo_vida`, `transicoes`, …). Séries anuais são listas alinhadas a `anos` (2000–2025). Nada de dados brutos no site.
4. **Site sem build.** HTML estático + módulos ES; ECharts 5.6 e GSAP 3.12 via cdnjs (versões fixas; a 5.5.1 do ECharts não
   existe no cdnjs). Cada card é um `<article class="card" data-chart="id">` com `.chart`, `.table-view` e botão "Tabela";
   `register(id, build)` em `viz.js` associa um construtor que devolve `{option, table, after?}`. `mountCommon(d, cfg)` em
   `shared.js` registra os cards padrão que existirem na página (ids: `dep-origem`, `dep-categoria`, `imp-tempo`, `imp-backlog`,
   `imp-concessoes`, `sit-coorte`, `funil`, `eventos`, `tempo-hist`, `ciclo`, `transicoes`, `race`, `top-dep`, `paises-bar`,
   `paises-linhas`, `mapa`, `regioes`, `uf-ranking`, `municipios`, `gen-dep`). Cards específicos ficam no `<ativo>.js`.
5. **Regras de visualização** (skill `dataviz`): paleta categórica de 8 tons em ordem fixa, validada para daltonismo nos dois
   modos com `validate_palette.js`; páginas de ativo usam **rotações** dessa ordem (marcas +1, desenhos +2, programas +5,
   IG +6), também validadas; sequencial de um matiz (azul) para mapas; sem eixo duplo; legenda só com 2+ séries; vista em
   tabela em todo gráfico; modo escuro com valores próprios, não inversão; **eixos de tempo sempre nomeados** com o
   significado da data (`X.deposito`, `X.concessao`, `X.despacho`, `X.safra`, `X.decorrido` em `shared.js`).
6. **Cores por ativo.** `html[data-asset="…"]` no `<html>` de cada página define `--accent`, gradiente do hero e a ordem
   `--s1..--s8` (CSS), e `viz.js` rotaciona `t.series` pelo mesmo `data-asset`. Ao copiar o cabeçalho de uma página para criar
   outra, troque o `data-asset` (já aconteceu de ficar errado).
7. **Verificação visual obrigatória.** Depois de qualquer mudança no site, renderizar com Playwright usando o Chrome instalado
   (`channel="chrome"`), rolar a página inteira para disparar os gráficos preguiçosos, contar `.chart canvas` vs `[data-chart]`,
   coletar erros de console e **olhar as capturas** (fatiar em tiles de ~2000 px). Foi assim que se acharam legendas de séries
   ocultas, rótulos cortados, estouro de números grandes e o `data-asset` errado. O script de referência ficou fora do repo
   (scratchpad); recrie-o a partir desta descrição.
8. **Conteúdo honesto.** Cada card tem nota com o significado e as limitações (série truncada à esquerda, último ano parcial para
   PCT/Madri, heurísticas). A página inicial e o rodapé trazem o aviso de que o projeto é independente e que estatísticas
   oficiais devem vir do INPI.

## Despachos: o que foi curado à mão (não está na fonte)

- **Patentes**: 304 códigos com descrição na fonte; mapeamento código → evento em `silver/patentes.py` (`EVENTO_POR_CODIGO`,
  regex de anulação/retificação, prefixos). `15.21` "Numeração anulada" = depósito não efetivado → situação própria.
- **Marcas**: a fonte traz só o código (`DESP###` até 2013, `IPAS###` desde então, tabelas diferentes). Descrições dos
  códigos decisivos foram confirmadas em publicações da RPI (histórico de processos específicos) e inferidas pela cronologia;
  estão em `silver/marcas.py` (`CODIGOS`, com "(inferido)" onde não houve confirmação). O site da RPI estava fora do ar
  (503) na construção; vale conferir a tabela oficial de "Códigos e Abreviações" quando acessível.
- **Desenhos**: códigos antigos com descrição; sistema novo (fim de 2023) numérico sem descrição, inferido pela cronologia
  (`CODIGOS_NOVOS` em `silver/desenho_industrial.py`): 860 depósito, 158 registro, 870 prorrogação, 136 exigência,
  139 arquivamento, 270 petição deferida, 1214/1233/1252 via Haia.
- **Programas**: com descrição; 730/120 = certificado. Tabela cobre só 2017–2023 → situação "Sem despacho na base".
- **IG**: com descrição (`DS_SITUACAO_NV`).

## Derivações que o site mostra e como são calculadas

- `derive_situacao` (silver/common.py): última data de cada evento; ordem concessão → anulação/extinção → numeração anulada
  → retirada → indeferimento (salvo recurso provido) → arquivamento (salvo desarquivamento/restauração) → deferida → em andamento.
  Vigência: patentes 20/15 anos (PI, MU) do depósito; desenhos 25; marcas e IG sem prazo; programas 50 (irrelevante na base).
- `ciclo_vida` (gold/common.py): estado de cada pedido a cada 0,5 ano desde o protocolo, só com pedidos observáveis; numeração
  anulada fica fora. Desenhos renomeiam o primeiro estado (não há publicação antes do registro).
- `transicoes`: pares consecutivos de despachos por pedido, por safra; top-N códigos como nós, resto em "OUTROS".
- `backlog`: pedidos protocolados sem decisão (deferimento/indeferimento/arquivamento/concessão/extinção/desistência/numeração anulada)
  ao fim de cada ano — inclui tramitação normal; é a tendência que importa.
- Categoria do depositante: regex sobre nome normalizado + tipo F/J; sem nome (sigilo) → "nao_identificado".
- Origem do pedido = depositante de ordem 1 (manual do BADEPI). Em marcas `NO_ORDEM` vem vazio → tratado como 1.

## Para adicionar um ativo (ex.: contratos, topografias)

1. Perfilar a bronze (cabeçalhos, encodings, códigos de despacho, chaves).
2. `silver/<slug>.py` com `build(force)` seguindo `indicacao_geografica.py` (pequeno) ou `marcas.py` (em blocos); usar os
   blocos de `silver/common.py`; marcar `silver_ready=True` em `config.py`.
3. `gold/<slug>.py` apoiado em `gold/common.py`; incluir o ativo em `gold/comparativo.py` (`ATIVOS` e `ATIVOS_TODOS`).
4. `docs/<slug>.html` (copiar de uma página existente e **trocar `data-asset`**, título, textos) + `docs/assets/js/<slug>.js`
   chamando `chrome`, `mountCommon` e registrando os cards específicos; adicionar à `PAGES` em `shared.js`, ao card da home
   (`ICON/COLOR/DESC` em `home.js`) e, se usar cor própria, validar a rotação da paleta e acrescentar os tokens em `style.css`.
5. Rodar silver + gold, renderizar com Playwright, olhar as capturas, testar, commitar. Publicar manualmente.

## Decisões do autor a respeitar

- pandas + parquet, sem DuckDB; particionar só quando necessário (despachos de patentes e marcas, por ano de publicação).
- GitHub Pages como destino (não artifacts do Claude); publicação e CI **só por disparo manual** (cota de Actions).
- Marca do site é só "BADEPI" (sem logo). Página inicial = índice dos ativos + comparativo + aviso.
- Eixos de tempo sempre dizem qual data é. Impactos (tempo até decisão, estoque, vigentes, difusão regional, academia, gênero)
  são o fio condutor da página de patentes.
