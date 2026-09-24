"""Sesiunea Pentana + primitivele de UI folosite de toate fluxurile.

Corespondența cu selectorii UiPath (aplicație WinForms):
    <wnd ctrlname='X' />                 -> child_window(auto_id='X')
    <wnd ctrlname='X' idx='2' />         -> child_window(auto_id='X', found_index=1)   (UiPath numără de la 1)
    <ctrl name='X' role='menu item' />   -> child_window(title='X', control_type='MenuItem')
    <ctrl name='X' role='outline item' />-> child_window(title='X', control_type='TreeItem')
    <ctrl name='X' role='page tab' />    -> child_window(title='X', control_type='TabItem')
    <wnd aaname='X' cls='WindowsForms10.Window.*' /> -> child_window(title='X')
    Click Image (scope = selector)       -> click_image(nume, within=spec)  (Data/Images, vezi images.py)
Ferestrele de nivel superior (MKInsightMainUI, DropDownComponentWindow, RiskTemplateEditor, ...) se iau cu
`self.window(auto_id)`; meniurile pop-up (`aaname='DropDown'`) cu `self.popup_menu()`.

Robotul UiPath trimitea hotkey-uri direct pe elementul din selector (SendHotkey cu Target), deci buclele de
TAB din workflow-uri nu contau; aici facem același lucru cu `set_focus()` + `send_keys`.
"""
from __future__ import annotations

import logging
import re
import subprocess
import time
import unicodedata
from typing import Iterable, Optional, Tuple, Union

import pyperclip
from pywinauto import Application, Desktop, keyboard
from pywinauto.findwindows import ElementAmbiguousError, ElementNotFoundError
from pywinauto.timings import TimeoutError as PwTimeoutError

from ..config import Config
from ..control import control
from ..exceptions import ApplicationException
from .fastspec import FastSpec, FereastraProces, copii_cu_nume, wrap
from .images import Imagini, Names, Region

log = logging.getLogger("tematica.pentana")

# un pas din lanțul de selectori: 'auto_id' sau ('auto_id', index_de_la_0)
Step = Union[str, Tuple[str, int]]


