"""Pauza / oprirea robotului (fără Pentana): un fir care trece prin puncte sigure, ca robotul."""
import threading
import time

import pytest

from tematica.control import Control, OprireCeruta


def _robot(ctrl: Control, pasi: list, rezultat: dict):
    try:
        for i in range(50):
            ctrl.punct_sigur(f"pasul {i}")
            pasi.append(i)
            ctrl.verifica()
            time.sleep(0.01)
        rezultat["stare"] = "terminat"
    except OprireCeruta:
        rezultat["stare"] = "oprit"


def test_pauza_si_continuare():
    ctrl, pasi, rezultat = Control(), [], {}
    fir = threading.Thread(target=_robot, args=(ctrl, pasi, rezultat))
    fir.start()
    time.sleep(0.05)
    ctrl.cere_pauza()
    time.sleep(0.1)
    assert ctrl.in_pauza
    facuti = len(pasi)
    time.sleep(0.1)
    assert len(pasi) == facuti  # în pauză nu se mai face nimic
    reluat = []
    ctrl.la_reluare = lambda: reluat.append(True)
    ctrl.continua()
    fir.join(2)
    assert rezultat["stare"] == "terminat" and len(pasi) == 50 and reluat == [True]


def test_oprire_din_pauza():
    ctrl, pasi, rezultat = Control(), [], {}
    fir = threading.Thread(target=_robot, args=(ctrl, pasi, rezultat))
    fir.start()
    ctrl.cere_pauza()
    time.sleep(0.1)
    ctrl.opreste()
    fir.join(2)
    assert rezultat["stare"] == "oprit" and len(pasi) < 50


def test_oprire_imediata():
    ctrl = Control()
    ctrl.opreste()
    with pytest.raises(OprireCeruta):
        ctrl.verifica()
