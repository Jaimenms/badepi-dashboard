"""Funções de limpeza compartilhadas pelas transformações silver."""

from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd

from ..config import REFERENCE_DIR

# Datas-sentinela usadas pelos sistemas do INPI para "sem data"
SENTINEL_DATES = {"0001-01-01", "1111-11-11", "1900-01-01", "2099-01-01", "9999-12-31"}
MIN_YEAR, MAX_YEAR = 1900, 2030


def parse_datetime(s: pd.Series) -> pd.Series:
    """'2000-09-01 17:00:00.000' → datetime64[ms]; sentinelas e datas implausíveis viram NaT."""
    s = s.astype("string")
    out = pd.to_datetime(s, format="%Y-%m-%d %H:%M:%S.%f", errors="coerce")
    bad = s.str[:10].isin(SENTINEL_DATES) | (out.dt.year < MIN_YEAR) | (out.dt.year > MAX_YEAR)
    return out.mask(bad.fillna(False)).astype("datetime64[ms]")


def parse_date(s: pd.Series) -> pd.Series:
    return parse_datetime(s).dt.floor("D")


def to_int(s: pd.Series, dtype: str = "Int32") -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(dtype)


def load_reference(name: str) -> pd.DataFrame:
    return pd.read_csv(REFERENCE_DIR / f"{name}.csv", sep=";", dtype="string", keep_default_na=False).replace("", pd.NA)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


_NOISE = re.compile(r"[\.,;:'\"`´]+")
_SPACES = re.compile(r"\s+")


def normalize_name(s: pd.Series) -> pd.Series:
    """Nome em caixa alta, sem acentos nem pontuação, para agrupar grafias diferentes."""
    def _norm(v):
        if v is None or v is pd.NA or (isinstance(v, float) and v != v):
            return pd.NA
        v = strip_accents(str(v)).upper()
        v = _NOISE.sub(" ", v)
        v = _SPACES.sub(" ", v).strip()
        return v or pd.NA
    return s.map(_norm).astype("string")


# Heurísticas de categoria do depositante (aplicadas sobre o nome normalizado)
_RE_UNIVERSIDADE = re.compile(
    r"\b(?:UNIVERSIDADE|UNIVERSITY|UNIVERSITAT|UNIVERSITE|UNIVERSITA|UNIVERSIDAD|UNIV|FACULDADE|FACULDADES|"
    r"INSTITUTO FEDERAL|CEFET|CENTRO UNIVERSITARIO|ESCOLA POLITECNICA|POLYTECHNIC|HOCHSCHULE|COLLEGE|"
    r"USP|UNICAMP|UNESP|UFRJ|UFMG|UFRGS|UFSC|UFPR|UFPE|UFBA|UFC|UFSCAR|UNIFESP|UFF|UFV|UFU|UFPB|UFRN|UFG|UFPA|UFES|UFJF|UNB|PUC)\b"
)
_RE_PESQUISA = re.compile(
    r"\b(?:INSTITUTO|INSTITUT|INSTITUTE|FUNDACAO|FOUNDATION|FIOCRUZ|EMBRAPA|CNPQ|CNEN|INPE|IPT|CPQD|CTI|INMETRO|"
    r"CENTRO DE PESQUISA|CENTRO DE TECNOLOGIA|CENTRO TECNOLOGICO|RESEARCH|RECHERCHE|FORSCHUNG|CNRS|CSIC|FRAUNHOFER|MAX PLANCK|"
    r"SENAI|SESI|SENAC|LABORATORIO NACIONAL|HOSPITAL|ACADEMY|ACADEMIA|SOCIEDADE BENEFICENTE)\b"
)
_RE_GOVERNO = re.compile(
    r"\b(?:MINISTERIO|SECRETARIA|PREFEITURA|GOVERNO|ESTADO DO|ESTADO DE|ESTADO DA|UNIAO FEDERAL|MUNICIPIO|AGENCIA NACIONAL|"
    r"EXERCITO|MARINHA|AERONAUTICA|FORCA AEREA|COMANDO|DEPARTMENT OF|GOVERNMENT|MINISTRY|THE SECRETARY OF)\b"
)
_RE_EMPRESA = re.compile(
    r"\b(?:LTDA|LIMITADA|S ?/ ?A|SA|S A|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|GMBH|AG|LLC|LTD|LIMITED|BV|B V|NV|N V|SE|KK|"
    r"KABUSHIKI KAISHA|SAS|SARL|SRL|SPA|S P A|EIRELI|ME|EPP|MEI|PLC|OY|AB|AS|A/S|APS|PTY|PTE|LLP|LP|HOLDING|HOLDINGS|INDUSTRIA|INDUSTRIAS|"
    r"COMERCIO|INDUSTRIES|TECHNOLOGIES|TECNOLOGIA|SISTEMAS|SYSTEMS|ENGENHARIA|CONSULTORIA|SOLUCOES|SOLUTIONS|GROUP|GRUPO|PARTICIPACOES|"
    r"COOPERATIVA|ASSOCIACAO|SERVICOS|PRODUTOS|EQUIPAMENTOS|MAQUINAS|QUIMICA|FARMACEUTICA|PETROBRAS|EMBRAER|VALE|WEG)\b"
)


