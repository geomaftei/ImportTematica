"""Logging în consolă și fișier - echivalentul Log Message + câmpurilor logF_* din REFramework."""
from __future__ import annotations

import logging
import sys
import threading
import time
import traceback
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

    root.addHandler(_watchdog)
    _watchdog.start()

    log = logging.getLogger("tematica")
    log.info("Proces: %s", process_name)
    return log


class HangWatchdog(logging.Handler):
    """Dacă nu apare nicio linie de log timp de `limit_s` secunde, scrie în log stiva firului principal
    (unde anume stă programul) - ca să vedem ce apel UIA/pywinauto se blochează."""

    def __init__(self, limit_s: float = 45) -> None:
        super().__init__(logging.DEBUG)
        self.limit_s = limit_s
        self.last = time.monotonic()
        self._thread: threading.Thread | None = None

    def emit(self, record: logging.LogRecord) -> None:
        if record.name != "tematica.watchdog":
            self.last = time.monotonic()

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="watchdog", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        log = logging.getLogger("tematica.watchdog")
        main_id = threading.main_thread().ident
        while True:
            time.sleep(5)
            idle = time.monotonic() - self.last
            if idle < self.limit_s:
                continue
            frame = sys._current_frames().get(main_id)
            stack = "".join(traceback.format_stack(frame)) if frame else "(stiva indisponibilă)"
            log.warning("Nicio activitate de %.0fs - programul stă aici:\n%s", idle, stack)
            self.last = time.monotonic()  # următorul raport peste încă limit_s secunde


_watchdog = HangWatchdog()