class PentanaApp:
    PROCESS_NAME = "pentanamk.exe"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.exe: str = cfg["pentana.exe"]
        self.main_id: str = cfg.get("pentana.main_window_auto_id", "MKInsightMainUI")
        self.timeout: float = float(cfg.get("pentana.wait_timeout_s", 15))
        self.delay: float = float(cfg.get("pentana.action_delay_s", 0.4))
        self.imagini = Imagini(cfg)
        self.app: Optional[Application] = None
        self._unde_gasit: dict = {}

    # ------------------------------------------------------------------ ciclu de viață
    def start(self) -> "PentanaApp":
        """StartProcess -> Click Image 'Modulul de Live' -> Delay -> LoginPentana (dacă apare panoul de login)."""
        log.info("Pornire Pentana: %s", self.exe)
        self.app = Application(backend="uia").start(self.exe)
        # "Click pe Modulul de Live": cardul 'Live Configuration' de pe ecranul de start - dacă apare;
        # altfel mergem mai departe imediat ce fereastra principală există
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if self.exists(self.main, timeout=1):
                break
            if self.imagini.gaseste("live_configuration", timeout=1) is not None:
                self.imagini.click("live_configuration", timeout=1)
                log.info("Am ales modulul 'Live Configuration'")
        self.main.wait("exists visible", timeout=max(self.timeout, 60))
        # "Delay logare in aplicatie": aplicația se autentifică singură (SSO); așteptăm cel mult login_delay_s
        # să apară meniul, iar dacă în schimb a rămas afișat formularul de login, îl completăm noi
        deadline = time.monotonic() + float(self.cfg.get("pentana.login_delay_s", 90))
        login_trimis = False
        secunde_formular_static = 0  # de câte secunde consecutive e afișat formularul fără "Please wait"
        while time.monotonic() < deadline and not self._ready():
            if self._login_visible() and not self._login_in_progress():
                secunde_formular_static += 1
            else:
                secunde_formular_static = 0
            # login manual doar dacă formularul a rămas afișat stabil (nu în tranziția de după auto-login)
            # și doar dacă avem credențiale configurate; altfel așteptăm autentificarea automată
            if not login_trimis and secunde_formular_static >= 8:
                if self._are_credentiale():
                    log.info("Formularul de autentificare a rămas afișat; completez credențialele din .env")
                    self.login()
                    login_trimis = True
                else:
                    log.info("Formularul de autentificare e afișat, dar nu am credențiale în .env; "
                             "aștept autentificarea automată")
                    secunde_formular_static = -30  # nu repeta mesajul la fiecare secundă
            time.sleep(1)
        # bara de meniu se încarcă ultima: așteptăm elementul "Instrumente" ("Tools" înainte de login)
        self.wait(self._menu_instrumente(), timeout=60)
        time.sleep(float(self.cfg.get("pentana.ready_delay_s", 2)))
        log.info("Pentana este pornită")
        control.la_reluare = self.aduce_in_fata
        return self

    def _menu_instrumente(self):
        return self.main.child_window(title_re=r"^(Instrumente|Tools).*", control_type="MenuItem")

    def _ready(self) -> bool:
        """Aplicația e autentificată și încărcată: meniul din stânga există și formularul de login a dispărut."""
        return (self.exists(self.main.child_window(auto_id="pnl_SectionMenu"), timeout=1)
                and not self._login_visible())

    def _are_credentiale(self) -> bool:
        try:
            self.cfg.pentana_credential
            return True
        except RuntimeError:
            return False

    def _login_in_progress(self) -> bool:
        """'Please wait while Ideagen Internal Audit logs in to your account...' (lbl_LoginWait) este afișat."""
        try:
            lbl = self.main.child_window(auto_id="lbl_LoginWait")
            return lbl.exists(timeout=1) and lbl.wrapper_object().is_visible()
        except Exception:
            return False

    def attach(self) -> "PentanaApp":
        """Se leagă de o instanță Pentana deja deschisă (util la depanare)."""
        self.app = Application(backend="uia").connect(path=self.exe, timeout=self.timeout)
        self.main.wait("exists visible", timeout=self.timeout)
        log.info("M-am atașat la instanța Pentana existentă")
        control.la_reluare = self.aduce_in_fata
        return self

    def aduce_in_fata(self) -> None:
        """După o pauză: fereastra Pentana din nou activă (tastele robotului trebuie să ajungă la ea)."""
        self.main.wrapper_object().set_focus()
        time.sleep(0.5)

    def _login_visible(self) -> bool:
        """Formularul de autentificare este afișat efectiv (câmpul de utilizator există și e vizibil)."""
        try:
            camp = self.main.child_window(auto_id="txt_UserName")
            return camp.exists(timeout=1) and camp.wrapper_object().is_visible()
        except Exception:
            return False

    def login(self) -> None:
        """LoginPentana.xaml: txt_UserName / txt_Password / btn_Login (credențiale din asset-ul AuditIntroducereTematica)."""
        cred = self.cfg.pentana_credential
        layout = self.path(self.main, "pnl_Main", "LoginSection", "pnl_Login", "tbl_Layout")
        self.paste_into(layout.child_window(auto_id="txt_UserName"), cred.username, select_all=True)
        self.paste_into(layout.child_window(auto_id="txt_Password"), cred.password, select_all=True)
        self.click(layout.child_window(auto_id="btn_Login"))
        log.info("Autentificare trimisă pentru utilizatorul %s", cred.username)
        time.sleep(float(self.cfg.get("pentana.login_delay_s", 12)) / 2)

    def close(self) -> None:
        """CloseApplication, cu KillProcess ca rezervă."""
        try:
            if self.app is not None:
                self.main.close()
                time.sleep(2)
        except Exception as exc:  # noqa: BLE001
            log.warning("Închiderea grațioasă a eșuat (%s); opresc procesul", exc)
        self.kill()

    @classmethod
    def kill(cls, *extra: str) -> None:
        """KillAllProcesses.xaml: pentanamk.exe + EXCEL (robotul închidea și Excel-urile deschise)."""
        for name in (cls.PROCESS_NAME, "EXCEL.EXE", *extra):
            subprocess.run(["taskkill", "/F", "/IM", name], capture_output=True, check=False)

    # ------------------------------------------------------------------ ferestre
    @property
    def main(self):
        assert self.app is not None, "Aplicația nu este pornită (start()/attach())"
        # același obiect la fiecare apel: FastSpec își memorează fereastra găsită
        if getattr(self, "_main_spec", None) is None or self._main_app is not self.app:
            self._main_spec = FastSpec(FereastraProces(self.app.process, auto_id=self.main_id))
            self._main_app = self.app
        return self._main_spec

    def _resolve(self, timeout: Optional[float] = None, diagnostic: bool = True, **criteria):
        """Găsește o fereastră/un panou după criterii (auto_id=..., title=...), căutând pe rând: fereastră de nivel
        superior a procesului (editoare, pop-up-uri), descendent al ferestrei principale (ecranele Pentana sunt
        panouri în MKInsightMainUI). diagnostic=False: la lipsă nu se listează ferestrele (verificări scurte)."""
        assert self.app is not None
        # FastSpec: tot ce se înlănțuie din fereastra găsită (child_window, path) folosește căutarea rapidă
        # ferestrele de nivel superior ale procesului (editoare, pop-up-uri): un singur apel UIA
        candidates = [FastSpec(FereastraProces(self.app.process, **criteria))]
        if criteria.get("auto_id") != self.main_id:
            # ecranele și listele derulante sunt copii apropiați ai ferestrei principale
            candidates.append(self.main.child_window(**criteria))
        # locul în care am găsit ultima dată fereastra se încearcă primul (economisește scanări)
        key = tuple(sorted(criteria.items()))
        order = list(range(len(candidates)))
        if key in self._unde_gasit:
            order.remove(self._unde_gasit[key])
            order.insert(0, self._unde_gasit[key])
        timeout = self.timeout if timeout is None else timeout
        if timeout < 1 and key in self._unde_gasit:
            order = order[:1]  # verificare scurtă ("mai e deschisă?"): doar locul în care a apărut mereu
        deadline = time.monotonic() + timeout
        while True:
            for i in order:
                if self.exists(candidates[i], timeout=0):  # o singură încercare pe loc, pe tură
                    if self._unde_gasit.get(key) != i:
                        log.debug("Fereastra %s găsită ca %s", criteria,
                                  ("fereastră a procesului", "descendent al ferestrei principale")[i])
                        self._unde_gasit[key] = i
                    return candidates[i]
            if time.monotonic() >= deadline:
                raise ApplicationException(
                    f"Nu am găsit fereastra {criteria} în {timeout}s"
                    + ((". Ferestre deschise:\n" + self.dump_windows()) if diagnostic else "")
                )
            time.sleep(0.1)

    def window(self, auto_id: str, timeout: Optional[float] = None):
        """O fereastră a aplicației după auto_id (editoare, DropDownComponentWindow, ConfigurationScreen...)."""
        return self._resolve(timeout, auto_id=auto_id)

    def fereastra_inchisa(self, auto_id: str, timeout: float = 0.5) -> bool:
        """Așteaptă să dispară fereastra: întoarce True imediat ce nu mai există (verificări repetate, rapide),
        False dacă e încă deschisă după `timeout`. Pentru "s-a închis lista?" - nu așteaptă degeaba."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                self._resolve(0, diagnostic=False, auto_id=auto_id)
            except ApplicationException:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def fereastra_deschisa(self, auto_id: str, timeout: float = 0.3) -> bool:
        """Verificare rapidă, fără diagnostic la lipsă (ex. "s-a închis lista derulantă?")."""
        try:
            self._resolve(timeout, diagnostic=False, auto_id=auto_id)
            return True
        except ApplicationException:
            return False

    screen = window  # alias istoric

    def dropdown(self):
        """<wnd ctrlname='DropDownComponentWindow' /> - fereastra pop-up folosită pentru toate listele."""
        return self.window("DropDownComponentWindow")

    def popup_menu(self, owner_auto_id: Optional[str] = None, timeout: Optional[float] = None):
        """<wnd aaname='DropDown' cls='WindowsForms10.Window.*' /><ctrl name='DropDown' role='popup menu' />.
        Întoarce fereastra meniului; elementele (MenuItem) se caută direct în ea, indiferent dacă meniul propriu-zis
        e fereastra însăși sau un copil al ei."""
        if owner_auto_id:
            return self.window(owner_auto_id, timeout=timeout)
        return self._resolve(timeout, title="DropDown")

    def menu_open(self, owner_auto_id: Optional[str] = None, timeout: float = 3) -> bool:
        try:
            self.popup_menu(owner_auto_id, timeout=timeout)
            return True
        except ApplicationException:
            return False

    def menu_item(self, name: str, owner_auto_id: Optional[str] = None, timeout: Optional[float] = None):
        """Un element de meniu după nume (regex tolerant la diacritice și la wildcard-ul '*' din UiPath)."""
        return self.popup_menu(owner_auto_id, timeout=timeout).child_window(title_re=_wild(name),
                                                                              control_type="MenuItem")

    @staticmethod
    def path(parent, *steps: Step):
        """Înlănțuie child_window(auto_id=...) ca un selector UiPath cu mai multe noduri <wnd ctrlname=... />."""
        spec = parent
        for step in steps:
            if isinstance(step, tuple):
                spec = spec.child_window(auto_id=step[0], found_index=step[1])
            else:
                spec = spec.child_window(auto_id=step)
        return spec

    # ------------------------------------------------------------------ acțiuni
    def wait(self, spec, timeout: Optional[float] = None):
        start = time.monotonic()
        try:
            return spec.wait("exists visible enabled", timeout=timeout or self.timeout)
        except (PwTimeoutError, ElementNotFoundError) as exc:
            raise ApplicationException(
                f"Nu am găsit elementul în {timeout or self.timeout}s: {describe(spec)}"
            ) from exc
        except ElementAmbiguousError as exc:
            raise ApplicationException(
                f"Selectorul se potrivește cu mai multe elemente (trebuie restrâns): {describe(spec)}"
            ) from exc
        finally:
            durata = time.monotonic() - start
            if durata > 2:
                log.info("Căutarea a durat %.1fs: %s", durata, describe(spec))

    def dump_windows(self) -> str:
        """Ferestrele procesului Pentana (de pe desktop) și copiii direcți ai ferestrei principale - pentru log."""
        if self.app is None:
            return "(aplicația nu este pornită)"
        lines = []

        def fmt(w, indent="  "):
            ei = w.element_info
            return (f"{indent}auto_id={ei.automation_id!r} title={ei.name!r} type={ei.control_type!r} "
                    f"class={ei.class_name!r} visible={ei.visible} rect={ei.rectangle}")

        try:
            lines.append(" ferestre pe desktop (procesul Pentana):")
            for w in Desktop(backend="uia").windows(process=self.app.process):
                lines.append(fmt(w))
            lines.append(" copiii direcți ai ferestrei principale:")
            for w in self.main.wrapper_object().children():
                lines.append(fmt(w, "    "))
        except Exception as exc:  # noqa: BLE001
            lines.append(f"  (eroare la listare: {exc})")
        return "\n".join(lines)

    def pause(self, factor: float = 1.0) -> None:
        control.verifica()  # oprirea cerută din interfață (F10) se aplică după acțiunea curentă
        time.sleep(self.delay * factor)

    def click(self, spec, double: bool = False, right: bool = False):
        ctl = self.wait(spec)
        if double:
            ctl.double_click_input()
        elif right:
            ctl.right_click_input()
        else:
            ctl.click_input()
        self.pause()
        return ctl

    def hover(self, spec):
        ctl = self.wait(spec)
        ctl.move_mouse_input()
        self.pause(0.5)
        return ctl

    def hotkey(self, spec, keys: str):
        """SendHotkey cu Target: focus pe element, apoi tasta (sintaxa pywinauto: ^v, %{DOWN}, {TAB}, {ENTER})."""
        ctl = self.wait(spec)
        ctl.set_focus()
        keyboard.send_keys(keys)
        self.pause()
        return ctl

    def seteaza_text(self, spec, text: str):
        """Pune textul direct în câmp (UIA ValuePattern), fără tastatură - nu mută focusul și nu închide listele
        derulante; verifică valoarea și, dacă nu s-a scris, revine la clic + Ctrl+A + lipire din clipboard."""
        ctl = self.wait(spec)
        try:
            ctl.iface_value.SetValue(text)
            self.pause(0.5)
            if _normalizeaza(ctl.iface_value.CurrentValue) == _normalizeaza(text):
                return ctl
            log.debug("SetValue nu a scris textul complet în %s; lipesc din clipboard", describe(spec))
        except Exception as exc:  # noqa: BLE001 - câmpul nu expune ValuePattern
            log.debug("SetValue indisponibil pentru %s: %s", describe(spec), exc)
        ctl.click_input()
        pyperclip.copy(text)
        keyboard.send_keys("^a^v")
        self.pause()
        return ctl

    def paste_into(self, spec, text: str, select_all: bool = False):
        """SetToClipboard + Ctrl+V (robotul lipea din clipboard ca să păstreze diacriticele)."""
        pyperclip.copy(text)
        return self.hotkey(spec, "^a^v" if select_all else "^v")

    def exists(self, spec, timeout: float = 2) -> bool:
        try:
            return bool(spec.exists(timeout=timeout))
        except Exception:
            return False

    # ------------------------------------------------------------------ imagini
    def region_of(self, spec) -> Region:
        r = self.wait(spec).rectangle()
        return (r.left, r.top, r.width(), r.height())

    def click_image(self, names: Names, within=None, timeout: Optional[float] = None, fallback=None,
                    double: bool = False) -> None:
        """Click Image: caută șablonul în dreptunghiul controlului `within` (scope-ul din UiPath); la eșec dă click pe
        `fallback` (un selector), dacă este dat."""
        if fallback is not None and not self.imagini.enabled:
            self.click(fallback, double=double)  # imaginile sunt dezactivate (images.enabled: false)
            return
        region = self.region_of(within) if within is not None else None
        if timeout is None and fallback is not None:
            timeout = 2  # avem selector de rezervă: nu așteptăm imaginea tot timeout-ul implicit (10 s)
        try:
            self.imagini.click(names, region=region, timeout=timeout, double=double)
            self.pause()
        except ApplicationException:
            if fallback is None:
                raise
            log.debug("Imaginea %s nu a fost găsită; folosesc selectorul de rezervă", names)
            self.click(fallback, double=double)

    def click_ok(self, editor_spec) -> None:
        """Butonul OK din editoarele Risc/Control/Test - Click Image 'OK' în fereastra editorului."""
        self.click_image("ok", within=editor_spec,
                         fallback=editor_spec.child_window(title="OK", control_type="Button"))

    # ------------------------------------------------------------------ meniuri și liste
    def click_menu_item(self, name: str, owner_auto_id: Optional[str] = None,
                        keyboard_fallback: Iterable[str] = ()) -> None:
        """Alege un element din meniul pop-up 'DropDown' după nume; dacă nu îl găsește, folosește tastele robotului."""
        try:
            self.click(self.menu_item(name, owner_auto_id))
            return
        except ApplicationException:
            log.warning("Elementul de meniu '%s' nu a fost găsit. Ferestre deschise:\n%s", name, self.dump_windows())
            if not keyboard_fallback:
                raise
            log.debug("Trimit tastele de rezervă %s", list(keyboard_fallback))
            for k in keyboard_fallback:
                keyboard.send_keys(k)
                self.pause(0.5)

    def select_tree_item(self, tree_spec, name: str):
        """Selectează un nod dintr-un TreeView după nume (tolerant la spații, majuscule, diacritice și la
        wildcard-ul '*'), expandând părinții dacă e nevoie. Nodul poate fi în afara zonei vizibile (lista
        deschisă derulată): îl aducem întâi la vedere, apoi dăm clic; dacă tot nu e vizibil, îl selectăm prin
        SelectionItem, fără clic pe coordonate."""
        tree = self.wait(tree_spec)
        item = _cauta_in_arbore(tree, name)
        if item is None:
            # posibil nodurile nu sunt încă încărcate: expandăm tot și mai încercăm o dată
            for it in tree.descendants(control_type="TreeItem"):
                try:
                    it.expand()
                except Exception:  # noqa: BLE001
                    pass
            item = _cauta_in_arbore(tree, name)
        if item is None:
            nume = [it.window_text() for it in tree.descendants(control_type="TreeItem")[:30]]
            raise ApplicationException(f"Nu am găsit în listă '{name}'. Primele elemente din listă: {nume}")
        _expand_ancestors(item)
        self._alege_element(tree, item)
        return item

    def _alege_element(self, tree, item) -> None:
        try:
            item.iface_scroll_item.ScrollIntoView()  # derulează lista până la element
            time.sleep(1)  # lista are nevoie de ~1 s să încarce ce s-a derulat
        except Exception as exc:  # noqa: BLE001 - elementul nu expune ScrollItem
            log.debug("ScrollIntoView indisponibil pentru '%s': %s", item.window_text(), exc)
        if _vizibil_in(tree, item):
            item.click_input()
        else:
            log.info("'%s' nu este în zona vizibilă a listei; îl selectez fără clic", item.window_text())
            item.select()
            try:
                item.set_focus()
            except Exception:  # noqa: BLE001
                tree.set_focus()
        self.pause()
        log.info("Ales din listă: %s", item.window_text())

    def select_tree_path(self, tree, cale: Iterable[str], asteptare_copii: float = 5):
        """Selectează nodul de la capătul căii [proces, arie, sub-arie], coborând nivel cu nivel: fiecare nume se
        caută doar printre copiii direcți ai nodului anterior (un singur apel UIA pe nivel), nu în tot arborele.
        După expandare copiii pot apărea cu întârziere, deci îi mai citim până la `asteptare_copii` secunde."""
        cale = list(cale)
        radacina = tree.wrapper_object() if hasattr(tree, "wrapper_object") else tree
        nod = radacina
        for nume in cale:
            if nod is not radacina:
                try:
                    if not nod.is_expanded():
                        nod.expand()
                except Exception:  # noqa: BLE001 - nodul nu expune ExpandCollapse
                    pass
            deadline = time.monotonic() + asteptare_copii
            while True:
                copii = copii_cu_nume(nod)
                gasit = next((el for el, n in copii if _match(nume, n)), None)
                if gasit is None and not nume.endswith("*"):
                    gasit = next((el for el, n in copii if _match(nume + "*", n)), None)
                if gasit is not None or time.monotonic() >= deadline:
                    break
                time.sleep(0.3)
            if gasit is None:
                raise ApplicationException(
                    f"Nu am găsit '{nume}' sub '{nod.window_text() or 'rădăcina listei'}'; "
                    f"copii: {[n for _, n in copii[:15]]}"
                )
            nod = wrap(gasit)
        self._alege_element(radacina, nod)
        log.info("Selectat în arbore: %s", " > ".join(cale))
        return nod

    def dropdown_select(self, name: Optional[str], tree_auto_id: str = "DataListTreeControl") -> bool:
        """În DropDownComponentWindow: alege elementul cu numele dat; None/negăsit -> 'Selectare niciun element'."""
        dd = self.dropdown()
        tree = self.path(dd, "pnl_Content", tree_auto_id, "tv_Items")
        if name:
            try:
                self.select_tree_item(tree, name)
                return True
            except ApplicationException:
                log.warning("'%s' nu există în listă; aleg 'Selectare niciun element'", name)
        self.click_image(("selectare_niciun_element", "selectare_niciun_element_2"), within=dd,
                         fallback=self.path(dd, "pnl_Content", tree_auto_id, "tb_Main", "btn_SelectNone"))
        return False

    def bifeaza_element(self, tree_spec, name: str):
        """Bifează un element dintr-o listă cu căsuțe (Entități asociate, Tipuri audit conexate). Clicul pe text doar
        selectează rândul; bifa se pune cu Toggle sau, dacă elementul nu îl expune, cu SPACE pe rândul selectat.
        Dacă elementul este deja bifat nu se mai apasă nimic (SPACE l-ar debifa)."""
        item = self.select_tree_item(tree_spec, name)
        stare = stare_bifa(item)
        log.info("'%s' selectat; bifat: %s", name, text_bifa(stare))
        if stare == 1:
            return item
        try:
            item.toggle()
            self.pause()
            stare = stare_bifa(item)
            log.info("După Toggle: bifat %s", text_bifa(stare))
        except Exception:  # noqa: BLE001 - elementul nu expune Toggle
            stare = None
        if stare != 1:
            item.click_input()
            keyboard.send_keys("{SPACE}")
            self.pause()
            stare = stare_bifa(item)
            log.info("După SPACE: bifat %s", text_bifa(stare))
        if stare == 0:
            raise ApplicationException(f"Nu am reușit să bifez '{name}'")
        return item

    def dropdown_toggle(self, name: str, tree_auto_id: str = "DataListTreeControl") -> None:
        """Bifează un element dintr-o listă cu bife (ex. tehnici de testare)."""
        tree = self.path(self.dropdown(), "pnl_Content", tree_auto_id, "tv_Items")
        item = self.select_tree_item(tree, name)
        try:
            if item.get_toggle_state() == 0:  # clicul pe text nu a bifat
                item.toggle()
        except Exception:
            # controlul nu expune Toggle; robotul apăsa o tastă pe element (SpecialKey) - folosim SPACE
            keyboard.send_keys("{SPACE}")
        self.pause()


_STATE_SYSTEM_CHECKED = 0x10


def stare_bifa(item) -> Optional[int]:
    """Starea căsuței unui element: 1 bifat, 0 nebifat, None dacă nu se poate afla. Întâi Toggle (UIA), apoi
    starea MSAA (LegacyIAccessible) - controalele WinForms custom raportează bifa doar acolo."""
    try:
        return int(item.get_toggle_state())
    except Exception:  # noqa: BLE001 - elementul nu expune Toggle
        pass
    try:
        if int(item.legacy_properties().get("State", 0)) & _STATE_SYSTEM_CHECKED:
            return 1
    except Exception:  # noqa: BLE001
        pass
    return None  # starea MSAA fără bifă nu înseamnă sigur "nebifat" (poate controlul nu o raportează)


def text_bifa(stare: Optional[int]) -> str:
    return {1: "da", 0: "nu"}.get(stare, "necunoscut")


def describe(spec) -> str:
    """Lanțul de criterii al unui WindowSpecification, lizibil în log (ca un selector UiPath)."""
    try:
        parts = []
        for crit in spec.criteria:
            keep = {k: v for k, v in crit.items()
                    if k in ("auto_id", "title", "title_re", "control_type", "found_index", "class_name")}
            parts.append(" ".join(f"{k}={v!r}" for k, v in keep.items()) or str(crit))
        return " > ".join(parts)
    except Exception:  # noqa: BLE001
        return str(spec)


_DIACRITICE = str.maketrans({c: "." for c in "ăâîșşțţĂÂÎȘŞȚŢ"})


def _wild(name: str) -> str:
    """'Risc aferent ... si *' (wildcard UiPath) -> regex; diacriticele devin '.', ca să se potrivească
    și 'Adăugare' și 'Adaugare' (traducerile aplicației diferă între versiuni)."""
    parts = [re.escape(p).translate(_DIACRITICE) for p in name.split("*")]
    return "^" + ".*".join(parts) + ("" if name.endswith("*") else "$")


def _normalizeaza(text: str) -> str:
    """Fără diacritice, litere mici, spațiile multiple comprimate - pentru comparat nume din Excel cu cele din UI."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.split()).casefold()


