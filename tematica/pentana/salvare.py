"""SalvareCopieSiguranta.xaml - salvează și închide șablonul, apoi face o copie de siguranță."""
from __future__ import annotations

import logging

from ..config import Config
from .app import PentanaApp

log = logging.getLogger("tematica.pentana.salvare")


class SalvareCopieSiguranta:
    def __init__(self, app: PentanaApp, cfg: Config):
        self.app = app
        self.cfg = cfg

    def ruleaza(self) -> None:
        app = self.app
        designer = app.path(app.main, "pnl_Main", "AuditDesignSection", "_sectionArea", "WPTemplateDesigner2")
        # bara cu Salvare / Închidere e copil direct al c_Editor (mai adânc există alte tb_Main, ex. în RCMatrixEditor);
        # idx-ul din selectorul UiPath numără în toată fereastra, nu sub părinte, deci nu îl folosim
        editor = app.path(designer, "mp_Pages", "mpp_Editor", "c_Editor")
        toolbar = editor.child_window(auto_id="tb_Main", depth=1)
        app.click(toolbar.child_window(auto_id="btn_Save"))    # "Salvare"
        app.click(toolbar.child_window(auto_id="btn_Close"))   # "Inchidere"

        # "Copie de siguranta": lista de șabloane -> acțiunea din meniul UserActionsLayoutContainer -> Confirm
        templates = app.path(designer, "mp_Pages", "mpp_List", "lst_Templates")
        app.click(templates.child_window(title="Horizontal"))
        actions = app.path(app.dropdown(), "pnl_Content", "UserActionsLayoutContainer", "c_ActionSelect")
        app.click(actions)
        confirm = actions.child_window(title_re="^Confirm.*", control_type="Button")
        if app.exists(confirm, timeout=3):
            app.click(confirm)
        else:
            app.click(actions)  # robotul dădea al doilea click în același container
        log.info("Șablonul a fost salvat și s-a făcut copia de siguranță")
