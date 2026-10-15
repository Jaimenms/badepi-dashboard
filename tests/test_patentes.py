import pandas as pd

from badepi.silver.patentes import build_situacao, classify_despacho, transform_deposito, transform_ipc


def test_classify_despacho_explicit_description_and_prefix():
    assert classify_despacho("16.1", "Concessão") == "concessao"
    assert classify_despacho("9.2.4", "Manutenção do Indeferimento") == "indeferimento"
    assert classify_despacho("6.9", "Publicação Anulada") == "anulacao_retificacao"
    assert classify_despacho("28.10.32", "Notificação de requerimento de trâmite prioritário de PPH") == "tramite_prioritario"
    assert classify_despacho("6.99", "Exigência qualquer") == "exigencia"
    assert classify_despacho("150", "Algo") == "recurso"
    assert classify_despacho("999", "Algo") == "outros"


def test_transform_deposito_natureza_and_format():
    df = pd.DataFrame({
        "NO_PEDIDO": ["PI0311748", "MU8401405", "102012000050", "112013004238", "202012000001", "132012000001", "erro1"],
        "ANO": ["2003", "2000", "2012", "2013", "2012", "2012", "2015"],
        "DT_ENTRADA_INPI": ["2003-01-01 00:00:00.000"] * 7,
        "DT_DEPOSITO": ["2003-01-01 00:00:00.000"] * 6 + ["2099-01-01 00:00:00.000"],
        "NM_TITULO_PATENTE": ["x"] * 7,
    }).astype("string")
    out = transform_deposito(df)
    assert out["natureza"].tolist()[:6] == ["PI", "MU", "PI", "PI", "MU", "CA"]
    assert out["natureza"].iloc[6] is pd.NA
    assert out["formato_numero"].tolist() == ["antigo", "antigo", "novo", "novo", "novo", "novo", "invalido"]
    assert out["dt_deposito"].iloc[6] is pd.NaT
    assert str(out["ano"].dtype) == "Int16"


def test_transform_ipc_splits_symbol_and_drops_empty():
    df = pd.DataFrame({"NO_PEDIDO": ["a", "a", "b"], "NO_ORDEM_CLASSE": ["1", "2", "1"], "CD_CLASSIF": ["A61K  31/4402", pd.NA, "H04W 4/12"],
                       "VERSION_INDICATOR": ["2006.01", "2006.01", "2009.01"], "CAMPO_TEC": ["16", pd.NA, "4"]}).astype("string")
    out = transform_ipc(df)
    assert len(out) == 2
    assert out.iloc[0][["ipc", "secao", "classe", "subclasse", "grupo_principal"]].tolist() == ["A61K 31/4402", "A", "A61", "A61K", "A61K 31"]
    assert out["campo_tec"].tolist() == [16, 4]


def _ev(rows):
    df = pd.DataFrame(rows, columns=["no_pedido", "dt_publicacao", "evento"])
    df["dt_publicacao"] = pd.to_datetime(df["dt_publicacao"]).astype("datetime64[ms]")
    df["no_pedido"] = df["no_pedido"].astype("string")
    return df


def test_build_situacao_rules():
    ev = _ev([
        ("A", "2010-01-01", "deposito"), ("A", "2012-01-01", "publicacao"), ("A", "2015-01-01", "deferimento"), ("A", "2015-06-01", "concessao"),
        ("B", "2010-01-01", "deposito"), ("B", "2015-06-01", "concessao"), ("B", "2020-01-01", "extincao"),
        ("C", "2010-01-01", "deposito"), ("C", "2014-01-01", "indeferimento"), ("C", "2016-01-01", "recurso_provido"), ("C", "2016-06-01", "deferimento"),
        ("D", "2010-01-01", "deposito"), ("D", "2013-01-01", "arquivamento"),
        ("E", "2010-01-01", "deposito"), ("E", "2013-01-01", "arquivamento"), ("E", "2013-06-01", "restauracao"),
        ("F", "2010-01-01", "deposito"), ("F", "2011-01-01", "desistencia_retirada"),
        ("G", "2024-01-01", "deposito"),
        ("I", "2015-01-01", "deposito"), ("I", "2015-03-01", "exigencia"), ("I", "2015-09-01", "numeracao_anulada"),
        ("J", "2015-01-01", "deposito"), ("J", "2015-09-01", "numeracao_anulada"), ("J", "2016-09-01", "publicacao"), ("J", "2020-01-01", "concessao"),
    ])
    dep = pd.DataFrame({"no_pedido": list("ABCDEFGHIJ"), "natureza": ["PI", "PI", "PI", "MU", "PI", "PI", "PI", "PI", "PI", "PI"],
                        "dt_deposito": pd.to_datetime(["2010-01-01"] * 6 + ["2024-01-01", "2025-01-01", "2015-01-01", "2015-01-01"]).astype("datetime64[ms]"),
                        "dt_entrada_inpi": pd.to_datetime(["2010-01-01"] * 6 + ["2024-01-01", "2025-01-01", "2015-01-01", "2015-01-01"]).astype("datetime64[ms]")})
    dep["no_pedido"] = dep["no_pedido"].astype("string")
    out = build_situacao(ev, dep, pd.Timestamp("2025-12-30")).set_index("no_pedido")
    assert out.loc["A", "situacao"] == "Concedida"
    assert out.loc["B", "situacao"] == "Extinta"
    assert out.loc["C", "situacao"] == "Deferida"
    assert out.loc["D", "situacao"] == "Arquivada"
    assert out.loc["E", "situacao"] == "Em andamento"
    assert out.loc["F", "situacao"] == "Retirada"
    assert out.loc["G", "situacao"] == "Em andamento"
    assert out.loc["H", "situacao"] == "Em andamento" and out.loc["H", "n_despachos"] == 0
    assert out.loc["I", "situacao"] == "Numeração anulada" and out.loc["I", "dt_primeira_decisao"] == pd.Timestamp("2015-09-01")
    assert out.loc["J", "situacao"] == "Concedida"  # numeração anulada revertida: publicado e concedido depois
    assert abs(out.loc["A", "anos_ate_concessao"] - 5.41) < 0.02
    assert out.loc["D", "dt_fim_vigencia"].year == 2025  # MU: 15 anos
    assert bool(out.loc["A", "prazo_expirado"]) is False
