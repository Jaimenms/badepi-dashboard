# badepi-dashboard

Pipeline **medalhão** (bronze → silver → gold) para os microdados do
[BADEPI](https://www.gov.br/inpi/pt-br/inpi-data/dados-e-series-temporais/badepi) — a Base de Dados
de Propriedade Intelectual do INPI — e um **dashboard publicado no GitHub Pages** com a leitura
visual do sistema brasileiro de patentes e do seu impacto.

- Site: https://jaimenms.github.io/badepi-dashboard/ (índice e comparativo) · [Patentes](https://jaimenms.github.io/badepi-dashboard/patentes.html) · [Marcas](https://jaimenms.github.io/badepi-dashboard/marcas.html) · [Desenhos industriais](https://jaimenms.github.io/badepi-dashboard/desenhos.html) · [Indicações geográficas](https://jaimenms.github.io/badepi-dashboard/indicacoes.html)
- Guia de uso e modelo de dados: https://jaimenms.github.io/badepi-dashboard/como-usar.html
- Versão da base: BADEPI **v12** (publicada em 13/10/2026, dados até 31/12/2025)

## O que tem aqui

| Camada | Onde | O que é |
|---|---|---|
| Bronze | `data/bronze/<ativo>/` | Os 8 zips do INPI (patentes, marcas, desenho industrial, indicação geográfica, contratos, programa de computador, topografia de CI, PI e gênero) baixados com validação de integridade e extraídos sem alteração, com manifesto (URL, SHA-256, tamanho, data). |
| Silver | `data/silver/<ativo>/` | Parquet tipado e relacionado, com o mesmo desenho em todos os ativos: um fato `<prefixo>_deposito` (1 linha por pedido, com origem e colunas derivadas), uma `<prefixo>_situacao` (situação derivada da cronologia dos despachos + marcos + tempos), depositantes, despachos (com evento derivado do código), classes e dimensões. Joins em pandas pela chave `no_pedido`. |
| Gold | `data/gold/<ativo>/` → `docs/data/<ativo>/` | Agregações em JSON pequenos: séries anuais, situação por safra, **ciclo de vida** (estado dos pedidos a cada meio ano desde o protocolo), tempo até concessão/registro, **grafo de transições entre despachos**, classes, UFs, países, depositantes, gênero, funil; mais `comparativo.json` para a página inicial. |
| Site | `docs/` | HTML/CSS/JS estático (ECharts + GSAP): página inicial com índice e comparativos, um painel por ativo, modo claro/escuro, vista em tabela em cada gráfico, eixos de tempo sempre nomeados (depósito, concessão, publicação do despacho…). |

Ativos com painel: **patentes**, **marcas**, **desenhos industriais** e **indicações geográficas** (+ a base "PI e Gênero"
cruzada com os três primeiros). Contratos, programas de computador e topografias estão na bronze.

## Rodando

Requisitos: Python 3.11+ e [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run badepi bronze                       # baixa e extrai os 8 zips (~500 MB; 3 GB extraídos)
uv run badepi bronze -s patentes -s pi_genero   # ou só o necessário para o painel
uv run badepi silver                       # CSV → parquet (patentes ≈1 min; marcas ≈1,5 min e 6 GB de RAM)
uv run badepi gold                         # parquet → JSON em data/gold e docs/data (+ comparativo)
python -m http.server -d docs 8000         # http://localhost:8000
```

`uv run badepi all` faz as três etapas para todos os ativos; use `-s <ativo>` para limitar. `--force` refaz uma camada já
construída; `BADEPI_DATA_DIR` muda a pasta dos dados. Testes: `uv run pytest`.

## Publicação

Push na `main` dispara `.github/workflows/pages.yml`, que publica a pasta `docs/` no GitHub Pages
(em *Settings → Pages* a origem deve ser **GitHub Actions**). Os JSON da gold ficam versionados em
`docs/data/`, então o site não depende de rodar o pipeline no CI.

## Despachos sem descrição

O BADEPI não traz a descrição dos despachos de **marcas** (códigos `DESP###` até 2013 e `IPAS###` desde então) nem dos
códigos novos de **desenhos industriais** (fim de 2023). Os códigos decisivos foram identificados em publicações da RPI e
pela cronologia dos processos e estão curados em `silver/marcas.py` e `silver/desenho_industrial.py` (tabela `dim_despacho`
de cada ativo marca os demais como "não documentado"). Detalhes no guia do site.

## Consultando a silver com pandas

```python
from badepi.ioutil import read_parquet
S = "data/silver/patentes"
dep = read_parquet(f"{S}/ptn_deposito.parquet")
sit = read_parquet(f"{S}/ptn_situacao.parquet")
df = dep.merge(sit, on="no_pedido")
df[df.residente].groupby("uf_origem").situacao.value_counts().unstack(fill_value=0)
```

`ptn_despacho` (3,9 milhões de linhas) é particionada por `ano_publicacao`; use
`read_parquet(path, filters=[("ano_publicacao", ">=", 2020)])` para ler só o necessário.
A descrição de todas as tabelas, colunas e regras de derivação está na página
[Como usar](https://jaimenms.github.io/badepi-dashboard/como-usar.html).

## Estrutura

```
src/badepi/            pacote Python (CLI: badepi)
├── config.py          fontes (8 zips do inpidrive), versão, diretórios
├── bronze.py          download com validação + extração + manifesto
├── ioutil.py          leitura dos CSV (encoding misto, ';', CRLF) e parquet/JSON
├── silver/            common.py (blocos compartilhados) + patentes.py, marcas.py, desenho_industrial.py, indicacao_geografica.py
├── gold/              common.py (agregações, ciclo de vida, transições) + um módulo por ativo + comparativo.py
└── reference/         campos tecnológicos OMPI, UFs, países
docs/                  site (GitHub Pages): index, patentes, marcas, desenhos, indicacoes, como-usar + docs/data/<ativo>/*.json
tests/                 testes unitários das transformações
```

## Fonte e licença

Dados: INPI — BADEPI v12 (uso para fins estatísticos; dados pessoais limitados conforme a LGPD).
Malha dos estados: IBGE. Código sob licença MIT.
