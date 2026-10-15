import pandas as pd

from badepi.silver import desenho_industrial as di
from badepi.silver import marcas as mrc
from badepi.silver.common import derive_situacao


def test_marcas_classify_despacho():
    assert mrc.classify_despacho("IPAS158") == ("Concessão de registro", "concessao")
    assert mrc.classify_despacho("DESP351")[1] == "deferimento"
    assert mrc.classify_despacho("351")[1] == "deferimento"          # código sem prefixo (RPI antiga)
    assert mrc.classify_despacho("009")[1] == "publicacao"           # alias de IPAS009 (2024)
    assert mrc.classify_despacho("IPAS423")[1] == "oposicao"
    assert mrc.classify_despacho("IPAS999")[1] == "outros"


def test_marcas_transform_deposito():
    df = pd.DataFrame({"NO_PEDIDO": ["933418981", "933418990"], "TP_ENTRADA": ["M", "T"], "ANO": ["2024", "2024"],
                       "DT_DEPOSITO": ["2024-02-05 12:45:14.000"] * 2, "DT_ENTRADA_INPI": ["2024-02-05 12:45:14.000"] * 2,
                       "NM_TITULO_MARCA": ["LABORANA", "SJM"], "CD_NATUREZ_MARCA": ["8", "2"], "DS_NATUREZ_MARCA": ["Marca de Produto/Serviço", "Madri Produto/Serviço"],
                       "CD_APRESEN_MARCA": ["M", "D"]}).astype("string")
    out = mrc.transform_deposito(df)
    assert out["via"].tolist() == ["Direta", "Madri"]
    assert out["natureza"].tolist() == ["Produto/Serviço", "Serviço"]
    assert out["madri"].tolist() == [False, True]
    assert out["apresentacao"].tolist() == ["Mista", "Nominativa"]


def test_di_classify_and_classe():
    assert di.classify_despacho("39", "Concessão do Registro") == "concessao"
    assert di.classify_despacho("158", None) == "concessao"
    assert di.classify_despacho("870", None) == "prorrogacao"
    assert di.classify_despacho("44", "Extinção - Art. 119 inciso III da LPI") == "extincao"
    assert di.classify_despacho("9999", "Publicação Anulada") == "anulacao_retificacao"
    cl = di.transform_classe(pd.DataFrame({"NO_PEDIDO": ["a", "b"], "NO_ORDEM_PEDIDO": ["1", "1"], "CD_CLASSIF": ["08-06.B 0460", "02-01"], "VERSION_INDICATOR": ["2006.01", "10.2014"]}).astype("string"))
    assert cl["classe_locarno"].tolist() == [8, 2]
    assert cl["subclasse_locarno"].tolist() == ["08-06", "02-01"]


def test_derive_situacao_sem_prazo_de_vigencia():
    ev = pd.DataFrame({"no_pedido": ["x", "x", "y"], "dt_publicacao": pd.to_datetime(["2019-01-01", "2019-06-01", "2020-01-01"]).astype("datetime64[ms]"),
                       "evento": pd.Categorical(["deferimento", "concessao", "publicacao"])})
    ev["no_pedido"] = ev["no_pedido"].astype("string")
    dep = pd.DataFrame({"no_pedido": pd.Series(["x", "y"], dtype="string"), "dt_deposito": pd.to_datetime(["2018-01-01", "2019-06-01"]).astype("datetime64[ms]"),
                        "dt_entrada_inpi": pd.to_datetime(["2018-01-01", "2019-06-01"]).astype("datetime64[ms]")})
    out = derive_situacao(ev, dep, pd.Timestamp("2025-12-30")).set_index("no_pedido")
    assert out.loc["x", "situacao"] == "Concedida" and bool(out.loc["x", "prazo_expirado"]) is False and pd.isna(out.loc["x", "dt_fim_vigencia"])
    assert out.loc["y", "situacao"] == "Em andamento" and out.loc["y", "dt_publicado"] == pd.Timestamp("2020-01-01")