def classify_applicant(nome_norm: pd.Series, tipo_pessoa: pd.Series) -> pd.Series:
    """Categoria do depositante: universidade, instituto_pesquisa, governo, empresa, pessoa_fisica ou nao_classificado."""
    nome = nome_norm.fillna("")
    cat = pd.Series(pd.NA, index=nome_norm.index, dtype="string")
    cat = cat.mask(nome.str.contains(_RE_UNIVERSIDADE, regex=True), "universidade")
    cat = cat.mask(cat.isna() & nome.str.contains(_RE_PESQUISA, regex=True), "instituto_pesquisa")
    cat = cat.mask(cat.isna() & nome.str.contains(_RE_GOVERNO, regex=True), "governo")
    cat = cat.mask(cat.isna() & (tipo_pessoa == "J"), "empresa")
    cat = cat.mask(cat.isna() & (tipo_pessoa == "F"), "pessoa_fisica")
    cat = cat.mask(cat.isna() & nome.str.contains(_RE_EMPRESA, regex=True), "empresa")
    # pessoa física não residente: nome de pessoa (duas a quatro palavras, sem sufixo societário) é a melhor aproximação
    looks_person = nome.str.match(r"^[A-Z][A-Z'\-]+(?: [A-Z][A-Z'\-]+){1,4}$") & ~nome.str.contains(_RE_EMPRESA, regex=True)
    cat = cat.mask(cat.isna() & looks_person & (nome != ""), "pessoa_fisica_provavel")
    cat = cat.fillna("nao_classificado")
    # pedidos ainda não publicados (sigilo de 18 meses) chegam sem nome: só o tipo de pessoa é conhecido
    sem_nome = nome_norm.isna()
    fisica = (tipo_pessoa == "F").fillna(False)
    cat = cat.mask(sem_nome & fisica, "pessoa_fisica").mask(sem_nome & ~fisica, "nao_identificado")
    return cat


# ----------------------------------------------------------------------------- blocos reutilizáveis entre ativos
def pessoa_base(df: pd.DataFrame, ordem_default: int | None = None) -> pd.DataFrame:
    """Colunas comuns de depositante/inventor/autor (nome, documento, domicílio)."""
    nome = df["NM_COMPLET_PFPJ"] if "NM_COMPLET_PFPJ" in df else pd.Series(pd.NA, index=df.index, dtype="string")
    uf = df["CD_UF_PFPJ"].mask(df["CD_UF_PFPJ"] == "XX")
    ibge = df["CD_IBGE_CIDADE"].mask(df["CD_IBGE_CIDADE"].isin(["0000000", "0"]))
    out = pd.DataFrame({"no_pedido": df["NO_PEDIDO"]})
    if "NO_ORDEM" in df:
        ordem = to_int(df["NO_ORDEM"], "Int16")
        if ordem_default is not None:
            ordem = ordem.fillna(ordem_default)
        out["no_ordem"] = ordem
    out["nome"] = nome
    out["nome_norm"] = normalize_name(nome)
    out["documento"] = df["NO_CNPJ_CPF"] if "NO_CNPJ_CPF" in df else pd.NA
    out["pais"] = df["CD_PAIS_PFPJ"]
    out["uf"] = uf
    out["cidade"] = df["NM_CIDADE_PFPJ"] if "NM_CIDADE_PFPJ" in df else pd.NA
    out["codigo_ibge_municipio"] = ibge
    return out


def transform_depositante(df: pd.DataFrame, ordem_default: int | None = None) -> pd.DataFrame:
    out = pessoa_base(df, ordem_default)
    out.insert(2, "tipo_pessoa", df["CD_TIPO_PFPJ"] if "CD_TIPO_PFPJ" in df else pd.NA)
    out["categoria"] = classify_applicant(out["nome_norm"], out["tipo_pessoa"])
    return out


