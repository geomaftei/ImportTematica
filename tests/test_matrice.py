"""Teste pentru partea de date (nu au nevoie de Pentana)."""
from pathlib import Path

import pandas as pd
import pytest

from tematica import matrice as m
from tematica.exceptions import BusinessRuleException


def _rand(proces, arie, subarie, risc, tip_risc="Risc operational", control="C1", test="T1"):
    return {
        m.COL_COD_APR: f"APR-{test}",
        m.COL_PROCES: proces, m.COL_ARIE: arie, m.COL_SUBARIE: subarie,
        m.COL_DESCRIERE_RISC: risc, m.COL_TIP_RISC: tip_risc,
        m.COL_DENUMIRE_CONTROL: control, m.COL_DESCRIERE_CONTROL: f"Descriere {control}",
        m.COL_TIP_CONTROL: "Preventiv", m.COL_FRECVENTA_CONTROL: "Lunar", m.COL_CADRU_CONTROL: "Regulament",
        m.COL_DENUMIRE_TEST: test, m.COL_TEHNICI_TEST: "Interviul; Observarea",
        m.COL_DETALII_TEHNICI: "Detalii",
        m.COL_AUDITOR: "Popescu Ion", m.COL_TERMEN: "31.10.2026",
    }


@pytest.fixture
def xlsx(tmp_path: Path) -> Path:
    rows = [
        _rand("P1", "A1", "", "R1", control="C1", test="T1"),
        _rand("P1", "A1", "", "R1", control="C1", test="T2"),
        _rand("P1", "A1", "S1", "R2", control="C2", test="T3"),
        _rand("P1", "A2", "", "R3", control="C3", test="T4"),
        _rand("P2", "A3", "", "R4", control="C4", test="T5"),
        {k: "" for k in _rand("", "", "", "")},  # rând gol la final
    ]
    p = tmp_path / "MatriceDeIntrodus.xlsx"
    pd.DataFrame(rows).to_excel(p, sheet_name="Sheet1", index=False)
    return p


def test_citire_si_deduplicare(xlsx):
    mat = m.citeste_matrice(xlsx)
    assert mat.procese == ["P1", "P2"]
    assert mat.arii_pentru("P1") == ["A1", "A2"]
    assert mat.subarii_pentru("P1", "A1") == ["S1"]
    assert mat.subarii_pentru("P1", "A2") == []
    assert len(mat.riscuri) == 4
    assert len(mat.controale) == 4
    assert len(mat.teste) == 5


def test_legaturi_risc_control_test(xlsx):
    mat = m.citeste_matrice(xlsx)
    riscuri_a1 = mat.riscuri_pentru("P1", "A1")
    assert riscuri_a1[m.COL_DESCRIERE_RISC].tolist() == ["R1"]
    riscuri_s1 = mat.riscuri_pentru("P1", "A1", "S1")
    assert riscuri_s1[m.COL_DESCRIERE_RISC].tolist() == ["R2"]

    control = mat.controale_pentru(riscuri_a1.iloc[0])
    assert control[m.COL_DENUMIRE_CONTROL].tolist() == ["C1"]
    teste = mat.teste_pentru(control.iloc[0])
    assert teste[m.COL_DENUMIRE_TEST].tolist() == ["T1", "T2"]


def test_coloane_lipsa(tmp_path):
    p = tmp_path / "gresit.xlsx"
    pd.DataFrame({"Proces": ["P1"], "Arie": ["A1"]}).to_excel(p, index=False)
    with pytest.raises(BusinessRuleException):
        m.citeste_matrice(p)


def test_numerotare(xlsx):
    mat = m.citeste_matrice(xlsx)
    df = m.numeroteaza(mat.baza)
    assert df[m.COL_PROCES].drop_duplicates().tolist() == ["1. P1", "2. P2"]
    assert df[m.COL_ARIE].drop_duplicates().tolist() == ["1. 1. A1", "1. 2. A2", "2. 1. A3"]


def test_normalizeaza_spatii():
    assert m.normalizeaza_spatii("a   b    c") == "a b c"


def test_cap_de_tabel_nou_si_vechi(tmp_path: Path):
    """Coloanele 'Descriere Control (Criterii)' / 'Cadru de reglementare Control (Criterii)'; numele vechi merg în continuare."""
    assert m.COL_DESCRIERE_CONTROL == "Descriere Control (Criterii)"
    assert m.COL_CADRU_CONTROL == "Cadru de reglementare Control (Criterii)"
    vechi = {"Descriere Control (Criterii)": "Descriere Control",
             "Cadru de reglementare Control (Criterii)": "Cadru de reglementare Control"}
    p = tmp_path / "vechi.xlsx"
    pd.DataFrame([_rand("P1", "A1", "", "R1")]).rename(columns=vechi).to_excel(p, sheet_name="Sheet1", index=False)
    mat = m.citeste_matrice(p)
    control = mat.controale.iloc[0]
    assert control[m.COL_DESCRIERE_CONTROL] == "Descriere C1"
    assert control[m.COL_CADRU_CONTROL] == "Regulament"


def test_cod_apr_la_teste(xlsx):
    """'Cod referinta APR (Nr. Crt.)' (prima coloană) ajunge la fiecare test."""
    mat = m.citeste_matrice(xlsx)
    control = mat.controale_pentru(mat.riscuri_pentru("P1", "A1").iloc[0]).iloc[0]
    assert mat.teste_pentru(control)[m.COL_COD_APR].tolist() == ["APR-T1", "APR-T2"]


def test_fara_cod_apr(tmp_path: Path):
    """O matrice fără coloana nouă se citește în continuare; codul e gol."""
    p = tmp_path / "fara_cod.xlsx"
    pd.DataFrame([_rand("P1", "A1", "", "R1")]).drop(columns=[m.COL_COD_APR]).to_excel(p, sheet_name="Sheet1",
                                                                                       index=False)
    mat = m.citeste_matrice(p)
    assert mat.teste[m.COL_COD_APR].tolist() == [""]


def test_auditor_si_termen_la_teste(xlsx):
    mat = m.citeste_matrice(xlsx)
    assert mat.teste[m.COL_AUDITOR].tolist()[0] == "Popescu Ion"
    assert mat.teste[m.COL_TERMEN].tolist()[0] == "31.10.2026"


def test_fara_auditor_si_termen(tmp_path: Path):
    p = tmp_path / "vechi.xlsx"
    pd.DataFrame([_rand("P1", "A1", "", "R1")]).drop(columns=[m.COL_AUDITOR, m.COL_TERMEN]).to_excel(
        p, sheet_name="Sheet1", index=False)
    mat = m.citeste_matrice(p)
    assert mat.teste[m.COL_AUDITOR].tolist() == [""] and mat.teste[m.COL_TERMEN].tolist() == [""]
