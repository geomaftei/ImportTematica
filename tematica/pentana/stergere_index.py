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
                app.pause(2)
            time.sleep(3)
            config_screen = app.screen("ConfigurationScreen", timeout=30)
            app.click(app.path(config_screen, "tb_Store", "btn_Section"))
            dd = app.dropdown()
            btn = app.path(dd, "pnl_Content", "ConfigurationMenu", "tbl_Layout", "btn_RiskProcesses")
            app.click(btn if app.exists(btn, timeout=3) else dd.child_window(title_re=r"^Proces\s*/\s*Aria.*"))

            log.info("Schimbare nume Proces: %s", proces)
            section = app.path(config_screen, "pnl_Sections", "RiskProcessSection", ("tbl_Layout", 0))
            app.select_tree_item(app.path(section, "pnl_Left", "tv_Universe"), proces)
            name = app.path(section, "pnl_Background", "pnl_Page", "c_Page", "pnl_Layout", "mp_Pages",
                            "mpp_Details", "tbl_Layout", "txt_Name")
            app.paste_into(name, proces, select_all=True)
            app.click(app.path(config_screen, "tb_Store", "btn_Submit"))
        app.close()
