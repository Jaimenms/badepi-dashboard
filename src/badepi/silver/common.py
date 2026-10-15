"""Funções de limpeza compartilhadas pelas transformações silver."""

from __future__ import annotations

import re
import unicodedata

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
