"""Silver — Patentes (badepiv12_ptn_*.csv → parquet relacionado).

Tabelas produzidas em data/silver/patentes/:

  ptn_deposito            1 linha por pedido (chave: no_pedido) + colunas derivadas de origem/via/campo
  ptn_depositante         n por pedido (chave: no_pedido + no_ordem)
  ptn_inventor            n por pedido (chave: no_pedido + no_ordem)
  ptn_despacho/           n por pedido, particionada por ano_publicacao (hive)
  ptn_ipc                 n por pedido (chave: no_pedido + ordem)
  ptn_pct                 1 por pedido (raros casos com 2)
  ptn_prioridade          n por pedido
  ptn_situacao            1 por pedido: situação atual derivada dos despachos e marcos (datas) do processo
  ptn_inventor_genero     n por pedido (inventores residentes; BADEPI PI e Gênero)
  ptn_depositante_genero  n por pedido (depositantes pessoa física residentes)
  dim_campo_tec, dim_despacho, dim_pais, dim_uf

Todas as chaves são strings sem espaços laterais; datas são datetime64[ms]; vazios são <NA>.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import BADEPI_VERSION, SOURCES
from ..ioutil import ParquetSink, iter_badepi_csv, read_badepi_csv, read_json, write_parquet
from .common import classify_applicant, load_reference, normalize_name, parse_date, parse_datetime, to_int

log = logging.getLogger(__name__)
SRC = SOURCES["patentes"]
PIGEN = SOURCES["pi_genero"]
CSV = f"badepi{BADEPI_VERSION}_ptn_{{}}.csv"

# ----------------------------------------------------------------------------- despachos → eventos
# Categorias de evento usadas para derivar a situação do pedido. Códigos conforme a RPI (seção
# "Códigos e Abreviações" de patentes). Primeiro casam os códigos explícitos, depois a descrição
# (anulações/retificações) e por fim o prefixo do código.
EVENTO_POR_CODIGO: dict[str, str] = {}
for _codes, _ev in [
    (["2.1", "2.10", "2.4", "23.1", "23.1.1", "15.50"], "deposito"),
    (["1.1", "1.3", "1.4"], "pct_fase_nacional"),
    (["1.2"], "desistencia_retirada"),
    (["3.1", "3.2", "3.5", "4.1"], "publicacao"),
    (["3.6"], "arquivamento"),
    (["1.5", "2.5", "4.2", "6.1", "6.2", "6.6", "6.6.1", "6.6.2", "6.6.3", "6.7", "6.20", "6.21", "6.22", "6.23",
      "8.1", "8.5", "24.1", "24.2", "22.5", "23.2", "121", "55", "28.21"], "exigencia"),
    (["7.1", "120", "26.4"], "parecer"),
    (["7.4", "7.5", "7.6", "7.7"], "anuencia_anvisa"),
    (["9.1", "23.13"], "deferimento"),
    (["9.2", "9.2.4", "23.7"], "indeferimento"),
    (["16.1", "23.9"], "concessao"),
    (["16.4", "200"], "patente_anulada"),
    (["8.6", "8.11", "8.12", "11.1", "11.1.1", "11.2", "11.3", "11.4", "11.5", "11.6", "11.6.1", "11.11", "11.12",
      "11.17", "11.18", "11.20", "11.21", "11.34", "15.1", "23.6", "138", "217", "22.14"], "arquivamento"),
    (["4.3", "11.16", "11.34.1", "15.34", "15.34.1", "102", "103"], "desarquivamento"),
    (["8.7", "24.4"], "restauracao"),
    (["10.1", "10.9"], "desistencia_retirada"),
    (["21.1", "21.2", "21.6", "24.3", "24.8", "24.10", "23.19"], "extincao"),
    (["12.2", "12.3", "12.6", "23.8", "130", "131", "134"], "recurso"),
    (["100", "100.1", "100.2", "104"], "recurso_provido"),
    (["111", "112", "113", "115"], "recurso_negado"),
    (["17.1", "201", "204", "205", "206", "210", "211", "212", "23.18"], "nulidade"),
    (["18.1", "18.4", "18.8"], "caducidade"),
    (["25.1", "25.2", "25.3", "25.4", "25.5", "25.6", "25.7", "25.8", "25.9", "25.13", "14.4"], "transferencia_alteracao"),
    (["22.12"], "licenca_oferta"),
    (["27.1", "27.2", "27.3", "28.1", "28.2", "28.10", "28.20", "28.22", "28.30", "28.32", "28.40", "28.41", "28.42", "28.93",
      "15.24", "15.24.1", "15.24.2", "15.24.3"], "tramite_prioritario"),
]:
    for _c in _codes:
        EVENTO_POR_CODIGO[_c] = _ev

_RE_ANULACAO = re.compile(r"anulad|retifica|republica|renumera", re.I)
_EVENTO_POR_PREFIXO = [
    ("28.", "tramite_prioritario"), ("27.", "tramite_prioritario"), ("6.", "exigencia"), ("8.", "arquivamento"),
    ("11.", "arquivamento"), ("21.", "extincao"), ("24.", "extincao"), ("25.", "transferencia_alteracao"),
    ("12.", "recurso"), ("1.", "pct_fase_nacional"), ("2.", "deposito"), ("3.", "publicacao"), ("7.", "parecer"),
    ("15.", "anotacao_administrativa"), ("19.", "anotacao_administrativa"), ("22.", "anotacao_administrativa"),
    ("29.", "anotacao_administrativa"), ("10.", "desistencia_retirada"), ("17.", "nulidade"), ("18.", "caducidade"),
]


def classify_despacho(codigo: str, descricao: str | None) -> str:
    if codigo in EVENTO_POR_CODIGO:
        return EVENTO_POR_CODIGO[codigo]
    if descricao and _RE_ANULACAO.search(descricao):
        return "anulacao_retificacao"
    for prefix, ev in _EVENTO_POR_PREFIXO:
        if codigo.startswith(prefix):
            return ev
    if codigo.isdigit():
        n = int(codigo)
        if 100 <= n < 200:
            return "recurso"
        if 200 <= n < 300:
            return "nulidade"
    return "outros"


# ----------------------------------------------------------------------------- transformações
_OLD = re.compile(r"^(PI|MU|PP|C)\d{7}$")
_NEW = re.compile(r"^(1[0-3]|2[0-3])\d{10}$")
_NATUREZA = {"PI": "PI", "10": "PI", "11": "PI", "12": "PI", "MU": "MU", "20": "MU", "21": "MU", "22": "MU",
             "C": "CA", "13": "CA", "23": "CA", "PP": "PP"}


def transform_deposito(df: pd.DataFrame) -> pd.DataFrame:
    no = df["NO_PEDIDO"].astype("string")
    pref = no.str.extract(r"^(PI|MU|PP|C|1[0-3]|2[0-3])(?=\d)")[0].astype("string")
    formato = pd.Series("invalido", index=df.index, dtype="string")
    formato = formato.mask(no.str.match(_OLD.pattern), "antigo").mask(no.str.match(_NEW.pattern), "novo")
    return pd.DataFrame({
        "no_pedido": no,
        "ano": to_int(df["ANO"], "Int16"),
        "dt_entrada_inpi": parse_datetime(df["DT_ENTRADA_INPI"]),
        "dt_deposito": parse_date(df["DT_DEPOSITO"]),
        "titulo": df["NM_TITULO_PATENTE"],
        "natureza": pref.map(_NATUREZA).astype("string"),
        "formato_numero": formato,
        "prefixo_numero": pref,
    })


def _pessoa_base(df: pd.DataFrame) -> pd.DataFrame:
    nome = df["NM_COMPLET_PFPJ"]
    uf = df["CD_UF_PFPJ"].mask(df["CD_UF_PFPJ"] == "XX")
    ibge = df["CD_IBGE_CIDADE"].mask(df["CD_IBGE_CIDADE"] == "0000000")
    return pd.DataFrame({
        "no_pedido": df["NO_PEDIDO"],
        "no_ordem": to_int(df["NO_ORDEM"], "Int16"),
        "nome": nome,
        "nome_norm": normalize_name(nome),
        "documento": df["NO_CNPJ_CPF"],
        "pais": df["CD_PAIS_PFPJ"],
        "uf": uf,
        "cidade": df["NM_CIDADE_PFPJ"],
        "codigo_ibge_municipio": ibge,
    })


def transform_depositante(df: pd.DataFrame) -> pd.DataFrame:
    out = _pessoa_base(df)
    out.insert(2, "tipo_pessoa", df["CD_TIPO_PFPJ"])
    out["categoria"] = classify_applicant(out["nome_norm"], out["tipo_pessoa"])
    return out


def transform_inventor(df: pd.DataFrame) -> pd.DataFrame:
    out = _pessoa_base(df)
    out.insert(2, "anonimo", (df["CD_ANONIMA"] == "S").fillna(False).astype("boolean"))
    return out


def transform_despacho(df: pd.DataFrame, cache: dict) -> pd.DataFrame:
    cd = df["CD_DESPACH_RPI"].astype("string")
    ds = df["DS_TIPO_DESPACH"].astype("string")
    pairs = pd.DataFrame({"cd": cd, "ds": ds}).drop_duplicates()
    for c, d in zip(pairs["cd"], pairs["ds"]):
        if c is not pd.NA and c not in cache:
            cache[c] = classify_despacho(c, None if d is pd.NA else d)
    dt = parse_date(df["DT_PUBLICACAO"])
    return pd.DataFrame({
        "no_pedido": df["NO_PEDIDO"],
        "no_rpi": to_int(df["NO_RPI"], "Int32"),
        "dt_publicacao": dt,
        "cd_despacho": cd,
        "ds_despacho": ds,
        "evento": cd.map(cache).astype("string"),
        "ano_publicacao": dt.dt.year.astype("Int16"),
    })


def transform_ipc(df: pd.DataFrame) -> pd.DataFrame:
    ipc = df["CD_CLASSIF"].str.replace(r"\s+", " ", regex=True)
    out = pd.DataFrame({
        "no_pedido": df["NO_PEDIDO"],
        "ordem": to_int(df["NO_ORDEM_CLASSE"], "Int16"),
        "ipc": ipc,
        "secao": ipc.str[:1],
        "classe": ipc.str[:3],
        "subclasse": ipc.str[:4],
        "grupo_principal": ipc.str.split("/").str[0],
        "versao_ipc": df["VERSION_INDICATOR"],
        "campo_tec": to_int(df["CAMPO_TEC"], "Int8"),
    })
    return out[out["ipc"].notna()].reset_index(drop=True)


def transform_pct(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "no_pedido": df["NO_PEDIDO"],
        "no_pct": df["NO_PCT"],
        "escritorio_receptor": df["NO_PCT"].str[:2],
        "dt_deposito_pct": parse_date(df["DT_PCT"]),
        "no_publicacao_ompi": df["CD_OMPI"],
        "dt_publicacao_ompi": parse_date(df["DT_OMPI"]),
    })


def transform_prioridade(df: pd.DataFrame) -> pd.DataFrame:
    # No BADEPI v12 a coluna DT_PEDIDO_ORIGEM repete o número da prioridade (defeito da fonte);
    # a data é convertida onde existir e fica <NA> no restante.
    return pd.DataFrame({
        "no_pedido": df["NO_PEDIDO"],
        "no_prioridade": df["NO_PEDIDO_ORIGEM"],
        "pais_prioridade": df["CD_PAIS"],
        "dt_prioridade": parse_date(df["DT_PEDIDO_ORIGEM"]),
    })


def transform_genero(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"no_pedido": df["NO_PEDIDO"], "sexo": df["SEXO_REC"]})
    out["seq"] = out.groupby("no_pedido").cumcount().add(1).astype("Int16")
    return out[["no_pedido", "seq", "sexo"]]


# ----------------------------------------------------------------------------- situação do pedido
SITUACOES = ["Concedida", "Deferida", "Em andamento", "Indeferida", "Arquivada", "Retirada", "Extinta", "Anulada"]


def build_situacao(ev: pd.DataFrame, deposito: pd.DataFrame, referencia: pd.Timestamp) -> pd.DataFrame:
    """Deriva a situação atual de cada pedido a partir da cronologia de eventos.

    ev: colunas no_pedido, dt_publicacao, evento (todos os despachos).
    Regras (aplicadas nesta ordem, usando a última data de cada tipo de evento):
      1. concessão → 'Anulada' se houve anulação posterior; 'Extinta' se a última extinção é posterior à
         última restauração; senão 'Concedida'.
      2. desistência/retirada posterior a qualquer decisão → 'Retirada'.
      3. indeferimento não revertido por recurso provido posterior → 'Indeferida'.
      4. arquivamento não revertido por desarquivamento/restauração posterior → 'Arquivada'.
      5. deferimento sem concessão → 'Deferida'.
      6. caso contrário → 'Em andamento'.
    """
    rel = ["concessao", "patente_anulada", "extincao", "restauracao", "indeferimento", "recurso_provido",
           "arquivamento", "desarquivamento", "desistencia_retirada", "deferimento", "publicacao", "exigencia",
           "parecer", "pct_fase_nacional"]
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
    anulada = concedida & gt("patente_anulada", "concessao")
    extinta = concedida & ~anulada & gt("extincao", "concessao") & gt("extincao", "restauracao")
    decisao_cols = ["concessao", "indeferimento", "arquivamento", "deferimento"]
    ultima_decisao = L[decisao_cols].max(axis=1)
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
        "dt_primeira_exigencia": first["exigencia"].values,
        "dt_primeiro_parecer": first["parecer"].values,
        "dt_deferimento": first["deferimento"].values,
        "dt_indeferimento": first["indeferimento"].values,
        "dt_concessao": first["concessao"].values,
        "dt_arquivamento": L["arquivamento"].values,
        "dt_extincao": L["extincao"].values,
    })
    counts = ev.groupby("no_pedido", observed=True).agg(
        n_despachos=("evento", "size"), dt_primeiro_despacho=("dt_publicacao", "min"), dt_ultimo_despacho=("dt_publicacao", "max")
    )
    n_exig = ev[ev["evento"] == "exigencia"].groupby("no_pedido", observed=True).size().rename("n_exigencias")
    out = out.merge(counts, left_on="no_pedido", right_index=True, how="left")
    out = out.merge(n_exig, left_on="no_pedido", right_index=True, how="left")
    out["n_exigencias"] = out["n_exigencias"].fillna(0).astype("Int16")
    out["n_despachos"] = out["n_despachos"].astype("Int32")

    # pedidos sem nenhum despacho ainda assim recebem uma linha
    out = deposito[["no_pedido", "natureza", "dt_deposito", "dt_entrada_inpi"]].merge(out, on="no_pedido", how="left")
    out["situacao"] = out["situacao"].fillna("Em andamento").astype("string")
    out["n_despachos"] = out["n_despachos"].fillna(0).astype("Int32")
    out["n_exigencias"] = out["n_exigencias"].fillna(0).astype("Int16")

    # primeira decisão de mérito/encerramento (para medir pendência) e prazo de vigência legal
    decisao = out[["dt_concessao", "dt_indeferimento", "dt_arquivamento", "dt_extincao"]].min(axis=1)
    out["dt_primeira_decisao"] = decisao.where(out["situacao"] != "Em andamento").astype("datetime64[ms]")
    # publicação efetiva: publicação nacional (3.x) ou publicação/admissão da fase nacional PCT (1.1/1.3)
    out["dt_publicado"] = out[["dt_publicacao_pedido", "dt_pct_fase_nacional"]].min(axis=1).astype("datetime64[ms]")
    mu = (out["natureza"] == "MU").fillna(False).to_numpy()
    fim = out["dt_deposito"] + pd.DateOffset(years=20)           # PI e CA: 20 anos do depósito
    fim[mu] = out.loc[mu, "dt_deposito"] + pd.DateOffset(years=15)  # MU: 15 anos
    out["dt_fim_vigencia"] = fim.astype("datetime64[ms]")
    out["prazo_expirado"] = (out["dt_fim_vigencia"] <= referencia).astype("boolean")
    out["anos_ate_concessao"] = ((out["dt_concessao"] - out["dt_entrada_inpi"]).dt.days / 365.25).round(2).astype("Float32")
    out["anos_ate_decisao"] = ((out["dt_primeira_decisao"] - out["dt_entrada_inpi"]).dt.days / 365.25).round(2).astype("Float32")
    out = out.drop(columns=["natureza", "dt_deposito", "dt_entrada_inpi"])
    return out


# ----------------------------------------------------------------------------- build
def _bronze_sha(bronze_dir: Path) -> str | None:
    m = bronze_dir / "_manifest.json"
    return read_json(m).get("zip_sha256") if m.exists() else None


def build(force: bool = False) -> Path:
    bronze, out = SRC.bronze_dir, SRC.silver_dir
    if not (bronze / "_manifest.json").exists():
        raise FileNotFoundError(f"bronze de patentes ausente em {bronze}. Rode 'badepi bronze -s patentes'.")
    manifest_path = out / "_manifest.json"
    zip_sha = _bronze_sha(bronze)
    if manifest_path.exists() and not force and read_json(manifest_path).get("bronze_zip_sha256") == zip_sha:
        log.info("[patentes] silver já construída a partir desta bronze; use --force para refazer")
        return out
    out.mkdir(parents=True, exist_ok=True)
    tables: dict[str, dict] = {}

    def register(name: str, rows: int, df_sample: pd.DataFrame, path: Path, partition: str | None = None, key: list[str] | None = None):
        tables[name] = {
            "path": str(path.relative_to(out)),
            "rows": int(rows),
            "partitioned_by": partition,
            "key": key or [],
            "columns": {c: str(t) for c, t in df_sample.dtypes.items()},
        }
        log.info("[patentes] %s: %s linhas → %s", name, f"{rows:,}", path.name)

    # 1) depósitos ------------------------------------------------------------------
    log.info("[patentes] lendo depósitos")
    dep = transform_deposito(read_badepi_csv(bronze / CSV.format("deposito")))
    dep = dep.drop_duplicates("no_pedido")
    pedidos = set(dep["no_pedido"].dropna())

    # 2) depositantes ---------------------------------------------------------------
    log.info("[patentes] lendo depositantes")
    dpt = transform_depositante(read_badepi_csv(bronze / CSV.format("depositante")))
    p = out / "ptn_depositante.parquet"
    register("ptn_depositante", write_parquet(dpt, p), dpt, p, key=["no_pedido", "no_ordem"])
    primeiro = (dpt.sort_values(["no_pedido", "no_ordem"]).drop_duplicates("no_pedido")
                [["no_pedido", "pais", "uf", "tipo_pessoa", "categoria", "nome_norm", "codigo_ibge_municipio"]]
                .rename(columns={"pais": "pais_origem", "uf": "uf_origem", "tipo_pessoa": "tipo_pessoa_origem",
                                 "categoria": "categoria_origem", "nome_norm": "depositante_principal",
                                 "codigo_ibge_municipio": "municipio_origem_ibge"}))
    n_dpt = dpt.groupby("no_pedido").size().rename("n_depositantes").astype("Int16")
    del dpt

    # 3) inventores (em blocos) -----------------------------------------------------
    log.info("[patentes] lendo inventores")
    inv_stats = []
    p = out / "ptn_inventor.parquet"
    with ParquetSink(p) as sink:
        for chunk in iter_badepi_csv(bronze / CSV.format("inventor")):
            t = transform_inventor(chunk)
            sink.write(t)
            inv_stats.append(t.groupby("no_pedido").agg(n=("no_ordem", "size"), n_br=("pais", lambda s: int((s == "BR").sum()))))
        sample = t
    inv_stats = pd.concat(inv_stats).groupby(level=0).sum()
    inv_stats = inv_stats.rename(columns={"n": "n_inventores", "n_br": "n_inventores_br"}).astype("Int16")
    register("ptn_inventor", sink.rows, sample, p, key=["no_pedido", "no_ordem"])

    # 4) despachos (em blocos, particionado por ano) --------------------------------
    log.info("[patentes] lendo despachos")
    cache: dict[str, str] = {}
    events = []
    dim_rows = []
    p = out / "ptn_despacho"
    with ParquetSink(p, partition_cols=["ano_publicacao"]) as sink:
        for chunk in iter_badepi_csv(bronze / CSV.format("despacho")):
            t = transform_despacho(chunk, cache)
            sink.write(t)
            events.append(t[["no_pedido", "dt_publicacao", "evento"]])
            dim_rows.append(t.groupby(["cd_despacho", "ds_despacho", "evento"], observed=True).size().rename("n").reset_index())
        sample = t
    register("ptn_despacho", sink.rows, sample, p, partition="ano_publicacao", key=["no_pedido", "no_rpi", "cd_despacho"])
    ev = pd.concat(events, ignore_index=True)
    ev["evento"] = ev["evento"].astype("category")
    del events
    referencia = ev["dt_publicacao"].max()
    pct_despacho = set(ev.loc[ev["evento"] == "pct_fase_nacional", "no_pedido"].unique())
    dividido_despacho = set(ev.loc[ev["evento"] == "deposito", "no_pedido"].unique())  # refinado abaixo

    # 5) IPC ------------------------------------------------------------------------
    log.info("[patentes] lendo IPC")
    ipc = transform_ipc(read_badepi_csv(bronze / CSV.format("ipc_campo_tec")))
    p = out / "ptn_ipc.parquet"
    register("ptn_ipc", write_parquet(ipc, p), ipc, p, key=["no_pedido", "ordem"])
    ipc_principal = (ipc.sort_values(["no_pedido", "campo_tec", "ordem"], na_position="last")
                     .drop_duplicates("no_pedido")[["no_pedido", "ipc", "secao", "subclasse", "campo_tec"]]
                     .rename(columns={"ipc": "ipc_principal", "secao": "secao_ipc_principal",
                                      "subclasse": "subclasse_ipc_principal", "campo_tec": "campo_tec_principal"}))
    # campo principal = campo da classificação de ordem 1; se ausente, o primeiro campo informado
    ordem1 = ipc[ipc["ordem"] == 1].drop_duplicates("no_pedido").set_index("no_pedido")
    ipc_principal = ipc_principal.set_index("no_pedido")
    common = ipc_principal.index.intersection(ordem1.index)
    has_campo = ordem1.loc[common, "campo_tec"].notna()
    idx = common[has_campo.values]
    ipc_principal.loc[idx, ["ipc_principal", "secao_ipc_principal", "subclasse_ipc_principal", "campo_tec_principal"]] = \
        ordem1.loc[idx, ["ipc", "secao", "subclasse", "campo_tec"]].values
    ipc_principal = ipc_principal.reset_index()
    n_ipc = ipc.groupby("no_pedido").size().rename("n_ipc").astype("Int16")
    del ipc

    # 6) PCT e prioridade -----------------------------------------------------------
    pct = transform_pct(read_badepi_csv(bronze / CSV.format("pct")))
    p = out / "ptn_pct.parquet"
    register("ptn_pct", write_parquet(pct, p), pct, p, key=["no_pedido", "no_pct"])
    pct_ids = set(pct["no_pedido"].dropna())
    pri = transform_prioridade(read_badepi_csv(bronze / CSV.format("prioridade")))
    p = out / "ptn_prioridade.parquet"
    register("ptn_prioridade", write_parquet(pri, p), pri, p, key=["no_pedido", "no_prioridade"])
    pri_stats = pri.groupby("no_pedido").agg(n_prioridades=("no_prioridade", "size"), pais_prioridade_principal=("pais_prioridade", "first"))
    pri_stats["n_prioridades"] = pri_stats["n_prioridades"].astype("Int16")
    del pct, pri

    # 7) depósito enriquecido -------------------------------------------------------
    log.info("[patentes] montando ptn_deposito enriquecido")
    dim_campo = load_reference("campos_tec")
    dim_campo["campo_tec"] = dim_campo["campo_tec"].astype("Int8")
    dep = (dep.merge(primeiro, on="no_pedido", how="left")
              .merge(n_dpt, left_on="no_pedido", right_index=True, how="left")
              .merge(inv_stats, left_on="no_pedido", right_index=True, how="left")
              .merge(ipc_principal, on="no_pedido", how="left")
              .merge(n_ipc, left_on="no_pedido", right_index=True, how="left")
              .merge(pri_stats, left_on="no_pedido", right_index=True, how="left")
              .merge(dim_campo[["campo_tec", "setor"]].rename(columns={"campo_tec": "campo_tec_principal", "setor": "setor_principal"}),
                     on="campo_tec_principal", how="left"))
    for c in ["n_depositantes", "n_inventores", "n_inventores_br", "n_ipc", "n_prioridades"]:
        dep[c] = dep[c].fillna(0).astype("Int16")
    dep["residente"] = (dep["pais_origem"] == "BR").astype("boolean")
    via_pct = dep["prefixo_numero"].isin(["11", "21"]) | dep["no_pedido"].isin(pct_ids) | dep["no_pedido"].isin(pct_despacho)
    dep["via"] = pd.Series(np.where(via_pct, "PCT", "Direta"), index=dep.index, dtype="string")
    dep["pedido_dividido"] = dep["prefixo_numero"].isin(["12", "22"]).astype("boolean")
    dep["tem_prioridade"] = (dep["n_prioridades"] > 0).astype("boolean")
    dep = dep.drop(columns=["prefixo_numero"])
    p = out / "ptn_deposito.parquet"
    register("ptn_deposito", write_parquet(dep, p), dep, p, key=["no_pedido"])

    # 8) situação -------------------------------------------------------------------
    log.info("[patentes] derivando situação dos pedidos")
    sit = build_situacao(ev, dep, referencia)
    p = out / "ptn_situacao.parquet"
    register("ptn_situacao", write_parquet(sit, p), sit, p, key=["no_pedido"])
    del ev

    # 9) dimensões ------------------------------------------------------------------
    agg = pd.concat(dim_rows).groupby(["cd_despacho", "ds_despacho", "evento"], observed=True)["n"].sum().reset_index()
    total = agg.groupby("cd_despacho")["n"].sum().rename("n")
    dim_desp = (agg.sort_values("n", ascending=False).drop_duplicates("cd_despacho")
                .drop(columns="n").merge(total, left_on="cd_despacho", right_index=True)
                .rename(columns={"ds_despacho": "descricao"}))
    dim_desp["n"] = dim_desp["n"].astype("Int32")
    dim_desp = dim_desp[["cd_despacho", "descricao", "evento", "n"]].sort_values("cd_despacho").reset_index(drop=True)
    for name, df in [("dim_campo_tec", dim_campo), ("dim_despacho", dim_desp),
                     ("dim_pais", load_reference("paises")), ("dim_uf", load_reference("ufs"))]:
        p = out / f"{name}.parquet"
        register(name, write_parquet(df, p), df, p, key=[df.columns[0]])

    # 10) gênero (BADEPI PI e Gênero) -----------------------------------------------
    for kind in ["inventor", "depositante"]:
        src = PIGEN.bronze_dir / f"badepi{BADEPI_VERSION}_ptn_{kind}_pigen.csv"
        if not src.exists():
            log.warning("[patentes] %s não encontrado; rode 'badepi bronze -s pi_genero'", src.name)
            continue
        g = transform_genero(read_badepi_csv(src))
        p = out / f"ptn_{kind}_genero.parquet"
        register(f"ptn_{kind}_genero", write_parquet(g, p), g, p, key=["no_pedido", "seq"])

    manifest = {
        "badepi_version": BADEPI_VERSION,
        "source": "patentes",
        "bronze_zip_sha256": zip_sha,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_referencia": referencia.date().isoformat(),
        "tables": tables,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    log.info("[patentes] silver concluída em %s", out)
    return out
