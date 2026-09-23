"""IntroducereRiscuri.xaml - creează șablonul de tematică și introduce riscurile, controalele și testele.

Ecranul: "Creare Sabloane" (btn_TemplateDesign) -> "Creare șablon" -> CreateWPTemplateForm (design nou, nume,
legătură cu entitatea, tip audit) -> WPTemplateDesigner2. Apoi, pentru fiecare Proces > Arie (> Sub-arie) din
matrice, nodul se alege în arborele de procese (pb_EditInclusion / ProcessUniverseSelectionTree) și:

    Risc      : btn_AddRisk -> "Creare risc nou" -> RiskTemplateEditor (descriere, tab "Tip Risc") -> OK
    Control   : [img] "Adăugare control" -> "Creare control nou" -> ControlTemplateEditor
                (denumire, [img] "< Fără >" tip, [img] "Liste răspunsuri", [img] tab "Detalii Control",
                 descriere, [img] "< None >" frecvență, cadru de reglementare) -> [img] OK
    Legătură  : [img] "Filtre risc/control" (risc + control) -> [img] "Aplicare filtre" -> celula matricei ->
                [img] "Creare legătură de risc/control pentru selecție"
    Teste     : "Editare teste" -> tb_Findings/btn_New -> "Test" -> TestTemplateEditor
                (denumire, [img] "Liste răspunsuri", [img] tab "Tehnici De Testare", [img] "< None >",
                 tehnici bifate, detalii) -> [img] OK

[img] = pasul era "Click Image" în robot; folosim aceeași imagine (Data/Images), căutată în fereastra pe care
robotul o avea ca scope. În robot ramura pentru Arie și cea pentru Sub-arie erau copiate una după alta (aceeași
logică cu alt filtru); aici este o singură implementare, `_proceseaza_nod`.
"""
from __future__ import annotations

import ctypes
import logging
import re
import time
from datetime import date
from typing import Dict, List

import pandas as pd
import pyautogui
from PIL import ImageGrab
from pywinauto import keyboard

from ..config import Config
from ..exceptions import ApplicationException
from ..matrice import (
    COL_CADRU_CONTROL, COL_DENUMIRE_CONTROL, COL_DENUMIRE_TEST, COL_DESCRIERE_CONTROL, COL_DESCRIERE_RISC,
    COL_AUDITOR, COL_COD_APR, COL_DETALII_TEHNICI, COL_TERMEN, COL_FRECVENTA_CONTROL, COL_TEHNICI_TEST, COL_TIP_RISC, Matrice, normalizeaza_spatii,
)
from ..nume_date import cuvinte as cuvinte_nume, imparte_auditori, parseaza_data, potriveste_nume
from .app import PentanaApp
from .fastspec import arbore_controale
from .ocr import citeste_ecran

log = logging.getLogger("tematica.pentana.sabloane")

# Switch "In functie de tipul riscului": valoarea din Excel -> elementul din lista "Tip Risc" (wildcard '*' ca în UiPath)
TIPURI_RISC: Dict[str, str] = {
    "Risc operational": "Risc operational",
    "Risc de conformitate": "Risc de conformitate",
    "Risc de credit": "Risc de credit",
    "Risc aferent tehnologiei informatiei si comunicatiilor (TIC) si de securitate":
        "Risc aferent tehnologiei informatiei si comunicatiilor (TIC) si *",
    "Risc de piata": "Risc de piata",
    "Risc de lichiditate": "Risc de lichiditate",
    "Risc reputational": "Risc reputational",
    "Risc strategic": "Risc strategic",
    "Risc de rata a dobanzii din activitati in afara portofoliului de tranzactionare":
        "Risc de rata a dobanzii din activitati in afara portofoliului de*",
    "Risc de rata a dobanzii din activitati din afara portofoliului de tranzactionare":
        "Risc de rata a dobanzii din activitati in afara portofoliului de*",
    "Risc asociat folosirii excesive a efectului de levier": "Risc asociat folosirii excesive a efectului de levier",
}

# Switch "In functie de Frecventa Control"
FRECVENTE_CONTROL = (
    "Zilnic sau ori de cate ori este nevoie", "Saptamanal", "Lunar", "Trimestrial", "Semestrial", "Anual sau mai rar",
)

# IF-urile "Bifam ... (Tehnici de testare)": cuvânt cheie din Excel -> elementul din listă
TEHNICI_TESTARE: Dict[str, str] = {
    "interviu": "Interviul",
    "observarea": "Observarea",
    "validarea": "Validarea procedurii pe baza unui esantion",
    "examinarea": "Examinarea documentelor, datelor, informatiilor si inregistraril*",
    "recalcularea": "Reefectuarea sau recalcularea",
}


