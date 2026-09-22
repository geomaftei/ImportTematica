"""Logging în consolă și fișier - echivalentul Log Message + câmpurilor logF_* din REFramework."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path


class TransactionContext(logging.Filter):
    """Adaugă în fiecare linie de log numărul tranzacției curente (ca AddLogFields)."""

    def __init__(self) -> None:
        super().__init__()
        self.transaction_number = 0
        self.transaction_id = ""

    def filter(self, record: logging.LogRecord) -> bool:
        record.transaction = f"T{self.transaction_number}" if self.transaction_number else "-"
        return True


context = TransactionContext()


def setup_logging(log_dir: Path, process_name: str) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{datetime.now():%Y-%m-%d}_IntroducereTematica.log"
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(transaction)s | %(name)s | %(message)s")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    console.addFilter(context)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    file_handler.addFilter(context)

    root.addHandler(console)
    root.addHandler(file_handler)
    # pywinauto este foarte vorbăreț pe DEBUG
    logging.getLogger("pywinauto").setLevel(logging.WARNING)

    log = logging.getLogger("tematica")
    log.info("Proces: %s", process_name)
    return log