def _match(pattern: str, text: str) -> bool:
    parts = [re.escape(_normalizeaza(p)) for p in pattern.split("*")]
    regex = "^" + ".*".join(parts) + ("" if pattern.endswith("*") else "$")
    return re.match(regex, _normalizeaza(text)) is not None


def _cauta_in_arbore(tree, name: str):
    """Primul TreeItem al cărui text se potrivește cu `name`; altfel primul care începe cu `name` (textul afișat
    poate avea un sufix, de ex. anul)."""
    items = tree.descendants(control_type="TreeItem")
    for item in items:
        if _match(name, item.window_text()):
            return item
    if not name.endswith("*"):
        for item in items:
            if _match(name + "*", item.window_text()):
                log.info("Potrivire după început: '%s' ~ '%s'", name, item.window_text())
                return item
    return None


def _vizibil_in(tree, item) -> bool:
    """Elementul este afișat în interiorul dreptunghiului listei (nu e derulat în afara ei)."""
    try:
        r, t = item.rectangle(), tree.rectangle()
        mijloc_y = (r.top + r.bottom) // 2
        return (not item.element_info.element.CurrentIsOffscreen and r.width() > 0
                and t.top <= mijloc_y <= t.bottom and t.left <= r.left + 5 <= t.right)
    except Exception:  # noqa: BLE001
        return False


def _expand_ancestors(item) -> None:
    try:
        parent = item.parent()
        while parent is not None and parent.element_info.control_type == "TreeItem":
            if not parent.is_expanded():
                parent.expand()
            parent = parent.parent()
    except Exception:
        pass
