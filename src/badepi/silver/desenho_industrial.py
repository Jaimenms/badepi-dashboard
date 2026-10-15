"""Silver — Desenho Industrial (badepiv12_di_*.csv → parquet relacionado).

Tabelas em data/silver/desenho_industrial/: di_deposito (+ origem, via, classe Locarno principal), di_depositante,
di_autor (sem nomes na fonte), di_despacho, di_classe, di_situacao, dim_despacho, dim_pais, dim_uf, di_depositante_genero.
"""

from __future__ import annotations

import json
import logging
import re

import pandas as pd
from datetime import datetime, timezone

from ..config import BADEPI_VERSION, SOURCES
from ..ioutil import read_badepi_csv, read_json, write_parquet
from .common import (derive_situacao, dim_despacho_from_parts, load_reference, parse_date, parse_datetime, pessoa_base,
                     primeiro_depositante, to_int, transform_depositante, transform_genero)

log = logging.getLogger(__name__)
SRC = SOURCES["desenho_industrial"]
PIGEN = SOURCES["pi_genero"]
CSV = f"badepi{BADEPI_VERSION}_di_{{}}.csv"

# descrição curada dos códigos do sistema novo (sem descrição no BADEPI) — ver notas no guia
CODIGOS_NOVOS: dict[str, tuple[str, str]] = {
    "860": ("Notificação de depósito (sistema novo, substitui o 31)", "deposito"),
    "158": ("Concessão do registro (sistema novo, substitui o 39)", "concessao"),
    "870": ("Prorrogação do registro (sistema novo, substitui o 46)", "prorrogacao"),
    "136": ("Exigência de mérito", "exigencia"),
    "139": ("Arquivamento definitivo por falta de cumprimento de exigência", "arquivamento"),
    "270": ("Deferimento de petição (transferência, alteração de nome/sede etc.)", "peticao_deferida"),
    "428": ("Petição não conhecida", "peticao"),
    "577": ("Emissão de folha de rosto de cópia reprográfica", "administrativo"),
    "1246": ("Expedição do certificado de registro (inferido)", "administrativo"),
    "400": ("Notificação de instauração de processo administrativo de nulidade", "nulidade"),
    "1010": ("Intimação para manifestação em processo de nulidade (inferido)", "nulidade"),
    "530": ("Decisão em processo de nulidade (inferido)", "nulidade"),
    "532": ("Nulidade: requerimento não provido (mantida a concessão)", "nulidade"),
    "1214": ("Notificação de pedido via Acordo de Haia (inferido)", "haia"),
    "1233": ("Tramitação de pedido via Acordo de Haia (inferido)", "haia"),
    "1252": ("Tramitação de pedido via Acordo de Haia (inferido)", "haia"),
}
EVENTO_POR_CODIGO: dict[str, str] = {c: e for c, (_, e) in CODIGOS_NOVOS.items()}
for _codes, _ev in [
    (["31", "32", "2.1", "2.10", "23.1"], "deposito"),
    (["33.1", "35", "35.1", "15.1", "138", "217"], "arquivamento"),
    (["33", "65", "65.1", "10.1"], "desistencia_retirada"),
    (["30", "34", "55", "46.2", "46.1", "121", "4.2", "23.2"], "exigencia"),
    (["34.2"], "administrativo"),
    (["34.1", "40", "39.5", "120"], "parecer"),
    (["36", "9.2"], "indeferimento"),
    (["37", "38", "12.2", "12.6", "130", "131"], "recurso"),
    (["104", "100", "109", "102", "103"], "recurso_provido"),
    (["115", "111", "112", "113"], "recurso_negado"),
    (["39", "16.1", "23.9"], "concessao"),
    (["41", "205", "201", "204", "210", "211", "212", "206", "17.1"], "nulidade"),
    (["200", "311"], "anulacao"),
    (["43", "44", "45", "21.1", "21.6", "24.8", "24.10"], "extincao"),
    (["46", "24.4"], "prorrogacao"),
    (["47", "47.1", "47.3", "47.4", "47.5", "47.6", "47.7", "47.8", "48", "136.1", "137", "216", "339"], "peticao"),
    (["56", "57", "58", "59", "60", "61", "62", "63", "64", "66", "25.1", "25.4", "25.7", "14.4"], "transferencia_alteracao"),
    (["49", "53", "53.1", "53.5", "53.7", "54", "54.1", "75", "75.1", "76", "214", "218", "141", "140", "211", "15.12", "15.22.1", "51", "50", "2.6"], "administrativo"),
    (["70", "71", "72", "73", "74", "133", "132", "135", "213", "215", "219", "220", "15.21", "15.30", "25.12", "52", "9.1.2"], "anulacao_retificacao"),
]:
    for _c in _codes:
        EVENTO_POR_CODIGO.setdefault(_c, _ev)
