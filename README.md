# badepi-dashboard

Pipeline **medalhão** (bronze → silver → gold) para os microdados do
[BADEPI](https://www.gov.br/inpi/pt-br/inpi-data/dados-e-series-temporais/badepi) — a Base de Dados
de Propriedade Intelectual do INPI — e um **dashboard publicado no GitHub Pages** com a leitura
visual do sistema brasileiro de patentes e do seu impacto.

- Site: https://jaimenms.github.io/badepi-dashboard/
- Guia de uso e modelo de dados: https://jaimenms.github.io/badepi-dashboard/como-usar.html
- Versão da base: BADEPI **v12** (publicada em 13/10/2026, dados até 31/12/2025)

## O que tem aqui

| Camada | Onde | O que é |
|---|---|---|
| Bronze | `data/bronze/<ativo>/` | Os 8 zips do INPI (patentes, marcas, desenho industrial, indicação geográfica, contratos, programa de computador, topografia de CI, PI e gênero) baixados com validação de integridade e extraídos sem alteração, com manifesto (URL, SHA-256, tamanho, data). |
| Silver | `data/silver/<ativo>/` | Parquet tipado e relacionado. Para **patentes**: 7 tabelas da fonte + `ptn_situacao` (situação derivada dos despachos) + tabelas de gênero + dimensões (campos tecnológicos OMPI, códigos de despacho, países, UFs). Joins em pandas pela chave `no_pedido`. |
| Gold | `data/gold/<ativo>/` → `docs/data/<ativo>/` | Agregações em JSON pequenos consumidas pelo dashboard (séries anuais, situação por safra, tempo até concessão, campos tecnológicos, UFs, países, depositantes, gênero, funil, indicadores de impacto). |
| Site | `docs/` | HTML/CSS/JS estático (ECharts + GSAP), modo claro/escuro, vista em tabela para cada gráfico. |

Foco atual: **patentes**. Os demais ativos já são baixados e extraídos (bronze); as camadas silver/gold
deles seguem o mesmo padrão e estão no roadmap.

## Rodando

Requisitos: Python 3.11+ e [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run badepi bronze                       # baixa e extrai os 8 zips (~500 MB; 3 GB extraídos)
uv run badepi bronze -s patentes -s pi_genero   # ou só o necessário para o painel
uv run badepi silver -s patentes           # CSV → parquet (≈1 min, pico de 2,6 GB de RAM)
uv run badepi gold -s patentes             # parquet → JSON em data/gold e docs/data
python -m http.server -d docs 8000         # http://localhost:8000
```

`uv run badepi all -s patentes -s pi_genero` faz as três etapas. `--force` refaz uma camada já
construída; `BADEPI_DATA_DIR` muda a pasta dos dados. Testes: `uv run pytest`.

## Publicação

Push na `main` dispara `.github/workflows/pages.yml`, que publica a pasta `docs/` no GitHub Pages
(em *Settings → Pages* a origem deve ser **GitHub Actions**). Os JSON da gold ficam versionados em
`docs/data/`, então o site não depende de rodar o pipeline no CI.

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
├── silver/patentes.py CSV → parquet relacionado + situação derivada + dimensões
├── gold/patentes.py   parquet → JSON do dashboard
└── reference/         campos tecnológicos OMPI, UFs, países
docs/                  site (GitHub Pages) + docs/data/*.json
tests/                 testes unitários das transformações
```

## Fonte e licença

Dados: INPI — BADEPI v12 (uso para fins estatísticos; dados pessoais limitados conforme a LGPD).
Malha dos estados: IBGE. Código sob licença MIT.