class IntroducereRiscuri:
    def __init__(self, app: PentanaApp, cfg: Config, matrice: Matrice):
        self.app = app
        self.cfg = cfg
        self.matrice = matrice
        self.prefix = str(cfg.get("pentana.process_name_prefix", "") or "")
        self.probleme_auditori: List[str] = []
        self.probleme_termen: List[str] = []

    # --- selectori -----------------------------------------------------
    @property
    def designer(self):
        return self.app.path(self.app.main, "pnl_Main", "AuditDesignSection", "_sectionArea", "WPTemplateDesigner2")

    @property
    def editor(self):
        return self.app.path(self.designer, "mp_Pages", "mpp_Editor", "c_Editor")

    @property
    def rc_matrix(self):
        return self.app.path(self.editor, "pnl_Main", "pnl_TypeEditor", "RCMatrixEditor")

    @property
    def tree_picker(self):
        return self.app.path(self.editor, "pnl_Main", "c_Processes", "tbl_Layout", "pnl_Gutter", "pb_EditInclusion")

    @staticmethod
    def _meta(editor):
        """tab-ul de metadate al unui editor: c_Tabs / tp_MetaData / c_MetaData / DataInputSection / tbl_Items"""
        return PentanaApp.path(editor, "c_Tabs", "tp_MetaData", "c_MetaData", "DataInputSection", "tbl_Items")

    # --- flux ----------------------------------------------------------
    def ruleaza(self) -> None:
        log.info("WorkFlow-ul Introducere Riscuri / Controale / Teste a pornit")
        self.creeaza_sablon()
        for proces in self.matrice.procese:
            nume_proces = self.prefix + proces
            for arie in self.matrice.arii_pentru(proces):
                # aria se caută doar sub procesul nostru, sub-aria doar sub aria noastră
                self.selecteaza_in_arbore([nume_proces, arie])
                self._proceseaza_nod(proces, arie, "")
                for subarie in self.matrice.subarii_pentru(proces, arie):
                    self.selecteaza_in_arbore([nume_proces, arie, subarie])
                    self._proceseaza_nod(proces, arie, subarie)
        self._rezumat()

    def _rezumat(self) -> None:
        if self.probleme_auditori:
            log.warning("Auditori alocați - %d probleme (bifele de mai jos NU au fost puse):\n  %s",
                        len(self.probleme_auditori), "\n  ".join(self.probleme_auditori))
        else:
            log.info("Auditori alocați: totul OK - toți auditorii din matrice au fost găsiți și bifați")
        if self.probleme_termen:
            log.warning("Termen finalizare test - %d probleme:\n  %s",
                        len(self.probleme_termen), "\n  ".join(self.probleme_termen))
        else:
            log.info("Termen finalizare test: totul OK")

    def _proceseaza_nod(self, proces: str, arie: str, subarie: str) -> None:
        for _, risc in self.matrice.riscuri_pentru(proces, arie, subarie).iterrows():
            self.adauga_risc(risc)
            for _, control in self.matrice.controale_pentru(risc).iterrows():
                self.adauga_control(control)
                self.leaga_risc_control(risc, control)
                self.deschide_teste()
                for _, test in self.matrice.teste_pentru(control).iterrows():
                    self.adauga_test(test)
                self.inchide_teste()

    # --- crearea șablonului -----------------------------------------------
    def creeaza_sablon(self) -> None:
        """Secvența "Crearea unei foi de lucru"."""
        app = self.app
        self._deschide_creare_sabloane()
        app.click(self.designer.child_window(auto_id="btn_CreateTemplate"))

        form = app.window("CreateWPTemplateForm")
        app.click(app.path(form, "pnl_Pages", "pg_Option", "btn_CreateBlank"))  # "Design Nou"
        log.info("Formularul 'Creare șablon' deschis, varianta 'Design Nou'")
        details = app.path(form, "pnl_Pages", "pg_Details", "tbl_DetailsLayout")
        nume = self.cfg["pentana.template_name"]
        app.paste_into(details.child_window(auto_id="txt_Name"), nume, select_all=True)
        log.info("Numele șablonului: %s", nume)

        # "Entități asociate" -> arborele AuditableEntityPickerControl -> bifăm entitatea din config
        entitate = self.cfg["pentana.entity_link"]
        app.click(details.child_window(auto_id="lst_EntityLinks"))
        app.bifeaza_element(app.path(app.dropdown(), "pnl_Content", "AuditableEntityPickerControl"), entitate)
        self._inchide_lista(form.child_window(auto_id="lbl_PageTitle"))
        log.info("Entitate asociată: %s", entitate)

        # "Tipuri audit conexate" -> bifăm tipul din config (Asigurare)
        tip = self.cfg["pentana.audit_type"]
        app.click(details.child_window(auto_id="lst_AuditType"))
        app.bifeaza_element(app.path(app.dropdown(), "pnl_Content", "MultiLevelListTreeControl", "tv_Items"), tip)
        self._inchide_lista(form.child_window(auto_id="lbl_PageTitle"))
        log.info("Tip audit conexat: %s", tip)
        app.click(app.path(form, "pnl_Buttons", "btn_Next"))  # "Finalizare"
        self._verifica_popup_formular(form)
        app.wait(self.editor)
        log.info("Șablonul '%s' a fost creat", nume)

    def _inchide_lista(self, neutru) -> None:
        """Închide lista derulantă confirmând (Enter, ca robotul); dacă a rămas deschisă, un clic pe un element
        neutru din fereastră (o etichetă). ESC ar anula alegerea, iar un al doilea Enter, după ce lista s-a închis,
        ar apăsa butonul implicit (OK) al editorului."""
        app = self.app
        keyboard.send_keys("{ENTER}")
        if self._lista_inchisa(0.3):
            return
        log.info("Lista a rămas deschisă după Enter; o închid cu un clic lângă ea")
        app.click(neutru)
        if not self._lista_inchisa(1):
            raise ApplicationException("Lista derulantă nu s-a închis nici după clicul în afara ei")

    def _lista_inchisa(self, timeout: float = 0.5) -> bool:
        """Lista derulantă s-a închis (returnează imediat ce a dispărut; False dacă e încă deschisă după timeout)."""
        return self.app.fereastra_inchisa("DropDownComponentWindow", timeout)

    def _lista_deschisa(self) -> bool:
        """Lista derulantă e încă deschisă (verificare scurtă: se folosește după ce am închis-o)."""
        return self.app.fereastra_deschisa("DropDownComponentWindow")

    def _verifica_popup_formular(self, form) -> None:
        """După 'Finalizare', Pentana poate afișa un mesaj de validare (InfoPopup) în loc să creeze șablonul."""
        popup = form.child_window(auto_id="InfoPopup")
        if self.app.exists(popup, timeout=3):
            mesaj = popup.child_window(auto_id="lbl_Details")
            text = mesaj.window_text() if self.app.exists(mesaj, timeout=1) else "(fără text)"
            raise ApplicationException(f"Pentana a refuzat crearea șablonului: {text}")

    def _deschide_creare_sabloane(self) -> None:
        """Hover + dublu-click pe "Creare Sabloane" din meniul din stânga, ca robotul. Dacă aplicația era ocupată
        (de ex. imediat după "Trimitere modificări") clicul se pierde, așa că verificăm că secțiunea s-a deschis
        (butonul "Creare șablon") și reîncercăm."""
        app = self.app
        tools = app.path(app.main, "pnl_SectionMenu", "c_SectionMenu", "pnl_ScrollArea", "pnl_Tools")
        btn = tools.child_window(auto_id="btn_TemplateDesign")
        creare = self.designer.child_window(auto_id="btn_CreateTemplate")
        for incercare in range(1, 4):
            app.hover(btn)
            app.click(btn, double=True)
            if app.exists(creare, timeout=15):
                log.info("Secțiunea 'Creare Sabloane' este deschisă")
                return
            log.warning("Secțiunea 'Creare Sabloane' nu s-a deschis (încercarea %d din 3)", incercare)
        raise ApplicationException("Secțiunea 'Creare Sabloane' nu s-a deschis după 3 dublu-clicuri. "
                                   "Ferestre deschise:\n" + app.dump_windows())

    # --- arborele de procese ---------------------------------------------
    def selecteaza_in_arbore(self, cale: List[str]) -> None:
        """"Click Tree pt a selecta procesul/aria/subaria".

        Robotul deschidea lista și apăsa săgeata dreapta de 1-2 ori (navigare pozițională); aici coborâm pe cale:
        procesul printre nodurile de pe primul nivel, aria printre copiii procesului, sub-aria printre copiii ariei,
        apoi confirmăm cu Enter.
        """
        app = self.app
        dd = None
        for incercare in range(1, 4):
            app.click(self.tree_picker)
            try:
                dd = app.window("DropDownComponentWindow", timeout=5)
                break
            except ApplicationException:
                log.warning("Lista de procese nu s-a deschis după clic (încercarea %d din 3)", incercare)
                app.pause(3)
        if dd is None:
            raise ApplicationException("Lista de procese (pb_EditInclusion) nu s-a deschis după 3 clicuri")
        tree = app.path(dd, "pnl_Content", "ProcessUniverseSelectionTree", "tv_Processes")
        app.select_tree_path(app.wait(tree), cale)
        keyboard.send_keys("{ENTER}")
        app.pause()
        if not app.fereastra_deschisa("DropDownComponentWindow"):
            return  # lista s-a închis după Enter
        log.info("Lista de procese a rămas deschisă după Enter; o închid cu ESC")
        keyboard.send_keys("{ESC}")
        app.pause()

    # --- risc ------------------------------------------------------------
    def adauga_risc(self, risc: pd.Series) -> None:
        app = self.app
        descriere = normalizeaza_spatii(risc[COL_DESCRIERE_RISC])
        log.info("Adauga risc: %s", descriere)
        app.click(app.path(self.rc_matrix, "tb_Main", "btn_AddRisk"))
        app.click_menu_item("Creare risc nou", keyboard_fallback=("{TAB}", "{ENTER}"))

        editor = app.window("RiskTemplateEditor")
        app.paste_into(app.path(editor, "c_Tabs", "tp_Details", "tbl_DetailsLayout", "txt_Description"), descriere)

        # [img] tab "Tip Risc" -> [img] câmpul "< None >" (Tip Risc:) -> lista DataListTreeControl
        app.click_image("tab_tip_risc", within=editor,
                        fallback=editor.child_window(auto_id="c_Tabs").child_window(title="Tip Risc",
                                                                                     control_type="TabItem"))
        meta = self._meta(editor)
        app.click_image("camp_none", within=_camp_lista(meta, "Tip Risc:"),
                        fallback=_camp_lista(meta, "Tip Risc:"))
        tip = risc[COL_TIP_RISC]
        if tip and tip not in TIPURI_RISC:
            log.warning("Tip risc necunoscut '%s' - aleg 'Selectare niciun element'", tip)
        app.dropdown_select(TIPURI_RISC.get(tip))
        app.click_ok(editor)

    # --- control ---------------------------------------------------------
    def adauga_control(self, control: pd.Series) -> None:
        app = self.app
        denumire = normalizeaza_spatii(control[COL_DENUMIRE_CONTROL])
        log.info("Adaugare control %s", denumire)

        app.click_image("adaugare_control", within=app.main,  # [img] scope: fereastra principală
                        fallback=app.path(self.rc_matrix, "tb_Main", "btn_AddControl"))
        app.click_menu_item("Creare control nou", keyboard_fallback=("{TAB}", "{ENTER}"))

        editor = app.window("ControlTemplateEditor")
        details = app.path(editor, "c_Tabs", "tp_Details", "tbl_DetailsLayout")
        app.paste_into(details.child_window(auto_id="txt_Description"), denumire)

        # [img] "< Fără >" (Tip Control) -> Down + Enter: robotul lua primul element din listă
        app.click_image("camp_fara", within=editor, fallback=details.child_window(auto_id="lst_ControlType"))
        keyboard.send_keys("{DOWN}")
        app.pause()
        self._inchide_lista(details.child_window(auto_id="lbl_Description"))  # eticheta "Denumire Control:"
        log.info("Tip control ales (primul element după '< Fără >')")

        # [img] "Liste răspunsuri" -> meniul m_AnswerLists -> "Functionalitatea de control"
        self._alege_lista_raspunsuri(editor, details,
                                     self.cfg.get("pentana.control_answer_list", "Functionalitatea de control"))

        # [img] tab "Detalii Control": descriere, frecvență, cadru de reglementare
        app.click_image("tab_detalii_control", within=editor,
                        fallback=editor.child_window(auto_id="c_Tabs").child_window(title="Detalii Control",
                                                                                     control_type="TabItem"))
        meta = self._meta(editor)
        app.paste_into(_camp_text(meta, "^Descriere Control.*"),
                       normalizeaza_spatii(control[COL_DESCRIERE_CONTROL]))

        # [img] "< None >" (Frecventa Control:) -> lista de frecvențe
        app.click_image("camp_none", within=_camp_lista(meta, "Frecventa Control:"),
                        fallback=_camp_lista(meta, "Frecventa Control:"))
        frecventa = control[COL_FRECVENTA_CONTROL]
        if frecventa and frecventa not in FRECVENTE_CONTROL:
            log.info("%s - nu aleg niciun element", frecventa)
        app.dropdown_select(frecventa if frecventa in FRECVENTE_CONTROL else None)

        app.paste_into(_camp_text(meta, "^Cadrul de reglementare.*"),
                       normalizeaza_spatii(control[COL_CADRU_CONTROL]))
        app.click_ok(editor)

    def _alege_lista_raspunsuri(self, editor, details, nume_lista: str) -> None:
        """"Liste răspunsuri": robotul deschidea meniul m_AnswerLists și alegea lista. În Pentana clicul pe partea
        principală a butonului poate aplica direct lista (răspunsurile apar în lst_Answers, fără meniu) - atunci
        mergem mai departe."""
        app = self.app
        answers = app.path(details, "c_Answers", "tb_Main")
        app.click_image("liste_raspunsuri", within=editor, fallback=answers.child_window(auto_id="btn_AnswerLists"))
        if app.fereastra_deschisa("m_AnswerLists", timeout=0.5):
            menu = app.window("m_AnswerLists")
        else:
            # rândurile listei de răspunsuri sunt desenate de control și nu apar în UIA, deci nu le putem număra
            log.info("Meniul listelor de răspunsuri nu a apărut: lista a fost aplicată direct de buton")
            return
        item = menu.child_window(title_re="^" + nume_lista + ".*", control_type="MenuItem")
        if app.exists(item, timeout=3):
            app.click(item)
            log.info("Lista de răspunsuri aleasă: %s", nume_lista)
        else:
            raise ApplicationException(
                f"Nu am găsit lista de răspunsuri '{nume_lista}' în meniul m_AnswerLists "
                "(setează pentana.control_answer_list / pentana.test_answer_list în config.yaml)"
            )

    # --- legătura risc/control -------------------------------------------
    def leaga_risc_control(self, risc: pd.Series, control: pd.Series) -> None:
        """"Pregatim adaugarea Testului": filtrare după riscul și controlul tocmai create, apoi legătura din celula
        rămasă în matrice. Celula poate fi deja legată (are teste) - atunci nu mai creăm legătura."""
        app = self.app
        log.info("Pregatim adaugarea testului %s", risc[COL_DESCRIERE_RISC])
        self._aplica_filtre(normalizeaza_spatii(risc[COL_DESCRIERE_RISC]),
                            normalizeaza_spatii(control[COL_DENUMIRE_CONTROL]))

        # după filtrare rămâne o singură celulă risc x control ("in patratel")
        app.pause(2)  # matricea se redesenează după filtrare
        self._click_celula()
        # "Creare legătură de risc/control pentru selecție": butonul din bara tb_Links, activ doar cu o celulă
        # nelegată selectată; pentru o celulă deja legată se activează "Eliminare legătură" / "Editare teste"
        btn = app.path(self.rc_matrix, "tb_Links", "btn_CreateRiskControlLink")
        if self._activ(btn):
            app.click(btn)
            log.info("Legătura risc/control a fost creată")
            return
        if self._activ(app.path(self.rc_matrix, "tb_Links", "btn_RemoveRiskControlLink"), timeout=1):
            log.info("Riscul și controlul sunt deja legate (celula are teste); trec la teste")
            return
        log.warning("Butonul 'Creare legătură' nu s-a activat după clicul pe celulă; încerc meniul contextual")
        self._meniu_matrice("Creare legătură de risc/control pentru selecție")
        log.info("Legătura risc/control a fost creată")

    def _aplica_filtre(self, risc: str, control: str) -> None:
        """"Filtre risc/control": riscul și controlul scrise direct în câmpuri (fără TAB, care putea închide lista),
        apoi "Aplicare filtre". Dacă lista se închide pe parcurs, o redeschidem și reluăm."""
        app = self.app
        btn_filtre = app.path(self.rc_matrix, "tb_Links", "btn_RCFilters")
        for incercare in range(1, 4):
            try:
                app.click_image(("filtre_risc_control", "filtre_risc_control_activ"), within=app.main, timeout=6,
                                fallback=btn_filtre)
                dd = app.window("DropDownComponentWindow", timeout=5)
                flt = app.path(dd, "pnl_Content", "RCTemplateFilterControl", "tbl_Layout")
                app.seteaza_text(flt.child_window(auto_id="txt_RiskFilter"), risc)
                app.seteaza_text(flt.child_window(auto_id="txt_ControlFilter"), control)
                app.click_image("aplicare_filtre", within=dd, fallback=flt.child_window(auto_id="btn_Apply"))
                log.info("Filtre aplicate: risc '%s', control '%s'", risc[:60], control[:60])
                return
            except ApplicationException as exc:
                log.warning("Filtrele risc/control nu s-au putut completa (încercarea %d din 3): %s", incercare, exc)
                if not self._lista_inchisa(0):
                    keyboard.send_keys("{ESC}")  # închidem lista pe jumătate completată și o luăm de la capăt
                app.pause(2)
        raise ApplicationException("Nu am reușit să aplic filtrele risc/control după 3 încercări")

    def _celula_matrice(self):
        return self.app.path(self.rc_matrix, "pnl_Outer", ("c_Matrix", 0))

    def _punct_celula(self):
        """Centrul pătrățelului risc x control rămas după filtrare. Matricea e desenată de control (celulele nu apar
        în UIA), deci folosim poziția din robot - regiunea (242, 226, 52, 51) față de c_Matrix, la 100% - înmulțită
        cu scalarea ecranului (la 125% celula e la 302-367 x 282-346)."""
        cell = self.app.wait(self._celula_matrice())
        r = cell.rectangle()
        s = _scalare(cell)
        x0, y0 = self.cfg.get("pentana.celula_matrice_100", [268, 251])
        return r.left + int(round(x0 * s)), r.top + int(round(y0 * s))

    def _click_celula(self, right: bool = False) -> None:
        x, y = self._punct_celula()
        log.info("Clic%s pe celula risc/control la (%d, %d)", " dreapta" if right else "", x, y)
        pyautogui.click(x, y, button="right" if right else "left")
        self.app.pause()

    def _activ(self, spec, timeout: float = 3) -> bool:
        """Butonul există și devine activ în `timeout` secunde."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                if self.app.exists(spec, timeout=0) and spec.wrapper_object().is_enabled():
                    return True
            except Exception:  # noqa: BLE001
                pass
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.3)

    def _meniu_matrice(self, element: str) -> None:
        """Meniul contextual c_RCMatrixContext al celulei (clic dreapta pe celulă)."""
        app = self.app
        self._click_celula(right=True)
        menu = app.popup_menu("c_RCMatrixContext")
        item = menu.child_window(title_re="^" + element.replace("(", r"\(").replace(")", r"\)") + "$",
                                 control_type="MenuItem")
        app.click(item)

    # --- teste -------------------------------------------------------------
    def deschide_teste(self) -> None:
        """"Editare teste pt control": butonul btn_EditTests (ramura Arie) sau meniul celulei (ramura Sub-arie)."""
        btn = self.app.path(self.rc_matrix, "tb_Links", "btn_EditTests")
        if not self._activ(btn):
            self._click_celula()  # butonul e activ doar cu celula risc/control selectată
        if self._activ(btn):
            self.app.click(btn)
            return
        self._meniu_matrice("Editare teste")

    def inchide_teste(self) -> None:
        log.info("Merg la urmatorul test")
        self.app.click_image("editare_teste_pentru_controlul_selectat", within=self.app.main,
                             fallback=self.app.path(self.rc_matrix, "tb_Links", "btn_EditTests"))

    def adauga_test(self, test: pd.Series) -> None:
        app = self.app
        denumire = normalizeaza_spatii(test[COL_DENUMIRE_TEST])
        log.info("Adaugare test nou %s", denumire)
        tests_panel = app.path(self.rc_matrix, "pnl_Outer", "pnl_TestEditor", "c_TestsPanel", "mp_DetailPages",
                               "mpp_Tests", "c_TestEditor", "mp_Pages", "mpp_EditTests")
        app.click(app.path(tests_panel, "tb_Findings", "btn_New"))  # "Test nou..."
        app.click_menu_item("Test", keyboard_fallback=("{TAB}", "{ENTER}"))

        editor = app.window("TestTemplateEditor")
        details = app.path(editor, "c_Tabs", "tp_Details", "tbl_DetailsLayout")
        app.paste_into(details.child_window(auto_id="txt_Description"), denumire)
        self._alege_lista_raspunsuri(editor, details, self.cfg.get("pentana.test_answer_list", "Exceptii"))

        # [img] tab "Tehnici De Testare" -> [img] "< None >" -> lista cu bife
        app.click_image("tab_tehnici_de_testare", within=editor,
                        fallback=editor.child_window(auto_id="c_Tabs").child_window(title="Tehnici De Testare",
                                                                                     control_type="TabItem"))
        meta = self._meta(editor)
        app.click_image("camp_none", within=_camp_lista(meta, "Tehnici de testare control:"),
                        fallback=_camp_lista(meta, "Tehnici de testare control:"))
        tehnici = str(test[COL_TEHNICI_TEST]).lower()
        log.info("Voi bifa tehnica de testare: %s", test[COL_TEHNICI_TEST])
        lista = app.path(app.dropdown(), "pnl_Content", "DataListTreeControl", "tv_Items")
        for cuvant, element in TEHNICI_TESTARE.items():
            if cuvant in tehnici:
                app.bifeaza_element(lista, element)
        self._inchide_lista_bife(meta, r"^Tehnici de testare control.*")

        log.info("Scriu Detalii Tehnici de Testare: %s", test[COL_DETALII_TEHNICI])
        app.paste_into(_camp_text(meta, "^Detalii tehnici de testare.*"),
                       normalizeaza_spatii(test[COL_DETALII_TEHNICI]))

        # tot pe tab-ul tehnicilor, de sus în jos: ResponsabilTest, Termen finalizare test, CodApr
        cod_test = normalizeaza_spatii(test.get(COL_COD_APR, ""))
        eticheta_test = f"'{denumire[:70]}'" + (f" (CodApr {cod_test})" if cod_test else "")
        self._bifeaza_auditori(meta, test.get(COL_AUDITOR, ""), eticheta_test)
        self._completeaza_termen(meta, test.get(COL_TERMEN, ""), eticheta_test)

        # "Cod referinta APR (Nr. Crt.)" din matrice -> câmpul de lângă eticheta "CodApr:" (tot pe tab-ul tehnicilor)
        cod = normalizeaza_spatii(test.get(COL_COD_APR, ""))
        if cod:
            log.info("Scriu CodApr: %s", cod)
            app.seteaza_text(_camp_nu_eticheta(meta, "^CodApr.*"), cod)
        else:
            log.info("Testul nu are Cod referinta APR; câmpul CodApr rămâne gol")
        app.click_ok(editor)


    # --- auditori alocați / termen --------------------------------------------
    def _bifeaza_auditori(self, meta, celula: str, eticheta_test: str) -> None:
        """"Auditor alocat" -> lista "ResponsabilTest:" (cu bife). Numele din Excel se potrivesc tolerant cu cele
        din listă; ce nu se găsește sigur (negăsit / ambiguu) NU se bifează și se raportează în log."""
        app = self.app
        auditori = imparte_auditori(celula)
        if not auditori:
            log.info("Testul %s nu are auditori alocați în matrice", eticheta_test)
            return
        app.click(_camp_nu_eticheta(meta, r"^Responsabil.*"))
        dd = app.window("DropDownComponentWindow", timeout=5)
        utilizatori = app.path(dd, "pnl_Content", "UserSelectionControl", "lst_Users")
        if app.exists(utilizatori, timeout=2):
            # lista de utilizatori e desenată de Pentana (rândurile nu apar în UIA): o citim prin OCR
            self._bifeaza_auditori_ocr(dd, utilizatori, auditori, eticheta_test)
            self._inchide_lista_bife(meta, r"^Responsabil.*")
            return
        lista = None
        for control in ("DataListTreeControl", "MultiLevelListTreeControl"):
            spec = app.path(dd, "pnl_Content", control, "tv_Items")
            if app.exists(spec, timeout=1):
                lista = spec
                break
        if lista is None:
            try:
                log.warning("Lista ResponsabilTest are altă structură:\n%s", arbore_controale(dd.wrapper_object(), 8))
            except Exception:  # noqa: BLE001
                pass
            raise ApplicationException("Nu am găsit lista de auditori (ResponsabilTest) în fereastra deschisă")
        nume_lista = [it.window_text() for it in app.wait(lista).descendants(control_type="TreeItem")]
        log.info("Lista ResponsabilTest: %d nume", len(nume_lista))  # numele nu se scriu în log (date personale)

        for auditor in auditori:
            p = potriveste_nume(auditor, nume_lista)
            if p.gasit is None:
                problema = f"Testul {eticheta_test}: auditorul '{auditor}' - {p.motiv}"
                log.warning("Nu am bifat: %s", problema)
                self.probleme_auditori.append(problema)
                continue
            if p.partiala:
                log.warning("Auditorul '%s' bifat ca '%s' (potrivire parțială, scor %.2f) - de verificat",
                            auditor, p.gasit, p.scor)
            else:
                log.info("Auditorul '%s' bifat ca '%s'", auditor, p.gasit)
            app.bifeaza_element(lista, p.gasit)
        self._inchide_lista_bife(meta, r"^Responsabil.*")

    def _bifeaza_auditori_ocr(self, dd, utilizatori, auditori: List[str], eticheta_test: str) -> None:
        """Lista "Utilizatori audit" (UserSelectionControl / lst_Users): căsuță + nume pe fiecare rând, desenate de
        control, în ordine alfabetică. O singură trecere de sus în jos: citim pagina afișată prin OCR, bifăm
        auditorii care apar pe ea, trecem la pagina următoare doar cât timp mai avem auditori de găsit."""
        app = self.app
        lst = app.wait(utilizatori)
        r = lst.rectangle()
        s = _scalare(lst)
        bara = utilizatori.child_window(control_type="ScrollBar")
        dreapta = bara.rectangle().left if app.exists(bara, timeout=1) else r.right
        # măsurat la 125%: căsuța are centrul la 17 px de marginea listei, textul începe la 30 px
        x_bifa = r.left + int(round(14 * s))
        zona_text = (r.left + int(round(22 * s)), r.top, dreapta, r.bottom)
        # primul clic în listă doar o activează (fără bifă): îl dăm pe "Line up" al barei de derulare - lista e deja
        # sus, deci nu se mișcă. Nu folosim set_focus(): aduce fereastra în față și lista derulantă se închide.
        try:
            app.wait(bara.child_window(title="Line up", control_type="Button"), timeout=1).click_input()
            time.sleep(0.3)
        except Exception:  # noqa: BLE001 - listă fără bară de derulare
            pass

        def pagina():
            """Rândurile cu nume de pe pagina afișată, citite când lista nu se mai mișcă (două citiri identice);
            fără antetul grupului ("Utilizatori audit", citit tăiat: "izatori audit")."""
            anterior, randuri = None, []
            for _ in range(8):
                randuri = [rand for rand in citeste_ecran(zona_text)
                           if len(cuvinte_nume(rand.text)) >= 2 and not _antet_grup(rand.text)]
                cheie = [(rand.text, rand.centru_y) for rand in randuri]
                if cheie == anterior:
                    break
                anterior = cheie
                time.sleep(0.25)
            return randuri

        def urmatoarea_pagina() -> bool:
            buton = bara.child_window(title="Page down", control_type="Button")
            try:
                app.wait(buton, timeout=1).click_input()
            except Exception:  # noqa: BLE001 - bara nu e expusă sau am ajuns jos
                return False
            time.sleep(0.4)
            return True

        def bifeaza(nume: str, y: int) -> bool:
            """Clic pe căsuța rândului și verificarea bifei; a doua încercare recitește pagina (rândul poate
            să se fi mutat). O căsuță deja bifată nu se mai atinge (clicul ar debifa-o)."""
            for incercare in (1, 2):
                if not _bifat(x_bifa, y):
                    pyautogui.click(x_bifa, y)
                    time.sleep(0.5)
                if _bifat(x_bifa, y):
                    return True
                log.info("Bifa pentru '%s' nu a apărut la y=%d (încercarea %d din 2)", nume, y, incercare)
                y = next((rand.centru_y for rand in pagina() if rand.text == nume), y)
            return False

        ramasi = list(auditori)
        vazute: List[str] = []
        anterioara = None
        for _ in range(60):
            randuri = pagina()
            texte = [rand.text for rand in randuri]
            if texte == anterioara:
                break  # derularea nu mai aduce nume noi: am ajuns la capătul listei
            anterioara = texte
            vazute += [t for t in texte if t not in vazute]
            for auditor in list(ramasi):
                p = potriveste_nume(auditor, texte)
                if p.gasit is None:
                    continue  # nu e pe pagina asta (sau e ambiguu aici: decidem la final, pe tot ce am văzut)
                rand = next(rand for rand in randuri if rand.text == p.gasit)
                if p.partiala:
                    log.warning("Auditorul '%s' potrivit cu '%s' (potrivire parțială, scor %.2f) - de verificat",
                                auditor, p.gasit, p.scor)
                if bifeaza(p.gasit, rand.centru_y):
                    log.info("Auditorul '%s' bifat ca '%s'", auditor, p.gasit)
                else:
                    problema = f"Testul {eticheta_test}: auditorul '{auditor}' ('{p.gasit}') - clicul nu a pus bifa"
                    log.warning("Nu am bifat: %s", problema)
                    self.probleme_auditori.append(problema)
                ramasi.remove(auditor)
            if not ramasi or not urmatoarea_pagina():
                break
        for auditor in ramasi:
            p = potriveste_nume(auditor, vazute)
            problema = f"Testul {eticheta_test}: auditorul '{auditor}' - {p.motiv or 'negăsit în listă'}"
            log.warning("Nu am bifat: %s", problema)
            self.probleme_auditori.append(problema)

    def _inchide_lista_bife(self, meta, eticheta_re: str) -> None:
        """Închide lista cu bife printr-un clic pe eticheta câmpului (bifele rămân). Robotul apăsa TAB, dar în
        Pentana TAB nu închide lista - se pierdea timp așteptând."""
        self.app.click(meta.child_window(title_re=eticheta_re, class_name_re=r"WindowsForms10\.STATIC.*"))
        if not self._lista_inchisa(1):
            log.warning("Lista de lângă '%s' nu s-a închis după clicul pe etichetă", eticheta_re)

    def _completeaza_termen(self, meta, celula: str, eticheta_test: str) -> None:
        """"Termen finalizare test": câmp de tip calendar. Încercăm, în ordine, (1) valoarea scrisă direct,
        (2) textul în calendarul care se deschide la clic, (3) tastarea datei; la final verificăm câmpul."""
        try:
            data = parseaza_data(celula)
        except ValueError as exc:
            problema = f"Testul {eticheta_test}: {exc}"
            log.warning("Termen necompletat: %s", problema)
            self.probleme_termen.append(problema)
            return
        if data is None:
            log.info("Testul %s nu are termen de finalizare în matrice", eticheta_test)
            return
        app = self.app
        text = data.strftime("%d.%m.%Y")
        w = app.wait(_camp_nu_eticheta(meta, r"^Termen finalizare.*"))
        log.info("Termen finalizare test: %s (câmp %s)", text, w.element_info.class_name)

        try:  # (1) ValuePattern
            w.iface_value.SetValue(text)
            app.pause()
            if _are_data(_valoare(w), data):
                log.info("Termen completat direct: %s", _valoare(w))
                return
        except Exception:  # noqa: BLE001 - câmpul nu expune ValuePattern
            pass

        w.click_input()
        app.pause()
        if "DateTimePick" in (w.element_info.class_name or ""):  # DateTimePicker: zi, lună, an pe rând
            keyboard.send_keys("{LEFT}{LEFT}{LEFT}" + data.strftime("%d") + "{RIGHT}" + data.strftime("%m")
                               + "{RIGHT}" + data.strftime("%Y") + "{ENTER}")
        elif self._lista_deschisa() and self._calendar_deschis():
            # (2) calendarul Windows (SysMonthCal32): selecția se mută din tastatură și se verifică din numele lui
            # verificarea: data selectată în calendar (citită înainte de confirmare) și calendarul închis după ea
            selectata, inchis = self._alege_in_calendar(data)
            if selectata == data and inchis:
                log.info("Termen completat: %s", text)
            else:
                citit = selectata.strftime("%d.%m.%Y") if selectata else "necunoscut"
                problema = f"Testul {eticheta_test}: termenul {text} nu a fost pus (în calendar: {citit})"
                log.warning("De verificat: %s", problema)
                self.probleme_termen.append(problema)
            return
        elif self._lista_deschisa():  # calendar de alt tip: îl scriem în log și căutăm un câmp de text
            dd = app.window("DropDownComponentWindow", timeout=2)
            try:
                log.debug("Calendarul termenului:\n%s", arbore_controale(dd.wrapper_object(), 8))
            except Exception:  # noqa: BLE001
                pass
            edit = dd.child_window(control_type="Edit")
            if app.exists(edit, timeout=1):
                app.seteaza_text(edit, text)
                keyboard.send_keys("{ENTER}")
            else:
                keyboard.send_keys(text + "{ENTER}")
        else:  # (3) tastăm data în câmp
            keyboard.send_keys("^a" + text + "{ENTER}")
        if not self._lista_inchisa(0.5):
            self._inchide_lista_bife(meta, r"^Termen finalizare.*")
        valoare = _valoare(w)
        if _are_data(valoare, data):
            log.info("Termen completat: %s", valoare)
        else:
            problema = f"Testul {eticheta_test}: termenul {text} nu apare în câmp (valoare citită: '{valoare}')"
            log.warning("De verificat: %s", problema)
            self.probleme_termen.append(problema)


    def _calendar(self, timeout: float = 2):
        dd = self.app.window("DropDownComponentWindow", timeout=timeout)
        return dd.child_window(class_name_re=r"WindowsForms10\.SysMonthCal32.*")

    def _calendar_deschis(self, timeout: float = 2) -> bool:
        """timeout = cât așteptăm să apară; după confirmare folosim o verificare scurtă (calendarul e deja închis)."""
        if not self.app.fereastra_deschisa("DropDownComponentWindow", timeout=timeout):
            return False
        try:
            return self.app.exists(self._calendar(timeout), timeout=timeout)
        except ApplicationException:
            return False

    def _alege_in_calendar(self, data):
        """Mută selecția calendarului pe `data` din tastatură (PageUp/PageDown = o lună, Home = prima zi a lunii,
        săgeți = o zi), verifică din numele calendarului ("08/09/2026 selected.") și confirmă alegerea."""
        app = self.app
        cal = app.wait(self._calendar(), timeout=3)
        curenta = _data_calendar(cal.window_text()) or date.today()
        cal.set_focus()
        luni = (data.year - curenta.year) * 12 + data.month - curenta.month
        taste = ("{PGDN}" if luni > 0 else "{PGUP}") * abs(luni) + "{HOME}" + "{RIGHT}" * (data.day - 1)
        keyboard.send_keys(taste, pause=0.03)
        for _ in range(3):  # corecție: dacă Home nu a dus la prima zi, ajustăm cu săgețile
            app.pause(0.5)
            selectata = _data_calendar(cal.window_text())
            if selectata is None or selectata == data:
                break
            zile = (data - selectata).days
            keyboard.send_keys(("{RIGHT}" if zile > 0 else "{LEFT}") * abs(zile), pause=0.03)
        selectata = _data_calendar(cal.window_text())
        keyboard.send_keys("{ENTER}")
        if not self._lista_inchisa(0.5):
            # Enter nu a închis calendarul: clic pe ziua selectată (alegerea cu mouse-ul o confirmă)
            for celula in cal.descendants():
                try:
                    if celula.is_selected():
                        celula.click_input()
                        break
                except Exception:  # noqa: BLE001 - elementul nu expune SelectionItem
                    continue
            if not self._lista_inchisa(0.5):
                keyboard.send_keys("{SPACE}")
            return selectata, self._lista_inchisa(0.5)
        return selectata, True

def _data_calendar(nume: str):
    """Data selectată din numele calendarului Windows: '08/09/2026 selected.' (zz/ll/aaaa pe acest sistem)."""
    m = re.search(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", nume or "")
    if not m:
        return None
    a, b, an = int(m.group(1)), int(m.group(2)), int(m.group(3))
    for zi, luna in ((a, b), (b, a)):
        try:
            return date(an, luna, zi)
        except ValueError:
            continue
    return None


def _antet_grup(text: str) -> bool:
    """Antetul grupului din lista de utilizatori ("Utilizatori audit"), eventual tăiat la stânga de zona citită."""
    c = cuvinte_nume(text)
    return bool(c) and len(c[0]) >= 4 and "utilizatori".endswith(c[0])


def _bifat(x: int, y: int) -> bool:
    """Căsuța de la (x, y) e bifată: interiorul ei nu mai e alb uniform (nebifată are luminozitatea ~243)."""
    zona = ImageGrab.grab(bbox=(x - 3, y - 3, x + 4, y + 4), all_screens=True).convert("L")
    pixeli = zona.tobytes()  # un octet pe pixel în modul "L"
    return sum(pixeli) / len(pixeli) < 220


def _valoare(w) -> str:
    """Textul afișat de un câmp: ValuePattern, apoi valoarea MSAA, apoi textele controlului."""
    for citire in (lambda: w.iface_value.CurrentValue, lambda: w.legacy_properties().get("Value", ""),
                   lambda: " ".join(t for t in w.texts() if t)):
        try:
            v = citire()
            if v:
                return str(v)
        except Exception:  # noqa: BLE001
            pass
    return ""


def _are_data(valoare: str, data) -> bool:
    """Valoarea afișată conține ziua, luna și anul datei (în orice ordine / separator: 31.10.2026, 10/31/2026)."""
    numere = [int(n) for n in re.findall(r"\d+", valoare or "")]
    return data.day in numere and data.month in numere and (data.year in numere or data.year % 100 in numere)


def _camp_lista(meta, eticheta: str):
    """Câmpul-listă de lângă eticheta dată ("Tip Risc:", "Frecventa Control:"...). Eticheta (STATIC) și câmpul au
    același nume, deci restrângem la clasa câmpului, ca selectorul robotului: aaname='X' cls='WindowsForms10.Window.*'."""
    return meta.child_window(title=eticheta, class_name_re=r"WindowsForms10\.Window\..*")


def _camp_nu_eticheta(meta, eticheta_re: str):
    """Câmpul de lângă o etichetă, oricare ar fi tipul lui (RichEdit, Edit...): orice control cu același nume în
    afară de eticheta însăși (STATIC)."""
    return meta.child_window(title_re=eticheta_re, class_name_re=r"WindowsForms10\.(?!STATIC).*")


def _camp_text(meta, eticheta_re: str):
    """Câmpul de text (RichEdit) de lângă etichetă: cls='WindowsForms10.RICHEDIT60W.*' ca în selectorul robotului."""
    return meta.child_window(title_re=eticheta_re, class_name_re=r"WindowsForms10\.RICHEDIT.*")


def _scalare(wrapper) -> float:
    """Scalarea ecranului pentru fereastra controlului (1.0 la 100%, 1.25 la 125%...)."""
    try:
        dpi = ctypes.windll.user32.GetDpiForWindow(wrapper.handle)
        if dpi:
            return dpi / 96.0
    except Exception:  # noqa: BLE001
        pass
    return 1.0
