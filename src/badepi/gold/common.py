"""Blocos de agregação compartilhados pelos ativos (patentes, marcas, DI, IG).

Todos recebem o "fato" do ativo: deposito ⨝ situacao (1 linha por pedido) com colunas harmonizadas
(no_pedido, ano, dt_entrada_inpi, residente, pais_origem, uf_origem, categoria_origem, depositante_principal,
situacao, dt_publicado, dt_concessao, dt_indeferimento, dt_arquivamento, dt_extincao, dt_desistencia,
dt_primeira_decisao, dt_fim_vigencia, prazo_expirado, anos_ate_concessao, anos_ate_decisao, ...).
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ..config import BADEPI_VERSION

ANO_INI, ANO_FIM = 2000, 2025
ANOS = list(range(ANO_INI, ANO_FIM + 1))

SITUACAO_DETALHADA = ["Concedida (vigente)", "Concedida (prazo expirado)", "Extinta", "Deferida", "Em andamento",
                      "Indeferida", "Arquivada", "Retirada", "Anulada"]
CATEGORIAS = ["empresa", "pessoa_fisica", "universidade", "instituto_pesquisa", "governo", "pessoa_fisica_provavel",
              "nao_classificado", "nao_identificado"]
CATEGORIA_LABEL = {
    "empresa": "Empresas", "pessoa_fisica": "Pessoas físicas", "universidade": "Universidades",
    "instituto_pesquisa": "Institutos de pesquisa", "governo": "Governo", "pessoa_fisica_provavel": "Pessoas físicas (provável)",
    "nao_classificado": "Não classificado", "nao_identificado": "Não identificado (pedido ainda sigiloso)",
}
ESTADOS_CICLO = ["Depositado (não publicado)", "Publicado / em exame", "Vigente", "Extinta ou expirada", "Indeferida", "Arquivada", "Retirada"]


# ----------------------------------------------------------------------------- utilidades
def serie(s: pd.Series, index=ANOS) -> list[int]:
    return [int(v) for v in s.reindex(index).fillna(0).tolist()]


def year(s: pd.Series) -> pd.Series:
    return s.dt.year.astype("Int16")


def pct(a, b) -> float | None:
    return round(float(a) / float(b) * 100, 1) if b else None


def q(s: pd.Series, qq: float) -> float | None:
    s = s.dropna().astype("float64")
    return round(float(s.quantile(qq)), 2) if len(s) else None


def records(df: pd.DataFrame) -> list[dict]:
    return [{k: (None if (v is pd.NA or (isinstance(v, float) and np.isnan(v))) else v) for k, v in r.items()}
            for r in df.to_dict(orient="records")]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ----------------------------------------------------------------------------- blocos
def serie_base(df: pd.DataFrame) -> dict:
    g = df.groupby("ano", observed=True)
    res = df[df["residente"] == True]  # noqa: E712
    return {
        "anos": ANOS, "total": serie(g.size()), "residente": serie(res.groupby("ano").size()),
        "nao_residente": serie(df[df["residente"] == False].groupby("ano").size()),  # noqa: E712
        "origem_nao_informada": serie(df[df["pais_origem"].isna()].groupby("ano").size()),
        "categoria_residente": {k: serie(res[res["categoria_origem"] == k].groupby("ano").size()) for k in CATEGORIAS},
        "categoria_label": CATEGORIA_LABEL,
        "media_depositantes": [round(float(v), 2) for v in g["n_depositantes"].mean().reindex(ANOS).fillna(0)] if "n_depositantes" in df else None,
    }


def serie_decisoes(df: pd.DataFrame, eventos_ano: pd.DataFrame | None) -> dict:
    def by_year(col):
        return serie(df.dropna(subset=[col]).groupby(year(df[col]), observed=True).size())
    out = {"anos": ANOS, "concessoes": by_year("dt_concessao"), "deferimentos": by_year("dt_deferimento"),
           "indeferimentos": by_year("dt_indeferimento"), "publicacoes": by_year("dt_publicado"),
           "primeiras_decisoes": by_year("dt_primeira_decisao"),
           "concessoes_residentes": serie(df[(df["residente"] == True) & df["dt_concessao"].notna()].groupby(year(df["dt_concessao"]), observed=True).size())}  # noqa: E712
    if eventos_ano is not None:
        out["eventos_pedidos_distintos"] = {e: serie(eventos_ano[eventos_ano["evento"] == e].set_index("ano_publicacao")["n"]) for e in eventos_ano["evento"].unique()}
    return out


def situacao_detalhada(df: pd.DataFrame) -> pd.Series:
    sit = df["situacao"].astype("string")
    vig = (sit == "Concedida") & (df["prazo_expirado"] == False)  # noqa: E712
    exp = (sit == "Concedida") & (df["prazo_expirado"] == True)  # noqa: E712
    return sit.mask(vig, "Concedida (vigente)").mask(exp, "Concedida (prazo expirado)")


def situacao_coorte(df: pd.DataFrame) -> dict:
    det = situacao_detalhada(df)
    res = df["residente"] == True  # noqa: E712
    def tab(mask):
        t = pd.crosstab(df.loc[mask, "ano"], det[mask]).reindex(index=ANOS, columns=SITUACAO_DETALHADA, fill_value=0)
        return {c: [int(v) for v in t[c]] for c in SITUACAO_DETALHADA}
    tot = det.value_counts().reindex(SITUACAO_DETALHADA, fill_value=0)
    return {"anos": ANOS, "situacoes": SITUACAO_DETALHADA, "por_coorte": tab(pd.Series(True, index=df.index)),
            "por_coorte_residentes": tab(res), "por_coorte_nao_residentes": tab(~res), "total": {c: int(tot[c]) for c in SITUACAO_DETALHADA}}


def tempo_concessao(df: pd.DataFrame, grupos: dict[str, str] | None = None, min_n_ano: int = 30) -> dict:
    """Tempo (anos) do protocolo até a concessão/registro por ano de concessão; `grupos` = {nome: coluna} para medianas recentes."""
    c = df.dropna(subset=["dt_concessao"]).copy()
    c["ano_concessao"] = year(c["dt_concessao"])
    por_ano = []
    for a, g in c.groupby("ano_concessao", observed=True):
        if not (ANO_INI <= a <= ANO_FIM) or len(g) < min_n_ano:
            continue
        por_ano.append({"ano": int(a), "n": int(len(g)), "mediana": q(g["anos_ate_concessao"], 0.5),
                        "media": round(float(g["anos_ate_concessao"].astype("float64").mean()), 2),
                        "p25": q(g["anos_ate_concessao"], 0.25), "p75": q(g["anos_ate_concessao"], 0.75),
                        "mediana_residentes": q(g.loc[g["residente"] == True, "anos_ate_concessao"], 0.5),  # noqa: E712
                        "mediana_nao_residentes": q(g.loc[g["residente"] == False, "anos_ate_concessao"], 0.5)})  # noqa: E712
    rec = c[c["ano_concessao"] >= ANO_FIM - 4]
    out = {"por_ano": por_ano, "periodo_recente": [ANO_FIM - 4, ANO_FIM]}
    for nome, col in (grupos or {}).items():
        out[f"por_{nome}_recente"] = [{"grupo": (int(k) if isinstance(k, (int, np.integer)) else str(k)), "n": int(len(g)), "mediana": q(g["anos_ate_concessao"], 0.5)}
                                      for k, g in rec.groupby(col, observed=True) if k is not pd.NA and len(g) >= 20]
    bins = list(range(0, 21))
    hist = np.histogram(rec["anos_ate_concessao"].dropna().astype("float64").clip(0, 20), bins=bins + [100])[0]
    out["histograma_recente"] = {"bins": bins, "n": [int(v) for v in hist]}
    d = df.dropna(subset=["dt_primeira_decisao"]).copy()
    d["ano_decisao"] = year(d["dt_primeira_decisao"])
    out["primeira_decisao_por_ano"] = [{"ano": int(a), "n": int(len(g)), "mediana": q(g["anos_ate_decisao"], 0.5)}
                                       for a, g in d.groupby("ano_decisao", observed=True) if ANO_INI <= a <= ANO_FIM and len(g) >= min_n_ano]
    return out


def uf(df: pd.DataFrame, dim_uf: pd.DataFrame, top: tuple[str, dict] | None = None) -> dict:
    """top = (coluna, {valor: nome}) para listar os 3 valores mais frequentes por UF (ex.: campo tecnológico, classe)."""
    res = df[(df["residente"] == True) & df["uf_origem"].notna()]  # noqa: E712
    ufs = []
    for _, r in dim_uf.iterrows():
        sub = res[res["uf_origem"] == r["uf"]]
        item = {"uf": r["uf"], "nome": r["nome"], "regiao": r["regiao"], "codigo_ibge": r["codigo_ibge"], "total": int(len(sub)),
                "concedidos": int(sub["dt_concessao"].notna().sum()),
                "vigentes": int(((sub["situacao"] == "Concedida") & (sub["prazo_expirado"] == False)).sum()),  # noqa: E712
                "ultimo_ano": int((sub["ano"] == ANO_FIM).sum()), "serie": serie(sub.groupby("ano").size()),
                "categorias": {k: int((sub["categoria_origem"] == k).sum()) for k in CATEGORIAS}}
        if top:
            col, nomes = top
            vc = sub[col].dropna().value_counts().head(3)
            item["top"] = [{"valor": (int(k) if isinstance(k, (int, np.integer)) else str(k)), "nome": nomes.get(k, str(k)), "n": int(v)} for k, v in vc.items()]
        ufs.append(item)
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
    for p, n in top.items():
        sub = d[d["pais_origem"] == p]
        itens.append({"pais": p, "nome": nomes.get(p, p), "total": int(n), "concedidos": int(sub["dt_concessao"].notna().sum()), "serie": serie(sub.groupby("ano").size())})
    outros = d[~d["pais_origem"].isin(top.index)]
    itens.append({"pais": "OUTROS", "nome": "Outros países", "total": int(len(outros)), "concedidos": int(outros["dt_concessao"].notna().sum()), "serie": serie(outros.groupby("ano").size())})
    return {"anos": ANOS, "paises": itens, "n_paises": int(tot.size)}


def depositantes(df: pd.DataFrame, dpt1: pd.DataFrame, dim_pais: pd.DataFrame, race: bool = True, top_n: int = 30) -> dict:
    nomes_pais = dict(zip(dim_pais["pais"], dim_pais["nome"]))
    d = df.merge(dpt1[["no_pedido", "nome"]], on="no_pedido", how="left").dropna(subset=["depositante_principal"])
    display = d.groupby("depositante_principal", observed=True)["nome"].agg(lambda s: s.mode().iloc[0] if len(s.mode()) else s.iloc[0])

    def top(sub: pd.DataFrame, n: int) -> list[dict]:
        g = sub.groupby("depositante_principal", observed=True).agg(
            total=("no_pedido", "size"), concedidos=("dt_concessao", lambda s: int(s.notna().sum())), pais=("pais_origem", "first"),
            categoria=("categoria_origem", "first"), ultimo_ano=("ano", lambda s: int((s == ANO_FIM).sum())), primeiro_ano=("ano", "min"))
        g = g.sort_values("total", ascending=False).head(n)
        return [{"nome": display.get(k, k), "pais": r["pais"], "pais_nome": nomes_pais.get(r["pais"], r["pais"]), "categoria": r["categoria"],
                 "total": int(r["total"]), "concedidos": int(r["concedidos"]), "ultimo_ano": int(r["ultimo_ano"]), "primeiro_ano": int(r["primeiro_ano"])}
                for k, r in g.iterrows()]

    res = d[d["residente"] == True]  # noqa: E712
    out = {"anos": ANOS, "top_geral": top(d, top_n), "top_residentes": top(res, top_n),
           "top_universidades": top(res[res["categoria_origem"] == "universidade"], 20),
           "top_empresas_residentes": top(res[res["categoria_origem"] == "empresa"], 20),
           "top_institutos": top(res[res["categoria_origem"] == "instituto_pesquisa"], 15),
           "top_nao_residentes": top(d[d["residente"] == False], 20),  # noqa: E712
           "categoria_label": CATEGORIA_LABEL, "n_depositantes_distintos": int(d["depositante_principal"].nunique()),
           "n_depositantes_residentes_distintos": int(res["depositante_principal"].nunique())}
    cat_ano = pd.crosstab(res["ano"], res["categoria_origem"]).reindex(index=ANOS, columns=CATEGORIAS, fill_value=0)
    out["categoria_residente_por_ano"] = {k: [int(v) for v in cat_ano[k]] for k in CATEGORIAS}
    if race:
        cum = (res.groupby(["ano", "depositante_principal"], observed=True).size().unstack(fill_value=0).reindex(ANOS, fill_value=0).cumsum())
        cat_of = res.drop_duplicates("depositante_principal").set_index("depositante_principal")["categoria_origem"]
        corrida = []
        for ano in ANOS:
            row = cum.loc[ano].sort_values(ascending=False).head(12)
            corrida.append({"ano": ano, "itens": [{"nome": display.get(k, k), "valor": int(v), "categoria": str(cat_of.get(k, ""))} for k, v in row.items() if v > 0]})
        out["corrida_residentes"] = corrida
    return out


def municipios(df: pd.DataFrame, dpt1: pd.DataFrame, top_n: int = 40) -> dict:
    d = df[df["residente"] == True].merge(dpt1[["no_pedido", "cidade", "uf"]], on="no_pedido", how="left").dropna(subset=["cidade", "uf"])  # noqa: E712
    d["cidade"] = d["cidade"].str.title()
    g = d.groupby(["cidade", "uf"], observed=True).agg(total=("no_pedido", "size"), concedidos=("dt_concessao", lambda s: int(s.notna().sum())),
                                                        ultimo_ano=("ano", lambda s: int((s == ANO_FIM).sum())),
                                                        universidades=("categoria_origem", lambda s: int((s == "universidade").sum())))
    g = g.sort_values("total", ascending=False).head(top_n).reset_index()
    return {"municipios": records(g), "n_municipios": int(d.groupby(["cidade", "uf"]).ngroups)}


def genero_depositantes(df: pd.DataFrame, dpt_gen: pd.DataFrame | None) -> dict:
    out: dict = {"anos": ANOS, "disponivel": dpt_gen is not None}
    if dpt_gen is None:
        return out
    d = dpt_gen.merge(df[["no_pedido", "ano"]], on="no_pedido", how="inner")
    tab = pd.crosstab(d["ano"], d["sexo"]).reindex(index=ANOS, columns=["F", "M", "I"], fill_value=0)
    out["depositantes_pf"] = {s: [int(v) for v in tab[s]] for s in ["F", "M", "I"]}
    out["share_f_depositantes"] = [pct(f, f + m) for f, m in zip(tab["F"], tab["M"])]
    return out


def funil(df: pd.DataFrame, etapas_extra: dict[str, pd.Series] | None = None) -> dict:
    g = df.groupby("ano", observed=True)
    vig = (df["situacao"] == "Concedida") & (df["prazo_expirado"] == False)  # noqa: E712
    decidido = df["dt_deferimento"].notna() | df["dt_indeferimento"].notna() | df["dt_concessao"].notna()
    out = {"anos": ANOS, "depositados": serie(g.size()), "publicados": serie(df[df["dt_publicado"].notna()].groupby("ano").size()),
           "decididos": serie(df[decidido].groupby("ano").size()), "concedidos": serie(df[df["dt_concessao"].notna()].groupby("ano").size()),
           "vigentes": serie(df[vig].groupby("ano").size()), "arquivados": serie(df[df["situacao"] == "Arquivada"].groupby("ano").size()),
           "indeferidos": serie(df[df["situacao"] == "Indeferida"].groupby("ano").size())}
    for k, mask in (etapas_extra or {}).items():
        out[k] = serie(df[mask].groupby("ano").size())
    return out


def backlog(df: pd.DataFrame) -> list[int]:
    """Pedidos protocolados e ainda sem decisão de mérito ao fim de cada ano."""
    decisao = df[["dt_deferimento", "dt_indeferimento", "dt_arquivamento", "dt_concessao", "dt_extincao", "dt_desistencia"]].min(axis=1)
    entrada = df["dt_entrada_inpi"]
    return [int(((entrada <= pd.Timestamp(year=a, month=12, day=31)) & (decisao.isna() | (decisao > pd.Timestamp(year=a, month=12, day=31)))).sum()) for a in ANOS]


def ciclo_vida(df: pd.DataFrame, referencia: pd.Timestamp, max_anos: int = 20, passo: float = 0.5) -> dict:
    """Estado de cada pedido em função do tempo decorrido desde o protocolo (ciclo de vida), por safra e no total.

    Só pedidos observáveis em cada ponto (protocolo + x ≤ data de referência) entram no denominador.
    """
    passos = np.round(np.arange(0, max_anos + 1e-9, passo), 2)
    t0 = df["dt_entrada_inpi"]
    yrs = lambda col: ((col - t0).dt.days / 365.25).to_numpy(dtype="float64", na_value=np.nan)  # noqa: E731
    sit = df["situacao"].astype("string").fillna("")
    t_obs = ((referencia - t0).dt.days / 365.25).to_numpy(dtype="float64", na_value=np.nan)
    t_pub = yrs(df["dt_publicado"])
    t_conc = yrs(df["dt_concessao"])
    t_end = np.full(len(df), np.inf)
    ext = (sit == "Extinta").to_numpy(); t_end[ext] = yrs(df["dt_extincao"])[ext]
    exp = ((sit == "Concedida") & (df["prazo_expirado"] == True)).to_numpy(); t_end[exp] = yrs(df["dt_fim_vigencia"])[exp]  # noqa: E712
    anu = (sit == "Anulada").to_numpy(); t_end[anu] = yrs(df["dt_ultimo_despacho"])[anu]
    t_end = np.where(np.isnan(t_end), np.inf, t_end)
    def final(cond, col):
        v = np.full(len(df), np.inf); m = cond.to_numpy(); arr = yrs(df[col]); v[m] = arr[m]; return np.where(np.isnan(v), yrs(df["dt_ultimo_despacho"]), v)
    t_ind = final(sit == "Indeferida", "dt_indeferimento")
    t_arq = final(sit == "Arquivada", "dt_arquivamento")
    t_ret = final(sit == "Retirada", "dt_desistencia")
    t_conc = np.where(np.isnan(t_conc), np.inf, t_conc); t_pub = np.where(np.isnan(t_pub), np.inf, t_pub)
    anos = df["ano"].to_numpy(dtype="float64", na_value=np.nan)

    def shares(mask: np.ndarray) -> dict:
        X = passos[None, :]
        obs = (t_obs[mask][:, None] >= X)
        pub = (t_pub[mask][:, None] <= X); con = (t_conc[mask][:, None] <= X); end = (t_end[mask][:, None] <= X)
        ind = (t_ind[mask][:, None] <= X); arq = (t_arq[mask][:, None] <= X); ret = (t_ret[mask][:, None] <= X)
        state = np.zeros(obs.shape, dtype=np.int8)      # 0 depositado
        state[pub] = 1                                   # publicado / em exame
        state[ind] = 4; state[arq] = 5; state[ret] = 6   # decisões negativas
        state[con] = 2                                   # vigente
        state[con & end] = 3                             # extinta/expirada
        n_obs = obs.sum(axis=0)
        out = {}
        for k, nome in enumerate(ESTADOS_CICLO):
            cnt = ((state == k) & obs).sum(axis=0)
            out[nome] = [round(float(c) / float(n) * 100, 2) if n else None for c, n in zip(cnt, n_obs)]
        return {"n_observados": [int(v) for v in n_obs], "estados": out}

    por_ano = {}
    for a in ANOS:
        m = anos == a
        if m.sum():
            por_ano[str(a)] = shares(m)
    return {"passos": [float(x) for x in passos], "estados": ESTADOS_CICLO, "todos": shares(np.ones(len(df), dtype=bool)), "por_ano": por_ano}


def transicoes(desp: pd.DataFrame, df: pd.DataFrame, dim_despacho: pd.DataFrame, top_n: int = 45, min_n: int = 3) -> dict:
    """Grafo de transições sequenciais entre despachos (a → b) por ano de depósito.

    desp: no_pedido, cd_despacho, dt_publicacao, no_rpi. Nós = os `top_n` códigos mais frequentes (demais = OUTROS).
    """
    d = desp.dropna(subset=["cd_despacho"]).sort_values(["no_pedido", "dt_publicacao", "no_rpi"], kind="stable")
    counts = d["cd_despacho"].value_counts()
    keep = set(counts.head(top_n).index)
    cd = d["cd_despacho"].where(d["cd_despacho"].isin(keep), "OUTROS").to_numpy()
    ped = d["no_pedido"].to_numpy()
    same = ped[1:] == ped[:-1]
    tr = pd.DataFrame({"no_pedido": ped[:-1][same], "a": cd[:-1][same], "b": cd[1:][same]})
    tr = tr.merge(df[["no_pedido", "ano"]], on="no_pedido", how="inner")
    agg = tr.groupby(["ano", "a", "b"], observed=True).size().rename("n").reset_index()
    nodes = list(counts.head(top_n).index) + ["OUTROS"]
    idx = {c: i for i, c in enumerate(nodes)}
    desc = dict(zip(dim_despacho["cd_despacho"], dim_despacho["descricao"])); evento = dict(zip(dim_despacho["cd_despacho"], dim_despacho["evento"]))
    nos = [{"id": c, "descricao": ("Demais códigos" if c == "OUTROS" else desc.get(c, "")), "evento": ("outros" if c == "OUTROS" else evento.get(c, "outros")),
            "total": int(counts.get(c, 0) if c != "OUTROS" else counts[~counts.index.isin(keep)].sum())} for c in nodes]
    por_ano = {}
    for a, g in agg.groupby("ano", observed=True):
        g = g[g["n"] >= min_n]
        por_ano[str(int(a))] = [[idx[r.a], idx[r.b], int(r.n)] for r in g.itertuples()]
    return {"nos": nos, "anos": ANOS, "por_ano": por_ano, "min_n": min_n}


def eventos_por_ano(desp: pd.DataFrame) -> pd.DataFrame:
    """Pedidos distintos com cada evento por ano de publicação (desp: no_pedido, evento, ano_publicacao)."""
    ev = desp.drop_duplicates().groupby(["ano_publicacao", "evento"], observed=True).size().rename("n").reset_index()
    ev["ano_publicacao"] = ev["ano_publicacao"].astype(int)
    return ev


def kpis_base(df: pd.DataFrame, bl: list[int] | None, tempo: dict) -> dict:
    ultimo = df[df["ano"] == ANO_FIM]; anterior = df[df["ano"] == ANO_FIM - 1]
    conc = df.dropna(subset=["dt_concessao"]); ca = year(conc["dt_concessao"])
    conc_u, conc_a = conc[ca == ANO_FIM], conc[ca == ANO_FIM - 1]
    vig = (df["situacao"] == "Concedida") & (df["prazo_expirado"] == False)  # noqa: E712
    med = {r["ano"]: r["mediana"] for r in tempo["por_ano"] if r["n"] >= 500}
    pior = max(med, key=lambda a: med[a] or 0) if med else None
    k = {"pedidos_total": int(len(df)), "pedidos_ultimo_ano": int(len(ultimo)), "pedidos_variacao_pct": pct(len(ultimo) - len(anterior), len(anterior)),
         "concessoes_total": int(len(conc)), "concessoes_ultimo_ano": int(len(conc_u)), "concessoes_variacao_pct": pct(len(conc_u) - len(conc_a), len(conc_a)),
         "vigentes": int(vig.sum()), "vigentes_residentes": int((vig & (df["residente"] == True)).sum()),  # noqa: E712
         "share_residentes_total": pct((df["residente"] == True).sum(), df["residente"].notna().sum()),  # noqa: E712
         "share_residentes_ultimo_ano": pct((ultimo["residente"] == True).sum(), ultimo["residente"].notna().sum()),  # noqa: E712
         "tempo_concessao_mediana_ultimo_ano": med.get(ANO_FIM), "tempo_concessao_pior_ano": pior, "tempo_concessao_pior_mediana": med.get(pior) if pior else None,
         "n_paises": int(df["pais_origem"].nunique()), "share_concedidos": pct(len(conc), len(df))}
    if bl is not None:
        k.update({"backlog_atual": bl[-1], "backlog_pico": int(max(bl)), "backlog_pico_ano": ANOS[int(np.argmax(bl))]})
    return k


def modelo(manifest: dict, relacoes: list[dict]) -> dict:
    return {"badepi_version": manifest.get("badepi_version"), "built_at": manifest.get("built_at"), "data_referencia": manifest.get("data_referencia"),
            "tabelas": manifest.get("tables", {}), "relacoes": relacoes}


def write_blocks(blocks: dict, out_dirs: list, log, slug: str) -> list:
    from ..ioutil import write_json
    written = []
    for name, obj in blocks.items():
        for d in out_dirs:
            p = d / f"{name}.json"
            write_json(obj, p)
            written.append(p)
        log.info("[%s] gold %s.json ok", slug, name)
    return written
