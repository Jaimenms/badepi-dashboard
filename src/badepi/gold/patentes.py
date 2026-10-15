"""Gold — Patentes: agregações em JSON consumidas pelo dashboard.

Cada função recebe os DataFrames silver já carregados e devolve um objeto serializável.
Os arquivos são gravados em data/gold/patentes/ e copiados para docs/data/patentes/
(a pasta publicada no GitHub Pages).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import BADEPI_VERSION, DOCS_DATA_DIR, GOLD_DIR, SOURCES
from ..ioutil import read_json, read_parquet, write_json

log = logging.getLogger(__name__)
SRC = SOURCES["patentes"]
ANO_INI, ANO_FIM = 2000, 2025
ANOS = list(range(ANO_INI, ANO_FIM + 1))

SITUACAO_DETALHADA = [
    "Concedida (vigente)", "Concedida (prazo expirado)", "Extinta", "Deferida", "Em andamento",
    "Indeferida", "Arquivada", "Retirada", "Anulada",
]
CATEGORIAS = ["empresa", "pessoa_fisica", "universidade", "instituto_pesquisa", "governo", "pessoa_fisica_provavel",
              "nao_classificado", "nao_identificado"]
CATEGORIA_LABEL = {
    "empresa": "Empresas", "pessoa_fisica": "Pessoas físicas", "universidade": "Universidades",
    "instituto_pesquisa": "Institutos de pesquisa", "governo": "Governo", "pessoa_fisica_provavel": "Pessoas físicas (provável)",
    "nao_classificado": "Não classificado", "nao_identificado": "Não identificado (pedido ainda sigiloso)",
}
ACADEMIA = ["universidade", "instituto_pesquisa"]


# ----------------------------------------------------------------------------- utilidades
def _serie(s: pd.Series, index=ANOS) -> list[int]:
    """Série anual alinhada a ANOS (zeros onde não há dado)."""
    return [int(v) for v in s.reindex(index).fillna(0).tolist()]


def _year(s: pd.Series) -> pd.Series:
    return s.dt.year.astype("Int16")


def _pct(a, b) -> float | None:
    return round(float(a) / float(b) * 100, 1) if b else None


def _q(s: pd.Series, q: float) -> float | None:
    s = s.dropna().astype("float64")
    return round(float(s.quantile(q)), 2) if len(s) else None


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: (None if (v is pd.NA or (isinstance(v, float) and np.isnan(v))) else v) for k, v in r.items()}
            for r in df.to_dict(orient="records")]


# ----------------------------------------------------------------------------- blocos
def serie_depositos(df: pd.DataFrame) -> dict:
    g = df.groupby("ano", observed=True)
    res = df[df["residente"] == True]  # noqa: E712
    gres = res.groupby("ano", observed=True)
    out = {
        "anos": ANOS,
        "total": _serie(g.size()),
        "natureza": {k: _serie(df[df["natureza"] == k].groupby("ano").size()) for k in ["PI", "MU", "CA"]},
        "residente": _serie(gres.size()),
        "nao_residente": _serie(df[df["residente"] == False].groupby("ano").size()),  # noqa: E712
        "origem_nao_informada": _serie(df[df["pais_origem"].isna()].groupby("ano").size()),
        "via": {k: _serie(df[df["via"] == k].groupby("ano").size()) for k in ["PCT", "Direta"]},
        "categoria_residente": {k: _serie(res[res["categoria_origem"] == k].groupby("ano").size()) for k in CATEGORIAS},
        "categoria_label": CATEGORIA_LABEL,
        "com_prioridade": _serie(df[df["tem_prioridade"] == True].groupby("ano").size()),  # noqa: E712
        "media_inventores": [round(float(v), 2) for v in g["n_inventores"].mean().reindex(ANOS).fillna(0)],
        "media_depositantes": [round(float(v), 2) for v in g["n_depositantes"].mean().reindex(ANOS).fillna(0)],
    }
    return out


def serie_decisoes(df: pd.DataFrame, eventos_ano: pd.DataFrame) -> dict:
    """Decisões por ano de publicação (1ª ocorrência por pedido) + eventos por ano (pedidos distintos)."""
    def by_year(col):
        return _serie(df.dropna(subset=[col]).groupby(_year(df[col]), observed=True).size())
    ev = {e: _serie(eventos_ano[eventos_ano["evento"] == e].set_index("ano_publicacao")["n"]) for e in eventos_ano["evento"].unique()}
    return {
        "anos": ANOS,
        "concessoes": by_year("dt_concessao"),
        "deferimentos": by_year("dt_deferimento"),
        "indeferimentos": by_year("dt_indeferimento"),
        "publicacoes": by_year("dt_publicacao_pedido"),
        "primeiras_decisoes": by_year("dt_primeira_decisao"),
        "concessoes_residentes": _serie(df[(df["residente"] == True) & df["dt_concessao"].notna()].groupby(_year(df["dt_concessao"]), observed=True).size()),  # noqa: E712
        "concessoes_natureza": {k: _serie(df[(df["natureza"] == k) & df["dt_concessao"].notna()].groupby(_year(df["dt_concessao"]), observed=True).size()) for k in ["PI", "MU", "CA"]},
        "eventos_pedidos_distintos": ev,
    }


def situacao_coorte(df: pd.DataFrame) -> dict:
    sit = df["situacao"].astype("string")
    vig = (sit == "Concedida") & (df["prazo_expirado"] == False)  # noqa: E712
    exp = (sit == "Concedida") & (df["prazo_expirado"] == True)  # noqa: E712
    det = sit.mask(vig, "Concedida (vigente)").mask(exp, "Concedida (prazo expirado)")
    tab = pd.crosstab(df["ano"], det).reindex(index=ANOS, columns=SITUACAO_DETALHADA, fill_value=0)
    tot = det.value_counts().reindex(SITUACAO_DETALHADA, fill_value=0)
    res = df["residente"] == True  # noqa: E712
    tab_res = pd.crosstab(df.loc[res, "ano"], det[res]).reindex(index=ANOS, columns=SITUACAO_DETALHADA, fill_value=0)
    tab_nres = pd.crosstab(df.loc[~res, "ano"], det[~res]).reindex(index=ANOS, columns=SITUACAO_DETALHADA, fill_value=0)
    return {
        "anos": ANOS,
        "situacoes": SITUACAO_DETALHADA,
        "por_coorte": {c: [int(v) for v in tab[c]] for c in SITUACAO_DETALHADA},
        "por_coorte_residentes": {c: [int(v) for v in tab_res[c]] for c in SITUACAO_DETALHADA},
        "por_coorte_nao_residentes": {c: [int(v) for v in tab_nres[c]] for c in SITUACAO_DETALHADA},
        "total": {c: int(tot[c]) for c in SITUACAO_DETALHADA},
    }


def tempo_concessao(df: pd.DataFrame) -> dict:
    c = df.dropna(subset=["dt_concessao"]).copy()
    c["ano_concessao"] = _year(c["dt_concessao"])
    anos_c = sorted(int(a) for a in c["ano_concessao"].dropna().unique() if ANO_INI <= a <= ANO_FIM)
    por_ano = []
    for a, g in c.groupby("ano_concessao", observed=True):
        if a not in anos_c:
            continue
        if len(g) < 30:
            continue
        por_ano.append({"ano": int(a), "n": int(len(g)), "mediana": _q(g["anos_ate_concessao"], 0.5), "media": round(float(g["anos_ate_concessao"].astype("float64").mean()), 2),
                        "p25": _q(g["anos_ate_concessao"], 0.25), "p75": _q(g["anos_ate_concessao"], 0.75),
                        "mediana_residentes": _q(g.loc[g["residente"] == True, "anos_ate_concessao"], 0.5),  # noqa: E712
                        "mediana_nao_residentes": _q(g.loc[g["residente"] == False, "anos_ate_concessao"], 0.5)})  # noqa: E712
    rec = c[c["ano_concessao"] >= ANO_FIM - 4]
    por_setor = [{"setor": s, "n": int(len(g)), "mediana": _q(g["anos_ate_concessao"], 0.5)}
                 for s, g in rec.groupby("setor_principal", observed=True) if s is not pd.NA]
    por_campo = [{"campo_tec": int(k), "n": int(len(g)), "mediana": _q(g["anos_ate_concessao"], 0.5)}
                 for k, g in rec.groupby("campo_tec_principal", observed=True) if k is not pd.NA]
    por_via = [{"via": v, "n": int(len(g)), "mediana": _q(g["anos_ate_concessao"], 0.5)} for v, g in rec.groupby("via", observed=True)]
    # distribuição (histograma de anos) para concessões recentes
    bins = list(range(0, 21))
    hist = np.histogram(rec["anos_ate_concessao"].dropna().astype("float64").clip(0, 20), bins=bins + [100])[0]
    d = df.dropna(subset=["dt_primeira_decisao"]).copy()
    d["ano_decisao"] = _year(d["dt_primeira_decisao"])
    decisao_por_ano = [{"ano": int(a), "n": int(len(g)), "mediana": _q(g["anos_ate_decisao"], 0.5)}
                       for a, g in d.groupby("ano_decisao", observed=True) if ANO_INI <= a <= ANO_FIM]
    return {"por_ano": por_ano, "por_setor_recente": por_setor, "por_campo_recente": por_campo, "por_via_recente": por_via,
            "periodo_recente": [ANO_FIM - 4, ANO_FIM], "histograma_recente": {"bins": bins, "n": [int(v) for v in hist]},
            "primeira_decisao_por_ano": decisao_por_ano}


def campos_tec(df: pd.DataFrame, dim_campo: pd.DataFrame) -> dict:
    conc = df["dt_concessao"].notna()
    res = df["residente"] == True  # noqa: E712
    setores = []
    for setor, dc in dim_campo.groupby("setor", sort=False):
        campos = []
        for _, r in dc.iterrows():
            m = df["campo_tec_principal"] == r["campo_tec"]
            sub = df[m]
            campos.append({
                "campo_tec": int(r["campo_tec"]), "nome": r["nome"], "total": int(m.sum()), "concedidos": int((m & conc).sum()),
                "residentes": int((m & res).sum()), "serie": _serie(sub.groupby("ano").size()),
                "serie_residentes": _serie(sub[sub["residente"] == True].groupby("ano").size()),  # noqa: E712
                "serie_concessoes": _serie(sub.dropna(subset=["dt_concessao"]).groupby(_year(sub["dt_concessao"].dropna())).size()),
            })
        ms = df["setor_principal"] == setor
        setores.append({"setor": setor, "total": int(ms.sum()), "concedidos": int((ms & conc).sum()), "residentes": int((ms & res).sum()),
                        "serie": _serie(df[ms].groupby("ano").size()), "campos": campos})
    sem = df["campo_tec_principal"].isna()
    return {"anos": ANOS, "setores": setores, "sem_classificacao": int(sem.sum()),
            "sem_classificacao_serie": _serie(df[sem].groupby("ano").size())}


def ipc_secoes(df: pd.DataFrame) -> dict:
    nomes = {"A": "Necessidades humanas", "B": "Operações e transporte", "C": "Química e metalurgia", "D": "Têxteis e papel",
             "E": "Construções fixas", "F": "Engenharia mecânica, iluminação, aquecimento, armas", "G": "Física", "H": "Eletricidade"}
    tab = pd.crosstab(df["ano"], df["secao_ipc_principal"]).reindex(index=ANOS, columns=list(nomes), fill_value=0)
    return {"anos": ANOS, "secoes": [{"secao": s, "nome": nomes[s], "serie": [int(v) for v in tab[s]], "total": int(tab[s].sum())} for s in nomes]}


def uf(df: pd.DataFrame, dim_uf: pd.DataFrame, dim_campo: pd.DataFrame) -> dict:
    res = df[(df["residente"] == True) & df["uf_origem"].notna()]  # noqa: E712
    nomes_campo = dict(zip(dim_campo["campo_tec"].astype(int), dim_campo["nome"]))
    ufs = []
    for _, r in dim_uf.iterrows():
        sub = res[res["uf_origem"] == r["uf"]]
        conc = sub.dropna(subset=["dt_concessao"])
        top = sub["campo_tec_principal"].dropna().astype(int).value_counts().head(3)
        ufs.append({
            "uf": r["uf"], "nome": r["nome"], "regiao": r["regiao"], "codigo_ibge": r["codigo_ibge"],
            "total": int(len(sub)), "concedidos": int(len(conc)), "vigentes": int(((sub["situacao"] == "Concedida") & (sub["prazo_expirado"] == False)).sum()),  # noqa: E712
            "ultimo_ano": int((sub["ano"] == ANO_FIM).sum()),
            "serie": _serie(sub.groupby("ano").size()),
            "categorias": {k: int((sub["categoria_origem"] == k).sum()) for k in CATEGORIAS},
            "top_campos": [{"campo_tec": int(k), "nome": nomes_campo.get(int(k)), "n": int(v)} for k, v in top.items()],
        })
    regioes = [{"regiao": reg, "total": int(sum(u["total"] for u in ufs if u["regiao"] == reg)),
                "serie": [int(sum(u["serie"][i] for u in ufs if u["regiao"] == reg)) for i in range(len(ANOS))]}
               for reg in ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"]]
    return {"anos": ANOS, "ufs": ufs, "regioes": regioes, "residentes_sem_uf": int(((df["residente"] == True) & df["uf_origem"].isna()).sum())}  # noqa: E712


def paises(df: pd.DataFrame, dim_pais: pd.DataFrame, top_n: int = 25) -> dict:
    nomes = dict(zip(dim_pais["pais"], dim_pais["nome"]))
    d = df.dropna(subset=["pais_origem"])
    tot = d["pais_origem"].value_counts()
    top = tot.head(top_n)
    itens = []
    for pais, n in top.items():
        sub = d[d["pais_origem"] == pais]
        itens.append({"pais": pais, "nome": nomes.get(pais, pais), "total": int(n), "concedidos": int(sub["dt_concessao"].notna().sum()),
                      "serie": _serie(sub.groupby("ano").size()),
                      "share_pct": _pct(sub["via"].eq("PCT").sum(), len(sub))})
    outros = d[~d["pais_origem"].isin(top.index)]
    itens.append({"pais": "OUTROS", "nome": "Outros países", "total": int(len(outros)), "concedidos": int(outros["dt_concessao"].notna().sum()),
                  "serie": _serie(outros.groupby("ano").size()), "share_pct": _pct(outros["via"].eq("PCT").sum(), len(outros))})
    # prioridade unionista: país do primeiro depósito
    pri = df.dropna(subset=["pais_prioridade_principal"])["pais_prioridade_principal"].value_counts().head(15)
    return {"anos": ANOS, "paises": itens, "n_paises": int(tot.size),
            "prioridade_top": [{"pais": k, "nome": nomes.get(k, k), "n": int(v)} for k, v in pri.items()]}


def depositantes(df: pd.DataFrame, dpt1: pd.DataFrame, dim_pais: pd.DataFrame) -> dict:
    """dpt1: primeiro depositante de cada pedido (no_pedido, nome, nome_norm, pais, categoria)."""
    nomes_pais = dict(zip(dim_pais["pais"], dim_pais["nome"]))
    d = df.merge(dpt1[["no_pedido", "nome"]], on="no_pedido", how="left")
    d = d.dropna(subset=["depositante_principal"])
    display = d.groupby("depositante_principal", observed=True)["nome"].agg(lambda s: s.mode().iloc[0] if len(s.mode()) else s.iloc[0])

    def top(sub: pd.DataFrame, n: int) -> list[dict]:
        g = sub.groupby("depositante_principal", observed=True).agg(
            total=("no_pedido", "size"), concedidos=("dt_concessao", lambda s: int(s.notna().sum())),
            pais=("pais_origem", "first"), categoria=("categoria_origem", "first"),
            ultimo_ano=("ano", lambda s: int((s == ANO_FIM).sum())), primeiro_ano=("ano", "min"))
        g = g.sort_values("total", ascending=False).head(n)
        return [{"nome": display.get(k, k), "pais": r["pais"], "pais_nome": nomes_pais.get(r["pais"], r["pais"]),
                 "categoria": r["categoria"], "total": int(r["total"]), "concedidos": int(r["concedidos"]),
                 "ultimo_ano": int(r["ultimo_ano"]), "primeiro_ano": int(r["primeiro_ano"])} for k, r in g.iterrows()]

    res = d[d["residente"] == True]  # noqa: E712
    # corrida acumulada de depositantes residentes (top 12 a cada ano)
    cum = (res.groupby(["ano", "depositante_principal"], observed=True).size().unstack(fill_value=0)
           .reindex(ANOS, fill_value=0).cumsum())
    corrida = []
    for ano in ANOS:
        row = cum.loc[ano].sort_values(ascending=False).head(12)
        corrida.append({"ano": ano, "itens": [{"nome": display.get(k, k), "valor": int(v),
                                                "categoria": str(res.loc[res["depositante_principal"] == k, "categoria_origem"].iloc[0])} for k, v in row.items() if v > 0]})
    cat_ano = pd.crosstab(res["ano"], res["categoria_origem"]).reindex(index=ANOS, columns=CATEGORIAS, fill_value=0)
    return {
        "anos": ANOS,
        "top_geral": top(d, 30),
        "top_residentes": top(res, 30),
        "top_universidades": top(res[res["categoria_origem"] == "universidade"], 20),
        "top_empresas_residentes": top(res[res["categoria_origem"] == "empresa"], 20),
        "top_institutos": top(res[res["categoria_origem"] == "instituto_pesquisa"], 15),
        "corrida_residentes": corrida,
        "categoria_residente_por_ano": {k: [int(v) for v in cat_ano[k]] for k in CATEGORIAS},
        "categoria_label": CATEGORIA_LABEL,
        "n_depositantes_distintos": int(d["depositante_principal"].nunique()),
        "n_depositantes_residentes_distintos": int(res["depositante_principal"].nunique()),
    }


def municipios(df: pd.DataFrame, dpt1: pd.DataFrame, top_n: int = 40) -> dict:
    d = df[df["residente"] == True].merge(dpt1[["no_pedido", "cidade", "uf"]], on="no_pedido", how="left")  # noqa: E712
    d = d.dropna(subset=["cidade", "uf"])
    d["cidade"] = d["cidade"].str.title()
    g = d.groupby(["cidade", "uf"], observed=True).agg(total=("no_pedido", "size"), concedidos=("dt_concessao", lambda s: int(s.notna().sum())),
                                                        ultimo_ano=("ano", lambda s: int((s == ANO_FIM).sum())),
                                                        universidades=("categoria_origem", lambda s: int((s == "universidade").sum())))
    g = g.sort_values("total", ascending=False).head(top_n).reset_index()
    return {"municipios": _records(g), "n_municipios": int(d.groupby(["cidade", "uf"]).ngroups)}


def genero(df: pd.DataFrame, inv_gen: pd.DataFrame | None, dpt_gen: pd.DataFrame | None) -> dict:
    out: dict = {"anos": ANOS, "disponivel": inv_gen is not None}
    if inv_gen is None:
        return out
    g = inv_gen.merge(df[["no_pedido", "ano", "categoria_origem", "setor_principal", "campo_tec_principal"]], on="no_pedido", how="inner")
    tab = pd.crosstab(g["ano"], g["sexo"]).reindex(index=ANOS, columns=["F", "M", "I"], fill_value=0)
    out["inventores"] = {s: [int(v) for v in tab[s]] for s in ["F", "M", "I"]}
    out["share_f_inventores"] = [_pct(f, f + m) for f, m in zip(tab["F"], tab["M"])]
    # pedidos com ao menos uma inventora
    ped = g.groupby("no_pedido").agg(tem_f=("sexo", lambda s: bool((s == "F").any())), ano=("ano", "first"))
    tab2 = pd.crosstab(ped["ano"], ped["tem_f"]).reindex(index=ANOS, fill_value=0)
    out["pedidos_com_inventora"] = [int(v) for v in tab2.get(True, pd.Series(0, index=ANOS))]
    out["pedidos_residentes_com_inventor"] = [int(v) for v in tab2.sum(axis=1)]
    out["share_f_por_setor"] = [{"setor": s, "share_f": _pct((sub["sexo"] == "F").sum(), (sub["sexo"].isin(["F", "M"])).sum()), "n": int(len(sub))}
                                for s, sub in g.groupby("setor_principal", observed=True) if s is not pd.NA]
    out["share_f_por_categoria"] = [{"categoria": c, "label": CATEGORIA_LABEL.get(c, c), "share_f": _pct((sub["sexo"] == "F").sum(), (sub["sexo"].isin(["F", "M"])).sum()), "n": int(len(sub))}
                                    for c, sub in g.groupby("categoria_origem", observed=True) if c is not pd.NA]
    out["share_f_por_campo"] = [{"campo_tec": int(c), "share_f": _pct((sub["sexo"] == "F").sum(), (sub["sexo"].isin(["F", "M"])).sum()), "n": int(len(sub))}
                                for c, sub in g.groupby("campo_tec_principal", observed=True) if c is not pd.NA]
    if dpt_gen is not None:
        d = dpt_gen.merge(df[["no_pedido", "ano"]], on="no_pedido", how="inner")
        tab = pd.crosstab(d["ano"], d["sexo"]).reindex(index=ANOS, columns=["F", "M", "I"], fill_value=0)
        out["depositantes_pf"] = {s: [int(v) for v in tab[s]] for s in ["F", "M", "I"]}
        out["share_f_depositantes"] = [_pct(f, f + m) for f, m in zip(tab["F"], tab["M"])]
    return out


def funil(df: pd.DataFrame) -> dict:
    g = df.groupby("ano", observed=True)
    vig = (df["situacao"] == "Concedida") & (df["prazo_expirado"] == False)  # noqa: E712
    examinado = df["dt_primeiro_parecer"].notna() | df["dt_deferimento"].notna() | df["dt_indeferimento"].notna()
    decidido = df["dt_deferimento"].notna() | df["dt_indeferimento"].notna() | df["dt_concessao"].notna()
    return {
        "anos": ANOS,
        "etapas": ["Depositados", "Publicados", "Com exame técnico", "Decididos no mérito", "Concedidos", "Vigentes hoje"],
        "depositados": _serie(g.size()),
        "publicados": _serie(df[df["dt_publicado"].notna()].groupby("ano").size()),
        "examinados": _serie(df[examinado].groupby("ano").size()),
        "decididos": _serie(df[decidido].groupby("ano").size()),
        "concedidos": _serie(df[df["dt_concessao"].notna()].groupby("ano").size()),
        "vigentes": _serie(df[vig].groupby("ano").size()),
        "arquivados": _serie(df[df["situacao"] == "Arquivada"].groupby("ano").size()),
        "indeferidos": _serie(df[df["situacao"] == "Indeferida"].groupby("ano").size()),
    }


def impacto(df: pd.DataFrame, eventos_ano: pd.DataFrame, dim_campo: pd.DataFrame, gen: dict) -> dict:
    # estoque pendente (sem decisão de mérito) ao final de cada ano
    decisao = df[["dt_deferimento", "dt_indeferimento", "dt_arquivamento", "dt_concessao", "dt_extincao"]].min(axis=1)
    entrada = df["dt_entrada_inpi"]
    backlog = []
    for a in ANOS:
        fim = pd.Timestamp(year=a, month=12, day=31)
        pend = (entrada <= fim) & (decisao.isna() | (decisao > fim))
        backlog.append(int(pend.sum()))
    res = df[df["residente"] == True]  # noqa: E712
    # parcelas por categoria só fazem sentido entre pedidos já publicados (com nome do depositante conhecido)
    named = res[res["depositante_principal"].notna()]
    cat = pd.crosstab(named["ano"], named["categoria_origem"]).reindex(index=ANOS, fill_value=0)
    ident = cat.sum(axis=1)
    total_res = res.groupby("ano").size().reindex(ANOS, fill_value=0)
    share_univ = [_pct(cat.loc[a].get("universidade", 0) + cat.loc[a].get("instituto_pesquisa", 0), ident.loc[a]) for a in ANOS]
    share_univ_only = [_pct(cat.loc[a].get("universidade", 0), ident.loc[a]) for a in ANOS]
    share_identificados = [_pct(ident.loc[a], total_res.loc[a]) for a in ANOS]
    ufs = pd.crosstab(res["ano"], res["uf_origem"]).reindex(index=ANOS, fill_value=0)
    ufs_ativas = [int((ufs.loc[a] >= 50).sum()) for a in ANOS]
    share_sp = [_pct(ufs.loc[a].get("SP", 0), ufs.loc[a].sum()) for a in ANOS]
    share_sudeste_sul = [_pct(sum(ufs.loc[a].get(u, 0) for u in ["SP", "RJ", "MG", "ES", "PR", "SC", "RS"]), ufs.loc[a].sum()) for a in ANOS]

    # crescimento por campo (média 2021-2025 vs 2011-2015)
    nomes_campo = dict(zip(dim_campo["campo_tec"].astype(int), dim_campo["nome"]))
    setor_campo = dict(zip(dim_campo["campo_tec"].astype(int), dim_campo["setor"]))
    def crescimento(sub: pd.DataFrame) -> list[dict]:
        t = pd.crosstab(sub["campo_tec_principal"].dropna().astype(int), sub.loc[sub["campo_tec_principal"].notna(), "ano"])
        base = t.loc[:, [a for a in range(2011, 2016) if a in t.columns]].mean(axis=1)
        rec = t.loc[:, [a for a in range(2021, 2026) if a in t.columns]].mean(axis=1)
        out = pd.DataFrame({"base": base, "recente": rec})
        out = out[out["base"] >= 100]
        out["variacao_pct"] = ((out["recente"] / out["base"]) - 1) * 100
        out = out.sort_values("variacao_pct", ascending=False)
        return [{"campo_tec": int(k), "nome": nomes_campo.get(int(k)), "setor": setor_campo.get(int(k)),
                 "media_2011_2015": round(float(r["base"]), 1), "media_2021_2025": round(float(r["recente"]), 1),
                 "variacao_pct": round(float(r["variacao_pct"]), 1)} for k, r in out.iterrows()]

    tp = eventos_ano[eventos_ano["evento"] == "tramite_prioritario"].set_index("ano_publicacao")["n"]
    lic = eventos_ano[eventos_ano["evento"] == "licenca_oferta"].set_index("ano_publicacao")["n"]
    transf = eventos_ano[eventos_ano["evento"] == "transferencia_alteracao"].set_index("ano_publicacao")["n"]
    conc = df.dropna(subset=["dt_concessao"])
    conc_ano = _year(conc["dt_concessao"])
    vig = (df["situacao"] == "Concedida") & (df["prazo_expirado"] == False)  # noqa: E712
    vig_setor = df[vig]["setor_principal"].value_counts()
    vig_res = df[vig]["residente"].value_counts()
    t = tempo_concessao_resumo(conc, conc_ano)
    return {
        "anos": ANOS,
        "backlog_fim_ano": backlog,
        "share_academia_residentes": share_univ,
        "share_universidades_residentes": share_univ_only,
        "share_residentes_identificados": share_identificados,
        "ufs_com_50_ou_mais": ufs_ativas,
        "share_sp_residentes": share_sp,
        "share_sudeste_sul_residentes": share_sudeste_sul,
        "crescimento_campos": crescimento(df),
        "crescimento_campos_residentes": crescimento(res),
        "tramite_prioritario_pedidos": _serie(tp),
        "oferta_licenca_pedidos": _serie(lic),
        "transferencias_pedidos": _serie(transf),
        "tempo_concessao": t,
        "vigentes": {"total": int(vig.sum()), "residentes": int(vig_res.get(True, 0)), "nao_residentes": int(vig_res.get(False, 0)),
                     "por_setor": [{"setor": k, "n": int(v)} for k, v in vig_setor.items() if k is not pd.NA]},
        "share_mulheres_inventoras": gen.get("share_f_inventores"),
        "concessoes_residentes_serie": _serie(conc[conc["residente"] == True].groupby(conc_ano[conc["residente"] == True]).size()),  # noqa: E712
        "concessoes_serie": _serie(conc.groupby(conc_ano).size()),
    }


def tempo_concessao_resumo(conc: pd.DataFrame, conc_ano: pd.Series) -> dict:
    med = {int(a): _q(g["anos_ate_concessao"], 0.5) for a, g in conc.groupby(conc_ano, observed=True)
           if ANO_INI <= a <= ANO_FIM and len(g) >= 1000}
    pior_ano = max(med, key=lambda a: med[a] or 0)
    return {"mediana_por_ano": med, "pior_ano": pior_ano, "pior_mediana": med[pior_ano], "ultimo_ano": ANO_FIM, "ultima_mediana": med.get(ANO_FIM)}


def resumo(df: pd.DataFrame, manifest: dict, gen: dict, dep_json: dict, pais_json: dict, imp: dict) -> dict:
    ultimo = df[df["ano"] == ANO_FIM]
    anterior = df[df["ano"] == ANO_FIM - 1]
    conc = df.dropna(subset=["dt_concessao"])
    conc_ultimo = conc[_year(conc["dt_concessao"]) == ANO_FIM]
    conc_anterior = conc[_year(conc["dt_concessao"]) == ANO_FIM - 1]
    vig = (df["situacao"] == "Concedida") & (df["prazo_expirado"] == False)  # noqa: E712
    share_f = gen.get("share_f_inventores") or []
    return {
        "badepi_version": BADEPI_VERSION,
        "data_referencia": manifest.get("data_referencia"),
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "periodo": [ANO_INI, ANO_FIM],
        "ano_ultimo": ANO_FIM,
        "kpis": {
            "pedidos_total": int(len(df)),
            "pedidos_ultimo_ano": int(len(ultimo)),
            "pedidos_variacao_pct": _pct(len(ultimo) - len(anterior), len(anterior)),
            "concessoes_total": int(len(conc)),
            "concessoes_ultimo_ano": int(len(conc_ultimo)),
            "concessoes_variacao_pct": _pct(len(conc_ultimo) - len(conc_anterior), len(conc_anterior)),
            "patentes_vigentes": int(vig.sum()),
            "share_residentes_total": _pct((df["residente"] == True).sum(), df["residente"].notna().sum()),  # noqa: E712
            "share_residentes_ultimo_ano": _pct((ultimo["residente"] == True).sum(), ultimo["residente"].notna().sum()),  # noqa: E712
            "tempo_concessao_mediana_ultimo_ano": imp["tempo_concessao"]["ultima_mediana"],
            "tempo_concessao_pior_ano": imp["tempo_concessao"]["pior_ano"],
            "tempo_concessao_pior_mediana": imp["tempo_concessao"]["pior_mediana"],
            "backlog_atual": imp["backlog_fim_ano"][-1],
            "backlog_pico": int(max(imp["backlog_fim_ano"])),
            "backlog_pico_ano": ANOS[int(np.argmax(imp["backlog_fim_ano"]))],
            "n_paises": pais_json["n_paises"],
            "n_depositantes_distintos": dep_json["n_depositantes_distintos"],
            "share_pct_ultimo_ano": _pct((ultimo["via"] == "PCT").sum(), len(ultimo)),
            "share_mulheres_inventoras_ultimo_ano": share_f[-1] if share_f else None,
            "share_mulheres_inventoras_primeiro_ano": share_f[0] if share_f else None,
            "n_inventores_linhas": int(df["n_inventores"].sum()),
            "share_academia_residentes_ultimo_ano": imp["share_academia_residentes"][-1],
        },
    }


def modelo(manifest: dict) -> dict:
    relacoes = [
        {"de": "ptn_depositante", "para": "ptn_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
        {"de": "ptn_inventor", "para": "ptn_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
        {"de": "ptn_despacho", "para": "ptn_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
        {"de": "ptn_ipc", "para": "ptn_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
        {"de": "ptn_pct", "para": "ptn_deposito", "chave": "no_pedido", "cardinalidade": "1:1"},
        {"de": "ptn_prioridade", "para": "ptn_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
        {"de": "ptn_situacao", "para": "ptn_deposito", "chave": "no_pedido", "cardinalidade": "1:1"},
        {"de": "ptn_inventor_genero", "para": "ptn_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
        {"de": "ptn_depositante_genero", "para": "ptn_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
        {"de": "ptn_ipc", "para": "dim_campo_tec", "chave": "campo_tec", "cardinalidade": "N:1"},
        {"de": "ptn_deposito", "para": "dim_campo_tec", "chave": "campo_tec_principal → campo_tec", "cardinalidade": "N:1"},
        {"de": "ptn_despacho", "para": "dim_despacho", "chave": "cd_despacho", "cardinalidade": "N:1"},
        {"de": "ptn_depositante", "para": "dim_pais", "chave": "pais", "cardinalidade": "N:1"},
        {"de": "ptn_depositante", "para": "dim_uf", "chave": "uf", "cardinalidade": "N:1"},
        {"de": "ptn_inventor", "para": "dim_pais", "chave": "pais", "cardinalidade": "N:1"},
        {"de": "ptn_inventor", "para": "dim_uf", "chave": "uf", "cardinalidade": "N:1"},
    ]
    return {"badepi_version": manifest.get("badepi_version"), "built_at": manifest.get("built_at"),
            "data_referencia": manifest.get("data_referencia"), "tabelas": manifest.get("tables", {}), "relacoes": relacoes}


# ----------------------------------------------------------------------------- build
def build(force: bool = False) -> list[Path]:
    silver = SRC.silver_dir
    manifest_path = silver / "_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"silver de patentes ausente em {silver}. Rode 'badepi silver -s patentes'.")
    manifest = read_json(manifest_path)
    out_dirs = [GOLD_DIR / "patentes", DOCS_DATA_DIR / "patentes"]

    log.info("[patentes] carregando silver")
    dep = read_parquet(silver / "ptn_deposito.parquet")
    sit = read_parquet(silver / "ptn_situacao.parquet")
    df = dep.merge(sit, on="no_pedido", how="left")
    df = df[(df["ano"] >= ANO_INI) & (df["ano"] <= ANO_FIM)]
    dim_campo = read_parquet(silver / "dim_campo_tec.parquet")
    dim_pais = read_parquet(silver / "dim_pais.parquet")
    dim_uf = read_parquet(silver / "dim_uf.parquet")
    dpt = read_parquet(silver / "ptn_depositante.parquet", columns=["no_pedido", "no_ordem", "nome", "nome_norm", "pais", "uf", "cidade", "categoria"])
    dpt1 = dpt.sort_values(["no_pedido", "no_ordem"]).drop_duplicates("no_pedido")
    del dpt
    desp = read_parquet(silver / "ptn_despacho", columns=["no_pedido", "evento", "ano_publicacao"])
    eventos_ano = (desp.drop_duplicates().groupby(["ano_publicacao", "evento"], observed=True).size().rename("n").reset_index())
    eventos_ano["ano_publicacao"] = eventos_ano["ano_publicacao"].astype(int)
    del desp
    inv_gen = read_parquet(silver / "ptn_inventor_genero.parquet") if (silver / "ptn_inventor_genero.parquet").exists() else None
    dpt_gen = read_parquet(silver / "ptn_depositante_genero.parquet") if (silver / "ptn_depositante_genero.parquet").exists() else None

    log.info("[patentes] agregando")
    gen = genero(df, inv_gen, dpt_gen)
    dep_json = depositantes(df, dpt1, dim_pais)
    pais_json = paises(df, dim_pais)
    imp = impacto(df, eventos_ano, dim_campo, gen)
    blocks = {
        "resumo": resumo(df, manifest, gen, dep_json, pais_json, imp),
        "serie_depositos": serie_depositos(df),
        "serie_decisoes": serie_decisoes(df, eventos_ano),
        "situacao_coorte": situacao_coorte(df),
        "tempo_concessao": tempo_concessao(df),
        "campos_tec": campos_tec(df, dim_campo),
        "ipc_secoes": ipc_secoes(df),
        "uf": uf(df, dim_uf, dim_campo),
        "paises": pais_json,
        "depositantes": dep_json,
        "municipios": municipios(df, dpt1),
        "genero": gen,
        "funil": funil(df),
        "impacto": imp,
        "modelo": modelo(manifest),
    }
    written = []
    for name, obj in blocks.items():
        for d in out_dirs:
            p = d / f"{name}.json"
            write_json(obj, p)
            written.append(p)
        log.info("[patentes] gold %s.json ok", name)
    return written
