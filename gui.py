"""Aplicația cu fereastră (ImportTematica.exe): alegerea matricei și a pașilor, Start / Pauză / Oprește, logul în
timp real și rezumatul de la final.

- Robotul rulează pe un fir separat; fereastra rămâne activă.
- La Start fereastra se minimizează, ca să nu acopere Pentana (robotul dă clic în fereastra Pentana); reapare când
  robotul intră în pauză și la final.
- F9 = pauză / continuă, F10 = oprește - taste globale, merg și cu fereastra minimizată, fără a atinge mouse-ul.
- Pauza se face la următorul punct sigur (între pași), iar la reluare Pentana e readusă în față.

    python gui.py                 # din sursă
    ImportTematica.exe            # executabilul (vezi build_exe.bat)
    ImportTematica.exe --selftest # verificarea executabilului: scrie selftest.txt lângă .exe
"""
from __future__ import annotations

import ctypes
import logging
import os
import queue
import sys
import threading
from ctypes import wintypes
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from tematica.config import Config
from tematica.control import control
from tematica.framework import Framework
from tematica.logging_setup import _watchdog, setup_logging

TITLU = "Import Tematică în Pentana"
VK_F9, VK_F10, WM_HOTKEY, WM_QUIT = 0x78, 0x79, 0x0312, 0x0012


class TasteGlobale:
    """F9 / F10 înregistrate în Windows (RegisterHotKey) pe un fir propriu, cât timp rulează robotul."""

    def __init__(self, la_tasta):
        self.la_tasta = la_tasta
        self._fir: threading.Thread | None = None
        self._id_fir = 0

    def porneste(self) -> None:
        if self._fir is None:
            self._fir = threading.Thread(target=self._bucla, name="taste", daemon=True)
            self._fir.start()

    def opreste(self) -> None:
        if self._fir is not None and self._id_fir:
            ctypes.windll.user32.PostThreadMessageW(self._id_fir, WM_QUIT, 0, 0)
        self._fir = None

    def _bucla(self) -> None:
        user32 = ctypes.windll.user32
        self._id_fir = ctypes.windll.kernel32.GetCurrentThreadId()
        inregistrate = [i for i, vk in ((1, VK_F9), (2, VK_F10)) if user32.RegisterHotKey(None, i, 0, vk)]
        if len(inregistrate) < 2:
            logging.getLogger("tematica.gui").warning(
                "Tastele F9/F10 nu au putut fi înregistrate (folosite de alt program) - folosește butoanele")
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                self.la_tasta("F9" if msg.wParam == 1 else "F10")
        for i in inregistrate:
            user32.UnregisterHotKey(None, i)


class HandlerCoada(logging.Handler):
    """Trimite liniile de log în coada interfeței (Tk se actualizează doar din firul principal)."""

    def __init__(self, coada: "queue.Queue"):
        super().__init__(logging.INFO)
        self.coada = coada
        self.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        self.coada.put(("log", record.levelno, self.format(record)))


