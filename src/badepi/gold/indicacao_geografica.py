"""Gold — Indicação Geográfica: agregações em JSON para docs/data/indicacao_geografica/."""

from __future__ import annotations

import logging

import pandas as pd

from ..config import BADEPI_VERSION, DOCS_DATA_DIR, GOLD_DIR, SOURCES
from ..ioutil import read_json, read_parquet
from . import common as C
from .common import ANO_FIM, ANO_INI, ANOS, pct, records, serie

log = logging.getLogger(__name__)
SRC = SOURCES["indicacao_geografica"]
RELACOES = [
    {"de": "ig_depositante", "para": "ig_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
    {"de": "ig_despacho", "para": "ig_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
    {"de": "ig_classificacao", "para": "ig_deposito", "chave": "no_pedido", "cardinalidade": "1:1"},
    {"de": "ig_situacao", "para": "ig_deposito", "chave": "no_pedido", "cardinalidade": "1:1"},
    {"de": "ig_despacho", "para": "dim_despacho", "chave": "cd_despacho", "cardinalidade": "N:1"},
    {"de": "ig_depositante", "para": "dim_pais", "chave": "pais", "cardinalidade": "N:1"},
    {"de": "ig_depositante", "para": "dim_uf", "chave": "uf", "cardinalidade": "N:1"},
]


def build(force: bool = False):
    silver = SRC.silver_dir
    manifest = read_json(silver / "_manifest.json")
    out_dirs = [GOLD_DIR / "indicacao_geografica", DOCS_DATA_DIR / "indicacao_geografica"]
    dep = read_parquet(silver / "ig_deposito.parquet"); sit = read_parquet(silver / "ig_situacao.parquet")
    df = dep.merge(sit, on="no_pedido", how="left"); df = df[(df["ano"] >= ANO_INI) & (df["ano"] <= ANO_FIM)]
    referencia = pd.Timestamp(manifest["data_referencia"])
    dim_pais = read_parquet(silver / "dim_pais.parquet"); dim_uf = read_parquet(silver / "dim_uf.parquet")
    dpt = read_parquet(silver / "ig_depositante.parquet", columns=["no_pedido", "no_ordem", "nome", "pais", "uf", "cidade"])
    dpt1 = dpt.sort_values(["no_pedido", "no_ordem"]).drop_duplicates("no_pedido")
    nomes_pais = dict(zip(dim_pais["pais"], dim_pais["nome"])); nomes_uf = dict(zip(dim_uf["uf"], dim_uf["nome"]))
    s = C.serie_base(df)
    s["tipo"] = {k: serie(df[df["tipo"] == k].groupby("ano").size()) for k in ["IP", "DO"]}
    s["wipo"] = {k: serie(df[df["classificacao_wipo"] == k].groupby("ano").size()) for k in df["classificacao_wipo"].dropna().unique()}
    tempo = C.tempo_concessao(df, {"tipo": "tipo", "wipo": "classificacao_wipo"}, min_n_ano=3)
    det = C.situacao_detalhada(df)
    k = C.kpis_base(df, None, tempo)
    k.update({"registradas": int((df["situacao"] == "Concedida").sum()), "do_registradas": int(((df["situacao"] == "Concedida") & (df["tipo_atual"] == "DO")).sum()),
              "ip_registradas": int(((df["situacao"] == "Concedida") & (df["tipo_atual"] == "IP")).sum()), "ufs_com_ig": int(df[df["situacao"] == "Concedida"]["uf_origem"].nunique()),
              "estrangeiras_registradas": int(((df["situacao"] == "Concedida") & (df["residente"] == False)).sum()),  # noqa: E712
              "tempo_registro_mediana_recente": tempo["por_ano"][-1]["mediana"] if tempo["por_ano"] else None})
    lista = df.merge(dpt1[["no_pedido", "nome", "cidade"]], on="no_pedido", how="left")
    lista = lista[["no_pedido", "nome_ig", "tipo_atual", "especie_atual", "ano", "situacao", "uf_origem", "pais_origem", "classificacao_wipo", "classe_produto_servico",
                   "nome", "cidade", "dt_entrada_inpi", "dt_concessao", "anos_ate_concessao"]].copy()
    lista["pais_nome"] = lista["pais_origem"].map(nomes_pais); lista["uf_nome"] = lista["uf_origem"].map(nomes_uf)
    for c in ["dt_entrada_inpi", "dt_concessao"]:
        lista[c] = lista[c].dt.strftime("%Y-%m-%d")
    lista = lista.sort_values(["ano", "nome_ig"], ascending=[False, True])
    wipo = df.groupby("classificacao_wipo", observed=True).agg(total=("no_pedido", "size"), registradas=("situacao", lambda s: int((s == "Concedida").sum()))).reset_index()
    blocks = {
        "resumo": {"ativo": "indicacao_geografica", "badepi_version": BADEPI_VERSION, "data_referencia": manifest.get("data_referencia"), "gerado_em": C.now_iso(), "periodo": [ANO_INI, ANO_FIM], "ano_ultimo": ANO_FIM, "kpis": k},
        "serie_depositos": s, "serie_decisoes": C.serie_decisoes(df, None), "situacao_coorte": C.situacao_coorte(df), "tempo_registro": tempo,
        "uf": C.uf(df, dim_uf, top=("classificacao_wipo", {})), "paises": C.paises(df, dim_pais, top_n=12),
        "wipo": {"categorias": records(wipo.sort_values("total", ascending=False))},
        "lista": {"colunas": list(lista.columns), "itens": records(lista)}, "funil": C.funil(df), "ciclo_vida": C.ciclo_vida(df, referencia, max_anos=10),
        "modelo": C.modelo(manifest, RELACOES),
    }
    blocks["funil"]["etapas"] = ["Depositados", "Publicados", "Decididos", "Registrados", "Vigentes hoje"]
    return C.write_blocks(blocks, out_dirs, log, "indicacao_geografica")
