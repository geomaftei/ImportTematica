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

import logging
from typing import Dict, Optional

import pandas as pd
from pywinauto import keyboard

from ..config import Config
from ..exceptions import ApplicationException
from ..matrice import (
    COL_CADRU_CONTROL, COL_DENUMIRE_CONTROL, COL_DENUMIRE_TEST, COL_DESCRIERE_CONTROL, COL_DESCRIERE_RISC,
    COL_DETALII_TEHNICI, COL_FRECVENTA_CONTROL, COL_TEHNICI_TEST, COL_TIP_RISC, Matrice, normalizeaza_spatii,
)
from .app import PentanaApp

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
            self.selecteaza_in_arbore(self.prefix + proces)
            log.info("A fost selectat procesul %s", proces)
            for arie in self.matrice.arii_pentru(proces):
                self.selecteaza_in_arbore(arie)
                self._proceseaza_nod(proces, arie, "")
                for subarie in self.matrice.subarii_pentru(proces, arie):
                    self.selecteaza_in_arbore(subarie)
                    self._proceseaza_nod(proces, arie, subarie)

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
        self._bifeaza_entitate(form, details, self.cfg["pentana.entity_link"])

        # "Tipuri audit" -> Asigurare
        app.click(details.child_window(auto_id="lst_AuditType"))
        app.dropdown_select(self.cfg["pentana.audit_type"], tree_auto_id="MultiLevelListTreeControl")
        log.info("Tip audit: %s", self.cfg["pentana.audit_type"])
        app.click(app.path(form, "pnl_Buttons", "btn_Next"))  # "Finalizare"
        self._verifica_popup_formular(form)
        app.wait(self.editor)
        log.info("Șablonul '%s' a fost creat", nume)

    def _bifeaza_entitate(self, form, details, entitate: str) -> None:
        """Lista 'Entități asociate' are căsuțe de bifat: clicul pe text doar selectează rândul, deci bifăm
        explicit (Toggle; altfel SPACE, tasta standard a unui TreeView cu căsuțe) și verificăm."""
        app = self.app
        app.click(details.child_window(auto_id="lst_EntityLinks"))
        picker = app.path(app.dropdown(), "pnl_Content", "AuditableEntityPickerControl")
        item = app.select_tree_item(picker, entitate)
        stare = _stare_bifa(item)
        log.info("Entitatea '%s' selectată; bifată: %s", entitate, _text_bifa(stare))
        if stare != 1:
            try:
                item.toggle()
                app.pause()
                stare = _stare_bifa(item)
                log.info("După Toggle: bifată %s", _text_bifa(stare))
            except Exception:  # noqa: BLE001 - elementul nu expune Toggle
                stare = None
            if stare != 1:
                # SPACE pe rândul selectat bifează căsuța într-un TreeView cu căsuțe
                item.click_input()
                keyboard.send_keys("{SPACE}")
                app.pause()
                stare = _stare_bifa(item)
                log.info("După SPACE: bifată %s", _text_bifa(stare))
        if stare == 0:
            raise ApplicationException(f"Nu am reușit să bifez entitatea '{entitate}' în 'Entități asociate'")
        # închidem lista confirmând (Enter, ca robotul), apoi un clic pe titlul formularului dacă a rămas deschisă;
        # ESC ar anula alegerea
        keyboard.send_keys("{ENTER}")
        app.pause()
        try:
            app.window("DropDownComponentWindow", timeout=1)
            log.info("Lista de entități a rămas deschisă; o închid cu un clic pe titlul formularului")
            app.click(form.child_window(auto_id="lbl_PageTitle"))
        except ApplicationException:
            pass  # lista s-a închis

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
    def selecteaza_in_arbore(self, nume: str) -> None:
        """"Click Tree pt a selecta procesul/aria/subaria".

        Robotul deschidea lista și apăsa săgeata dreapta de 1-2 ori (navigare pozițională); aici alegem nodul după
        nume în ProcessUniverseSelectionTree, apoi confirmăm cu Enter.
        """
        app = self.app
        app.click(self.tree_picker)
        tree = app.path(app.dropdown(), "pnl_Content", "ProcessUniverseSelectionTree", "tv_Processes")
        app.select_tree_item(tree, nume)
        keyboard.send_keys("{ENTER}")
        app.pause()
        if app.exists(app.dropdown(), timeout=1):
            keyboard.send_keys("{ESC}")
            app.pause()

    # --- risc ------------------------------------------------------------
    def adauga_risc(self, risc: pd.Series) -> None:
        app = self.app
        descriere = normalizeaza_spatii(risc[COL_DESCRIERE_RISC])
        log.info("Adauga risc: %s", descriere)
        app.click(app.path(self.rc_matrix, ("tb_Main", 1), "btn_AddRisk"))
        app.click_menu_item("Creare risc nou", keyboard_fallback=("{TAB}", "{ENTER}"))

        editor = app.window("RiskTemplateEditor")
        app.paste_into(app.path(editor, "c_Tabs", "tp_Details", "tbl_DetailsLayout", "txt_Description"), descriere)

        # [img] tab "Tip Risc" -> [img] câmpul "< None >" (Tip Risc:) -> lista DataListTreeControl
        app.click_image("tab_tip_risc", within=editor,
                        fallback=editor.child_window(auto_id="c_Tabs").child_window(title="Tip Risc",
                                                                                     control_type="TabItem"))
        meta = self._meta(editor)
        app.click_image("camp_none", within=meta.child_window(title="Tip Risc:"),
                        fallback=meta.child_window(title="Tip Risc:"))
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

        app.click_image("adaugare_control", within=app.main)  # [img] scope: fereastra principală
        app.click_menu_item("Creare control nou", keyboard_fallback=("{TAB}", "{ENTER}"))

        editor = app.window("ControlTemplateEditor")
        details = app.path(editor, "c_Tabs", "tp_Details", "tbl_DetailsLayout")
        app.paste_into(details.child_window(auto_id="txt_Description"), denumire)

        # [img] "< Fără >" (Tip Control) -> Down + Enter: robotul lua primul element din listă
        app.click_image("camp_fara", within=editor, fallback=details.child_window(auto_id="lst_ControlType"))
        keyboard.send_keys("{DOWN}{ENTER}")
        app.pause()

        # [img] "Liste răspunsuri" -> meniul m_AnswerLists -> "Functionalitatea de control"
        self._alege_lista_raspunsuri(editor, details,
                                     self.cfg.get("pentana.control_answer_list", "Functionalitatea de control"))

        # [img] tab "Detalii Control": descriere, frecvență, cadru de reglementare
        app.click_image("tab_detalii_control", within=editor,
                        fallback=editor.child_window(auto_id="c_Tabs").child_window(title="Detalii Control",
                                                                                     control_type="TabItem"))
        meta = self._meta(editor)
        app.paste_into(meta.child_window(title_re="^Descriere Control.*"),
                       normalizeaza_spatii(control[COL_DESCRIERE_CONTROL]))

        # [img] "< None >" (Frecventa Control:) -> lista de frecvențe
        app.click_image("camp_none", within=meta.child_window(title="Frecventa Control:"),
                        fallback=meta.child_window(title="Frecventa Control:"))
        frecventa = control[COL_FRECVENTA_CONTROL]
        if frecventa and frecventa not in FRECVENTE_CONTROL:
            log.info("%s - nu aleg niciun element", frecventa)
        app.dropdown_select(frecventa if frecventa in FRECVENTE_CONTROL else None)

        app.paste_into(meta.child_window(title_re="^Cadrul de reglementare.*"),
                       normalizeaza_spatii(control[COL_CADRU_CONTROL]))
        app.click_ok(editor)

    def _alege_lista_raspunsuri(self, editor, details, nume_lista: str) -> None:
        app = self.app
        answers = app.path(details, "c_Answers", "tb_Main")
        app.hover(answers.child_window(auto_id="btn_AnswerLists"))
        app.click_image("liste_raspunsuri", within=editor, fallback=answers)
        menu = app.window("m_AnswerLists")
        item = menu.child_window(title_re="^" + nume_lista + ".*", control_type="MenuItem")
        if app.exists(item, timeout=3):
            app.click(item)
        else:
            raise ApplicationException(
                f"Nu am găsit lista de răspunsuri '{nume_lista}' în meniul m_AnswerLists "
                "(setează pentana.control_answer_list / pentana.test_answer_list în config.yaml)"
            )

    # --- legătura risc/control -------------------------------------------
    def leaga_risc_control(self, risc: pd.Series, control: pd.Series) -> None:
        """"Pregatim adaugarea Testului": filtrare după risc + control, apoi legătura din celula matricei."""
        app = self.app
        log.info("Pregatim adaugarea testului %s", risc[COL_DESCRIERE_RISC])
        app.click_image(("filtre_risc_control", "filtre_risc_control_activ"), within=app.main, timeout=6,
                        fallback=app.path(self.rc_matrix, "tb_Links", "btn_RCFilters"))
        flt = app.path(app.dropdown(), "pnl_Content", "RCTemplateFilterControl", "tbl_Layout")
        app.paste_into(flt.child_window(auto_id="txt_RiskFilter"), normalizeaza_spatii(risc[COL_DESCRIERE_RISC]),
                       select_all=True)
        keyboard.send_keys("{TAB}")
        app.paste_into(flt.child_window(auto_id="txt_ControlFilter"),
                       normalizeaza_spatii(control[COL_DENUMIRE_CONTROL]), select_all=True)
        app.click_image("aplicare_filtre", within=app.dropdown(), fallback=flt.child_window(auto_id="btn_Apply"))

        # după filtrare rămâne o singură celulă risc x control ("in patratel")
        cell = self._celula_matrice()
        app.click(cell)
        # [img] elementul de meniu "Creare legătură de risc/control pentru selecție"
        try:
            app.click_image("creare_legatura_risc_control", timeout=3)
        except ApplicationException:
            self._meniu_matrice("Creare legătură de risc/control pentru selecție", cell)

    def _celula_matrice(self):
        return self.app.path(self.rc_matrix, "pnl_Outer", ("c_Matrix", 0))

    def _meniu_matrice(self, element: str, cell) -> None:
        """Meniul contextual c_RCMatrixContext; robotul dădea două clicuri pe celulă - noi încercăm și click dreapta."""
        app = self.app
        menu = app.popup_menu("c_RCMatrixContext")
        item = menu.child_window(title_re="^" + element.replace("(", r"\(").replace(")", r"\)") + "$",
                                 control_type="MenuItem")
        if not app.exists(item, timeout=2):
            app.click(cell, right=True)
        app.click(item)

    # --- teste -------------------------------------------------------------
    def deschide_teste(self) -> None:
        """"Editare teste pt control": butonul btn_EditTests (ramura Arie) sau meniul celulei (ramura Sub-arie)."""
        btn = self.app.path(self.rc_matrix, ("tb_Links", 1), "btn_EditTests")
        if self.app.exists(btn, timeout=3):
            self.app.click(btn)
            return
        cell = self._celula_matrice()
        self.app.click(cell)
        self._meniu_matrice("Editare teste", cell)

    def inchide_teste(self) -> None:
        log.info("Merg la urmatorul test")
        self.app.click_image("editare_teste_pentru_controlul_selectat", within=self.app.main,
                             fallback=self.app.path(self.rc_matrix, ("tb_Links", 1), "btn_EditTests"))

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
        app.click_image("camp_none", within=meta.child_window(title="Tehnici de testare control:"),
                        fallback=meta.child_window(title="Tehnici de testare control:"))
        tehnici = str(test[COL_TEHNICI_TEST]).lower()
        log.info("Voi bifa tehnica de testare: %s", test[COL_TEHNICI_TEST])
        for cuvant, element in TEHNICI_TESTARE.items():
            if cuvant in tehnici:
                app.dropdown_toggle(element)
        keyboard.send_keys("{TAB}")  # închide lista, ca în robot
        app.pause()

        log.info("Scriu Detalii Tehnici de Testare: %s", test[COL_DETALII_TEHNICI])
        app.paste_into(meta.child_window(title_re="^Detalii tehnici de testare.*"),
                       normalizeaza_spatii(test[COL_DETALII_TEHNICI]))
        app.click_ok(editor)


def _stare_bifa(item) -> Optional[int]:
    """Starea căsuței unui element de arbore: 1 bifat, 0 nebifat, None dacă nu se poate citi."""
    try:
        return int(item.get_toggle_state())
    except Exception:  # noqa: BLE001 - elementul nu expune Toggle
        return None


def _text_bifa(stare: Optional[int]) -> str:
    return {1: "da", 0: "nu"}.get(stare, "necunoscut")
