"""Gold — Desenho Industrial: agregações em JSON para docs/data/desenho_industrial/."""

from __future__ import annotations

import logging

import pandas as pd

from ..config import BADEPI_VERSION, DOCS_DATA_DIR, GOLD_DIR, SOURCES
from ..ioutil import read_json, read_parquet
from . import common as C
from .common import ANO_FIM, ANO_INI, ANOS, pct, serie

log = logging.getLogger(__name__)
SRC = SOURCES["desenho_industrial"]
LOCARNO = {1: "Alimentos", 2: "Vestuário e acessórios", 3: "Artigos de viagem e pessoais", 4: "Escovas", 5: "Têxteis e materiais em folha", 6: "Mobiliário",
           7: "Utensílios domésticos", 8: "Ferramentas e ferragens", 9: "Embalagens e recipientes", 10: "Relógios e instrumentos de medida", 11: "Adornos",
           12: "Veículos e meios de transporte", 13: "Equipamentos elétricos", 14: "Gravação, comunicação e informática", 15: "Máquinas", 16: "Fotografia e ótica",
           17: "Instrumentos musicais", 18: "Impressão e escritório", 19: "Papelaria e material de ensino", 20: "Equipamentos de venda e publicidade",
           21: "Jogos, brinquedos e esportes", 22: "Armas e caça", 23: "Instalações hidráulicas, aquecimento e ventilação", 24: "Medicina e laboratório",
           25: "Construção", 26: "Iluminação", 27: "Tabaco", 28: "Farmacêuticos, cosméticos e toalete", 29: "Combate a incêndio e segurança", 30: "Cuidados de animais",
           31: "Máquinas de preparar alimentos e bebidas", 32: "Símbolos gráficos, logotipos e ornamentação"}
