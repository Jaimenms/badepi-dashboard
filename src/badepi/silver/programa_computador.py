"""Silver — Programa de Computador (badepiv12_prg_*.csv → parquet).

Tabelas em data/silver/programa_computador/: prg_deposito (+ origem, tipo principal), prg_depositante, prg_autor (com nomes),
prg_tipo (vários tipos por pedido), prg_despacho, prg_situacao, dim_tipo_programa, dim_despacho, dim_pais, dim_uf, prg_depositante_genero.

Atenção: no BADEPI v12 a tabela de despachos cobre só publicações de 2017 a 2023 (31% dos pedidos). Pedidos sem nenhum
despacho recebem a situação "Sem despacho na base" em vez de "Em andamento".
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pandas as pd

from ..config import BADEPI_VERSION, SOURCES
from ..ioutil import read_badepi_csv, read_json, write_parquet
from .common import derive_situacao, dim_despacho_from_parts, load_reference, parse_date, parse_datetime, pessoa_base, primeiro_depositante, to_int, transform_depositante, transform_genero

log = logging.getLogger(__name__)
SRC = SOURCES["programa_computador"]
PIGEN = SOURCES["pi_genero"]
CSV = f"badepi{BADEPI_VERSION}_prg_{{}}.csv"

GRUPOS = {"AP": "Aplicativos", "AT": "Automação", "AV": "Avaliação de desempenho", "CD": "Comunicação de dados", "CT": "Comutação e telecomunicações",
          "DS": "Desenvolvimento de sistemas", "ET": "Entretenimento", "FA": "Ferramentas de apoio", "GI": "Gerenciadores de informações",
          "IA": "Inteligência artificial", "IT": "Instrumentação", "LG": "Linguagens e compiladores", "PD": "Proteção de dados",
          "SM": "Simulação e modelagem", "SO": "Software básico e sistema operacional", "TC": "Técnico-científico", "TI": "Teleinformática",
          "UT": "Utilitários", "OO": "Não informado", "XX": "Código inválido"}
EVENTO_POR_CODIGO = {
    "730": "concessao", "120": "concessao", "080": "publicacao", "090": "deferimento", "105": "desistencia_retirada", "709": "extincao", "106": "extincao",
    "734": "transferencia_alteracao", "704": "transferencia_alteracao", "100": "transferencia_alteracao", "740": "transferencia_alteracao",
    "732": "transferencia_alteracao", "733": "transferencia_alteracao", "731": "transferencia_alteracao", "091": "transferencia_alteracao", "097": "transferencia_alteracao",
    "747": "retificacao", "111": "anulacao_retificacao", "110": "anulacao_retificacao", "113": "anulacao_retificacao", "744": "anulacao", "745": "restauracao",
    "742": "peticao", "104": "peticao", "108": "administrativo", "741": "administrativo", "736": "administrativo", "115": "recurso",
}
SEM_DESPACHO = "Sem despacho na base"


def transform_deposito(df: pd.DataFrame) -> pd.DataFrame:
    no = df["NO_PEDIDO"].astype("string")
    novo = no.str.match(r"^5\d{11}$")
    return pd.DataFrame({"no_pedido": no, "ano": to_int(df["ANO"], "Int16"), "dt_entrada_inpi": parse_datetime(df["DT_ENTRADA_INPI"]),
                         "dt_deposito": parse_date(df["DT_ENTRADA_INPI"]), "titulo": df["NM_TITULO_PROGRAMA"],
                         "formato_numero": pd.Series("antigo", index=df.index, dtype="string").mask(novo, "novo")})


def transform_autor(df: pd.DataFrame) -> pd.DataFrame:
    out = pessoa_base(df)
    out["no_ordem"] = out.groupby("no_pedido").cumcount().add(1).astype("Int16")
    out.insert(2, "tipo_pessoa", df["CD_TIPO_PFPJ"])
    return out[["no_pedido", "no_ordem", "tipo_pessoa", "nome", "nome_norm", "documento", "pais", "uf", "cidade", "codigo_ibge_municipio"]]


def transform_tipo(df: pd.DataFrame) -> pd.DataFrame:
    cd = df["CD_TIPO_PROGRAMA"].str.strip().str.upper()
    ds = df["DS_TIPO_PROGRAMA"].str.replace(r"\s+", " ", regex=True).str.strip()
    nome = ds.str.split(" - ", n=1).str[-1].str.strip().str.replace("ä", "ã").str.replace("ö", "õ")
    grupo = cd.str[:2]
    out = pd.DataFrame({"no_pedido": df["NO_PEDIDO"], "cd_tipo": cd, "nome_tipo": nome.astype("string"), "grupo": grupo,
                        "nome_grupo": grupo.map(GRUPOS).fillna("Outros").astype("string")})
    out["ordem"] = out.groupby("no_pedido").cumcount().add(1).astype("Int16")
    return out[["no_pedido", "ordem", "cd_tipo", "nome_tipo", "grupo", "nome_grupo"]]


def transform_despacho(df: pd.DataFrame) -> pd.DataFrame:
    cd = df["CD_DESPACH"].astype("string"); dt = parse_date(df["DT_PUBLICACAO"])
    return pd.DataFrame({"no_pedido": df["NO_PEDIDO"], "no_rpi": to_int(df["NO_RPI"], "Int32"), "dt_publicacao": dt, "cd_despacho": cd,
                         "ds_despacho": df["DS_DESPACH"], "evento": cd.map(EVENTO_POR_CODIGO).fillna("outros").astype("string"),
                         "ano_publicacao": dt.dt.year.astype("Int16")})


def build(force: bool = False):
    bronze, out = SRC.bronze_dir, SRC.silver_dir
    if not (bronze / "_manifest.json").exists():
        raise FileNotFoundError(f"bronze de programas ausente em {bronze}. Rode 'badepi bronze -s programa_computador'.")
    manifest_path = out / "_manifest.json"
    zip_sha = read_json(bronze / "_manifest.json").get("zip_sha256")
    if manifest_path.exists() and not force and read_json(manifest_path).get("bronze_zip_sha256") == zip_sha:
        log.info("[programa_computador] silver já construída; use --force para refazer")
        return out
    out.mkdir(parents=True, exist_ok=True)
    tables: dict[str, dict] = {}

    def register(name, df, path, key=None):
        rows = write_parquet(df, path)
        tables[name] = {"path": str(path.relative_to(out)), "rows": int(rows), "partitioned_by": None, "key": key or [], "columns": {c: str(t) for c, t in df.dtypes.items()}}
        log.info("[programa_computador] %s: %s linhas → %s", name, f"{rows:,}", path.name)

    dep = transform_deposito(read_badepi_csv(bronze / CSV.format("deposito"))).drop_duplicates("no_pedido")
    dpt = transform_depositante(read_badepi_csv(bronze / CSV.format("depositante")))
    dpt["no_ordem"] = dpt.groupby("no_pedido").cumcount().add(1).astype("Int16")
    dpt = dpt[["no_pedido", "no_ordem"] + [c for c in dpt.columns if c not in ("no_pedido", "no_ordem")]]
    register("prg_depositante", dpt, out / "prg_depositante.parquet", key=["no_pedido", "no_ordem"])
    primeiro = primeiro_depositante(dpt); n_dpt = dpt.groupby("no_pedido").size().rename("n_depositantes").astype("Int16")
    aut = transform_autor(read_badepi_csv(bronze / CSV.format("autor")))
    register("prg_autor", aut, out / "prg_autor.parquet", key=["no_pedido", "no_ordem"])
    aut_stats = aut.groupby("no_pedido").agg(n_autores=("no_ordem", "size"), n_autores_br=("pais", lambda s: int((s == "BR").sum()))).astype("Int16")
    tipo = transform_tipo(read_badepi_csv(bronze / CSV.format("tipo")))
    register("prg_tipo", tipo, out / "prg_tipo.parquet", key=["no_pedido", "ordem"])
    tipo_main = tipo[tipo["ordem"] == 1][["no_pedido", "cd_tipo", "grupo", "nome_grupo"]].rename(columns={"cd_tipo": "tipo_principal", "grupo": "grupo_principal", "nome_grupo": "nome_grupo_principal"})
    n_tipos = tipo.groupby("no_pedido").size().rename("n_tipos").astype("Int16")
    des = transform_despacho(read_badepi_csv(bronze / CSV.format("despacho")))
    register("prg_despacho", des, out / "prg_despacho.parquet", key=["no_pedido", "no_rpi", "cd_despacho"])
    referencia = des["dt_publicacao"].max()

    dep = (dep.merge(primeiro, on="no_pedido", how="left").merge(n_dpt, left_on="no_pedido", right_index=True, how="left")
              .merge(aut_stats, left_on="no_pedido", right_index=True, how="left").merge(tipo_main, on="no_pedido", how="left")
              .merge(n_tipos, left_on="no_pedido", right_index=True, how="left"))
    for c in ["n_depositantes", "n_autores", "n_autores_br", "n_tipos"]:
        dep[c] = dep[c].fillna(0).astype("Int16")
    dep["residente"] = (dep["pais_origem"] == "BR").astype("boolean")
    register("prg_deposito", dep, out / "prg_deposito.parquet", key=["no_pedido"])

    sit = derive_situacao(des[["no_pedido", "dt_publicacao", "evento"]], dep[["no_pedido", "dt_deposito", "dt_entrada_inpi"]], referencia)
    sit["situacao"] = sit["situacao"].mask((sit["n_despachos"] == 0) & (sit["situacao"] == "Em andamento"), SEM_DESPACHO).astype("string")
    register("prg_situacao", sit, out / "prg_situacao.parquet", key=["no_pedido"])

    dim_tipo = (tipo.groupby(["cd_tipo", "grupo", "nome_grupo"], observed=True).agg(nome_tipo=("nome_tipo", lambda s: s.value_counts().index[0]), n=("no_pedido", "size"))
                .reset_index()[["cd_tipo", "nome_tipo", "grupo", "nome_grupo", "n"]])
    dim_tipo["n"] = dim_tipo["n"].astype("Int32")
    register("dim_tipo_programa", dim_tipo, out / "dim_tipo_programa.parquet", key=["cd_tipo"])
    register("dim_despacho", dim_despacho_from_parts([des.groupby(["cd_despacho", "ds_despacho", "evento"], observed=True, dropna=False).size().rename("n").reset_index()]), out / "dim_despacho.parquet", key=["cd_despacho"])
    register("dim_pais", load_reference("paises"), out / "dim_pais.parquet", key=["pais"])
    register("dim_uf", load_reference("ufs"), out / "dim_uf.parquet", key=["uf"])
    src = PIGEN.bronze_dir / f"badepi{BADEPI_VERSION}_prg_depositante_pigen.csv"
    if src.exists():
        register("prg_depositante_genero", transform_genero(read_badepi_csv(src)), out / "prg_depositante_genero.parquet", key=["no_pedido", "seq"])
    manifest = {"badepi_version": BADEPI_VERSION, "source": "programa_computador", "bronze_zip_sha256": zip_sha,
                "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data_referencia": referencia.date().isoformat(), "tables": tables,
                "nota": "A tabela de despachos cobre só publicações de 2017 a 2023; pedidos sem despacho recebem 'Sem despacho na base'."}
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    log.info("[programa_computador] silver concluída em %s", out)
    return out
