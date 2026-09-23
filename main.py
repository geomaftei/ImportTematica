"""Punct de intrare - echivalentul Main.xaml.

Exemple:
    python main.py                                   # procesează MatriceDeIntrodus.xlsx din folderul de proiect
    python main.py --file alta_matrice.xlsx
    python main.py --dry-run                         # doar verifică Excel-ul, fără Pentana
    python main.py --only riscuri --attach           # un singur pas, pe Pentana deja deschis
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tematica.config import Config
from tematica.framework import PASI, Framework
from tematica.logging_setup import setup_logging


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Introducere Tematica in Pentana")
    parser.add_argument("--config", default=None, help="calea către config.yaml (implicit: cel din proiect)")
    parser.add_argument("--file", type=Path, default=None,
                        help="matricea Excel (implicit: MatriceDeIntrodus.xlsx din folderul de proiect)")
    parser.add_argument("--dry-run", action="store_true", help="doar citește matricea și afișează ce s-ar introduce")
    parser.add_argument("--attach", action="store_true", help="folosește instanța Pentana deja deschisă")
    parser.add_argument("--only", nargs="+", choices=PASI, default=None,
                        help="rulează doar pașii indicați: univers riscuri salvare "
                             "(implicit toți, fără 'univers' dacă framework.sari_peste_univers e true)")
    args = parser.parse_args(argv)

    cfg = Config.load(args.config)
    setup_logging(cfg.path("paths.log_dir"), cfg.get("framework.business_process_name", "Introducere Tematica"))
    pasi = args.only
    if pasi is None:
        pasi = [p for p in PASI if not (p == "univers" and cfg.get("framework.sari_peste_univers", False))]
    fw = Framework(cfg, pasi=pasi, dry_run=args.dry_run, attach=args.attach)
    return fw.run(args.file)


if __name__ == "__main__":
    sys.exit(main())
