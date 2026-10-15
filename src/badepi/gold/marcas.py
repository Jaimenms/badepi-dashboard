"""Gold — Marcas: agregações em JSON para docs/data/marcas/."""

from __future__ import annotations

import logging

import pandas as pd

from ..config import BADEPI_VERSION, DOCS_DATA_DIR, GOLD_DIR, SOURCES
from ..ioutil import read_json, read_parquet
from . import common as C
from .common import ANO_FIM, ANO_INI, ANOS, pct, serie, year

log = logging.getLogger(__name__)
SRC = SOURCES["marcas"]
NICE = {1: "Produtos químicos", 2: "Tintas e vernizes", 3: "Cosméticos e limpeza", 4: "Óleos e combustíveis", 5: "Farmacêuticos", 6: "Metais comuns", 7: "Máquinas",
        8: "Ferramentas manuais", 9: "Aparelhos científicos e eletrônicos", 10: "Aparelhos médicos", 11: "Iluminação e aquecimento", 12: "Veículos", 13: "Armas e fogos",
        14: "Joalheria", 15: "Instrumentos musicais", 16: "Papel e impressos", 17: "Borracha e plásticos", 18: "Couro e bagagens", 19: "Materiais de construção",
        20: "Móveis", 21: "Utensílios domésticos", 22: "Cordas e lonas", 23: "Fios têxteis", 24: "Tecidos", 25: "Vestuário e calçados", 26: "Rendas e bordados",
        27: "Tapetes", 28: "Jogos e brinquedos", 29: "Carnes e laticínios", 30: "Café, cereais e doces", 31: "Produtos agrícolas", 32: "Cervejas e bebidas não alcoólicas",
        33: "Bebidas alcoólicas", 34: "Tabaco", 35: "Publicidade e gestão de negócios", 36: "Seguros e finanças", 37: "Construção e reparos", 38: "Telecomunicações",
        39: "Transporte e logística", 40: "Tratamento de materiais", 41: "Educação e entretenimento", 42: "Serviços científicos e de TI", 43: "Alimentação e hospedagem",
        44: "Serviços médicos e de beleza", 45: "Serviços jurídicos e pessoais"}
