"""Orchestrarea procesului - port simplificat al REFramework (Main.xaml):

    Initialization -> Process -> (Set Transaction Status) -> End Process

Tranzacția este fișierul `MatriceDeIntrodus.xlsx` din folderul de proiect (sau cel dat cu --file).
Erorile de business (BusinessRuleException) opresc procesarea fără retry; erorile de sistem fac captură de ecran,
închid aplicațiile și (opțional, `framework.max_retries`) reîncearcă.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from .config import Config
from .exceptions import BusinessRuleException
from .logging_setup import context as log_context
from .matrice import Matrice, citeste_matrice

log = logging.getLogger("tematica.framework")

PASI = ("univers", "riscuri", "salvare")


class Framework:
    def __init__(self, cfg: Config, pasi: Sequence[str] = PASI, dry_run: bool = False, attach: bool = False):
        self.cfg = cfg
        self.pasi = tuple(pasi)
        self.dry_run = dry_run
        self.attach = attach
        self.app = None  # PentanaApp

    # ------------------------------------------------------------ Process
    def proceseaza(self, fisier: Path) -> None:
        matrice = citeste_matrice(fisier, self.cfg.get("paths.sheet", "Sheet1"))
        log.info("Matrice: %d procese, %d arii, %d riscuri, %d controale, %d teste",
                 len(matrice.procese), len(matrice.arii), len(matrice.riscuri), len(matrice.controale),
                 len(matrice.teste))
        if self.dry_run:
            self._afiseaza(matrice)
            return

        from .pentana import IntroducereProceseInUnivers, IntroducereRiscuri, PentanaApp, SalvareCopieSiguranta

        self.app = PentanaApp(self.cfg)
        self.app.attach() if self.attach else self.app.start()

        if "univers" in self.pasi:
            IntroducereProceseInUnivers(self.app, self.cfg, matrice).ruleaza()
        if "riscuri" in self.pasi:
            IntroducereRiscuri(self.app, self.cfg, matrice).ruleaza()
        if "salvare" in self.pasi:
            SalvareCopieSiguranta(self.app, self.cfg).ruleaza()

    @staticmethod
    def _afiseaza(m: Matrice) -> None:
        """--dry-run: arată ce s-ar introduce în Pentana, fără să deschidă aplicația."""
        for proces in m.procese:
            print(f"PROCES  {proces}")
            for arie in m.arii_pentru(proces):
                print(f"  ARIE  {arie}")
                Framework._afiseaza_riscuri(m, proces, arie, "", "    ")
                for subarie in m.subarii_pentru(proces, arie):
                    print(f"    SUB-ARIE  {subarie}")
                    Framework._afiseaza_riscuri(m, proces, arie, subarie, "      ")

    @staticmethod
    def _afiseaza_riscuri(m: Matrice, proces: str, arie: str, subarie: str, indent: str) -> None:
        for _, risc in m.riscuri_pentru(proces, arie, subarie).iterrows():
            print(f"{indent}RISC [{risc['Tip Risc']}] {risc['Descriere Risc']}")
            for _, control in m.controale_pentru(risc).iterrows():
                print(f"{indent}  CONTROL [{control['Frecventa Control']}] {control['Denumire Control']}")
                for _, test in m.teste_pentru(control).iterrows():
                    print(f"{indent}    TEST {test['Denumire Test']}  ({test['Tehnici de Testare']})")

    # ------------------------------------------------------------ Main loop
    def run(self, fisier: Optional[Path] = None) -> int:
        """Returnează 0 la succes, 1 la eroare."""
        fisier = fisier or self.cfg.input_file
        log.info("Initializare")
        if not self.dry_run and not self.attach:
            from .pentana import PentanaApp

            PentanaApp.kill()  # KillAllProcesses (first run)

        log_context.transaction_number = 1
        log.info("Fisier de procesat: %s", fisier)
        max_retries = int(self.cfg.get("framework.max_retries", 0))
        incercare = 0
        rezultat = 1
        while True:
            start = datetime.now()
            try:
                self.proceseaza(fisier)
                log.info("Transaction Successful (%.3f min)", (datetime.now() - start).total_seconds() / 60)
                rezultat = 0
                break
            except BusinessRuleException as exc:
                log.error("Business rule exception: %s", exc)
                break
            except Exception as exc:  # noqa: BLE001 - System Exception
                log.exception("System exception: %s", exc)
                self._captura_ecran()
                self._inchide_aplicatiile()
                if incercare < max_retries:
                    incercare += 1
                    log.warning("Retry %d/%d", incercare, max_retries)
                    continue
                break
        log_context.transaction_number = 0
        log.info("Process finished")
        self._inchide_aplicatiile()
        return rezultat

    def _captura_ecran(self) -> None:
        try:
            from PIL import ImageGrab

            folder = self.cfg.path("paths.screenshots_dir")
            folder.mkdir(parents=True, exist_ok=True)
            cale = folder / f"ExceptionScreenshot_{datetime.now():%Y%m%d_%H%M%S}.png"
            ImageGrab.grab().save(cale)
            log.info("Captura de ecran salvata: %s", cale)
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to take screenshot: %s", exc)

    def _inchide_aplicatiile(self) -> None:
        if self.dry_run or self.attach:
            return
        try:
            if self.app is not None:
                self.app.close()
        except Exception as exc:  # noqa: BLE001
            log.warning("CloseAllApplications failed: %s", exc)
            from .pentana import PentanaApp

            PentanaApp.kill()
        self.app = None
