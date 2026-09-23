"""Selector rapid, compatibil cu WindowSpecification din pywinauto (child_window / wait / exists / wrapper_object).

De ce: pywinauto rezolvă child_window(...) citind TOT subarborele (FindAll descendants) și filtrând apoi în Python,
cu mai multe apeluri între procese pentru fiecare element - chiar și cu depth=N. Sub ecranul de configurare se află
tv_Universe, cu sute de noduri, deci fiecare căutare dura 40-90 s.

Aici căutarea e în lățime (BFS), cu un singur apel UIA pe nod (FindAllBuildCache pe copiii direcți, cu proprietățile
necesare în cache), și NU coboară în arbori / liste / tabele (nodurile lor nu sunt niciodată ținta unui selector;
elementul Tree/List însuși poate fi găsit, doar conținutul lui nu e parcurs). Primul rezultat e cel mai apropiat
de părinte, ca la un selector UiPath cu <wnd ctrlname=... /> care sare peste niveluri.
"""
from __future__ import annotations

import re
import time
from collections import deque
from typing import Any, Dict, List, Optional

from pywinauto.controls.uiawrapper import UIAWrapper
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.timings import TimeoutError as PwTimeoutError
from pywinauto.uia_defines import IUIA
from pywinauto.uia_element_info import UIAElementInfo

# conținutul acestor controale nu se parcurge (tv_Universe are sute de noduri)
NU_COBORI = {"Tree", "TreeItem", "List", "ListItem", "DataGrid", "DataItem", "Table"}
MAX_NODURI = 5000
DEFAULT_TIMEOUT = 5.0

_CRITERII = {"auto_id", "title", "title_re", "control_type", "class_name", "class_name_re", "found_index",
             "depth", "visible_only"}


def _cache_request():
    u = IUIA()
    cr = u.iuia.CreateCacheRequest()
    d = u.UIA_dll
    for pid in (d.UIA_AutomationIdPropertyId, d.UIA_NamePropertyId, d.UIA_ControlTypePropertyId,
                d.UIA_ClassNamePropertyId, d.UIA_IsOffscreenPropertyId):
        cr.AddProperty(pid)
    return cr


def _element(obj):
    """IUIAutomationElement din wrapper / element_info / element."""
    if hasattr(obj, "element_info"):
        return obj.element_info.element
    if isinstance(obj, UIAElementInfo):
        return obj.element
    return obj


def wrap(elem) -> UIAWrapper:
    # UIAWrapper alege singur clasa specializată după tipul controlului (TreeItem, Button, ...)
    return UIAWrapper(UIAElementInfo(elem))


class _Potrivire:
    def __init__(self, criteria: Dict[str, Any]):
        unknown = set(criteria) - _CRITERII
        if unknown:
            raise TypeError(f"Criterii nesuportate de FastSpec: {sorted(unknown)}")
        self.auto_id = criteria.get("auto_id")
        self.title = criteria.get("title")
        self.title_re = re.compile(criteria["title_re"]) if criteria.get("title_re") else None
        self.control_type = criteria.get("control_type")
        self.class_name = criteria.get("class_name")
        self.class_name_re = re.compile(criteria["class_name_re"]) if criteria.get("class_name_re") else None
        self.visible_only = criteria.get("visible_only", True)
        self.depth = criteria.get("depth")
        self.found_index = criteria.get("found_index") or 0

    def __call__(self, el) -> bool:
        if self.auto_id is not None and (el.CachedAutomationId or "") != self.auto_id:
            return False
        name = el.CachedName or ""
        if self.title is not None and name != self.title:
            return False
        if self.title_re is not None and not self.title_re.match(name):
            return False
        if self.control_type is not None and \
                IUIA().known_control_type_ids.get(el.CachedControlType) != self.control_type:
            return False
        cls = el.CachedClassName or ""
        if self.class_name is not None and cls != self.class_name:
            return False
        if self.class_name_re is not None and not self.class_name_re.match(cls):
            return False
        if self.visible_only and el.CachedIsOffscreen:
            return False
        return True


