"""Încărcarea configurației (config.yaml) și a credențialelor.

Echivalentul InitAllSettings.xaml: în UiPath se citeau foile Settings/Constants din Config.xlsx
și Assets din Orchestrator. Aici totul vine din config.yaml, iar parolele din variabile de mediu,
fișier .env sau Windows Credential Manager (keyring).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv


def radacina() -> Path:
    """Folderul proiectului; în executabil (PyInstaller), folderul în care stă ImportTematica.exe."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


@dataclass
class Credential:
    username: str
    password: str


class Config:
    def __init__(self, data: Dict[str, Any], root: Path):
        self._data = data
        self.root = root

    @classmethod
    def load(cls, path: Optional[str] = None) -> "Config":
        root = radacina()
        cfg_path = Path(path) if path else root / "config.yaml"
        with open(cfg_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        load_dotenv(root / ".env")
        return cls(data, root)

    # --- acces generic --------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def __getitem__(self, dotted: str) -> Any:
        value = self.get(dotted, None)
        if value is None:
            raise KeyError(f"Lipsește cheia de configurare '{dotted}' din config.yaml")
        return value

    # --- căi -----------------------------------------------------------
    def path(self, dotted: str) -> Path:
        p = Path(self[dotted])
        return p if p.is_absolute() else self.root / p

    @property
    def input_file(self) -> Path:
        """MatriceDeIntrodus.xlsx din folderul de proiect (sau calea absolută din config)."""
        return self.path("paths.input_file")

    # --- credențiale ----------------------------------------------------
    def credential(self, env_prefix: str) -> Credential:
        """Caută USER/PASSWORD în variabile de mediu, apoi în keyring."""
        user = os.environ.get(f"{env_prefix}_USER")
        password = os.environ.get(f"{env_prefix}_PASSWORD")
        if not (user and password):
            try:
                import keyring

                service = self.get("credentials.keyring_service", "IntroducereTematica")
                user = user or keyring.get_password(service, f"{env_prefix}_USER")
                if user:
                    password = password or keyring.get_password(service, user)
            except Exception:  # keyring indisponibil
                pass
        if not (user and password):
            raise RuntimeError(
                f"Lipsesc credențialele {env_prefix}_USER / {env_prefix}_PASSWORD "
                "(variabile de mediu, .env sau keyring)."
            )
        return Credential(user, password)

    @property
    def pentana_credential(self) -> Credential:
        return self.credential(self.get("credentials.pentana_env_prefix", "PENTANA"))