RELACOES = [
    {"de": "mrc_depositante", "para": "mrc_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
    {"de": "mrc_classe", "para": "mrc_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
    {"de": "mrc_despacho", "para": "mrc_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
    {"de": "mrc_situacao", "para": "mrc_deposito", "chave": "no_pedido", "cardinalidade": "1:1"},
    {"de": "mrc_depositante_genero", "para": "mrc_deposito", "chave": "no_pedido", "cardinalidade": "N:1"},
    {"de": "mrc_despacho", "para": "dim_despacho", "chave": "cd_despacho", "cardinalidade": "N:1"},
    {"de": "mrc_depositante", "para": "dim_pais", "chave": "pais", "cardinalidade": "N:1"},
    {"de": "mrc_depositante", "para": "dim_uf", "chave": "uf", "cardinalidade": "N:1"},
]


def build(force: bool = False):
    silver = SRC.silver_dir
    manifest = read_json(silver / "_manifest.json")
    out_dirs = [GOLD_DIR / "marcas", DOCS_DATA_DIR / "marcas"]
    log.info("[marcas] carregando silver")
    dep = read_parquet(silver / "mrc_deposito.parquet", columns=["no_pedido", "ano", "dt_entrada_inpi", "dt_deposito", "via", "natureza", "apresentacao", "madri",
                                                                   "pais_origem", "uf_origem", "tipo_pessoa_origem", "categoria_origem", "depositante_principal",
                                                                   "n_depositantes", "classe_nice_principal", "n_classes", "residente"])
    sit = read_parquet(silver / "mrc_situacao.parquet")
    df = dep.merge(sit, on="no_pedido", how="left"); df = df[(df["ano"] >= ANO_INI) & (df["ano"] <= ANO_FIM)]; del dep, sit
    referencia = pd.Timestamp(manifest["data_referencia"])
    dim_pais = read_parquet(silver / "dim_pais.parquet"); dim_uf = read_parquet(silver / "dim_uf.parquet"); dim_desp = read_parquet(silver / "dim_despacho.parquet")
    dpt = read_parquet(silver / "mrc_depositante.parquet", columns=["no_pedido", "no_ordem", "nome", "pais", "uf", "cidade"])
    dpt1 = dpt.sort_values(["no_pedido", "no_ordem"]).drop_duplicates("no_pedido"); del dpt
    desp = read_parquet(silver / "mrc_despacho", columns=["no_pedido", "cd_despacho", "evento", "dt_publicacao", "no_rpi", "ano_publicacao"])
    eventos_ano = C.eventos_por_ano(desp[["no_pedido", "evento", "ano_publicacao"]])
    dpt_gen = read_parquet(silver / "mrc_depositante_genero.parquet") if (silver / "mrc_depositante_genero.parquet").exists() else None

    log.info("[marcas] agregando")
    s = C.serie_base(df)
    s["via"] = {k: serie(df[df["via"] == k].groupby("ano").size()) for k in ["Direta", "Madri"]}
    s["natureza"] = {k: serie(df[df["natureza"] == k].groupby("ano").size()) for k in ["Produto", "Serviço", "Produto/Serviço", "Coletiva", "Certificação"]}
    s["apresentacao"] = {k: serie(df[df["apresentacao"] == k].groupby("ano").size()) for k in ["Nominativa", "Mista", "Figurativa", "Tridimensional"]}
    s["media_classes"] = [round(float(v), 2) for v in df.groupby("ano")["n_classes"].mean().reindex(ANOS).fillna(0)]
    tempo = C.tempo_concessao(df, {"via": "via", "natureza": "natureza", "apresentacao": "apresentacao"})
    bl = C.backlog(df)
    # classes de Nice
    tab = pd.crosstab(df["ano"], df["classe_nice_principal"]).reindex(index=ANOS, fill_value=0)
    classes = []
    for c in range(1, 46):
        sub = df[df["classe_nice_principal"] == c]
        classes.append({"classe": c, "nome": NICE.get(c, str(c)), "tipo": "Serviço" if c >= 35 else "Produto", "total": int(len(sub)),
                        "registrados": int(sub["dt_concessao"].notna().sum()), "residentes": int((sub["residente"] == True).sum()),  # noqa: E712
                        "serie": [int(v) for v in tab[c]] if c in tab.columns else [0] * len(ANOS)})
    classes_json = {"anos": ANOS, "classes": classes, "sem_classe": int(df["classe_nice_principal"].isna().sum()),
                    "produtos_vs_servicos": {"Produto": serie(df[df["classe_nice_principal"] <= 34].groupby("ano").size()), "Serviço": serie(df[df["classe_nice_principal"] >= 35].groupby("ano").size())}}
    oposicao = df["dt_oposicao"].notna()
    fun = C.funil(df, {"com_oposicao": oposicao})
    fun["etapas"] = ["Depositados", "Publicados", "Decididos no mérito", "Registrados", "Vigentes hoje"]
    k = C.kpis_base(df, bl, tempo)
    k.update({"share_madri_ultimo_ano": pct((df[df["ano"] == ANO_FIM]["via"] == "Madri").sum(), (df["ano"] == ANO_FIM).sum()),
              "share_pf_residentes": pct((df[df["residente"] == True]["tipo_pessoa_origem"] == "F").sum(), (df["residente"] == True).sum()),  # noqa: E712
              "share_oposicao": pct(oposicao.sum(), len(df)), "n_depositantes_distintos": int(df["depositante_principal"].nunique())})
    ufj = C.uf(df, dim_uf, top=("classe_nice_principal", NICE))
    blocks = {
        "resumo": {"ativo": "marcas", "badepi_version": BADEPI_VERSION, "data_referencia": manifest.get("data_referencia"), "gerado_em": C.now_iso(), "periodo": [ANO_INI, ANO_FIM], "ano_ultimo": ANO_FIM, "kpis": k},
        "serie_depositos": s, "serie_decisoes": C.serie_decisoes(df, eventos_ano), "situacao_coorte": C.situacao_coorte(df), "tempo_registro": tempo,
        "classes": classes_json, "uf": ufj, "paises": C.paises(df, dim_pais), "depositantes": C.depositantes(df, dpt1, dim_pais), "municipios": C.municipios(df, dpt1),
        "genero": C.genero_depositantes(df, dpt_gen), "funil": fun, "backlog": {"anos": ANOS, "backlog_fim_ano": bl},
        "ciclo_vida": C.ciclo_vida(df, referencia, max_anos=15), "transicoes": C.transicoes(desp, df, dim_desp, top_n=40, min_n=20), "modelo": C.modelo(manifest, RELACOES),
    }
    return C.write_blocks(blocks, out_dirs, log, "marcas")
