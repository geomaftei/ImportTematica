"""IntroducereProceseInUnivers.xaml - adaugă Procese / Arii / Sub-arii în Universul de procese.

Ecranul: Instrumente (Alt+I) -> Configurare -> secțiunea "Procese" (ConfigurationScreen / RiskProcessSection).
Pentru fiecare nod: btn_New -> meniul "Adăugare sub-obiect la selecție" / "Adăugare obiect la același nivel ca
selecția", numele în txt_Name, tipul (Proces / Arie / Sub-arie) în lst_Type. La final: "Trimite modificari".

Robotul UiPath naviga în arbore numai cu tastele Up/Down și ținea contoare (Contor_Reasignare_Proces,
ElementeDeScazutDinProcesClick) ca să revină la nivelul corect. Aici selectăm părintele după nume în tv_Universe
înainte de fiecare adăugare, ceea ce dă același rezultat fără contoare.
"""
from __future__ import annotations

import logging
import time

from pywinauto import keyboard

from ..config import Config
from ..matrice import Matrice
from .app import PentanaApp, describe

log = logging.getLogger("tematica.pentana.univers")

MENIU_SUB_OBIECT = "Adăugare sub-obiect la selecție"
MENIU_ACELASI_NIVEL = "Adăugare obiect la același nivel ca selecția"

TIP_PROCES = "Proces"
TIP_ARIE = "Arie"
TIP_SUBARIE = "Sub-arie"


class IntroducereProceseInUnivers:
    def __init__(self, app: PentanaApp, cfg: Config, matrice: Matrice):
        self.app = app
        self.cfg = cfg
        self.matrice = matrice
        self.prefix = str(cfg.get("pentana.process_name_prefix", "") or "")
        self._config_screen = None

    # --- selectori -----------------------------------------------------
    @property
    def config_screen(self):
        if self._config_screen is None:
            self._config_screen = self.app.screen("ConfigurationScreen", timeout=30)
        return self._config_screen

    @property
    def section(self):
        return self.app.path(self.config_screen, "pnl_Sections", "RiskProcessSection", ("tbl_Layout", 0))

    @property
    def tree(self):
        return self.app.path(self.section, "pnl_Left", "tv_Universe")

    @property
    def btn_new(self):
        return self.app.path(self.section, "pnl_Left", "tb_Left", "btn_New")

    @property
    def details(self):
        return self.app.path(self.section, "pnl_Background", "pnl_Page", "c_Page", "pnl_Layout", "mp_Pages",
                             "mpp_Details", "tbl_Layout")

    # --- flux ----------------------------------------------------------
    def ruleaza(self) -> None:
        log.info("WorkFlow-ul Introducere Procese in Universul de Procese a pornit")
        self.deschide_ecranul_procese()
        for proces in self.matrice.procese:
            nume_proces = self.prefix + proces
            self.adauga_nod(nume_proces, TIP_PROCES, parinte=None)
            for arie in self.matrice.arii_pentru(proces):
                self.adauga_nod(arie, TIP_ARIE, parinte=nume_proces)
                for subarie in self.matrice.subarii_pentru(proces, arie):
                    self.adauga_nod(subarie, TIP_SUBARIE, parinte=arie)
        self.trimite_modificari()

    def deschide_ecranul_procese(self) -> None:
        """Alt+I, C, C, Enter -> Configurare; apoi butonul de secțiune -> 'Procese'."""
        main = self.app.wait(self.app.main)
        main.set_focus()
        self.app.pause(2)
        # meniul "Instrumente" (Alt+I) -> "Configurare" (c, c) -> Enter; cu pauze, ca meniul să apuce să se deschidă
        for key in ("%i", "c", "c", "{ENTER}"):
            keyboard.send_keys(key)
            self.app.pause(2)
        time.sleep(3)  # "Delay 3 sec" din workflow
        self._config_screen = None
        log.info("Ecranul de configurare găsit: %s", describe(self.config_screen))
        self.app.click(self.app.path(self.config_screen, "tb_Store", "btn_Section"))
        self.app.click(self.app.path(self.app.dropdown(), "pnl_Content", "ConfigurationMenu", "tbl_Layout",
                                     "btn_RiskProcesses"))
        self.app.wait(self.tree)

    def adauga_nod(self, nume: str, tip: str, parinte: str | None) -> None:
        log.info("Adaugare %s: %s", tip, nume)
        if parinte is None:
            # procesul se adaugă la același nivel cu selecția curentă (ca în robot)
            self.app.click(self.btn_new)
            self.app.click_menu_item(MENIU_ACELASI_NIVEL, keyboard_fallback=("{TAB}", "{TAB}", "{ENTER}"))
        else:
            self.app.select_tree_item(self.tree, parinte)
            self.app.click(self.btn_new)
            self.app.click_menu_item(MENIU_SUB_OBIECT, keyboard_fallback=("{TAB}", "{ENTER}"))

        # "Scrierea Numelui": Ctrl+A pe numele implicit, apoi lipire din clipboard
        self.app.paste_into(self.details.child_window(auto_id="txt_Name"), nume, select_all=True)

        # "Selectarea tipului": Alt+Down pe lst_Type deschide lista MultiLevelListTreeControl
        self.app.hotkey(self.details.child_window(auto_id="lst_Type"), "%{DOWN}")
        self.app.dropdown_select(tip, tree_auto_id="MultiLevelListTreeControl")

    def trimite_modificari(self) -> None:
        """"Click 'Trimite modificari'" (btn_Submit); robotul avea și varianta cu imagine, păstrată ca rezervă."""
        btn = self.app.path(self.config_screen, "tb_Store", "btn_Submit")
        if self.app.exists(btn, timeout=3):
            self.app.click(btn)
        else:
            self.app.click_image("trimite_modificari", within=self.config_screen)
        log.info("Modificările din Universul de procese au fost trimise")
