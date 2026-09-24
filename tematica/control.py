"""Pauză / oprire pentru rularea robotului (butoanele și tastele F9 / F10 din aplicația cu fereastră).

- Oprirea se verifică după fiecare acțiune (`verifica()`, apelat din PentanaApp.pause()), deci e aproape imediată.
- Pauza se face doar în punctele sigure (`punct_sigur()`), între pași - înainte de un nod, un risc, un control, un
  test - ca să nu rămână o listă derulantă sau un editor deschis pe jumătate. La reluare, fereastra Pentana e adusă
  din nou în față (`la_reluare`), pentru că între timp utilizatorul a lucrat în altă fereastră.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

log = logging.getLogger("tematica.control")


class OprireCeruta(Exception):
    """Utilizatorul a oprit rularea."""


class Control:
    def __init__(self) -> None:
        self._pauza_ceruta = threading.Event()
        self._continua = threading.Event()
        self._oprire = threading.Event()
        self.in_pauza = False
        self.pas_curent = ""
        self.la_reluare: Optional[Callable[[], None]] = None      # ex. readuce Pentana în față
        self.la_schimbare: Optional[Callable[[], None]] = None    # notifică interfața (pauză intrată / reluată)

    def reseteaza(self) -> None:
        self._pauza_ceruta.clear()
        self._continua.clear()
        self._oprire.clear()
        self.in_pauza = False
        self.pas_curent = ""

    # --- comenzi (din interfață) ------------------------------------------
    def cere_pauza(self) -> None:
        if not self._oprire.is_set():
            self._continua.clear()
            self._pauza_ceruta.set()
            log.warning("Pauză cerută - robotul se oprește la următorul punct sigur (între pași)")

    def continua(self) -> None:
        self._pauza_ceruta.clear()
        self._continua.set()

    def opreste(self) -> None:
        self._oprire.set()
        self._continua.set()  # deblochează o pauză în curs
        log.warning("Oprire cerută de utilizator")

    @property
    def pauza_ceruta(self) -> bool:
        return self._pauza_ceruta.is_set()

    @property
    def oprire_ceruta(self) -> bool:
        return self._oprire.is_set()

    # --- apelate de robot -------------------------------------------------
    def verifica(self) -> None:
        """După fiecare acțiune: dacă s-a cerut oprirea, ieșim imediat."""
        if self._oprire.is_set():
            raise OprireCeruta("Rulare oprită de utilizator")

    def punct_sigur(self, pas: str = "") -> None:
        """Între pași: aici se intră în pauză, dacă s-a cerut; la reluare Pentana e adusă din nou în față."""
        if pas:
            self.pas_curent = pas
        self.verifica()
        if not self._pauza_ceruta.is_set():
            return
        self.in_pauza = True
        log.warning("ÎN PAUZĂ înainte de: %s. Apasă Continuă (F9) sau Oprește (F10).", self.pas_curent or "pasul următor")
        self._notifica()
        self._continua.wait()
        self.in_pauza = False
        self.verifica()
        log.warning("Rularea continuă cu: %s", self.pas_curent or "pasul următor")
        if self.la_reluare is not None:
            try:
                self.la_reluare()
            except Exception as exc:  # noqa: BLE001
                log.warning("Nu am putut readuce Pentana în față: %s", exc)
        self._notifica()

    def _notifica(self) -> None:
        if self.la_schimbare is not None:
            try:
                self.la_schimbare()
            except Exception:  # noqa: BLE001
                pass


control = Control()
