"""Recunoașterea textului de pe ecran cu motorul OCR inclus în Windows 10/11 (Windows.Media.Ocr, prin pachetele
winrt-*). Folosit pentru listele pe care Pentana le desenează singură, fără elemente UIA (ex. lista de utilizatori
din "ResponsabilTest:"): citim rândurile și pozițiile lor, apoi dăm clic la coordonate.
"""
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PIL import Image, ImageGrab

# textul mic se recunoaște mult mai bine mărit
MARIRE = 2


@dataclass
class RandText:
    text: str
    left: int
    top: int
    right: int
    bottom: int

    @property
    def centru_y(self) -> int:
        return (self.top + self.bottom) // 2


def _motor(limba: Optional[str] = None):
    from winrt.windows.globalization import Language
    from winrt.windows.media.ocr import OcrEngine

    if limba:
        motor = OcrEngine.try_create_from_language(Language(limba))
        if motor is not None:
            return motor
    motor = OcrEngine.try_create_from_user_profile_languages()
    if motor is None:
        raise RuntimeError("Motorul OCR din Windows nu este disponibil (lipsește pachetul de limbă?)")
    return motor


async def _recunoaste_async(png: bytes, limba: Optional[str]):
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(png)
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    return await _motor(limba).recognize_async(bitmap)


def citeste_randuri(imagine: Image.Image, limba: Optional[str] = "ro-RO") -> List[RandText]:
    """Rândurile de text din imagine, cu dreptunghiul fiecăruia (în pixelii imaginii originale)."""
    mare = imagine.convert("RGB").resize((imagine.width * MARIRE, imagine.height * MARIRE), Image.LANCZOS)
    buf = io.BytesIO()
    mare.save(buf, format="PNG")
    rezultat = asyncio.run(_recunoaste_async(buf.getvalue(), limba))
    randuri = []
    for linie in rezultat.lines:
        cuvinte = list(linie.words)
        if not cuvinte:
            continue
        r = [c.bounding_rect for c in cuvinte]
        randuri.append(RandText(
            text=" ".join(c.text for c in cuvinte),
            left=int(min(x.x for x in r) / MARIRE), top=int(min(x.y for x in r) / MARIRE),
            right=int(max(x.x + x.width for x in r) / MARIRE), bottom=int(max(x.y + x.height for x in r) / MARIRE),
        ))
    return randuri


def citeste_ecran(zona: Tuple[int, int, int, int], limba: Optional[str] = "ro-RO") -> List[RandText]:
    """zona = (left, top, right, bottom) pe ecran; coordonatele rândurilor sunt tot pe ecran."""
    imagine = ImageGrab.grab(bbox=zona, all_screens=True)
    randuri = citeste_randuri(imagine, limba)
    for r in randuri:
        r.left += zona[0]
        r.right += zona[0]
        r.top += zona[1]
        r.bottom += zona[1]
    return randuri