def cauta(root, criteria: Dict[str, Any]):
    """O singură trecere BFS sub `root` (fără root). Întoarce IUIAutomationElement sau None."""
    u = IUIA()
    cr = _cache_request()
    potriveste = _Potrivire(criteria)
    gasite = 0
    coada = deque([(_element(root), 0)])
    vizitate = 0
    while coada and vizitate < MAX_NODURI:
        el, nivel = coada.popleft()
        vizitate += 1
        try:
            copii = el.FindAllBuildCache(u.tree_scope["children"], u.true_condition, cr)
        except Exception:  # noqa: BLE001 - elementul a dispărut între timp
            continue
        for i in range(copii.Length):
            c = copii.GetElement(i)
            try:
                if potriveste(c):
                    if gasite == potriveste.found_index:
                        return c
                    gasite += 1
                tip = IUIA().known_control_type_ids.get(c.CachedControlType)
            except Exception:  # noqa: BLE001
                continue
            if tip not in NU_COBORI and (potriveste.depth is None or nivel + 1 < potriveste.depth):
                coada.append((c, nivel + 1))
    return None


def arbore_controale(root, depth: int = 8) -> str:
    """Arborele de controale (ca UI Explorer) pentru pachetul de diagnostic: auto_id, nume, tip, clasă. Conținutul
    arborilor / listelor mari nu se listează (doar numărul de elemente), ca să rămână rapid și lizibil."""
    u = IUIA()
    cr = _cache_request()
    linii: List[str] = []

    def copii(el):
        arr = el.FindAllBuildCache(u.tree_scope["children"], u.true_condition, cr)
        return [arr.GetElement(i) for i in range(arr.Length)]

    def viziteaza(el, nivel: int) -> None:
        try:
            lista = copii(el)
        except Exception as exc:  # noqa: BLE001
            linii.append("  " * nivel + f"(eroare: {exc})")
            return
        for c in lista:
            tip = IUIA().known_control_type_ids.get(c.CachedControlType, str(c.CachedControlType))
            ascuns = " [offscreen]" if c.CachedIsOffscreen else ""
            linii.append("  " * nivel + f"{tip} auto_id={c.CachedAutomationId!r} name={c.CachedName!r} "
                                        f"class={c.CachedClassName!r}{ascuns}")
            if tip in NU_COBORI:
                try:
                    linii.append("  " * (nivel + 1) + f"... {len(copii(c))} elemente (neparcurse)")
                except Exception:  # noqa: BLE001
                    pass
            elif nivel + 1 < depth:
                viziteaza(c, nivel + 1)

    viziteaza(_element(root), 0)
    return "\n".join(linii)


def copii_cu_nume(parinte, control_type: Optional[str] = "TreeItem"):
    """Copiii direcți ai unui element, cu numele lor, dintr-un singur apel UIA: [(IUIAutomationElement, nume)].
    Mult mai rapid decât wrapper.children() pe liste cu sute de noduri."""
    u = IUIA()
    arr = _element(parinte).FindAllBuildCache(u.tree_scope["children"], u.true_condition, _cache_request())
    rezultat = []
    for i in range(arr.Length):
        c = arr.GetElement(i)
        if control_type is None or IUIA().known_control_type_ids.get(c.CachedControlType) == control_type:
            rezultat.append((c, c.CachedName or ""))
    return rezultat


