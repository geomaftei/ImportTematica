"""StergereIndexProcese.xaml - rescrie numele proceselor în Universul de procese.

În Process.xaml acest pas era comentat (dezactivat); îl păstrăm pentru rulare manuală (`--only stergere`).
"""
from __future__ import annotations

import logging
import time
from typing import Iterable

from pywinauto import keyboard

from ..config import Config
from .app import PentanaApp

log = logging.getLogger("tematica.pentana.stergere")


class StergereIndexProcese:
    def __init__(self, app: PentanaApp, cfg: Config, procese: Iterable[str]):
        self.app = app
        self.cfg = cfg
        self.procese = list(procese)

    def ruleaza(self) -> None:
        app = self.app
        for proces in self.procese:
            app.wait(app.main).set_focus()
            for key in ("%i", "c", "c", "{ENTER}"):
                keyboard.send_keys(key)
                time.sleep(0.5)
            config_screen = app.window("ConfigurationScreen", timeout=30)
            app.click(config_screen.child_window(auto_id="btn_Section"))
            dd = app.dropdown()
            btn = dd.child_window(auto_id="btn_RiskProcesses")
            app.click(btn if app.exists(btn, timeout=3) else dd.child_window(title_re=r"^Proces\s*/\s*Aria.*"))

            log.info("Schimbare nume Proces: %s", proces)
            app.select_tree_item(config_screen.child_window(auto_id="tv_Universe"), proces)
            app.paste_into(config_screen.child_window(auto_id="txt_Name"), proces, select_all=True)
            app.click(config_screen.child_window(auto_id="btn_Submit"))
        app.close()
