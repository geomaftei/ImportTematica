"""Recunoaștere de imagine - echivalentul activității "Click Image" din UiPath.

Șabloanele din Data/Images sunt exact imaginile pe care le căuta robotul (TargetImageBase64 din .xaml, Accuracy 0.8).
`region` limitează căutarea la dreptunghiul unui control (scope-ul din selectorul UiPath), ca să nu nimerim, de
exemplu, alt câmp "< None >" de pe același formular.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Iterable, Optional, Tuple, Union

import pyautogui

from ..config import Config
from ..exceptions import ApplicationException

log = logging.getLogger("tematica.pentana.images")

Region = Tuple[int, int, int, int]  # left, top, width, height
Names = Union[str, Iterable[str]]

pyautogui.FAILSAFE = False  # robotul nu se oprea când mouse-ul ajungea în colț


class Imagini:
    def __init__(self, cfg: Config):
        self.dir: Path = cfg.path("images.dir")
        self.confidence: float = float(cfg.get("images.confidence", 0.8))
        self.timeout: float = float(cfg.get("images.timeout_s", 10))

    def cale(self, name: str) -> Path:
        p = self.dir / f"{name}.png"
        if not p.exists():
            raise ApplicationException(f"Lipsește șablonul de imagine {p}")
        return p

    def gaseste(self, names: Names, region: Optional[Region] = None, timeout: Optional[float] = None):
        """Caută (până la timeout) oricare dintre imaginile date; întoarce (nume, Box) sau None."""
        names = [names] if isinstance(names, str) else list(names)
        paths = [(n, str(self.cale(n))) for n in names]
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while True:
            for name, path in paths:
                try:
                    box = pyautogui.locateOnScreen(path, confidence=self.confidence, region=region, grayscale=False)
                except pyautogui.ImageNotFoundException:  # pyautogui >= 0.9.54 ridică excepție
                    box = None
                if box is not None:
                    return name, box
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.5)

    def click(self, names: Names, region: Optional[Region] = None, timeout: Optional[float] = None,
              double: bool = False) -> Tuple[int, int]:
        found = self.gaseste(names, region, timeout)
        if found is None:
            raise ApplicationException(f"Nu am găsit pe ecran imaginea {names} (region={region})")
        name, box = found
        x, y = pyautogui.center(box)
        log.debug("Click Image '%s' la (%d, %d)", name, x, y)
        pyautogui.click(x, y, clicks=2 if double else 1, interval=0.1)
        return int(x), int(y)
