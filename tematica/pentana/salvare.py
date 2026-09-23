"""SalvareCopieSiguranta.xaml - salvează și închide șablonul, apoi face o copie de siguranță.

Copia de siguranță: în lista de șabloane, clic pe starea "In progres" a șablonului nostru -> fereastra de acțiuni
(DropDownComponentWindow / UserActionsLayoutContainer / c_ActionSelect) -> acțiunea -> "Confirm".
Grila de șabloane își desenează singură rândurile (nu apar în UIA), deci:
  - filtrăm lista după numele șablonului (câmpul "Filtre:"), ca să rămână doar rândul nostru;
  - găsim starea după imaginea Data/Images/stare_in_progres.png (decupată din aplicație, la scalarea 125%).
"""
from __future__ import annotations

import logging
import time

from ..config import Config
from ..exceptions import ApplicationException
from .app import PentanaApp
from .fastspec import arbore_controale

log = logging.getLogger("tematica.pentana.salvare")


class SalvareCopieSiguranta:
    def __init__(self, app: PentanaApp, cfg: Config):
        self.app = app
        self.cfg = cfg

    def ruleaza(self) -> None:
        app = self.app
        designer = app.path(app.main, "pnl_Main", "AuditDesignSection", "_sectionArea", "WPTemplateDesigner2")
        # bara cu Salvare / Închidere e copil direct al c_Editor (mai adânc există alte tb_Main, ex. în RCMatrixEditor);
        # idx-ul din selectorul UiPath numără în toată fereastra, nu sub părinte, deci nu îl folosim
        editor = app.path(designer, "mp_Pages", "mpp_Editor", "c_Editor")
        toolbar = editor.child_window(auto_id="tb_Main", depth=1)
        if app.exists(toolbar.child_window(auto_id="btn_Save"), timeout=3):
            app.click(toolbar.child_window(auto_id="btn_Save"))    # "Salvare"
            log.info("Șablonul a fost salvat")
            app.click(toolbar.child_window(auto_id="btn_Close"))   # "Inchidere"
            log.info("Editorul șablonului a fost închis")
        else:
            # ex. `python main.py --only salvare --attach` cu lista de șabloane deja afișată
            log.info("Editorul șablonului nu este deschis; trec direct la copia de siguranță")

        self.copie_de_siguranta(app.path(designer, "mp_Pages", "mpp_List", "lst_Templates"))

    def copie_de_siguranta(self, templates) -> None:
        app = self.app
        nume = self.cfg["pentana.template_name"]
        app.wait(templates, timeout=30)

        # doar rândul nostru în listă: câmpul "Filtre:" de deasupra grilei
        # (câmpul poate fi dezactivat - atunci nu filtrăm și alegem primul "In progres" din listă)
        filtru = templates.child_window(title="Filtre:", control_type="Edit")
        if self._activ(filtru):
            app.seteaza_text(filtru, nume)
            time.sleep(2)  # lista se reîmprospătează după filtrare
            log.info("Lista de șabloane filtrată după '%s'", nume)
        else:
            log.info("Câmpul 'Filtre:' al listei de șabloane nu este activ; aleg primul 'In progres' din listă")

        # "Copie de siguranta": clic pe starea "In progres" -> fereastra de acțiuni
        app.click_image("stare_in_progres", within=templates, timeout=10)
        try:
            dd = app.window("DropDownComponentWindow", timeout=10)
        except ApplicationException as exc:
            raise ApplicationException("După clicul pe 'In progres' nu a apărut fereastra de acțiuni") from exc
        try:
            log.debug("Fereastra de acțiuni:\n%s", arbore_controale(dd.wrapper_object(), depth=8))
        except Exception:  # noqa: BLE001 - doar diagnostic
            pass

        # "Acțiuni Șablon": Deschidere șablon / Returnare la recenzant / Copie de siguranță securizată -
        # alegem ultima după nume (UIA); dacă elementul nu e expus, după imaginea textului (decupată la 125%)
        actiune = dd.child_window(title_re=r"^Copie de siguran.. securizat.*")
        if app.exists(actiune, timeout=2):
            app.click(actiune)
        else:
            app.click_image("copie_siguranta_securizata", within=dd, timeout=5)
        log.info("Am ales acțiunea 'Copie de siguranță securizată'")
        self._confirma()
        log.info("Copia de siguranță a șablonului '%s' a fost confirmată", nume)

    def _activ(self, spec) -> bool:
        try:
            return self.app.exists(spec, timeout=2) and spec.wrapper_object().is_enabled()
        except Exception:  # noqa: BLE001
            return False

    def _confirma(self) -> None:
        """Dacă Pentana cere confirmare după acțiune, apăsăm butonul de confirmare (Confirm / Da / OK)."""
        app = self.app
        buton = app.main.child_window(title_re=r"^(Confirm.*|Da|Yes|OK)$", control_type="Button")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if app.exists(buton, timeout=0.5):
                log.info("Confirm acțiunea: %s", buton.window_text())
                app.click(buton)
                return
        log.info("Nu a fost cerută nicio confirmare")
