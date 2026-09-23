"""IntroducereProceseInUnivers.xaml - adaugă Procese / Arii / Sub-arii în Universul de procese.

Ecranul: Instrumente (Alt+I) -> Configurare -> secțiunea "Proces/Aria/Sub Aria" (ConfigurationScreen /
RiskProcessSection). Pentru fiecare nod: săgeata butonului "+ Add item" -> meniul "Adăugare sub-obiect la selecție"
/ "Adăugare obiect la același nivel ca selecția", tab-ul "Detalii", numele în txt_Name, tipul (Proces / Arie /
Sub-arie) în lst_Type. La final: "Trimitere modificări".

Structura reală a ecranului (din arborele de controale al aplicației):
    ConfigurationScreen
      tb_Store: btn_Section, btn_Submit
      pnl_Sections
        RiskProcessSection / tbl_Layout
          pnl_Left: tv_Universe (arborele, sute de noduri), tb_Left / btn_New ("+ Add item ▼")
          pnl_Background / pnl_Page / c_Page / ... / mpp_Details / tbl_Layout: txt_Name, lst_Type
        AuditUniverseSection (altă secțiune, ascunsă, cu aceleași auto_id-uri -> căutăm doar în RiskProcessSection)
Căutările se fac în panouri mici și cu adâncime limitată, pentru că o scanare a arborelui durează secunde.

Poziționarea în arbore e ca la robotul UiPath: nodul nou rămâne selectat, sub-obiect / același nivel din meniu,
iar la revenirea pe nivelul de sus săgeata sus de câte rânduri s-au adăugat (fără căutări după nume în arbore).
"""
from __future__ import annotations

import logging
import time

