"""Auditorii alocați și termenul de finalizare din matrice: despărțirea listei de auditori, potrivirea tolerantă
a numelor din Excel cu cele din lista Pentana și citirea datei (dd.mm.yyyy sau dată Excel).

Numele din Excel nu sunt mereu scrise exact ca în aplicație: pot lipsi diacriticele, ordinea poate fi
"Nume Prenume" sau "Prenume Nume", prenumele poate fi doar inițiala, pot exista greșeli mici de tastare sau un
al doilea prenume lipsă. Potrivirea compară cuvintele (fără diacritice, litere mici), nu textul întreg.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from typing import List, Optional, Sequence

# prag minim pentru a accepta o potrivire și diferența minimă față de al doilea candidat (altfel e ambiguă)
PRAG_POTRIVIRE = 0.75
DIFERENTA_MINIMA = 0.1


def _fara_diacritice(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c))


def cuvinte(nume: str) -> List[str]:
    """'Popescu-Ionescu, Ana-Maria' -> ['popescu', 'ionescu', 'ana', 'maria']"""
    return [c for c in re.split(r"[^a-z0-9]+", _fara_diacritice(nume).casefold()) if c]


def imparte_auditori(text: str) -> List[str]:
    """Celula 'Auditor alocat' poate conține mai mulți auditori: separați prin virgulă, punct și virgulă, rând nou,
    '/', '|', '+', '&' sau cuvântul 'si' / 'și'."""
    parti = re.split(r"[,;\n\r/|+&]+|\s+(?:si|și|şi)\s+", str(text or ""), flags=re.IGNORECASE)
    return [" ".join(p.split()) for p in parti if p and p.strip()]


def _scor_cuvant(a: str, b: str) -> float:
    if a == b:
        return 1.0
    # inițială sau prescurtare: "a" / "a." ~ "ana", "alex" ~ "alexandru"
    if len(a) <= 2 and b.startswith(a) or len(b) <= 2 and a.startswith(b):
        return 0.9
    if len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)):
        return 0.9
    r = SequenceMatcher(None, a, b).ratio()  # greșeli mici de tastare
    return r if r >= 0.8 else 0.0


def scor_nume(din_excel: str, din_aplicatie: str) -> float:
    """0..1: cât de bine se potrivește numele din Excel cu cel din aplicație, indiferent de ordinea cuvintelor.
    Fiecare cuvânt din Excel se împerechează cu cel mai bun cuvânt încă liber din aplicație; cuvintele din aplicație
    rămase nefolosite (ex. al doilea prenume) scad scorul doar puțin."""
    ce, ca = cuvinte(din_excel), cuvinte(din_aplicatie)
    if not ce or not ca:
        return 0.0
    libere = list(ca)
    total = 0.0
    for c in ce:
        cel_mai_bun, idx = 0.0, -1
        for i, d in enumerate(libere):
            s = _scor_cuvant(c, d)
            if s > cel_mai_bun:
                cel_mai_bun, idx = s, i
        if idx >= 0:
            libere.pop(idx)
        total += cel_mai_bun
    scor = total / len(ce)
    # penalizare mică pentru cuvinte din aplicație care nu au pereche (al doilea prenume, nume de fată)
    return scor * (1 - 0.05 * len(libere))


@dataclass
class Potrivire:
    cautat: str
    gasit: Optional[str]      # numele din aplicație ales, sau None
    scor: float
    motiv: str = ""           # de ce nu s-a ales nimic (negăsit / ambiguu)

    @property
    def partiala(self) -> bool:
        """Potrivire acceptată, dar pe un singur cuvânt sau cu greșeli - de verificat de om."""
        return self.gasit is not None and (len(cuvinte(self.cautat)) < 2 or self.scor < 0.95)


def potriveste_nume(cautat: str, candidati: Sequence[str]) -> Potrivire:
    """Alege numele din aplicație pentru un auditor din Excel; None dacă nu e sigur (sub prag sau ambiguu)."""
    scoruri = sorted(((scor_nume(cautat, c), c) for c in candidati), reverse=True)
    if not scoruri or scoruri[0][0] < PRAG_POTRIVIRE:
        cel_mai_apropiat = f" (cel mai apropiat: '{scoruri[0][1]}', scor {scoruri[0][0]:.2f})" if scoruri else ""
        return Potrivire(cautat, None, scoruri[0][0] if scoruri else 0.0, "negăsit" + cel_mai_apropiat)
    if len(scoruri) > 1 and scoruri[0][0] - scoruri[1][0] < DIFERENTA_MINIMA:
        return Potrivire(cautat, None, scoruri[0][0],
                         f"ambiguu între '{scoruri[0][1]}' și '{scoruri[1][1]}'")
    return Potrivire(cautat, scoruri[0][1], scoruri[0][0])


_FORMATE_DATA = ("%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S",
                 "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M")


def parseaza_data(text) -> Optional[date]:
    """'31.10.2026', '31.10.26', '2026-10-31 00:00:00' (dată Excel citită ca text) sau numărul de serie Excel
    ('46326'). None pentru celulă goală; ValueError pentru un text care nu e dată."""
    if text is None:
        return None
    if isinstance(text, datetime):
        return text.date()
    if isinstance(text, date):
        return text
    t = " ".join(str(text).split()).rstrip(".")
    if not t or t.lower() in ("nan", "nat", "none"):
        return None
    for fmt in _FORMATE_DATA:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    if re.fullmatch(r"\d{5}(\.0+)?", t):  # număr de serie Excel (zile de la 30.12.1899)
        return date(1899, 12, 30) + timedelta(days=int(float(t)))
    raise ValueError(f"'{text}' nu este o dată de forma zz.ll.aaaa")
