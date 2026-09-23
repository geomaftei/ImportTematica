"""Potrivirea numelor de auditori și citirea termenului (fără Pentana)."""
from datetime import date

import pytest

from tematica.nume_date import imparte_auditori, parseaza_data, potriveste_nume

LISTA = ["Popescu Ion", "Popescu Ioana", "Ionescu Ana-Maria", "Mărgineanu Ștefan Alexandru", "Dumitru Andrei",
         "Maftei George", "Cristian-lon Cimpoesu"]


@pytest.mark.parametrize("din_excel, asteptat", [
    ("Popescu Ion", "Popescu Ion"),
    ("Ion Popescu", "Popescu Ion"),               # ordine inversă
    ("ioana popescu", "Popescu Ioana"),           # litere mici
    ("Ana Maria Ionescu", "Ionescu Ana-Maria"),   # cratimă
    ("Stefan Margineanu", "Mărgineanu Ștefan Alexandru"),  # fără diacritice, al doilea prenume lipsă
    ("Margineanu S.", "Mărgineanu Ștefan Alexandru"),      # inițială
    ("Dumitru Andreii", "Dumitru Andrei"),        # greșeală de tastare
    ("George Maftei", "Maftei George"),
    ("Cristian-Ion Cimpoesu", "Cristian-lon Cimpoesu"),   # nume citit prin OCR (I citit ca l)
])
def test_potrivire_gasita(din_excel, asteptat):
    assert potriveste_nume(din_excel, LISTA).gasit == asteptat


@pytest.mark.parametrize("din_excel, motiv", [
    ("Popescu", "ambiguu"),       # două persoane Popescu
    ("I. Popescu", "ambiguu"),    # Ion / Ioana
    ("Vasilescu Dan", "negăsit"),
])
def test_potrivire_nesigura_nu_se_bifeaza(din_excel, motiv):
    p = potriveste_nume(din_excel, LISTA)
    assert p.gasit is None and p.motiv.startswith(motiv)


def test_potrivire_partiala_semnalata():
    assert potriveste_nume("Maftei", LISTA).partiala
    assert not potriveste_nume("Maftei George", LISTA).partiala


def test_imparte_auditori():
    assert imparte_auditori("Popescu Ion; Maftei George, Ana Ionescu si Dumitru Andrei\nX Y") == [
        "Popescu Ion", "Maftei George", "Ana Ionescu", "Dumitru Andrei", "X Y"]
    assert imparte_auditori("") == []


@pytest.mark.parametrize("text, asteptat", [
    ("31.10.2026", date(2026, 10, 31)),
    ("1.2.2026", date(2026, 2, 1)),
    ("31.10.26", date(2026, 10, 31)),
    ("2026-10-31 00:00:00", date(2026, 10, 31)),  # celulă de tip dată în Excel
    ("46326", date(2026, 10, 31)),                 # număr de serie Excel
    ("", None),
])
def test_parseaza_data(text, asteptat):
    assert parseaza_data(text) == asteptat


def test_data_invalida():
    with pytest.raises(ValueError):
        parseaza_data("sfarsitul lunii")
