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
from typing import Iterable, Optional, Tuple, Union

import pyperclip
from pywinauto import Application, Desktop, keyboard
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.timings import TimeoutError as PwTimeoutError

from ..config import Config
from ..exceptions import ApplicationException
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
        # "Delay logare in aplicatie": așteptăm până se încarcă meniul din stânga sau apare panoul de login,
        # cel mult login_delay_s
        deadline = time.monotonic() + float(self.cfg.get("pentana.login_delay_s", 12))
        while time.monotonic() < deadline:
            if self._login_visible():
                self.login()
                break
            if self.exists(self.main.child_window(auto_id="pnl_SectionMenu"), timeout=1):
                break
        log.info("Pentana este pornită")
        return self

    def attach(self) -> "PentanaApp":
        """Se leagă de o instanță Pentana deja deschisă (util la depanare)."""
        self.app = Application(backend="uia").connect(path=self.exe, timeout=self.timeout)
        self.main.wait("exists visible", timeout=self.timeout)
        log.info("M-am atașat la instanța Pentana existentă")
        return self

    def _login_visible(self) -> bool:
        try:
            return self.main.child_window(auto_id="pnl_Login").exists(timeout=1)
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
        return self.app.window(auto_id=self.main_id)

    def _resolve(self, timeout: Optional[float] = None, **criteria):
        """Găsește o fereastră/un panou după criterii (auto_id=..., title=...), căutând pe rând:
        fereastră de nivel superior a procesului, fereastră pe desktop aparținând procesului (pop-up-uri),
        copil al ferestrei principale (ecranele Pentana sunt panouri în MKInsightMainUI)."""
        assert self.app is not None
        candidates = [
            self.app.window(**criteria),
            Desktop(backend="uia").window(process=self.app.process, **criteria),
        ]
        if criteria.get("auto_id") != self.main_id:
            candidates.append(self.main.child_window(**criteria))
        # locul în care am găsit ultima dată fereastra se încearcă primul (economisește scanări)
        key = tuple(sorted(criteria.items()))
        order = list(range(len(candidates)))
        if key in self._unde_gasit:
            order.remove(self._unde_gasit[key])
            order.insert(0, self._unde_gasit[key])
        deadline = time.monotonic() + (timeout or self.timeout)
        while True:
            for i in order:
                if self.exists(candidates[i], timeout=0.5):
                    if self._unde_gasit.get(key) != i:
                        log.debug("Fereastra %s găsită ca %s", criteria,
                                  ("fereastră a procesului", "fereastră pe desktop", "copil al ferestrei principale")[i])
                        self._unde_gasit[key] = i
                    return candidates[i]
            if time.monotonic() >= deadline:
                raise ApplicationException(
                    f"Nu am găsit fereastra {criteria} în {timeout or self.timeout}s. Ferestre deschise:\n"
                    + self.dump_windows()
                )

    def window(self, auto_id: str, timeout: Optional[float] = None):
        """O fereastră a aplicației după auto_id (editoare, DropDownComponentWindow, ConfigurationScreen...)."""
        return self._resolve(timeout, auto_id=auto_id)

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
        region = self.region_of(within) if within is not None else None
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
        """Selectează un nod dintr-un TreeView după nume, expandând părinții dacă e nevoie."""
        tree = self.wait(tree_spec)
        for item in tree.descendants(control_type="TreeItem"):
            if _match(name, item.window_text()):
                _expand_ancestors(item)
                item.click_input()
                self.pause()
                return item
        # posibil nodurile nu sunt încă încărcate: expandăm tot și mai încercăm o dată
        for item in tree.descendants(control_type="TreeItem"):
            try:
                item.expand()
            except Exception:
                pass
        for item in tree.descendants(control_type="TreeItem"):
            if _match(name, item.window_text()):
                item.click_input()
                self.pause()
                return item
        raise ApplicationException(f"Nu am găsit în arbore nodul '{name}'")

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


def _match(pattern: str, text: str) -> bool:
    return re.match(_wild(pattern), (text or "").strip(), flags=re.IGNORECASE) is not None


def _expand_ancestors(item) -> None:
    try:
        parent = item.parent()
        while parent is not None and parent.element_info.control_type == "TreeItem":
            if not parent.is_expanded():
                parent.expand()
            parent = parent.parent()
    except Exception:
        pass