import pyautogui
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
        self.noduri_adaugate = 0
        self._config_screen = None
        self._tree = None      # wrapper memorat pentru tv_Universe
        self._btn_new = None   # wrapper memorat pentru btn_New

    # --- selectori -----------------------------------------------------
    @property
    def config_screen(self):
        if self._config_screen is None:
            self._config_screen = self.app.window("ConfigurationScreen", timeout=30)
        return self._config_screen

    @property
    def section(self):
        return self.config_screen.child_window(auto_id="RiskProcessSection", depth=2)

    @property
    def pnl_left(self):
        return self.section.child_window(auto_id="pnl_Left", depth=2)

    @property
    def pnl_background(self):
        return self.section.child_window(auto_id="pnl_Background", depth=2)

    @property
    def tree(self):
        """Wrapper-ul arborelui tv_Universe (memorat: rezolvarea lui rescanează sute de noduri)."""
        if self._tree is None:
            self._tree = self.app.wait(self.pnl_left.child_window(auto_id="tv_Universe", control_type="Tree",
                                                                  depth=1), timeout=30)
        return self._tree

    @property
    def btn_new(self):
        if self._btn_new is None:
            self._btn_new = self.app.wait(self.pnl_left.child_window(auto_id="btn_New", depth=2))
        return self._btn_new

    def buton_store(self, auto_id: str):
        return self.config_screen.child_window(auto_id="tb_Store", depth=1).child_window(auto_id=auto_id, depth=1)

    # --- flux ----------------------------------------------------------
    def ruleaza(self) -> None:
        """Ca robotul UiPath: nodul nou adăugat rămâne selectat în arbore, iar poziția pentru următorul nod se
        obține din meniul 'Add item' (sub-obiect / același nivel) și, la revenirea pe un nivel superior, cu
        săgeata sus în tv_Universe, numărând rândurile adăugate. Nu se caută noduri după nume în arbore."""
        log.info("WorkFlow-ul Introducere Procese in Universul de Procese a pornit")
        self.deschide_ecranul_procese()
        for i, proces in enumerate(self.matrice.procese):
            if i == 0:
                # primul proces: lângă un nod de pe primul nivel (implicit "Archived"); următoarele: lângă procesul
                # anterior, pe care revenim cu săgeata sus la finalul fiecărui proces
                self._selecteaza_nod_prim_nivel()
            self.adauga_nod(self.prefix + proces, TIP_PROCES, MENIU_ACELASI_NIVEL)
            randuri_sub_proces = 0   # arii + sub-arii adăugate sub procesul curent
            subarii_ultima_arie = 0  # câte rânduri de sub-arie sunt sub aria selectată acum
            for j, arie in enumerate(self.matrice.arii_pentru(proces)):
                # prima arie: sub proces; următoarele: la același nivel cu aria anterioară (selectată)
                self.adauga_nod(arie, TIP_ARIE, MENIU_SUB_OBIECT if j == 0 else MENIU_ACELASI_NIVEL)
                randuri_sub_proces += 1
                subarii = self.matrice.subarii_pentru(proces, arie)
                for k, subarie in enumerate(subarii):
                    self.adauga_nod(subarie, TIP_SUBARIE, MENIU_SUB_OBIECT if k == 0 else MENIU_ACELASI_NIVEL)
                randuri_sub_proces += len(subarii)
                subarii_ultima_arie = len(subarii)
                if subarii:
                    # "Click in sus pentru a iesi din Sub Arie": de pe ultima sub-arie înapoi pe arie
                    self._sus_in_arbore(len(subarii), "înapoi pe aria '%s'" % arie)
            # de pe ultima arie înapoi pe proces: toate rândurile de sub proces, fără sub-ariile ultimei arii
            self._sus_in_arbore(randuri_sub_proces - subarii_ultima_arie, "înapoi pe procesul '%s'" % proces)
        self.trimite_modificari()

    def deschide_ecranul_procese(self) -> None:
        """Alt+I, C, C, Enter -> Configurare; apoi butonul de secțiune -> 'Proces/Aria/Sub Aria'."""
        main = self.app.wait(self.app.main)
        # așteptăm ca bara de meniu să fie gata: elementul "Instrumente" să existe și să fie activ
        meniu = self.app.wait(self.app._menu_instrumente(), timeout=60)
        time.sleep(float(self.cfg.get("pentana.ready_delay_s", 1)))
        main.set_focus()
        self.app.pause()
        # meniul "Instrumente" (Alt+I; "Tools" -> Alt+T) -> "Configurare" (c, c) -> Enter
        text_meniu = meniu.window_text()
        keyboard.send_keys("%t" if text_meniu.lower().startswith("tools") else "%i")
        log.info("Meniul '%s' deschis", text_meniu)
        time.sleep(0.8)
        for key in ("c", "c", "{ENTER}"):
            keyboard.send_keys(key)
            time.sleep(0.4)
        self._config_screen = self._tree = self._btn_new = None
        log.info("Ecranul de configurare găsit: %s", describe(self.config_screen))
        self.app.click(self.buton_store("btn_Section"))  # "Selectați secțiunea de configurare..."
        self.app.click(self._buton_sectiune_procese())
        self.tree  # așteaptă încărcarea arborelui
        log.info("Secțiunea 'Proces/Aria/Sub Aria' este deschisă")

    def _buton_sectiune_procese(self):
        """Elementul 'Proces/Aria/Sub Aria' din meniul de secțiuni (btn_RiskProcesses), cu rezervă după text."""
        dd = self.app.dropdown()
        btn = dd.child_window(auto_id="btn_RiskProcesses")
        if self.app.exists(btn, timeout=3):
            return btn
        log.info("btn_RiskProcesses negăsit după auto_id; caut după textul 'Proces/Aria/Sub Aria'")
        return dd.child_window(title_re=r"^Proces\s*/\s*Aria\s*/\s*Sub\s*Aria.*")

    def adauga_nod(self, nume: str, tip: str, meniu: str) -> None:
        """Adaugă un nod relativ la selecția curentă din arbore (meniu = sub-obiect / același nivel)."""
        log.info("Adaugare %s: %s (%s)", tip, nume, meniu)
        self._deschide_meniul_add_item()
        # rezerva din tastatură e cea a robotului: TAB -> primul element (sub-obiect), TAB TAB -> al doilea
        taste = ("{TAB}",) if meniu == MENIU_SUB_OBIECT else ("{TAB}", "{TAB}")
        self.app.click_menu_item(meniu, keyboard_fallback=taste + ("{ENTER}",))
        self.app.pause(2)

        # "Scrierea Numelui": Ctrl+A pe numele implicit, apoi lipire din clipboard
        log.info("Scriu numele în txt_Name")
        self.app.paste_into(self._camp_detalii("txt_Name"), nume, select_all=True)

        # "Selectarea tipului": Alt+Down pe lst_Type deschide lista MultiLevelListTreeControl
        log.info("Deschid lista de tipuri (lst_Type)")
        self.app.hotkey(self._camp_detalii("lst_Type"), "%{DOWN}")
        log.info("Aleg tipul '%s'", tip)
        self.app.dropdown_select(tip, tree_auto_id="MultiLevelListTreeControl")
        log.info("%s '%s' adăugat(ă)", tip, nume)
        self.noduri_adaugate += 1

    def _selecteaza_nod_prim_nivel(self) -> None:
        top = [it for it in self.tree.children() if it.element_info.control_type == "TreeItem"]
        log.info("Noduri pe primul nivel în tv_Universe: %s", [t.window_text() for t in top[:8]])
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

    def _sus_in_arbore(self, pasi: int, motiv: str) -> None:
        """Săgeata sus de `pasi` ori în tv_Universe (robotul: "Click in sus pentru a iesi din Sub Arie")."""
        if pasi <= 0:
            return
        log.info("Săgeata sus de %d ori în arbore (%s)", pasi, motiv)
        self.tree.set_focus()
        time.sleep(0.3)
        for _ in range(pasi):
            keyboard.send_keys("{UP}")
            time.sleep(0.2)
        self.app.pause()

    def _deschide_meniul_add_item(self) -> None:
        """Deschide meniul butonului "+ Add item ▼" din săgeata neagră (partea de dropdown a split-button-ului).

        Clicul pe partea cu text adaugă direct un sub-element, deci nu apăsăm acolo. Întâi căutăm butonul ca imagine
        (Data/Images/add_item_buton.png, decupat din aplicație) în ecranul de configurare și dăm click pe marginea
        lui dreaptă; apoi, ca rezervă, clicul pe marginea dreaptă a dreptunghiului raportat de UIA pentru btn_New.
        După fiecare încercare verificăm că meniul chiar s-a deschis.
        """
        region = self.app.region_of(self.config_screen)
        found = self.app.imagini.gaseste("add_item_buton", region=region, timeout=3)
        if found is not None:
            _, box = found
            x, y = int(box.left + box.width - 9), int(box.top + box.height / 2)
            log.info("Click pe săgeata butonului 'Add item' la (%d, %d) [imagine la %s]", x, y, box)
            pyautogui.click(x, y)
            self.app.pause(2)
            if self.app.menu_open():
                return
            log.warning("Meniul nu s-a deschis după clicul pe săgeată (imagine)")

        btn = self.btn_new
        r = btn.rectangle()
        log.info("btn_New: tip=%s nume=%r rect=%s", btn.element_info.control_type, btn.element_info.name, r)
        x, y = r.right - 7, (r.top + r.bottom) // 2
        log.info("Click pe marginea dreaptă a btn_New la (%d, %d)", x, y)
        pyautogui.click(x, y)
        self.app.pause(2)
        if self.app.menu_open():
            return
        raise ApplicationException("Nu am reușit să deschid meniul butonului 'Add item' (săgeata de lângă buton). "
                                   "Ferestre deschise:\n" + self.app.dump_windows())

    def _camp_detalii(self, auto_id: str):
        """Un câmp din tab-ul 'Detalii' (txt_Name, lst_Type), căutat doar în panoul din dreapta (pnl_Background).
        Panoul se poate deschide pe tab-ul 'Pictogramă', caz în care 'Detalii' trebuie apăsat întâi."""
        tab = self.pnl_background.child_window(title="Detalii", control_type="TabItem")
        if self.app.exists(tab, timeout=2):
            try:
                if not tab.wrapper_object().is_selected():
                    self.app.click(tab)
            except Exception:  # noqa: BLE001 - controlul nu expune SelectionItem
                self.app.click(tab)
        return self.pnl_background.child_window(auto_id=auto_id)

    def trimite_modificari(self) -> None:
        """"Click 'Trimite modificari'" (btn_Submit); robotul avea și varianta cu imagine, păstrată ca rezervă."""
        btn = self.buton_store("btn_Submit")
        if self.app.exists(btn, timeout=3):
            self.app.click(btn)
        else:
            self.app.click_image("trimite_modificari", within=self.config_screen)
        log.info("Modificările din Universul de procese au fost trimise")
        # salvarea închide ecranul de configurare; până atunci aplicația ignoră clicurile din meniul din stânga
        ecran = self.app.main.child_window(auto_id="ConfigurationScreen", depth=1)
        deadline = time.monotonic() + 120
        while self.app.exists(ecran, timeout=0) and time.monotonic() < deadline:
            time.sleep(0.5)
        if self.app.exists(ecran, timeout=0):
            log.warning("Ecranul de configurare este încă deschis după 120 s de la trimiterea modificărilor")
        else:
            log.info("Ecranul de configurare s-a închis")
        self.app.pause(3)