_RE_ANUL = re.compile(r"anulad|retifica|republica|renumera", re.I)


def classify_despacho(codigo: str, descricao: str | None) -> str:
    if codigo in EVENTO_POR_CODIGO:
        return EVENTO_POR_CODIGO[codigo]
    if descricao and _RE_ANUL.search(descricao):
        return "anulacao_retificacao"
    return "outros"


_NATUREZA = {"DI": "Direta", "30": "Direta", "31": "Via Haia", "32": "Dividido (provável)", "33": "Outro"}


def transform_deposito(df: pd.DataFrame) -> pd.DataFrame:
    no = df["NO_PEDIDO"].astype("string")
    pref = no.str.extract(r"^(DI|3[0-3])(?=\d)")[0].astype("string")
    return pd.DataFrame({
        "no_pedido": no, "ano": to_int(df["ANO"], "Int16"),
        "dt_entrada_inpi": parse_datetime(df["DT_ENTRADA_INPI"]), "dt_deposito": parse_date(df["DT_DEPOSITO"]),
        "titulo": df["NM_TITULO_DI"], "prefixo_numero": pref,
        "via": pref.map(_NATUREZA).astype("string"),
        "formato_numero": pd.Series("novo", index=df.index, dtype="string").mask(pref == "DI", "antigo"),
    })


def transform_autor(df: pd.DataFrame) -> pd.DataFrame:
    out = pessoa_base(df)
    return out.drop(columns=["nome", "nome_norm", "documento"])


def transform_despacho(df: pd.DataFrame) -> pd.DataFrame:
    cd = df["CD_DESPACH_RPI"].astype("string"); ds = df["DS_TIPO_DESPACH"].astype("string")
    pairs = pd.DataFrame({"cd": cd, "ds": ds}).drop_duplicates()
    cache = {c: classify_despacho(c, None if d is pd.NA else d) for c, d in zip(pairs["cd"], pairs["ds"]) if c is not pd.NA}
    dt = parse_date(df["DT_PUBLICACAO"])
    desc_novos = {c: d for c, (d, _) in CODIGOS_NOVOS.items()}
    return pd.DataFrame({"no_pedido": df["NO_PEDIDO"], "no_rpi": to_int(df["NO_RPI"], "Int32"), "dt_publicacao": dt,
                         "cd_despacho": cd, "ds_despacho": ds.fillna(cd.map(desc_novos)).astype("string"),
                         "evento": cd.map(cache).astype("string"), "ano_publicacao": dt.dt.year.astype("Int16")})


def transform_classe(df: pd.DataFrame) -> pd.DataFrame:
    raw = df["CD_CLASSIF"].str.replace(r"\s+", " ", regex=True)
    m = raw.str.extract(r"^(\d{1,2})[-\.\s](\d{1,2})")
    classe = to_int(m[0], "Int8"); sub = to_int(m[1], "Int8")
    return pd.DataFrame({
        "no_pedido": df["NO_PEDIDO"], "ordem": to_int(df["NO_ORDEM_PEDIDO"], "Int16"), "classificacao": raw,
        "classe_locarno": classe,
        "subclasse_locarno": (classe.astype("string").str.zfill(2) + "-" + sub.astype("string").str.zfill(2)).where(classe.notna() & sub.notna()).astype("string"),
        "versao_locarno": df["VERSION_INDICATOR"],
    })


def _fim_vigencia(out: pd.DataFrame) -> pd.Series:
    """DI: 10 anos do depósito, prorrogáveis por 3 períodos de 5 anos (máximo 25 anos, Art. 108 da LPI)."""
    return out["dt_deposito"] + pd.DateOffset(years=25)