class Aplicatie:
    def __init__(self) -> None:
        self.cfg = Config.load()
        self.coada: "queue.Queue" = queue.Queue()
        self.fw: Framework | None = None
        self.fir: threading.Thread | None = None
        self.taste = TasteGlobale(lambda t: self.coada.put(("tasta", t)))
        control.la_schimbare = lambda: self.coada.put(("stare",))

        self.root = Tk()
        self.root.title(TITLU)
        self.root.geometry("980x640")
        self.root.minsize(760, 480)
        self.root.protocol("WM_DELETE_WINDOW", self._inchide)
        self._construieste()
        self.root.after(200, self._proceseaza_coada)

    # --- interfața ---------------------------------------------------------
    def _construieste(self) -> None:
        r = self.root
        cadru = ttk.Frame(r, padding=10)
        cadru.pack(fill="both", expand=True)

        f = ttk.LabelFrame(cadru, text="Matricea de importat", padding=8)
        f.pack(fill="x")
        self.fisier = StringVar(value=str(self.cfg.input_file))
        ttk.Entry(f, textvariable=self.fisier).pack(side="left", fill="x", expand=True)
        ttk.Button(f, text="Alege…", command=self._alege_fisier).pack(side="left", padx=(6, 0))

        p = ttk.LabelFrame(cadru, text="Pași", padding=8)
        p.pack(fill="x", pady=(8, 0))
        self.pas_univers = BooleanVar(value=not self.cfg.get("framework.sari_peste_univers", False))
        self.pas_riscuri = BooleanVar(value=True)
        self.pas_salvare = BooleanVar(value=True)
        self.atasare = BooleanVar(value=False)
        ttk.Checkbutton(p, text="Universul de procese", variable=self.pas_univers).pack(side="left")
        ttk.Checkbutton(p, text="Șablon (riscuri, controale, teste)", variable=self.pas_riscuri).pack(side="left", padx=12)
        ttk.Checkbutton(p, text="Salvare + copie de siguranță", variable=self.pas_salvare).pack(side="left")
        ttk.Checkbutton(p, text="Pe Pentana deja deschis", variable=self.atasare).pack(side="right")

        b = ttk.Frame(cadru)
        b.pack(fill="x", pady=8)
        self.btn_verifica = ttk.Button(b, text="Verifică matricea", command=lambda: self._start(dry_run=True))
        self.btn_start = ttk.Button(b, text="▶  Start", command=self._start)
        self.btn_pauza = ttk.Button(b, text="⏸  Pauză (F9)", command=self._comuta_pauza, state="disabled")
        self.btn_stop = ttk.Button(b, text="■  Oprește (F10)", command=self._opreste, state="disabled")
        for w in (self.btn_verifica, self.btn_start, self.btn_pauza, self.btn_stop):
            w.pack(side="left", padx=(0, 6))
        ttk.Button(b, text="Config", command=lambda: self._deschide(self.cfg.root / "config.yaml")).pack(side="right")
        ttk.Button(b, text="Loguri", command=lambda: self._deschide(self.cfg.path("paths.log_dir"))).pack(
            side="right", padx=6)

        s = ttk.Frame(cadru)
        s.pack(fill="x")
        self.stare = StringVar(value="Gata de pornire. Robotul lucrează singur în Pentana - nu folosi mouse-ul "
                                     "cât rulează; pentru pauză / oprire: F9 / F10.")
        ttk.Label(s, textvariable=self.stare).pack(side="left", fill="x", expand=True)
        self.progres = ttk.Progressbar(s, length=220, mode="determinate")
        self.progres.pack(side="right")

        self.log = ScrolledText(cadru, height=20, font=("Consolas", 9), state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, pady=(8, 0))
        self.log.tag_config("WARNING", foreground="#b35c00")
        self.log.tag_config("ERROR", foreground="#c00000")

    def _alege_fisier(self) -> None:
        cale = filedialog.askopenfilename(title="Matricea de importat", filetypes=[("Excel", "*.xlsx"), ("Toate", "*.*")],
                                          initialdir=str(Path(self.fisier.get()).parent))
        if cale:
            self.fisier.set(cale)

    @staticmethod
    def _deschide(cale: Path) -> None:
        cale.mkdir(parents=True, exist_ok=True) if cale.suffix == "" else None
        os.startfile(str(cale))

    def _scrie(self, text: str, nivel: int = logging.INFO) -> None:
        self.log.configure(state="normal")
        tag = "ERROR" if nivel >= logging.ERROR else "WARNING" if nivel >= logging.WARNING else ""
        self.log.insert("end", text + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    # --- rularea -------------------------------------------------------------
    def _start(self, dry_run: bool = False) -> None:
        if self.fir is not None and self.fir.is_alive():
            return
        pasi = [n for n, v in (("univers", self.pas_univers), ("riscuri", self.pas_riscuri),
                               ("salvare", self.pas_salvare)) if v.get()]
        if not pasi:
            messagebox.showwarning(TITLU, "Alege cel puțin un pas.")
            return
        fisier = Path(self.fisier.get())
        if not fisier.exists():
            messagebox.showerror(TITLU, f"Nu există fișierul:\n{fisier}")
            return
        control.reseteaza()
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.progres["value"] = 0
        self._butoane(ruleaza=True, dry_run=dry_run)
        self.stare.set("Verific matricea…" if dry_run else "Rulează… (F9 = pauză, F10 = oprește)")
        if not dry_run:
            self.taste.porneste()
            self.root.after(1500, self.root.iconify)  # nu acoperim Pentana
        self.fir = threading.Thread(target=self._ruleaza, args=(fisier, pasi, dry_run), name="robot", daemon=True)
        self.fir.start()

    def _ruleaza(self, fisier: Path, pasi, dry_run: bool) -> None:
        rezultat = 1
        try:
            self.cfg = Config.load()
            _watchdog.fir_urmarit = threading.get_ident()
            setup_logging(self.cfg.path("paths.log_dir"), self.cfg.get("framework.business_process_name", TITLU))
            logging.getLogger().addHandler(HandlerCoada(self.coada))
            self.fw = Framework(self.cfg, pasi=pasi, dry_run=dry_run, attach=self.atasare.get())
            rezultat = self.fw.run(fisier)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("tematica.gui").exception("Eroare neașteptată: %s", exc)
        finally:
            self.coada.put(("gata", rezultat, dry_run))

    def _comuta_pauza(self) -> None:
        if self.fir is None or not self.fir.is_alive() or control.oprire_ceruta:
            return
        if control.in_pauza or control.pauza_ceruta:
            control.continua()
            self.stare.set("Rulează… (F9 = pauză, F10 = oprește)")
            if control.in_pauza:
                self.root.iconify()  # robotul readuce Pentana în față și continuă
        else:
            control.cere_pauza()
            self.stare.set("Pauză cerută - robotul se oprește după pasul curent…")
        self._actualizeaza_pauza()

    def _opreste(self, confirma: bool = True) -> None:
        if self.fir is None or not self.fir.is_alive():
            return
        if confirma and not messagebox.askyesno(TITLU, "Oprești rularea? Pentana rămâne deschis cu ce s-a introdus "
                                                       "până acum."):
            return
        control.opreste()
        self.stare.set("Oprire cerută - se oprește după acțiunea curentă…")
        self._actualizeaza_pauza()

    def _butoane(self, ruleaza: bool, dry_run: bool = False) -> None:
        self.btn_start.configure(state="disabled" if ruleaza else "normal")
        self.btn_verifica.configure(state="disabled" if ruleaza else "normal")
        activ = "normal" if ruleaza and not dry_run else "disabled"
        self.btn_pauza.configure(state=activ)
        self.btn_stop.configure(state=activ)
        self._actualizeaza_pauza()

    def _actualizeaza_pauza(self) -> None:
        if control.in_pauza:
            self.btn_pauza.configure(text="▶  Continuă (F9)")
        elif control.pauza_ceruta:
            self.btn_pauza.configure(text="⏳ Pauză cerută… (F9 anulează)")
        else:
            self.btn_pauza.configure(text="⏸  Pauză (F9)")

    def _proceseaza_coada(self) -> None:
        try:
            while True:
                ev = self.coada.get_nowait()
                if ev[0] == "log":
                    self._scrie(ev[2], ev[1])
                elif ev[0] == "tasta":
                    self._comuta_pauza() if ev[1] == "F9" else self._opreste(confirma=False)
                elif ev[0] == "stare":
                    self._actualizeaza_pauza()
                    if control.in_pauza:
                        self.stare.set(f"ÎN PAUZĂ înainte de: {control.pas_curent}. Continuă (F9) sau Oprește (F10).")
                        self.root.deiconify()
                        self.root.lift()
                elif ev[0] == "gata":
                    self._la_final(ev[1], ev[2])
        except queue.Empty:
            pass
        self._actualizeaza_progres()
        self.root.after(200, self._proceseaza_coada)

    def _actualizeaza_progres(self) -> None:
        fw = self.fw
        if fw is None or fw.matrice is None or self.fir is None or not self.fir.is_alive():
            return
        total = len(fw.matrice.teste)
        facute = fw.riscuri.introduse["teste"] if fw.riscuri is not None else 0
        self.progres["maximum"] = max(total, 1)
        self.progres["value"] = facute
        if not control.in_pauza and not control.pauza_ceruta and not control.oprire_ceruta and control.pas_curent:
            self.stare.set(f"Teste {facute}/{total} - {control.pas_curent}   (F9 = pauză, F10 = oprește)")

    def _la_final(self, rezultat: int, dry_run: bool) -> None:
        self.taste.opreste()
        self._butoane(ruleaza=False)
        self.root.deiconify()
        self.root.lift()
        if dry_run:
            self.stare.set("Matricea a fost citită - vezi arborele mai sus." if rezultat == 0
                           else "Matricea nu a putut fi citită - vezi eroarea mai sus.")
            return
        self.stare.set({0: "Finalizat - vezi rezumatul la sfârșitul logului.",
                        2: "Oprit de utilizator - Pentana a rămas deschis."}.get(
            rezultat, "Eșuat - vezi eroarea și pachetul de diagnostic (Data/Exceptions_Screenshots)."))

    def _inchide(self) -> None:
        if self.fir is not None and self.fir.is_alive():
            if not messagebox.askyesno(TITLU, "Robotul încă rulează. Îl oprești și închizi aplicația?"):
                return
            control.opreste()
        self.taste.opreste()
        self.root.destroy()

    def ruleaza(self) -> None:
        self.root.mainloop()


def selftest() -> int:
    """Verificarea executabilului, fără Pentana: dependențele se încarcă, UIA și OCR funcționează. Scrie
    selftest.txt lângă ImportTematica.exe."""
    rezultate = []

    def pas(nume, functie):
        try:
            rezultate.append(f"OK    {nume}: {functie()}")
        except Exception as exc:  # noqa: BLE001
            rezultate.append(f"EROARE {nume}: {type(exc).__name__}: {exc}")

    cfg = Config.load()
    pas("config", lambda: f"{cfg.root}  template={cfg.get('pentana.template_name')}")
    pas("imagini", lambda: f"{len(list(cfg.path('images.dir').glob('*.png')))} fișiere png")

    def matrice():
        from tematica.matrice import citeste_matrice
        m = citeste_matrice(cfg.root / "Data" / "Input" / "MatriceDeIntrodus.exemplu.xlsx")
        return f"{len(m.teste)} teste citite din exemplu"
    pas("citire Excel", matrice)

    def uia():
        from tematica.pentana.fastspec import FastSpec, FereastraProces
        root = Tk()
        root.title("selftest-uia")
        ttk.Button(root, text="Buton test").pack()
        root.update()
        w = FastSpec(FereastraProces(os.getpid(), title="selftest-uia")).wrapper_object()
        n = len(w.descendants())
        root.destroy()
        return f"fereastra găsită, {n} elemente"
    pas("UI Automation (pywinauto)", uia)

    def ocr():
        from PIL import Image, ImageDraw
        from tematica.pentana.ocr import citeste_randuri
        img = Image.new("RGB", (360, 60), "white")
        ImageDraw.Draw(img).text((10, 15), "Antonella Maria Timis", fill="black", font_size=24)
        return repr([r.text for r in citeste_randuri(img)])
    pas("OCR Windows", ocr)

    import pyautogui  # noqa: F401 - încărcarea bibliotecii de clic / capturi
    rezultate.append("OK    pyautogui încărcat")
    (cfg.root / "selftest.txt").write_text("\n".join(rezultate) + "\n", encoding="utf-8")
    return 0 if all(r.startswith("OK") for r in rezultate) else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # coordonate reale pe ecranele cu scalare (125%)
    except Exception:  # noqa: BLE001
        pass
    Aplicatie().ruleaza()