class FastSpec:
    """Selector leneș: se rezolvă abia la wait()/exists()/wrapper_object(), de fiecare dată din nou (elementele
    WinForms pot fi recreate). `parent` poate fi alt FastSpec, un WindowSpecification pywinauto sau un wrapper."""

    def __init__(self, parent, criteria: Optional[Dict[str, Any]] = None):
        self.parent = parent
        self._criteria = dict(criteria or {})
        if self._criteria:
            _Potrivire(self._criteria)  # validează criteriile imediat

    # --- compatibilitate cu WindowSpecification ---------------------------
    @property
    def criteria(self) -> List[Dict[str, Any]]:
        parinte = getattr(self.parent, "criteria", None)
        if isinstance(parinte, list):
            baza = list(parinte)
        elif hasattr(self.parent, "element_info"):
            ei = self.parent.element_info
            baza = [{"auto_id": ei.automation_id, "title": ei.name}]
        else:
            baza = []
        return baza + ([self._criteria] if self._criteria else [])

    def child_window(self, **criteria) -> "FastSpec":
        return FastSpec(self, criteria)

    def _find_once(self):
        """Wrapper-ul elementului sau None (o singură încercare, fără așteptare)."""
        if isinstance(self.parent, FastSpec):
            p = self.parent._find_once()
            if p is None:
                return None
        elif hasattr(self.parent, "wrapper_object"):  # WindowSpecification pywinauto (fereastră de nivel superior)
            p = self._radacina()
            if p is None:
                return None
        else:
            p = self.parent
        if not self._criteria:
            return p
        el = cauta(p, self._criteria)
        return wrap(el) if el is not None else None

    def _radacina(self):
        """Fereastra de nivel superior (WindowSpecification pywinauto), memorată cât timp e încă validă
        (găsirea ei pe desktop costă ~0,4 s, iar fereastra principală e folosită la fiecare pas)."""
        w = self.__dict__.get("_root_cache")
        if w is not None:
            try:
                if w.element_info.element.CurrentProcessId and w.is_visible():
                    return w
            except Exception:  # noqa: BLE001 - fereastra a fost închisă
                pass
            self._root_cache = None
        try:
            # exists(timeout=0) = o singură încercare; wrapper_object() singur ar aștepta 5 s dacă lipsește
            if not self.parent.exists(timeout=0):
                return None
            w = self.parent.wrapper_object()
        except Exception:  # noqa: BLE001
            return None
        self._root_cache = w
        return w

    def find(self, timeout: Optional[float] = None):
        deadline = time.monotonic() + (DEFAULT_TIMEOUT if timeout is None else timeout)
        while True:
            w = self._find_once()
            if w is not None:
                return w
            if time.monotonic() >= deadline:
                raise ElementNotFoundError(str(self.criteria))
            time.sleep(0.2)

    def exists(self, timeout: Optional[float] = None, retry_interval: Optional[float] = None) -> bool:
        try:
            self.find(0 if timeout is None else timeout)
            return True
        except ElementNotFoundError:
            return False

    def wait(self, wait_for: str = "exists", timeout: Optional[float] = None, retry_interval: Optional[float] = None):
        conditii = wait_for.split()
        deadline = time.monotonic() + (DEFAULT_TIMEOUT if timeout is None else timeout)
        while True:
            w = self._find_once()
            if w is not None:
                try:
                    ok = (("visible" not in conditii or w.is_visible())
                          and ("enabled" not in conditii or w.is_enabled())
                          and ("ready" not in conditii or (w.is_visible() and w.is_enabled())))
                except Exception:  # noqa: BLE001 - elementul a dispărut între timp
                    ok = False
                if ok:
                    return w
            if time.monotonic() >= deadline:
                raise PwTimeoutError(f"{wait_for} nu s-a îndeplinit în {timeout}s pentru {self.criteria}")
            time.sleep(0.2)

    def wrapper_object(self):
        return self.find()

    def __getattr__(self, name):
        # metodele wrapper-ului (rectangle, close, set_focus, children, ...) direct pe selector, ca în pywinauto
        if name.startswith("_") or name in ("parent",):
            raise AttributeError(name)
        return getattr(self.wrapper_object(), name)

    def __repr__(self) -> str:
        return f"FastSpec({self.criteria})"