def transform_genero(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"no_pedido": df["NO_PEDIDO"], "sexo": df["SEXO_REC"]})
    out["seq"] = out.groupby("no_pedido").cumcount().add(1).astype("Int16")
    return out[["no_pedido", "seq", "sexo"]]


def primeiro_depositante(dpt: pd.DataFrame) -> pd.DataFrame:
    """Origem do pedido = depositante de ordem 1 (regra do manual do BADEPI)."""
    cols = ["no_pedido", "pais", "uf", "tipo_pessoa", "categoria", "nome_norm", "codigo_ibge_municipio"]
    sort_cols = ["no_pedido", "no_ordem"] if "no_ordem" in dpt else ["no_pedido"]
    return (dpt.sort_values(sort_cols).drop_duplicates("no_pedido")[cols]
            .rename(columns={"pais": "pais_origem", "uf": "uf_origem", "tipo_pessoa": "tipo_pessoa_origem",
                             "categoria": "categoria_origem", "nome_norm": "depositante_principal",
                             "codigo_ibge_municipio": "municipio_origem_ibge"}))


EVENTOS_SITUACAO = ["concessao", "anulacao", "extincao", "restauracao", "indeferimento", "recurso_provido", "arquivamento",
                    "desarquivamento", "desistencia_retirada", "deferimento", "publicacao", "exigencia", "parecer",
                    "pct_fase_nacional", "oposicao", "recurso", "sobrestamento", "prorrogacao"]


