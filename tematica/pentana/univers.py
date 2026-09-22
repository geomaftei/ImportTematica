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
from ..exceptions import ApplicationException
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

    def _camp_detalii(self, auto_id: str):
        """Un câmp din tab-ul 'Detalii' (txt_Name, lst_Type). Panoul se poate deschide pe tab-ul 'Pictogramă',
        caz în care 'Detalii' trebuie apăsat întâi; câmpul se caută apoi oriunde în secțiune."""
        tab = self.section.child_window(title="Detalii", control_type="TabItem")
        if self.app.exists(tab, timeout=2):
            try:
                if not tab.wrapper_object().is_selected():
                    self.app.click(tab)
            except Exception:  # noqa: BLE001 - controlul nu expune SelectionItem
                self.app.click(tab)
        camp = self.details.child_window(auto_id=auto_id)
        if self.app.exists(camp, timeout=3):
            return camp
        return self.section.child_window(auto_id=auto_id)

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
        self.app.click(self._buton_sectiune_procese())
        self.app.wait(self.tree)

    def _buton_sectiune_procese(self):
        """Elementul 'Proces/Aria/Sub Aria' din meniul de secțiuni (btn_RiskProcesses), cu rezervă după text."""
        dd = self.app.dropdown()
        btn = self.app.path(dd, "pnl_Content", "ConfigurationMenu", "tbl_Layout", "btn_RiskProcesses")
        if self.app.exists(btn, timeout=3):
            return btn
        log.info("btn_RiskProcesses negăsit după auto_id; caut după textul 'Proces/Aria/Sub Aria'")
        return dd.child_window(title_re=r"^Proces\s*/\s*Aria\s*/\s*Sub\s*Aria.*")

    def adauga_nod(self, nume: str, tip: str, parinte: str | None) -> None:
        log.info("Adaugare %s: %s", tip, nume)
        if parinte is None:
            # procesul se adaugă la același nivel cu selecția: selectăm întâi un nod de pe primul nivel al
            # arborelui (implicit "Archived"), ca noul proces să ajungă pe primul nivel, nu în interiorul lui
            self._selecteaza_nod_prim_nivel()
            self._deschide_meniul_add_item()
            self.app.click_menu_item(MENIU_ACELASI_NIVEL)
        else:
            self.app.select_tree_item(self.tree, parinte)
            self._deschide_meniul_add_item()
            self.app.click_menu_item(MENIU_SUB_OBIECT)
        self.app.pause(2)

    def _deschide_meniul_add_item(self) -> None:
        """Deschide meniul butonului "+ Add item ▼" din săgeata neagră (partea de dropdown a split-button-ului).

        Clicul pe partea cu text adaugă direct un sub-element, deci nu apăsăm acolo. Robotul UiPath trimitea Enter
        pe buton, ceea ce în versiunea lui de aplicație deschidea meniul; aici încercăm ExpandCollapse, apoi
        clicul pe marginea dreaptă a butonului, și verificăm de fiecare dată că meniul chiar s-a deschis.
        """
        btn = self.app.wait(self.btn_new)
        ei = btn.element_info
        copii = [(c.element_info.control_type, c.window_text()) for c in btn.children()]
        log.info("btn_New: tip=%s nume=%r rect=%s copii=%s", ei.control_type, ei.name, btn.rectangle(), copii)

        try:
            btn.expand()  # pattern ExpandCollapse (SplitButton / DropDownButton)
            if self.app.menu_open():
                return
        except Exception as exc:  # noqa: BLE001
            log.debug("expand() pe btn_New nu e disponibil: %s", exc)

        r = btn.rectangle()
        btn.click_input(coords=(r.width() - 6, r.height() // 2))  # săgeata neagră de la marginea dreaptă
        if self.app.menu_open():
            return

        for copil in btn.children():
            if copil.element_info.control_type in ("Button", "SplitButton", "MenuItem"):
                copil.click_input()
                if self.app.menu_open():
                    return
        raise ApplicationException("Nu am reușit să deschid meniul butonului 'Add item' (săgeata de lângă buton). "
                                   "Ferestre deschise:\n" + self.app.dump_windows())

        # "Scrierea Numelui": Ctrl+A pe numele implicit, apoi lipire din clipboard
        self.app.paste_into(self._camp_detalii("txt_Name"), nume, select_all=True)

        # "Selectarea tipului": Alt+Down pe lst_Type deschide lista MultiLevelListTreeControl
        self.app.hotkey(self._camp_detalii("lst_Type"), "%{DOWN}")
        self.app.dropdown_select(tip, tree_auto_id="MultiLevelListTreeControl")

    def _selecteaza_nod_prim_nivel(self) -> None:
        tree = self.app.wait(self.tree)
        top = [it for it in tree.children() if it.element_info.control_type == "TreeItem"]
        if not top:
            top = tree.descendants(control_type="TreeItem")[:1]
        log.info("Noduri pe primul nivel în tv_Universe: %s", [t.window_text() for t in top[:15]])
        dorit = str(self.cfg.get("pentana.process_sibling_node", "Archived") or "")
        ales = next((t for t in top if t.window_text().strip().lower() == dorit.lower()), None) or (top[0] if top else None)
        if ales is None:
            log.warning("Arborele tv_Universe pare gol; adaug procesul la selecția curentă")
            return
        try:
            if ales.is_expanded():
                ales.collapse()  # "să dea pe săgeata de lângă": strângem nodul ca selecția să rămână pe el
        except Exception:  # noqa: BLE001
            pass
        ales.click_input()
        self.app.pause()
        log.info("Selectat nodul '%s' pentru adăugare la același nivel", ales.window_text())

    def trimite_modificari(self) -> None:
        """"Click 'Trimite modificari'" (btn_Submit); robotul avea și varianta cu imagine, păstrată ca rezervă."""
        btn = self.app.path(self.config_screen, "tb_Store", "btn_Submit")
        if self.app.exists(btn, timeout=3):
            self.app.click(btn)
        else:
            self.app.click_image("trimite_modificari", within=self.config_screen)
        log.info("Modificările din Universul de procese au fost trimise")