RELACOES = [
    {"de": "di_depositante", "para": "di_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
    {"de": "di_autor", "para": "di_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
    {"de": "di_classe", "para": "di_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
    {"de": "di_despacho", "para": "di_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
    {"de": "di_situacao", "para": "di_deposito", "chave": "no_pedido", "cardinalidade": "1:1"},
    {"de": "di_depositante_genero", "para": "di_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
    {"de": "di_despacho", "para": "dim_despacho", "chave": "cd_despacho", "cardinalidade": "N:1"},
    {"de": "di_depositante", "para": "dim_pais", "chave": "pais", "cardinalidade": "N:1"},
    {"de": "di_depositante", "para": "dim_uf", "chave": "uf", "cardinalidade": "N:1"},
]


def _ciclo_di(cv: dict) -> dict:
    """Desenhos não têm publicação antes do registro: o primeiro estado é 'depositado / em exame formal'."""
    old, new = "Depositado (não publicado)", "Depositado / em exame formal"
    cv["estados"] = [new if e == old else e for e in cv["estados"]]
    for blk in [cv["todos"], *cv["por_ano"].values()]:
        blk["estados"] = {(new if k == old else k): v for k, v in blk["estados"].items()}
    return cv


def build(force: bool = False):
    silver = SRC.silver_dir
    manifest = read_json(silver / "_manifest.json")
    out_dirs = [GOLD_DIR / "desenho_industrial", DOCS_DATA_DIR / "desenho_industrial"]
    log.info("[desenho_industrial] carregando silver")
    dep = read_parquet(silver / "di_deposito.parquet"); sit = read_parquet(silver / "di_situacao.parquet")
    df = dep.merge(sit, on="no_pedido", how="left"); df = df[(df["ano"] >= ANO_INI) & (df["ano"] <= ANO_FIM)]
    referencia = pd.Timestamp(manifest["data_referencia"])
    dim_pais = read_parquet(silver / "dim_pais.parquet"); dim_uf = read_parquet(silver / "dim_uf.parquet"); dim_desp = read_parquet(silver / "dim_despacho.parquet")
    dpt = read_parquet(silver / "di_depositante.parquet", columns=["no_pedido", "no_ordem", "nome", "pais", "uf", "cidade"])
    dpt1 = dpt.sort_values(["no_pedido", "no_ordem"]).drop_duplicates("no_pedido")
    desp = read_parquet(silver / "di_despacho.parquet", columns=["no_pedido", "cd_despacho", "evento", "dt_publicacao", "no_rpi", "ano_publicacao"])
    eventos_ano = C.eventos_por_ano(desp[["no_pedido", "evento", "ano_publicacao"]])
    dpt_gen = read_parquet(silver / "di_depositante_genero.parquet") if (silver / "di_depositante_genero.parquet").exists() else None

    log.info("[desenho_industrial] agregando")
    s = C.serie_base(df)
    s["via"] = {k: serie(df[df["via"] == k].groupby("ano").size()) for k in ["Direta", "Via Haia", "Dividido (provável)"]}
    s["media_autores"] = [round(float(v), 2) for v in df.groupby("ano")["n_autores"].mean().reindex(ANOS).fillna(0)]
    tempo = C.tempo_concessao(df, {"via": "via", "classe": "classe_locarno_principal"}, min_n_ano=30)
    bl = C.backlog(df)
    tab = pd.crosstab(df["ano"], df["classe_locarno_principal"]).reindex(index=ANOS, fill_value=0)
    classes = []
    for c in range(1, 33):
        sub = df[df["classe_locarno_principal"] == c]
        classes.append({"classe": c, "nome": LOCARNO.get(c, str(c)), "total": int(len(sub)), "registrados": int(sub["dt_concessao"].notna().sum()),
                        "residentes": int((sub["residente"] == True).sum()), "serie": [int(v) for v in tab[c]] if c in tab.columns else [0] * len(ANOS)})  # noqa: E712
    # prorrogações e vigência: registros com ao menos uma prorrogação
    prorr = df["dt_ultima_prorrogacao"].notna()
    fun = C.funil(df)
    del fun["publicados"]  # desenhos não são publicados antes do registro (exame formal apenas)
    fun["etapas"] = ["Depositados", "Decididos", "Registrados", "Vigentes hoje"]
    k = C.kpis_base(df, bl, tempo)
    k.update({"share_haia_ultimo_ano": pct((df[df["ano"] == ANO_FIM]["via"] == "Via Haia").sum(), (df["ano"] == ANO_FIM).sum()),
              "share_pf_residentes": pct((df[df["residente"] == True]["tipo_pessoa_origem"] == "F").sum(), (df["residente"] == True).sum()),  # noqa: E712
              "registros_prorrogados": int(prorr.sum()), "n_depositantes_distintos": int(df["depositante_principal"].nunique()),
              "n_autores_linhas": int(df["n_autores"].sum())})
    blocks = {
        "resumo": {"ativo": "desenho_industrial", "badepi_version": BADEPI_VERSION, "data_referencia": manifest.get("data_referencia"), "gerado_em": C.now_iso(), "periodo": [ANO_INI, ANO_FIM], "ano_ultimo": ANO_FIM, "kpis": k},
        "serie_depositos": s, "serie_decisoes": C.serie_decisoes(df, eventos_ano), "situacao_coorte": C.situacao_coorte(df), "tempo_registro": tempo,
        "classes": {"anos": ANOS, "classes": classes, "sem_classe": int(df["classe_locarno_principal"].isna().sum())},
        "uf": C.uf(df, dim_uf, top=("classe_locarno_principal", LOCARNO)), "paises": C.paises(df, dim_pais), "depositantes": C.depositantes(df, dpt1, dim_pais),
        "municipios": C.municipios(df, dpt1), "genero": C.genero_depositantes(df, dpt_gen), "funil": fun, "backlog": {"anos": ANOS, "backlog_fim_ano": bl},
        "ciclo_vida": _ciclo_di(C.ciclo_vida(df, referencia, max_anos=25)), "transicoes": C.transicoes(desp, df, dim_desp, top_n=40, min_n=3), "modelo": C.modelo(manifest, RELACOES),
    }
    return C.write_blocks(blocks, out_dirs, log, "desenho_industrial")
