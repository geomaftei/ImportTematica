"""Generează o matrice de exemplu (Data/Input/MatriceDeIntrodus.exemplu.xlsx) cu structura așteptată de robot."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tematica import matrice as m  # noqa: E402

ROWS = []


def rand(proces, arie, subarie, risc, tip_risc, control, frecventa, test, tehnici):
    ROWS.append({
        m.COL_PROCES: proces, m.COL_ARIE: arie, m.COL_SUBARIE: subarie,
        m.COL_DESCRIERE_RISC: risc, m.COL_TIP_RISC: tip_risc,
        m.COL_DENUMIRE_CONTROL: control, m.COL_DESCRIERE_CONTROL: f"Descriere {control}",
        m.COL_TIP_CONTROL: "Preventiv", m.COL_FRECVENTA_CONTROL: frecventa,
        m.COL_CADRU_CONTROL: "Regulament intern",
        m.COL_DENUMIRE_TEST: test, m.COL_TEHNICI_TEST: tehnici, m.COL_DETALII_TEHNICI: f"Detalii {test}",
    })


rand("Creditare", "Analiza creditului", "", "Evaluare incompleta a bonitatii", "Risc de credit",
     "Verificare dosar", "Lunar", "Test dosar 1", "Interviul; Examinarea")
rand("Creditare", "Analiza creditului", "", "Evaluare incompleta a bonitatii", "Risc de credit",
     "Verificare dosar", "Lunar", "Test dosar 2", "Observarea")
rand("Creditare", "Analiza creditului", "Persoane fizice", "Documente lipsa", "Risc operational",
     "Checklist documente", "Zilnic sau ori de cate ori este nevoie", "Test checklist", "Validarea; Recalcularea")
rand("Creditare", "Aprobare", "", "Depasire competente", "Risc de conformitate",
     "Matrice competente", "Trimestrial", "Test competente", "Examinarea")

if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "Data" / "Input" / "MatriceDeIntrodus.exemplu.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(ROWS).to_excel(out, sheet_name="Sheet1", index=False)
    print(f"Scris {out}")