def build(force: bool = False):
    bronze, out = SRC.bronze_dir, SRC.silver_dir
    if not (bronze / "_manifest.json").exists():
        raise FileNotFoundError(f"bronze de desenho industrial ausente em {bronze}. Rode 'badepi bronze -s desenho_industrial'.")
    manifest_path = out / "_manifest.json"
    zip_sha = read_json(bronze / "_manifest.json").get("zip_sha256")
    if manifest_path.exists() and not force and read_json(manifest_path).get("bronze_zip_sha256") == zip_sha:
        log.info("[desenho_industrial] silver já construída; use --force para refazer")
        return out
    out.mkdir(parents=True, exist_ok=True)
    tables: dict[str, dict] = {}

    def register(name, df, path, partition=None, key=None):
        rows = write_parquet(df, path, [partition] if partition else None)
        tables[name] = {"path": str(path.relative_to(out)), "rows": int(rows), "partitioned_by": partition, "key": key or [],
                        "columns": {c: str(t) for c, t in df.dtypes.items()}}
        log.info("[desenho_industrial] %s: %s linhas → %s", name, f"{rows:,}", path.name)

    dep = transform_deposito(read_badepi_csv(bronze / CSV.format("deposito"))).drop_duplicates("no_pedido")
    dpt = transform_depositante(read_badepi_csv(bronze / CSV.format("depositante")))
    register("di_depositante", dpt, out / "di_depositante.parquet", key=["no_pedido", "no_ordem"])
    primeiro = primeiro_depositante(dpt)
    n_dpt = dpt.groupby("no_pedido").size().rename("n_depositantes").astype("Int16")
    aut = transform_autor(read_badepi_csv(bronze / CSV.format("autor")))
    register("di_autor", aut, out / "di_autor.parquet", key=["no_pedido", "no_ordem"])
    aut_stats = aut.groupby("no_pedido").agg(n_autores=("no_ordem", "size"), n_autores_br=("pais", lambda s: int((s == "BR").sum()))).astype("Int16")
    des = transform_despacho(read_badepi_csv(bronze / CSV.format("despacho")))
    register("di_despacho", des, out / "di_despacho.parquet", key=["no_pedido", "no_rpi", "cd_despacho"])
    referencia = des["dt_publicacao"].max()
    cls = transform_classe(read_badepi_csv(bronze / CSV.format("classes")))
    register("di_classe", cls, out / "di_classe.parquet", key=["no_pedido", "ordem"])
    cls_main = cls.sort_values(["no_pedido", "ordem"]).drop_duplicates("no_pedido")[["no_pedido", "classe_locarno", "subclasse_locarno"]]
    cls_main = cls_main.rename(columns={"classe_locarno": "classe_locarno_principal", "subclasse_locarno": "subclasse_locarno_principal"})
    n_cls = cls.groupby("no_pedido").size().rename("n_classes").astype("Int16")

    dep = (dep.merge(primeiro, on="no_pedido", how="left").merge(n_dpt, left_on="no_pedido", right_index=True, how="left")
              .merge(aut_stats, left_on="no_pedido", right_index=True, how="left").merge(cls_main, on="no_pedido", how="left")
              .merge(n_cls, left_on="no_pedido", right_index=True, how="left"))
    for c in ["n_depositantes", "n_autores", "n_autores_br", "n_classes"]:
        dep[c] = dep[c].fillna(0).astype("Int16")
    dep["residente"] = (dep["pais_origem"] == "BR").astype("boolean")
    dep = dep.drop(columns=["prefixo_numero"])
    register("di_deposito", dep, out / "di_deposito.parquet", key=["no_pedido"])

    sit = derive_situacao(des[["no_pedido", "dt_publicacao", "evento"]], dep[["no_pedido", "dt_deposito", "dt_entrada_inpi"]], referencia, fim_vigencia=_fim_vigencia)
    register("di_situacao", sit, out / "di_situacao.parquet", key=["no_pedido"])

    dim_rows = [des.groupby(["cd_despacho", "ds_despacho", "evento"], observed=True, dropna=False).size().rename("n").reset_index()]
    dim_desp = dim_despacho_from_parts(dim_rows, descricoes={c: d for c, (d, _) in CODIGOS_NOVOS.items()})
    dim_desp["descricao"] = dim_desp["descricao"].fillna("Código não documentado no BADEPI")
    register("dim_despacho", dim_desp, out / "dim_despacho.parquet", key=["cd_despacho"])
    register("dim_pais", load_reference("paises"), out / "dim_pais.parquet", key=["pais"])
    register("dim_uf", load_reference("ufs"), out / "dim_uf.parquet", key=["uf"])
    src = PIGEN.bronze_dir / f"badepi{BADEPI_VERSION}_di_depositante_pigen.csv"
    if src.exists():
        register("di_depositante_genero", transform_genero(read_badepi_csv(src)), out / "di_depositante_genero.parquet", key=["no_pedido", "seq"])

    manifest = {"badepi_version": BADEPI_VERSION, "source": "desenho_industrial", "bronze_zip_sha256": zip_sha,
                "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data_referencia": referencia.date().isoformat(), "tables": tables}
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    log.info("[desenho_industrial] silver concluída em %s", out)
    return out
