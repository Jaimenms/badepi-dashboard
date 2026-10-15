import pandas as pd

from badepi.silver.common import classify_applicant, normalize_name, parse_date, parse_datetime, to_int


def test_parse_datetime_handles_sentinels_and_format():
    s = pd.Series(["2000-09-01 17:00:00.000", "0001-01-01 00:00:00.000", "2099-01-01 00:00:00.000", "", None])
    out = parse_datetime(s)
    assert out.iloc[0] == pd.Timestamp("2000-09-01 17:00")
    assert out.iloc[1:].isna().all()
    assert str(out.dtype) == "datetime64[ms]"


def test_parse_date_floors_to_day():
    assert parse_date(pd.Series(["2011-08-24 16:48:00.000"])).iloc[0] == pd.Timestamp("2011-08-24")


def test_to_int_nullable():
    out = to_int(pd.Series(["1", "", "x"]), "Int16")
    assert out.iloc[0] == 1 and out.iloc[1:].isna().all() and str(out.dtype) == "Int16"


def test_normalize_name_strips_accents_and_punctuation():
    s = pd.Series(["Société des Produits Nestlé S.A.", "  qualcomm  incorporated ", None])
    out = normalize_name(s)
    assert out.iloc[0] == "SOCIETE DES PRODUITS NESTLE S A"
    assert out.iloc[1] == "QUALCOMM INCORPORATED"
    assert out.iloc[2] is pd.NA


def test_classify_applicant_categories():
    nomes = pd.Series(["UNIVERSIDADE FEDERAL DE MINAS GERAIS", "FUNDACAO OSWALDO CRUZ", "PETROLEO BRASILEIRO S A PETROBRAS",
                       "MARIA DA SILVA", "QUALCOMM INCORPORATED", pd.NA, pd.NA], dtype="string")
    tipos = pd.Series(["J", "J", "J", "F", pd.NA, "J", "F"], dtype="string")
    out = classify_applicant(nomes, tipos).tolist()
    assert out == ["universidade", "instituto_pesquisa", "empresa", "pessoa_fisica", "empresa", "nao_identificado", "pessoa_fisica"]
