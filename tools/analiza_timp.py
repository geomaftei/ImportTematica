"""Unde se duce timpul într-o rulare: citește un log din logs/ și arată durata fiecărui tip de pas.

    python tools/analiza_timp.py                      # cel mai nou log din logs/
    python tools/analiza_timp.py logs/2026-09-23_19-03-22_IntroducereTematica.log

Durata unei linii = timpul până la linia următoare (cât a lucrat programul după mesajul respectiv). Mesajele se
grupează după text, fără părțile variabile (nume, numere, texte între ghilimele), deci rezultatul nu conține date
din matrice și poate fi trimis mai departe.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

LINIE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \| (\w+)\s*\| [^|]*\| ([^|]+)\| (.*)$")


def sablon(mesaj: str) -> str:
    """Mesajul fără părțile variabile: 'Adauga risc: Proces ...' -> 'Adauga risc: …'."""
    m = re.sub(r"'[^']*'|\"[^\"]*\"", "'…'", mesaj)
    m = re.sub(r"\(\d+, \d+\)", "(x, y)", m)
    m = re.sub(r"\d+([.,:/]\d+)*", "N", m)
    for prefix in ("Adauga risc:", "Adaugare control", "Adaugare test nou", "Pregatim adaugarea testului",
                   "Scriu Detalii Tehnici de Testare:", "Voi bifa tehnica de testare:", "Ales din listă:",
                   "Selectat în arbore:", "Filtre aplicate:", "Scriu CodApr:", "Căutarea a durat", "Termen finalizare test:",
                   "Auditorul", "Nu am bifat:"):
        if m.startswith(prefix):
            return prefix + " …"
    return m[:110]


def main(argv) -> int:
    if len(argv) > 1:
        cale = Path(argv[1])
    else:
        loguri = sorted(Path(__file__).resolve().parent.parent.joinpath("logs").glob("*_IntroducereTematica.log"))
        if not loguri:
            print("Nu am găsit niciun log în logs/")
            return 1
        cale = loguri[-1]
    linii = []
    for rand in cale.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LINIE.match(rand)
        if m:
            linii.append((datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f"), m.group(3).strip(), m.group(4)))
    if len(linii) < 2:
        print("Logul nu are destule linii")
        return 1

    total = (linii[-1][0] - linii[0][0]).total_seconds()
    pe_pas = defaultdict(lambda: [0.0, 0])
    for (t, modul, mesaj), (t2, _, _) in zip(linii, linii[1:]):
        cheie = f"{modul.split('.')[-1]}: {sablon(mesaj)}"
        pe_pas[cheie][0] += (t2 - t).total_seconds()
        pe_pas[cheie][1] += 1

    print(f"Log: {cale.name}   durată totală: {total / 60:.1f} min")
    print(f"{'total s':>8} {'ori':>4} {'medie s':>8}  pas (timpul de după mesaj)")
    for cheie, (sec, n) in sorted(pe_pas.items(), key=lambda kv: -kv[1][0])[:30]:
        print(f"{sec:8.1f} {n:4d} {sec / n:8.1f}  {cheie}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
