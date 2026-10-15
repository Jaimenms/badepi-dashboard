"""Silver — Marcas (badepiv12_mrc_*.csv → parquet relacionado).

Tabelas em data/silver/marcas/:
  mrc_deposito      1 linha por pedido + origem (1º depositante), via (direta/Madri), classe principal
  mrc_depositante   n por pedido (no_pedido + no_ordem)
  mrc_classe        n por pedido (classe de Nice)
  mrc_despacho/     19 milhões de linhas, particionada por ano_publicacao (só o código: o BADEPI não traz a descrição)
  mrc_situacao      1 por pedido: situação derivada + marcos
  mrc_depositante_genero, dim_despacho, dim_pais, dim_uf

Os despachos de marcas vêm sem descrição. A tabela dim_despacho traz a descrição curada dos códigos
decisivos (confirmada em publicações da RPI) e marca os demais como não documentados.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pandas as pd

from ..config import BADEPI_VERSION, SOURCES
from ..ioutil import ParquetSink, iter_badepi_csv, read_badepi_csv, read_json, write_parquet
from .common import (derive_situacao, dim_despacho_from_parts, load_reference, parse_date, parse_datetime,
                     primeiro_depositante, to_int, transform_depositante, transform_genero)

log = logging.getLogger(__name__)
SRC = SOURCES["marcas"]
PIGEN = SOURCES["pi_genero"]
CSV = f"badepi{BADEPI_VERSION}_mrc_{{}}.csv"
CHUNK = 1_000_000

NATUREZA = {"1": "Produto", "2": "Serviço", "8": "Produto/Serviço", "3": "Coletiva", "4": "Certificação", "6": "Genérica", "7": "Propaganda"}
APRESENTACAO = {"M": "Mista", "D": "Nominativa", "F": "Figurativa", "T": "Tridimensional", "P": "Posição", "O": "Outra"}

# código → (descrição, evento). "(inferido)" = deduzido da cronologia típica dos processos; os demais foram
# confirmados em publicações da RPI. Códigos de três dígitos sem prefixo (2000–2013 e 2024) equivalem aos IPAS/DESP.
CODIGOS: dict[str, tuple[str, str]] = {
    "DESP000": ("Pedido de registro depositado (notificação)", "deposito"),
    "DESP003": ("Publicação do pedido de registro para oposição (Art. 158 da LPI)", "publicacao"),
    "DESP241": ("Pedido sobrestado, aguardando decisão definitiva sobre pedido anterior", "sobrestamento"),
    "DESP100": ("Indeferimento do pedido de registro", "indeferimento"),
    "DESP145": ("Arquivamento do pedido por decurso do prazo de recurso", "arquivamento"),
    "DESP351": ("Deferimento do pedido de registro (Art. 122 da LPI)", "deferimento"),
    "DESP400": ("Concessão do registro", "concessao"),
    "DESP150": ("Arquivamento definitivo do pedido por falta de pagamento da concessão (inferido)", "arquivamento"),
    "DESP560": ("Anotação de alteração de nome, sede ou endereço", "transferencia_alteracao"),
    "DESP565": ("Anotação de transferência de titularidade", "transferencia_alteracao"),
    "IPAS009": ("Publicação de pedido de registro para oposição (exame formal concluído)", "publicacao"),
    "IPAS005": ("Exigência formal (inferido)", "exigencia"),
    "IPAS423": ("Notificação de oposição", "oposicao"),
    "IPAS142": ("Exigência de mérito (código usado até 2024, inferido)", "exigencia"),
    "IPAS136": ("Exigência de mérito", "exigencia"),
    "IPAS029": ("Deferimento do pedido", "deferimento"),
    "IPAS158": ("Concessão de registro", "concessao"),
    "IPAS157": ("Arquivamento definitivo de pedido de registro por falta de pagamento da concessão", "arquivamento"),
    "IPAS139": ("Arquivamento definitivo de pedido de registro por falta de cumprimento de exigência de mérito", "arquivamento"),
    "IPAS024": ("Indeferimento do pedido", "indeferimento"),
    "IPAS360": ("Notificação de recurso contra o indeferimento", "recurso"),
    "IPAS237": ("Recurso provido: reformada a decisão para deferimento", "recurso_provido"),
    "IPAS235": ("Recurso não provido: mantido o indeferimento (inferido)", "recurso_negado"),
    "IPAS161": ("Extinção de registro", "extincao"),
    "IPAS270": ("Deferimento de petição (prorrogação, transferência, alteração de nome/sede etc.)", "peticao_deferida"),
    "IPAS271": ("Indeferimento de petição", "peticao"),
    "IPAS428": ("Petição não conhecida", "peticao"),
    "IPAS577": ("Emissão de folha de rosto de cópia reprográfica", "administrativo"),
    "IPAS532": ("Nulidade: requerimento não provido (mantida a concessão)", "nulidade"),
    "IPAS400": ("Notificação de instauração de processo administrativo de nulidade", "nulidade"),
    "IPAS566": ("Petição de retificação atendida", "retificacao"),
}
_ALIAS = {"000": "DESP000", "003": "DESP003", "241": "DESP241", "100": "DESP100", "145": "DESP145", "351": "DESP351",
          "400": "DESP400", "150": "DESP150", "560": "DESP560", "565": "DESP565"}


def classify_despacho(codigo: str) -> tuple[str, str]:
    c = codigo.strip()
    if c in CODIGOS:
        return CODIGOS[c]
    if c.isdigit():
        if c in _ALIAS and _ALIAS[c] in CODIGOS:
            return CODIGOS[_ALIAS[c]]
        if "IPAS" + c in CODIGOS:
            return CODIGOS["IPAS" + c]
    return ("Código não documentado no BADEPI", "outros")


def transform_deposito(df: pd.DataFrame) -> pd.DataFrame:
    ds = df["DS_NATUREZ_MARCA"].fillna("")
    return pd.DataFrame({
        "no_pedido": df["NO_PEDIDO"],
        "ano": to_int(df["ANO"], "Int16"),
        "dt_entrada_inpi": parse_datetime(df["DT_ENTRADA_INPI"]),
        "dt_deposito": parse_date(df["DT_DEPOSITO"]),
        "marca": df["NM_TITULO_MARCA"],
        "via": df["TP_ENTRADA"].map({"M": "Direta", "T": "Madri"}).astype("string"),
        "cd_natureza": df["CD_NATUREZ_MARCA"],
        "natureza": df["CD_NATUREZ_MARCA"].map(NATUREZA).astype("string"),
        "madri": ds.str.contains("Madri", case=False).astype("boolean"),
        "cd_apresentacao": df["CD_APRESEN_MARCA"],
        "apresentacao": df["CD_APRESEN_MARCA"].map(APRESENTACAO).astype("string"),
    })


def transform_classe(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "no_pedido": df["NO_PEDIDO"],
        "classe_nice": to_int(df["CD_CLASSE_NICE"], "Int8"),
        "revisao_nice": to_int(df["REV_CLASSE_NICE"], "Int8"),
        "status_classe": df["ST_CLASSE_NICE"],
    })


def transform_despacho(df: pd.DataFrame, cache: dict) -> pd.DataFrame:
    cd = df["CD_DESPACH_RPI"].astype("string")
    for c in cd.dropna().unique():
        if c not in cache:
            cache[c] = classify_despacho(c)[1]
    dt = parse_date(df["DT_PUBLICACAO"])
    return pd.DataFrame({
        "no_pedido": df["NO_PEDIDO"],
        "no_rpi": to_int(df["NO_RPI"], "Int32"),
        "dt_publicacao": dt,
        "cd_despacho": cd,
        "evento": cd.map(cache).astype("string"),
        "ano_publicacao": dt.dt.year.astype("Int16"),
    })


def build(force: bool = False):
    bronze, out = SRC.bronze_dir, SRC.silver_dir
    if not (bronze / "_manifest.json").exists():
        raise FileNotFoundError(f"bronze de marcas ausente em {bronze}. Rode 'badepi bronze -s marcas'.")
    manifest_path = out / "_manifest.json"
    zip_sha = read_json(bronze / "_manifest.json").get("zip_sha256")
    if manifest_path.exists() and not force and read_json(manifest_path).get("bronze_zip_sha256") == zip_sha:
        log.info("[marcas] silver já construída a partir desta bronze; use --force para refazer")
        return out
    out.mkdir(parents=True, exist_ok=True)
    tables: dict[str, dict] = {}

    def register(name, rows, sample, path, partition=None, key=None):
        tables[name] = {"path": str(path.relative_to(out)), "rows": int(rows), "partitioned_by": partition, "key": key or [],
                        "columns": {c: str(t) for c, t in sample.dtypes.items()}}
        log.info("[marcas] %s: %s linhas → %s", name, f"{rows:,}", path.name)

    # 1) depósitos (mantidos em memória para o enriquecimento final) ---------------
    log.info("[marcas] lendo depósitos")
    dep = pd.concat([transform_deposito(ch) for ch in iter_badepi_csv(bronze / CSV.format("deposito"), chunksize=CHUNK)], ignore_index=True)
    dep = dep.drop_duplicates("no_pedido")

    # 2) depositantes ----------------------------------------------------------------
    log.info("[marcas] lendo depositantes")
    firsts, counts = [], []
    p = out / "mrc_depositante.parquet"
    with ParquetSink(p) as sink:
        for ch in iter_badepi_csv(bronze / CSV.format("depositante"), chunksize=CHUNK):
            t = transform_depositante(ch, ordem_default=1)
            sink.write(t)
            firsts.append(primeiro_depositante(t))
            counts.append(t.groupby("no_pedido").size())
        sample = t
    register("mrc_depositante", sink.rows, sample, p, key=["no_pedido", "no_ordem"])
    primeiro = pd.concat(firsts).drop_duplicates("no_pedido")
    n_dpt = pd.concat(counts).groupby(level=0).sum().rename("n_depositantes").astype("Int16")
    del firsts, counts

    # 3) classes de Nice ----------------------------------------------------------------
    log.info("[marcas] lendo classes")
    cls_parts = []
    p = out / "mrc_classe.parquet"
    with ParquetSink(p) as sink:
        for ch in iter_badepi_csv(bronze / CSV.format("classes"), chunksize=CHUNK):
            t = transform_classe(ch)
            sink.write(t)
            cls_parts.append(t.groupby("no_pedido").agg(classe_nice_principal=("classe_nice", "first"), n_classes=("classe_nice", "size")))
        sample = t
    register("mrc_classe", sink.rows, sample, p, key=["no_pedido", "classe_nice"])
    cls = pd.concat(cls_parts).groupby(level=0).agg(classe_nice_principal=("classe_nice_principal", "first"), n_classes=("n_classes", "sum"))
    cls["n_classes"] = cls["n_classes"].astype("Int16")
    del cls_parts

    # 4) despachos (particionado; agregados parciais para a situação) --------------------
    log.info("[marcas] lendo despachos (19 milhões de linhas)")
    cache: dict[str, str] = {}
    ev_parts, cnt_parts, dim_rows = [], [], []
    p = out / "mrc_despacho"
    with ParquetSink(p, partition_cols=["ano_publicacao"]) as sink:
        for i, ch in enumerate(iter_badepi_csv(bronze / CSV.format("despacho"), chunksize=2_000_000)):
            t = transform_despacho(ch, cache)
            sink.write(t)
            g = t.groupby(["no_pedido", "evento"], observed=True)["dt_publicacao"].agg(["min", "max"]).reset_index()
            ev_parts.append(g)
            c = t.groupby("no_pedido").agg(n_despachos=("evento", "size"), dt_primeiro_despacho=("dt_publicacao", "min"), dt_ultimo_despacho=("dt_publicacao", "max"))
            c["n_exigencias"] = t[t["evento"] == "exigencia"].groupby("no_pedido").size()
            cnt_parts.append(c)
            dim_rows.append(t.groupby(["cd_despacho", "evento"], observed=True).size().rename("n").reset_index())
            log.info("[marcas]   bloco %d (%s linhas acumuladas)", i + 1, f"{sink.rows:,}")
        sample = t
    register("mrc_despacho", sink.rows, sample, p, partition="ano_publicacao", key=["no_pedido", "no_rpi", "cd_despacho"])
    referencia = max(x["dt_ultimo_despacho"].max() for x in cnt_parts)
    evp = pd.concat(ev_parts, ignore_index=True); del ev_parts
    evp = evp.groupby(["no_pedido", "evento"], observed=True).agg(min=("min", "min"), max=("max", "max")).reset_index()
    # frame reduzido de eventos: primeira e última data de cada (pedido, evento) reproduzem exatamente first/last
    ev = pd.concat([evp[["no_pedido", "evento", "min"]].rename(columns={"min": "dt_publicacao"}),
                    evp[["no_pedido", "evento", "max"]].rename(columns={"max": "dt_publicacao"})], ignore_index=True)
    del evp
    ev["evento"] = ev["evento"].astype("category")
    cnt = pd.concat(cnt_parts); del cnt_parts
    cnt = cnt.groupby(level=0).agg(n_despachos=("n_despachos", "sum"), dt_primeiro_despacho=("dt_primeiro_despacho", "min"),
                                   dt_ultimo_despacho=("dt_ultimo_despacho", "max"), n_exigencias=("n_exigencias", "sum"))

    # 5) depósito enriquecido ------------------------------------------------------------
    log.info("[marcas] montando mrc_deposito enriquecido")
    dep = (dep.merge(primeiro, on="no_pedido", how="left").merge(n_dpt, left_on="no_pedido", right_index=True, how="left")
              .merge(cls, left_on="no_pedido", right_index=True, how="left"))
    dep["n_depositantes"] = dep["n_depositantes"].fillna(0).astype("Int16")
    dep["n_classes"] = dep["n_classes"].fillna(0).astype("Int16")
    dep["residente"] = (dep["pais_origem"] == "BR").astype("boolean")
    p = out / "mrc_deposito.parquet"
    register("mrc_deposito", write_parquet(dep, p), dep, p, key=["no_pedido"])
    del primeiro, n_dpt, cls

    # 6) situação --------------------------------------------------------------------------
    log.info("[marcas] derivando situação dos pedidos")
    sit = derive_situacao(ev, dep[["no_pedido", "dt_deposito", "dt_entrada_inpi"]], referencia, fim_vigencia=None, counts=cnt)
    p = out / "mrc_situacao.parquet"
    register("mrc_situacao", write_parquet(sit, p), sit, p, key=["no_pedido"])
    del ev, sit, cnt

    # 7) dimensões e gênero ----------------------------------------------------------------
    dim_desp = dim_despacho_from_parts(dim_rows, descricoes={c: d for c, (d, _) in CODIGOS.items()})
    dim_desp["descricao"] = dim_desp["descricao"].fillna("Código não documentado no BADEPI")
    for name, df in [("dim_despacho", dim_desp), ("dim_pais", load_reference("paises")), ("dim_uf", load_reference("ufs"))]:
        p = out / f"{name}.parquet"
        register(name, write_parquet(df, p), df, p, key=[df.columns[0]])
    src = PIGEN.bronze_dir / f"badepi{BADEPI_VERSION}_mrc_depositante_pigen.csv"
    if src.exists():
        g = transform_genero(read_badepi_csv(src))
        p = out / "mrc_depositante_genero.parquet"
        register("mrc_depositante_genero", write_parquet(g, p), g, p, key=["no_pedido", "seq"])

    manifest = {"badepi_version": BADEPI_VERSION, "source": "marcas", "bronze_zip_sha256": zip_sha,
                "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data_referencia": referencia.date().isoformat(), "tables": tables}
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    log.info("[marcas] silver concluída em %s", out)
    return out
