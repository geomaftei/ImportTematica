"""Citirea și structurarea matricei de tematică (MatriceDeIntrodus.xlsx).

Echivalentul secvențelor "Citire Matrice" din Process.xaml / IntroducereProceseInUnivers.xaml /
IntroducereRiscuri.xaml: Read Range -> Filter Data Table (păstrează coloane) -> Remove Duplicate Rows,
plus condițiile IF cu care robotul lega riscurile, controalele și testele de proces/arie/sub-arie.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Union

import pandas as pd

from .exceptions import BusinessRuleException

log = logging.getLogger("tematica.matrice")

# Coloanele matricei, exact cum apar în Sheet1 (numele sunt cele folosite în selectorii UiPath).
COL_COD_APR = "Cod referinta APR (Nr. Crt.)"  # prima coloană; se scrie la test, câmpul "CodApr:"
COL_PROCES = "Proces"
COL_ARIE = "Arie"
COL_SUBARIE = "SubArie"
COL_DESCRIERE_RISC = "Descriere Risc"
COL_TIP_RISC = "Tip Risc"
COL_DENUMIRE_CONTROL = "Denumire Control"
COL_DESCRIERE_CONTROL = "Descriere Control (Criterii)"
COL_TIP_CONTROL = "Tip Control"
COL_FRECVENTA_CONTROL = "Frecventa Control"
COL_CADRU_CONTROL = "Cadru de reglementare Control (Criterii)"
COL_DENUMIRE_TEST = "Denumire Test"
COL_TEHNICI_TEST = "Tehnici de Testare"
COL_DETALII_TEHNICI = "Detalii Tehnici de Testare"

# Numele vechi ale coloanelor (matricele făcute înainte de redenumire se citesc în continuare)
COLOANE_VECHI = {
    "Descriere Control": COL_DESCRIERE_CONTROL,
    "Cadru de reglementare Control": COL_CADRU_CONTROL,
    "Cadru de reglementare (Criterii)": COL_CADRU_CONTROL,
}

COLOANE_OBLIGATORII = [
    COL_PROCES, COL_ARIE, COL_SUBARIE,
    COL_DESCRIERE_RISC, COL_TIP_RISC,
    COL_DENUMIRE_CONTROL, COL_DESCRIERE_CONTROL, COL_TIP_CONTROL, COL_FRECVENTA_CONTROL, COL_CADRU_CONTROL,
    COL_DENUMIRE_TEST, COL_TEHNICI_TEST, COL_DETALII_TEHNICI,
]

COLOANE_RISC = [COL_DESCRIERE_RISC, COL_TIP_RISC, COL_PROCES, COL_ARIE, COL_SUBARIE]
COLOANE_CONTROL = COLOANE_RISC[:2] + [
    COL_DENUMIRE_CONTROL, COL_DESCRIERE_CONTROL, COL_TIP_CONTROL, COL_FRECVENTA_CONTROL, COL_CADRU_CONTROL,
] + COLOANE_RISC[2:]
COLOANE_TEST = COLOANE_CONTROL[:7] + [COL_DENUMIRE_TEST, COL_TEHNICI_TEST, COL_DETALII_TEHNICI, COL_COD_APR] + COLOANE_RISC[2:]


def normalizeaza_spatii(text: str) -> str:
    """Regex.Replace(text, " {2,}", " ") - robotul înlocuia spațiile multiple înainte de a lipi textul."""
    return re.sub(r" {2,}", " ", str(text))


def _mask(df: pd.DataFrame, **egal: str) -> pd.Series:
    """Construiește condiția AND `coloana == valoare` pentru fiecare pereche primită."""
    mask = pd.Series(True, index=df.index)
    for col, val in egal.items():
        mask &= df[col] == val
    return mask


@dataclass
class Matrice:
    """Matricea citită din Excel, deja despărțită în tabelele pe care le folosea robotul."""

    baza: pd.DataFrame
    procese: List[str]
    arii: pd.DataFrame        # Proces, Arie
    subarii: pd.DataFrame     # Proces, Arie, SubArie (inclusiv rânduri cu SubArie gol)
    riscuri: pd.DataFrame
    controale: pd.DataFrame
    teste: pd.DataFrame

    # --- interogări folosite de fluxurile din Pentana --------------------
    def arii_pentru(self, proces: str) -> List[str]:
        return self.arii.loc[self.arii[COL_PROCES] == proces, COL_ARIE].tolist()

    def subarii_pentru(self, proces: str, arie: str) -> List[str]:
        """Doar sub-ariile ne-goale (rândurile cu SubArie == "" înseamnă "aria nu are sub-arii")."""
        m = _mask(self.subarii, **{COL_PROCES: proces, COL_ARIE: arie}) & (self.subarii[COL_SUBARIE] != "")
        return self.subarii.loc[m, COL_SUBARIE].tolist()

    def riscuri_pentru(self, proces: str, arie: str, subarie: str = "") -> pd.DataFrame:
        """subarie == "" -> riscurile atașate direct ariei (ca în ramura "For Each Risc Arie")."""
        return self.riscuri[_mask(self.riscuri, **{COL_PROCES: proces, COL_ARIE: arie, COL_SUBARIE: subarie})]

    def controale_pentru(self, risc: pd.Series) -> pd.DataFrame:
        chei = {c: risc[c] for c in (COL_PROCES, COL_ARIE, COL_SUBARIE, COL_DESCRIERE_RISC, COL_TIP_RISC)}
        return self.controale[_mask(self.controale, **chei)]

    def teste_pentru(self, control: pd.Series) -> pd.DataFrame:
        chei = {c: control[c] for c in COLOANE_CONTROL}
        return self.teste[_mask(self.teste, **chei)]


def citeste_matrice(cale: Union[str, Path], sheet: str = "Sheet1") -> Matrice:
    """Read Range + filtre + eliminare duplicate, ca în workflow-urile UiPath."""
    cale = Path(cale)
    if not cale.exists():
        raise BusinessRuleException(f"Nu există fișierul cu matricea: {cale}")

    baza = pd.read_excel(cale, sheet_name=sheet, dtype=str)
    baza = baza.fillna("")
    baza.columns = [str(c).strip() for c in baza.columns]
    baza = baza.rename(columns={v: n for v, n in COLOANE_VECHI.items() if v in baza.columns and n not in baza.columns})
    for col in baza.columns:
        baza[col] = baza[col].astype(str).str.strip()

    if COL_COD_APR not in baza.columns:
        # matricele de dinainte de coloana "Cod referinta APR" se pot citi în continuare, fără cod la teste
        log.warning("Matricea nu are coloana '%s'; câmpul CodApr al testelor rămâne gol", COL_COD_APR)
        baza[COL_COD_APR] = ""
    lipsa = [c for c in COLOANE_OBLIGATORII if c not in baza.columns]
    if lipsa:
        raise BusinessRuleException(
            "Matricea nu respectă template-ul; lipsesc coloanele: " + ", ".join(lipsa)
        )
    # rândurile complet goale (după ultimul proces) nu se procesează
    baza = baza[baza[COL_PROCES] != ""].reset_index(drop=True)
    if baza.empty:
        raise BusinessRuleException("Matricea nu conține niciun proces.")

    def selecteaza(coloane: List[str]) -> pd.DataFrame:
        return baza[coloane].drop_duplicates().reset_index(drop=True)

    return Matrice(
        baza=baza,
        procese=selecteaza([COL_PROCES])[COL_PROCES].tolist(),
        arii=selecteaza([COL_PROCES, COL_ARIE]),
        subarii=selecteaza([COL_PROCES, COL_ARIE, COL_SUBARIE]),
        riscuri=selecteaza(COLOANE_RISC),
        controale=selecteaza(COLOANE_CONTROL),
        teste=selecteaza(COLOANE_TEST),
    )


def numeroteaza(baza: pd.DataFrame) -> pd.DataFrame:
    """Port al NumerotareTree.xaml: prefixează procesele cu "1. ", "2. " și ariile cu "1. 1. ", "1. 2. " etc.

    Workflow-ul există în proiectul UiPath dar nu este apelat din Process.xaml; îl păstrăm ca utilitar.
    """
    df = baza.copy()
    for idx_p, proces in enumerate(df[COL_PROCES].drop_duplicates()):
        nume_proces = f"{idx_p + 1}. {proces}"
        randuri_proces = df[COL_PROCES] == proces
        df.loc[randuri_proces, COL_PROCES] = nume_proces
        for idx_a, arie in enumerate(df.loc[randuri_proces, COL_ARIE].drop_duplicates()):
            m = randuri_proces & (df[COL_ARIE] == arie)
            df.loc[m, COL_ARIE] = f"{idx_p + 1}. {idx_a + 1}. {arie}"
    return df