def derive_situacao(ev: pd.DataFrame, deposito: pd.DataFrame, referencia: pd.Timestamp,
                    fim_vigencia=None, anulacao_evento: str = "anulacao", counts: pd.DataFrame | None = None) -> pd.DataFrame:
    """Situação atual de cada pedido a partir da cronologia de eventos (comum a patentes, marcas e DI).

    ev: colunas no_pedido, dt_publicacao, evento. deposito: no_pedido, dt_deposito, dt_entrada_inpi (+ natureza).
    fim_vigencia: função(out) -> Series de datas de fim de vigência legal (None = sem prazo fixo, ex.: marcas).
    Regras (última data de cada tipo de evento):
      1. concessão → 'Anulada' se anulação posterior; 'Extinta' se a última extinção é posterior à última restauração; senão 'Concedida'.
      2. desistência/retirada posterior a qualquer decisão → 'Retirada'.
      3. indeferimento não revertido por recurso provido nem seguido de deferimento → 'Indeferida'.
      4. arquivamento não revertido por desarquivamento/restauração nem seguido de deferimento → 'Arquivada'.
      5. deferimento sem concessão → 'Deferida'.  6. senão → 'Em andamento'.
    """
    rel = [e for e in EVENTOS_SITUACAO if e != "anulacao"] + [anulacao_evento]
    sub = ev[ev["evento"].isin(rel)]
    last = sub.groupby(["no_pedido", "evento"], observed=True)["dt_publicacao"].max().unstack("evento")
    first = sub.groupby(["no_pedido", "evento"], observed=True)["dt_publicacao"].min().unstack("evento")
    for col in rel:
        if col not in last.columns:
            last[col] = pd.NaT
            first[col] = pd.NaT
    L = last

    def gt(a: str, b: str) -> pd.Series:  # a existe e (b não existe ou a >= b)
        return L[a].notna() & (L[b].isna() | (L[a] >= L[b]))

    concedida = L["concessao"].notna()
    anulada = concedida & gt(anulacao_evento, "concessao")
    extinta = concedida & ~anulada & gt("extincao", "concessao") & gt("extincao", "restauracao")
    ultima_decisao = L[["concessao", "indeferimento", "arquivamento", "deferimento"]].max(axis=1)
    retirada = ~concedida & L["desistencia_retirada"].notna() & (ultima_decisao.isna() | (L["desistencia_retirada"] >= ultima_decisao))
    indeferida = ~concedida & ~retirada & gt("indeferimento", "recurso_provido") & gt("indeferimento", "deferimento")
    arquivada = (~concedida & ~retirada & ~indeferida & gt("arquivamento", "desarquivamento")
                 & gt("arquivamento", "restauracao") & gt("arquivamento", "deferimento"))
    deferida = ~concedida & ~retirada & ~indeferida & ~arquivada & L["deferimento"].notna()
    situacao = np.select(
        [anulada, extinta, concedida, retirada, indeferida, arquivada, deferida],
        ["Anulada", "Extinta", "Concedida", "Retirada", "Indeferida", "Arquivada", "Deferida"],
        default="Em andamento",
    )
    out = pd.DataFrame({
        "no_pedido": L.index.astype("string"),
        "situacao": pd.Series(situacao, index=L.index, dtype="string").values,
        "dt_publicacao_pedido": first["publicacao"].values,
        "dt_pct_fase_nacional": first["pct_fase_nacional"].values,
        "dt_oposicao": first["oposicao"].values,
        "dt_primeira_exigencia": first["exigencia"].values,
        "dt_primeiro_parecer": first["parecer"].values,
        "dt_sobrestamento": first["sobrestamento"].values,
        "dt_deferimento": first["deferimento"].values,
        "dt_indeferimento": first["indeferimento"].values,
        "dt_concessao": first["concessao"].values,
        "dt_recurso": first["recurso"].values,
        "dt_arquivamento": L["arquivamento"].values,
        "dt_extincao": L["extincao"].values,
        "dt_desistencia": L["desistencia_retirada"].values,
        "dt_ultima_prorrogacao": L["prorrogacao"].values,
    })
    if counts is None:  # counts: índice no_pedido; colunas n_despachos, dt_primeiro_despacho, dt_ultimo_despacho, n_exigencias
        counts = ev.groupby("no_pedido", observed=True).agg(
            n_despachos=("evento", "size"), dt_primeiro_despacho=("dt_publicacao", "min"), dt_ultimo_despacho=("dt_publicacao", "max"))
        counts["n_exigencias"] = ev[ev["evento"] == "exigencia"].groupby("no_pedido", observed=True).size()
    out = out.merge(counts, left_on="no_pedido", right_index=True, how="left")
    extra_cols = [c for c in deposito.columns if c != "no_pedido"]
    out = deposito.merge(out, on="no_pedido", how="left")
    out["situacao"] = out["situacao"].fillna("Em andamento").astype("string")
    out["n_despachos"] = out["n_despachos"].fillna(0).astype("Int32")
    out["n_exigencias"] = out["n_exigencias"].fillna(0).astype("Int16")
    for c in out.columns:
        if c.startswith("dt_"):
            out[c] = out[c].astype("datetime64[ms]")
    # publicação efetiva (nacional ou fase nacional PCT), 1ª decisão de encerramento, vigência e tempos
    out["dt_publicado"] = out[["dt_publicacao_pedido", "dt_pct_fase_nacional"]].min(axis=1).astype("datetime64[ms]")
    decisao = out[["dt_concessao", "dt_indeferimento", "dt_arquivamento", "dt_extincao", "dt_desistencia"]].min(axis=1)
    out["dt_primeira_decisao"] = decisao.where(out["situacao"] != "Em andamento").astype("datetime64[ms]")
    if fim_vigencia is not None:
        out["dt_fim_vigencia"] = fim_vigencia(out).astype("datetime64[ms]")
        out["prazo_expirado"] = (out["dt_fim_vigencia"] <= referencia).astype("boolean")
    else:
        out["dt_fim_vigencia"] = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ms]")
        out["prazo_expirado"] = pd.Series(False, index=out.index, dtype="boolean")
    out["anos_ate_concessao"] = ((out["dt_concessao"] - out["dt_entrada_inpi"]).dt.days / 365.25).round(2).astype("Float32")
    out["anos_ate_decisao"] = ((out["dt_primeira_decisao"] - out["dt_entrada_inpi"]).dt.days / 365.25).round(2).astype("Float32")
    return out.drop(columns=extra_cols)


def dim_despacho_from_parts(parts: list[pd.DataFrame], descricoes: dict[str, str] | None = None) -> pd.DataFrame:
    """Consolida contagens parciais (cd_despacho, ds_despacho, evento, n) numa dimensão; usa descrição curada quando a fonte não traz."""
    agg = pd.concat(parts)
    if "ds_despacho" not in agg:
        agg["ds_despacho"] = pd.NA
    agg = agg.groupby(["cd_despacho", "ds_despacho", "evento"], observed=True, dropna=False)["n"].sum().reset_index()
    total = agg.groupby("cd_despacho")["n"].sum().rename("n")
    dim = (agg.sort_values("n", ascending=False).drop_duplicates("cd_despacho").drop(columns="n")
           .merge(total, left_on="cd_despacho", right_index=True).rename(columns={"ds_despacho": "descricao"}))
    if descricoes:
        cur = dim["cd_despacho"].map(descricoes)
        dim["descricao"] = dim["descricao"].astype("string").fillna(cur.astype("string"))
    dim["descricao"] = dim["descricao"].astype("string")
    dim["n"] = dim["n"].astype("Int32")
    return dim[["cd_despacho", "descricao", "evento", "n"]].sort_values("cd_despacho").reset_index(drop=True)
