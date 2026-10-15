"""Gold — Programa de Computador: agregações em JSON para docs/data/programa_computador/."""

from __future__ import annotations

import logging

import pandas as pd

from ..config import BADEPI_VERSION, DOCS_DATA_DIR, GOLD_DIR, SOURCES
from ..ioutil import read_json, read_parquet
from . import common as C
from .common import ANO_FIM, ANO_INI, ANOS, pct, records, serie

log = logging.getLogger(__name__)
SRC = SOURCES["programa_computador"]
RELACOES = [
    {"de": "prg_depositante", "para": "prg_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
    {"de": "prg_autor", "para": "prg_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
    {"de": "prg_tipo", "para": "prg_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
    {"de": "prg_despacho", "para": "prg_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
    {"de": "prg_situacao", "para": "prg_deposito", "chave": "no_pedido", "cardinalidade": "1:1"},
    {"de": "prg_depositante_genero", "para": "prg_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
    {"de": "prg_tipo", "para": "dim_tipo_programa", "chave": "cd_tipo", "cardinalidade": "N:1"},
    {"de": "prg_despacho", "para": "dim_despacho", "chave": "cd_despacho", "cardinalidade": "N:1"},
    {"de": "prg_depositante", "para": "dim_pais", "chave": "pais", "cardinalidade": "N:1"},
    {"de": "prg_depositante", "para": "dim_uf", "chave": "uf", "cardinalidade": "N:1"},
    {"de": "prg_autor", "para": "dim_uf", "chave": "uf", "cardinalidade": "N:1"},
]


def build(force: bool = False):
    silver = SRC.silver_dir
    manifest = read_json(silver / "_manifest.json")
    out_dirs = [GOLD_DIR / "programa_computador", DOCS_DATA_DIR / "programa_computador"]
    dep = read_parquet(silver / "prg_deposito.parquet"); sit = read_parquet(silver / "prg_situacao.parquet")
    df = dep.merge(sit, on="no_pedido", how="left"); df = df[(df["ano"] >= ANO_INI) & (df["ano"] <= ANO_FIM)]
    dim_pais = read_parquet(silver / "dim_pais.parquet"); dim_uf = read_parquet(silver / "dim_uf.parquet"); dim_tipo = read_parquet(silver / "dim_tipo_programa.parquet")
    dpt = read_parquet(silver / "prg_depositante.parquet", columns=["no_pedido", "no_ordem", "nome", "pais", "uf", "cidade"])
    dpt1 = dpt.sort_values(["no_pedido", "no_ordem"]).drop_duplicates("no_pedido")
    aut = read_parquet(silver / "prg_autor.parquet", columns=["no_pedido", "uf", "pais", "tipo_pessoa"])
    tipo = read_parquet(silver / "prg_tipo.parquet")
    desp = read_parquet(silver / "prg_despacho.parquet", columns=["no_pedido", "evento", "ano_publicacao"])
    eventos_ano = C.eventos_por_ano(desp)
    dpt_gen = read_parquet(silver / "prg_depositante_genero.parquet") if (silver / "prg_depositante_genero.parquet").exists() else None
    nomes_grupo = dict(zip(dim_tipo["grupo"], dim_tipo["nome_grupo"]))

    s = C.serie_base(df)
    s["pf_pj"] = {"Pessoa física": serie(df[df["tipo_pessoa_origem"] == "F"].groupby("ano").size()), "Pessoa jurídica": serie(df[df["tipo_pessoa_origem"] == "J"].groupby("ano").size())}
    s["media_autores"] = [round(float(v), 2) for v in df.groupby("ano")["n_autores"].mean().reindex(ANOS).fillna(0)]
    s["media_tipos"] = [round(float(v), 2) for v in df.groupby("ano")["n_tipos"].mean().reindex(ANOS).fillna(0)]
    s["com_despacho"] = serie(df[df["situacao"] != "Sem despacho na base"].groupby("ano").size())
    # tipos de programa: todos os tipos declarados (não só o principal)
    tt = tipo.merge(df[["no_pedido", "ano", "residente"]], on="no_pedido", how="inner")
    tab_g = pd.crosstab(tt["ano"], tt["nome_grupo"]).reindex(index=ANOS, fill_value=0)
    grupos = [{"grupo": ", ".join(sorted(sub["grupo"].dropna().unique())), "nome": nome, "total": int(len(sub)), "pedidos": int(sub["no_pedido"].nunique()),
               "serie": [int(v) for v in tab_g[nome]] if nome in tab_g.columns else [0] * len(ANOS)}
              for nome, sub in tt.groupby("nome_grupo", observed=True)]
    grupos.sort(key=lambda x: -x["total"])
    tipos_top = (tt.groupby(["cd_tipo", "nome_tipo", "nome_grupo"], observed=True).size().rename("n").reset_index().sort_values("n", ascending=False).head(40))
    tipos_json = {"anos": ANOS, "grupos": grupos, "tipos_top": records(tipos_top), "mencoes": int(len(tt)), "media_tipos_por_pedido": round(float(df["n_tipos"].mean()), 2)}
    # autores: por UF e média
    au = aut.merge(df[["no_pedido", "ano"]], on="no_pedido", how="inner")
    aut_uf = au[au["pais"] == "BR"]["uf"].value_counts()
    autores_json = {"mencoes": int(len(au)), "pedidos_com_autor": int(au["no_pedido"].nunique()), "media_por_pedido": round(float(df["n_autores"].mean()), 2),
                    "por_uf": [{"uf": k, "n": int(v)} for k, v in aut_uf.items()], "pf": int((au["tipo_pessoa"] == "F").sum()), "pj": int((au["tipo_pessoa"] == "J").sum()),
                    "distribuicao": {str(int(k)): int(v) for k, v in df["n_autores"].clip(upper=10).value_counts().sort_index().items()}}
    tempo = C.tempo_concessao(df, {"categoria": "categoria_origem"}, min_n_ano=30)
    k = C.kpis_base(df, None, tempo)
    sem = df["situacao"] == "Sem despacho na base"
    k.update({"certificados": int((df["situacao"].isin(["Concedida", "Extinta"])).sum()), "sem_despacho": int(sem.sum()),
              "share_pf_residentes": pct((df[df["residente"] == True]["tipo_pessoa_origem"] == "F").sum(), (df["residente"] == True).sum()),  # noqa: E712
              "share_academia": pct(df["categoria_origem"].isin(["universidade", "instituto_pesquisa"]).sum(), df["categoria_origem"].notna().sum()),
              "n_depositantes_distintos": int(df["depositante_principal"].nunique()), "n_autores_linhas": int(df["n_autores"].sum()),
              "dias_ate_certificado_mediana_recente": round(float(df[df["ano"] >= 2018]["anos_ate_concessao"].dropna().median() * 365.25), 1) if df[df["ano"] >= 2018]["anos_ate_concessao"].notna().any() else None,
              "cobertura_despachos_periodo": "2017–2023"})
    sc = C.situacao_coorte(df)
    sc["situacoes"] = sc["situacoes"] + ["Sem despacho na base"]
    for key, msk in [("por_coorte", pd.Series(True, index=df.index)), ("por_coorte_residentes", df["residente"] == True), ("por_coorte_nao_residentes", df["residente"] == False)]:  # noqa: E712
        sc[key]["Sem despacho na base"] = serie(df[sem & msk].groupby("ano").size())
    sc["total"]["Sem despacho na base"] = int(sem.sum())
    fun = C.funil(df); del fun["publicados"]; fun["etapas"] = ["Depositados", "Decididos", "Registrados (certificado)", "Vigentes hoje"]
    blocks = {
        "resumo": {"ativo": "programa_computador", "badepi_version": BADEPI_VERSION, "data_referencia": manifest.get("data_referencia"), "gerado_em": C.now_iso(), "periodo": [ANO_INI, ANO_FIM], "ano_ultimo": ANO_FIM, "kpis": k, "nota": manifest.get("nota")},
        "serie_depositos": s, "serie_decisoes": C.serie_decisoes(df, eventos_ano), "situacao_coorte": sc, "tempo_registro": tempo, "tipos": tipos_json, "autores": autores_json,
        "uf": C.uf(df, dim_uf, top=("nome_grupo_principal", {})), "paises": C.paises(df, dim_pais, top_n=10), "depositantes": C.depositantes(df, dpt1, dim_pais),
        "municipios": C.municipios(df, dpt1), "genero": C.genero_depositantes(df, dpt_gen), "funil": fun, "modelo": C.modelo(manifest, RELACOES),
    }
    return C.write_blocks(blocks, out_dirs, log, "programa_computador")
