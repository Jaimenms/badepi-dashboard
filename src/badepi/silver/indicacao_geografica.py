"""Silver — Indicação Geográfica (badepiv12_ig_*.csv → parquet).

Tabelas em data/silver/indicacao_geografica/: ig_deposito (+ origem, classificação OMPI), ig_depositante, ig_despacho,
ig_classificacao, ig_situacao, dim_despacho, dim_pais, dim_uf. Base pequena (≈250 pedidos desde 2000).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pandas as pd

from ..config import BADEPI_VERSION, SOURCES
from ..ioutil import read_badepi_csv, read_json, write_parquet
from .common import derive_situacao, dim_despacho_from_parts, load_reference, parse_date, parse_datetime, primeiro_depositante, to_int, transform_depositante

log = logging.getLogger(__name__)
SRC = SOURCES["indicacao_geografica"]
CSV = f"badepi{BADEPI_VERSION}_ig_{{}}.csv"

EVENTO_POR_CODIGO = {
    "1": "deposito", "335": "publicacao", "336": "publicacao_alteracao", "340": "oposicao", "303": "exigencia", "304": "exigencia",
    "305": "exigencia", "306": "exigencia", "307": "exigencia", "315": "exigencia", "400": "exigencia", "373": "deferimento",
    "374": "peticao_deferida", "375": "indeferimento", "395": "concessao", "325": "arquivamento", "380": "recurso", "385": "recurso_provido",
    "390": "recurso_negado", "410": "peticao", "415": "desistencia_retirada", "416": "administrativo", "419": "anulacao_retificacao",
    "423": "anulacao_retificacao",
}
TIPO = {"IP": "Indicação de Procedência", "DO": "Denominação de Origem"}


def transform_deposito(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "no_pedido": df["NO_PEDIDO"], "ano": to_int(df["ANO"], "Int16"),
        "dt_entrada_inpi": parse_datetime(df["DT_ENTRADA_INPI"]), "dt_deposito": parse_date(df["DT_ENTRADA_INPI"]),
        "nome_ig": df["NM_IG"], "tipo": df["TIPO_IG"], "tipo_nome": df["TIPO_IG"].map(TIPO).astype("string"),
        "tipo_atual": df["TIPO_IG_ALTER"], "especie_atual": df["DS_ESPECIE_ALTER"], "dt_alteracao_especie": parse_date(df["DT_ALTERACAO"]),
        "formato_numero": pd.Series("novo", index=df.index, dtype="string").mask(df["NO_PEDIDO"].str.startswith("IG"), "antigo"),
    })


def transform_despacho(df: pd.DataFrame) -> pd.DataFrame:
    cd = df["CD_DESPACH_RPI"].astype("string")
    dt = parse_date(df["DT_PUBLICACAO"])
    return pd.DataFrame({"no_pedido": df["NO_PEDIDO"], "no_rpi": to_int(df["NO_RPI"], "Int32"), "dt_publicacao": dt, "cd_despacho": cd,
                         "ds_despacho": df["DS_SITUACAO_NV"], "evento": cd.map(EVENTO_POR_CODIGO).fillna("outros").astype("string"),
                         "ano_publicacao": dt.dt.year.astype("Int16")})


def transform_classificacao(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"no_pedido": df["NO_PEDIDO"], "classe_produto_servico": df["DS_CLASSE_PROD_SERV"].str.strip().str.capitalize(),
                         "classificacao_wipo": df["CLASSIF_WIPO"]})


def build(force: bool = False):
    bronze, out = SRC.bronze_dir, SRC.silver_dir
    if not (bronze / "_manifest.json").exists():
        raise FileNotFoundError(f"bronze de IG ausente em {bronze}. Rode 'badepi bronze -s indicacao_geografica'.")
    manifest_path = out / "_manifest.json"
    zip_sha = read_json(bronze / "_manifest.json").get("zip_sha256")
    if manifest_path.exists() and not force and read_json(manifest_path).get("bronze_zip_sha256") == zip_sha:
        log.info("[indicacao_geografica] silver já construída; use --force para refazer")
        return out
    out.mkdir(parents=True, exist_ok=True)
    tables: dict[str, dict] = {}

    def register(name, df, path, key=None):
        rows = write_parquet(df, path)
        tables[name] = {"path": str(path.relative_to(out)), "rows": int(rows), "partitioned_by": None, "key": key or [],
                        "columns": {c: str(t) for c, t in df.dtypes.items()}}
        log.info("[indicacao_geografica] %s: %s linhas → %s", name, f"{rows:,}", path.name)

    dep = transform_deposito(read_badepi_csv(bronze / CSV.format("deposito"))).drop_duplicates("no_pedido")
    dpt = transform_depositante(read_badepi_csv(bronze / CSV.format("depositante")))
    dpt["no_ordem"] = dpt.groupby("no_pedido").cumcount().add(1).astype("Int16")
    register("ig_depositante", dpt, out / "ig_depositante.parquet", key=["no_pedido", "no_ordem"])
    des = transform_despacho(read_badepi_csv(bronze / CSV.format("despacho")))
    register("ig_despacho", des, out / "ig_despacho.parquet", key=["no_pedido", "no_rpi", "cd_despacho"])
    referencia = des["dt_publicacao"].max()
    cl = transform_classificacao(read_badepi_csv(bronze / CSV.format("classif_wipo"))).drop_duplicates("no_pedido")
    register("ig_classificacao", cl, out / "ig_classificacao.parquet", key=["no_pedido"])

    dep = dep.merge(primeiro_depositante(dpt), on="no_pedido", how="left").merge(cl, on="no_pedido", how="left")
    dep["residente"] = (dep["pais_origem"] == "BR").astype("boolean")
    register("ig_deposito", dep, out / "ig_deposito.parquet", key=["no_pedido"])
    sit = derive_situacao(des[["no_pedido", "dt_publicacao", "evento"]], dep[["no_pedido", "dt_deposito", "dt_entrada_inpi"]], referencia)
    register("ig_situacao", sit, out / "ig_situacao.parquet", key=["no_pedido"])
    dim_desp = dim_despacho_from_parts([des.groupby(["cd_despacho", "ds_despacho", "evento"], observed=True, dropna=False).size().rename("n").reset_index()])
    register("dim_despacho", dim_desp, out / "dim_despacho.parquet", key=["cd_despacho"])
    register("dim_pais", load_reference("paises"), out / "dim_pais.parquet", key=["pais"])
    register("dim_uf", load_reference("ufs"), out / "dim_uf.parquet", key=["uf"])
    manifest = {"badepi_version": BADEPI_VERSION, "source": "indicacao_geografica", "bronze_zip_sha256": zip_sha,
                "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data_referencia": referencia.date().isoformat(), "tables": tables}
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    log.info("[indicacao_geografica] silver concluída em %s", out)
    return out
