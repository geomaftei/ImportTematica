"""Teste pentru partea de date (nu au nevoie de Pentana)."""
from pathlib import Path

import pandas as pd
import pytest

from tematica import matrice as m
from tematica.exceptions import BusinessRuleException


def _rand(proces, arie, subarie, risc, tip_risc="Risc operational", control="C1", test="T1"):
    return {
        m.COL_PROCES: proces, m.COL_ARIE: arie, m.COL_SUBARIE: subarie,
        m.COL_DESCRIERE_RISC: risc, m.COL_TIP_RISC: tip_risc,
        m.COL_DENUMIRE_CONTROL: control, m.COL_DESCRIERE_CONTROL: f"Descriere {control}",
        m.COL_TIP_CONTROL: "Preventiv", m.COL_FRECVENTA_CONTROL: "Lunar", m.COL_CADRU_CONTROL: "Regulament",
        m.COL_DENUMIRE_TEST: test, m.COL_TEHNICI_TEST: "Interviul; Observarea",
        m.COL_DETALII_TEHNICI: "Detalii",
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
