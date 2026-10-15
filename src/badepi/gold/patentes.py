"""Gold — Patentes: agregações em JSON consumidas pelo dashboard (docs/data/patentes/)."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..config import BADEPI_VERSION, DOCS_DATA_DIR, GOLD_DIR, SOURCES
from ..ioutil import read_json, read_parquet
from . import common as C
from .common import ANO_FIM, ANO_INI, ANOS, CATEGORIA_LABEL, pct, q, serie, year

log = logging.getLogger(__name__)
SRC = SOURCES["patentes"]


def serie_depositos(df: pd.DataFrame) -> dict:
    out = C.serie_base(df)
    g = df.groupby("ano", observed=True)
    out.update({
        "natureza": {k: serie(df[df["natureza"] == k].groupby("ano").size()) for k in ["PI", "MU", "CA"]},
        "via": {k: serie(df[df["via"] == k].groupby("ano").size()) for k in ["PCT", "Direta"]},
        "com_prioridade": serie(df[df["tem_prioridade"] == True].groupby("ano").size()),  # noqa: E712
        "media_inventores": [round(float(v), 2) for v in g["n_inventores"].mean().reindex(ANOS).fillna(0)],
    })
    return out


def serie_decisoes(df: pd.DataFrame, eventos_ano: pd.DataFrame) -> dict:
    out = C.serie_decisoes(df, eventos_ano)
    out["concessoes_natureza"] = {k: serie(df[(df["natureza"] == k) & df["dt_concessao"].notna()].groupby(year(df["dt_concessao"]), observed=True).size()) for k in ["PI", "MU", "CA"]}
    return out


def campos_tec(df: pd.DataFrame, dim_campo: pd.DataFrame) -> dict:
    conc = df["dt_concessao"].notna(); res = df["residente"] == True  # noqa: E712
    setores = []
    for setor, dc in dim_campo.groupby("setor", sort=False):
        campos = []
        for _, r in dc.iterrows():
            m = df["campo_tec_principal"] == r["campo_tec"]; sub = df[m]
            campos.append({"campo_tec": int(r["campo_tec"]), "nome": r["nome"], "total": int(m.sum()), "concedidos": int((m & conc).sum()), "residentes": int((m & res).sum()),
                           "serie": serie(sub.groupby("ano").size()), "serie_residentes": serie(sub[sub["residente"] == True].groupby("ano").size()),  # noqa: E712
                           "serie_concessoes": serie(sub.dropna(subset=["dt_concessao"]).groupby(year(sub["dt_concessao"].dropna())).size())})
        ms = df["setor_principal"] == setor
        setores.append({"setor": setor, "total": int(ms.sum()), "concedidos": int((ms & conc).sum()), "residentes": int((ms & res).sum()), "serie": serie(df[ms].groupby("ano").size()), "campos": campos})
    sem = df["campo_tec_principal"].isna()
    return {"anos": ANOS, "setores": setores, "sem_classificacao": int(sem.sum()), "sem_classificacao_serie": serie(df[sem].groupby("ano").size())}


def ipc_secoes(df: pd.DataFrame) -> dict:
    nomes = {"A": "Necessidades humanas", "B": "Operações e transporte", "C": "Química e metalurgia", "D": "Têxteis e papel", "E": "Construções fixas",
             "F": "Engenharia mecânica, iluminação, aquecimento, armas", "G": "Física", "H": "Eletricidade"}
    tab = pd.crosstab(df["ano"], df["secao_ipc_principal"]).reindex(index=ANOS, columns=list(nomes), fill_value=0)
    return {"anos": ANOS, "secoes": [{"secao": s, "nome": nomes[s], "serie": [int(v) for v in tab[s]], "total": int(tab[s].sum())} for s in nomes]}


def genero(df: pd.DataFrame, inv_gen, dpt_gen) -> dict:
    out = C.genero_depositantes(df, dpt_gen)
    out["disponivel"] = inv_gen is not None
    if inv_gen is None:
        return out
    g = inv_gen.merge(df[["no_pedido", "ano", "categoria_origem", "setor_principal", "campo_tec_principal"]], on="no_pedido", how="inner")
    tab = pd.crosstab(g["ano"], g["sexo"]).reindex(index=ANOS, columns=["F", "M", "I"], fill_value=0)
    out["inventores"] = {s: [int(v) for v in tab[s]] for s in ["F", "M", "I"]}
    out["share_f_inventores"] = [pct(f, f + m) for f, m in zip(tab["F"], tab["M"])]
    ped = g.groupby("no_pedido").agg(tem_f=("sexo", lambda s: bool((s == "F").any())), ano=("ano", "first"))
    tab2 = pd.crosstab(ped["ano"], ped["tem_f"]).reindex(index=ANOS, fill_value=0)
    out["pedidos_com_inventora"] = [int(v) for v in tab2.get(True, pd.Series(0, index=ANOS))]
    out["pedidos_residentes_com_inventor"] = [int(v) for v in tab2.sum(axis=1)]
    shr = lambda sub: pct((sub["sexo"] == "F").sum(), sub["sexo"].isin(["F", "M"]).sum())  # noqa: E731
    out["share_f_por_setor"] = [{"setor": s, "share_f": shr(sub), "n": int(len(sub))} for s, sub in g.groupby("setor_principal", observed=True) if s is not pd.NA]
    out["share_f_por_categoria"] = [{"categoria": c, "label": CATEGORIA_LABEL.get(c, c), "share_f": shr(sub), "n": int(len(sub))} for c, sub in g.groupby("categoria_origem", observed=True) if c is not pd.NA]
    out["share_f_por_campo"] = [{"campo_tec": int(c), "share_f": shr(sub), "n": int(len(sub))} for c, sub in g.groupby("campo_tec_principal", observed=True) if c is not pd.NA]
    return out


def impacto(df: pd.DataFrame, eventos_ano: pd.DataFrame, dim_campo: pd.DataFrame, gen: dict, tempo: dict) -> dict:
    bl = C.backlog(df)
    res = df[df["residente"] == True]  # noqa: E712
    named = res[res["depositante_principal"].notna()]
    cat = pd.crosstab(named["ano"], named["categoria_origem"]).reindex(index=ANOS, fill_value=0); ident = cat.sum(axis=1)
    total_res = res.groupby("ano").size().reindex(ANOS, fill_value=0)
    ufs = pd.crosstab(res["ano"], res["uf_origem"]).reindex(index=ANOS, fill_value=0)
    nomes_campo = dict(zip(dim_campo["campo_tec"].astype(int), dim_campo["nome"])); setor_campo = dict(zip(dim_campo["campo_tec"].astype(int), dim_campo["setor"]))

    def crescimento(sub):
        t = pd.crosstab(sub["campo_tec_principal"].dropna().astype(int), sub.loc[sub["campo_tec_principal"].notna(), "ano"])
        base = t.loc[:, [a for a in range(2011, 2016) if a in t.columns]].mean(axis=1); rec = t.loc[:, [a for a in range(2021, 2026) if a in t.columns]].mean(axis=1)
        o = pd.DataFrame({"base": base, "recente": rec}); o = o[o["base"] >= 100]; o["variacao_pct"] = ((o["recente"] / o["base"]) - 1) * 100
        return [{"campo_tec": int(k), "nome": nomes_campo.get(int(k)), "setor": setor_campo.get(int(k)), "media_2011_2015": round(float(r["base"]), 1),
                 "media_2021_2025": round(float(r["recente"]), 1), "variacao_pct": round(float(r["variacao_pct"]), 1)} for k, r in o.sort_values("variacao_pct", ascending=False).iterrows()]

    ev = lambda e: serie(eventos_ano[eventos_ano["evento"] == e].set_index("ano_publicacao")["n"])  # noqa: E731
    conc = df.dropna(subset=["dt_concessao"]); conc_ano = year(conc["dt_concessao"])
    vig = (df["situacao"] == "Concedida") & (df["prazo_expirado"] == False)  # noqa: E712
    med = {r["ano"]: r["mediana"] for r in tempo["por_ano"] if r["n"] >= 1000}
    pior = max(med, key=lambda a: med[a] or 0)
    return {
        "anos": ANOS, "backlog_fim_ano": bl,
        "share_academia_residentes": [pct(cat.loc[a].get("universidade", 0) + cat.loc[a].get("instituto_pesquisa", 0), ident.loc[a]) for a in ANOS],
        "share_universidades_residentes": [pct(cat.loc[a].get("universidade", 0), ident.loc[a]) for a in ANOS],
        "share_residentes_identificados": [pct(ident.loc[a], total_res.loc[a]) for a in ANOS],
        "ufs_com_50_ou_mais": [int((ufs.loc[a] >= 50).sum()) for a in ANOS],
        "share_sp_residentes": [pct(ufs.loc[a].get("SP", 0), ufs.loc[a].sum()) for a in ANOS],
        "share_sudeste_sul_residentes": [pct(sum(ufs.loc[a].get(u, 0) for u in ["SP", "RJ", "MG", "ES", "PR", "SC", "RS"]), ufs.loc[a].sum()) for a in ANOS],
        "crescimento_campos": crescimento(df), "crescimento_campos_residentes": crescimento(res),
        "tramite_prioritario_pedidos": ev("tramite_prioritario"), "oferta_licenca_pedidos": ev("licenca_oferta"), "transferencias_pedidos": ev("transferencia_alteracao"),
        "tempo_concessao": {"mediana_por_ano": med, "pior_ano": pior, "pior_mediana": med[pior], "ultimo_ano": ANO_FIM, "ultima_mediana": med.get(ANO_FIM)},
        "vigentes": {"total": int(vig.sum()), "residentes": int((vig & (df["residente"] == True)).sum()), "nao_residentes": int((vig & (df["residente"] == False)).sum()),  # noqa: E712
                     "por_setor": [{"setor": k, "n": int(v)} for k, v in df[vig]["setor_principal"].value_counts().items() if k is not pd.NA]},
        "share_mulheres_inventoras": gen.get("share_f_inventores"),
        "concessoes_residentes_serie": serie(conc[conc["residente"] == True].groupby(conc_ano[conc["residente"] == True]).size()),  # noqa: E712
        "concessoes_serie": serie(conc.groupby(conc_ano).size()),
    }


def resumo(df, manifest, gen, dep_json, pais_json, imp, tempo) -> dict:
    k = C.kpis_base(df, imp["backlog_fim_ano"], tempo)
    share_f = gen.get("share_f_inventores") or []
    ultimo = df[df["ano"] == ANO_FIM]
    k.update({"patentes_vigentes": k["vigentes"], "tempo_concessao_mediana_ultimo_ano": imp["tempo_concessao"]["ultima_mediana"],
              "tempo_concessao_pior_ano": imp["tempo_concessao"]["pior_ano"], "tempo_concessao_pior_mediana": imp["tempo_concessao"]["pior_mediana"],
              "n_paises": pais_json["n_paises"], "n_depositantes_distintos": dep_json["n_depositantes_distintos"],
              "share_pct_ultimo_ano": pct((ultimo["via"] == "PCT").sum(), len(ultimo)),
              "share_mulheres_inventoras_ultimo_ano": share_f[-1] if share_f else None, "share_mulheres_inventoras_primeiro_ano": share_f[0] if share_f else None,
              "n_inventores_linhas": int(df["n_inventores"].sum()), "share_academia_residentes_ultimo_ano": imp["share_academia_residentes"][-1]})
    return {"ativo": "patentes", "badepi_version": BADEPI_VERSION, "data_referencia": manifest.get("data_referencia"), "gerado_em": C.now_iso(),
            "periodo": [ANO_INI, ANO_FIM], "ano_ultimo": ANO_FIM, "kpis": k}


RELACOES = [
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


def build(force: bool = False):
    silver = SRC.silver_dir
    manifest_path = silver / "_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"silver de patentes ausente em {silver}. Rode 'badepi silver -s patentes'.")
    manifest = read_json(manifest_path)
    out_dirs = [GOLD_DIR / "patentes", DOCS_DATA_DIR / "patentes"]
    log.info("[patentes] carregando silver")
    dep = read_parquet(silver / "ptn_deposito.parquet"); sit = read_parquet(silver / "ptn_situacao.parquet")
    df = dep.merge(sit, on="no_pedido", how="left"); df = df[(df["ano"] >= ANO_INI) & (df["ano"] <= ANO_FIM)]
    referencia = pd.Timestamp(manifest["data_referencia"])
    dim_campo = read_parquet(silver / "dim_campo_tec.parquet"); dim_pais = read_parquet(silver / "dim_pais.parquet"); dim_uf = read_parquet(silver / "dim_uf.parquet")
    dim_desp = read_parquet(silver / "dim_despacho.parquet")
    dpt = read_parquet(silver / "ptn_depositante.parquet", columns=["no_pedido", "no_ordem", "nome", "nome_norm", "pais", "uf", "cidade", "categoria"])
    dpt1 = dpt.sort_values(["no_pedido", "no_ordem"]).drop_duplicates("no_pedido"); del dpt
    desp = read_parquet(silver / "ptn_despacho", columns=["no_pedido", "cd_despacho", "evento", "dt_publicacao", "no_rpi", "ano_publicacao"])
    eventos_ano = C.eventos_por_ano(desp[["no_pedido", "evento", "ano_publicacao"]])
    inv_gen = read_parquet(silver / "ptn_inventor_genero.parquet") if (silver / "ptn_inventor_genero.parquet").exists() else None
    dpt_gen = read_parquet(silver / "ptn_depositante_genero.parquet") if (silver / "ptn_depositante_genero.parquet").exists() else None

    log.info("[patentes] agregando")
    nomes_campo = dict(zip(dim_campo["campo_tec"].astype(int), dim_campo["nome"]))
    gen = genero(df, inv_gen, dpt_gen)
    dep_json = C.depositantes(df, dpt1, dim_pais)
    pais_json = C.paises(df, dim_pais)
    pri = df.dropna(subset=["pais_prioridade_principal"])["pais_prioridade_principal"].value_counts().head(15)
    nomes_pais = dict(zip(dim_pais["pais"], dim_pais["nome"]))
    pais_json["prioridade_top"] = [{"pais": k, "nome": nomes_pais.get(k, k), "n": int(v)} for k, v in pri.items()]
    tempo = C.tempo_concessao(df, {"setor": "setor_principal", "campo": "campo_tec_principal", "via": "via"})
    imp = impacto(df, eventos_ano, dim_campo, gen, tempo)
    examinado = df["dt_primeiro_parecer"].notna() | df["dt_deferimento"].notna() | df["dt_indeferimento"].notna()
    fun = C.funil(df, {"examinados": examinado})
    fun["etapas"] = ["Depositados", "Publicados", "Com exame técnico", "Decididos no mérito", "Concedidos", "Vigentes hoje"]
    uf_json = C.uf(df, dim_uf, top=("campo_tec_principal", nomes_campo))
    for u in uf_json["ufs"]:
        u["top_campos"] = [{"campo_tec": t["valor"], "nome": t["nome"], "n": t["n"]} for t in u.pop("top", [])]
    blocks = {
        "resumo": resumo(df, manifest, gen, dep_json, pais_json, imp, tempo),
        "serie_depositos": serie_depositos(df), "serie_decisoes": serie_decisoes(df, eventos_ano), "situacao_coorte": C.situacao_coorte(df),
        "tempo_concessao": tempo, "campos_tec": campos_tec(df, dim_campo), "ipc_secoes": ipc_secoes(df), "uf": uf_json, "paises": pais_json,
        "depositantes": dep_json, "municipios": C.municipios(df, dpt1), "genero": gen, "funil": fun, "impacto": imp,
        "ciclo_vida": C.ciclo_vida(df, referencia), "transicoes": C.transicoes(desp, df, dim_desp), "modelo": C.modelo(manifest, RELACOES),
    }
    return C.write_blocks(blocks, out_dirs, log, "patentes")
