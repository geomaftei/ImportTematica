"""Tipărește arborele de controale al unei ferestre Pentana - echivalentul UI Explorer din UiPath.

Folosește-l ca să verifici/ajustezi auto_id-urile din tematica/pentana/*.py:
    python tools/inspect_pentana.py                       # fereastra principală (MKInsightMainUI)
    python tools/inspect_pentana.py RiskTemplateEditor    # o fereastră după auto_id
    python tools/inspect_pentana.py DropDownComponentWindow --depth 12 --out dropdown.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pywinauto import Application

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tematica.config import Config  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("auto_id", nargs="?", default=None)
    p.add_argument("--depth", type=int, default=8)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    cfg = Config.load()
    app = Application(backend="uia").connect(path=cfg["pentana.exe"], timeout=10)
    win = app.window(auto_id=args.auto_id or cfg.get("pentana.main_window_auto_id", "MKInsightMainUI"))
    win.wait("exists", timeout=10)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            win.print_control_identifiers(depth=args.depth, filename=str(args.out))
        print(f"Scris în {args.out}")
    else:
        win.print_control_identifiers(depth=args.depth)


if __name__ == "__main__":
    main()
