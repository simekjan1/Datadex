from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .cesty import KOREN, ZDROJE, je_uvnitr, zapis_log
from .konfigurace import nacti_galerie, nacti_nastaveni, nacti_projekty, nacti_weby
from .markdown_bezpecny import preved_markdown
from .model import skenuj


def zkontroluj() -> tuple[list[str], Path]:
    zpravy: list[str] = []
    for funkce, nazev in ((nacti_nastaveni, "nastavení"), (nacti_projekty, "projekty"), (nacti_weby, "webové odkazy"), (nacti_galerie, "galerie")):
        try:
            funkce()
        except (ValueError, OSError) as chyba:
            zpravy.append(f"Chyba konfigurace {nazev}: {chyba}")
    sken = skenuj()
    zpravy.extend(f"Konflikt: {x}" for x in sken.konflikty)
    mapa = {d.zdroj.resolve(strict=False) for d in sken.dokumenty}
    for doc in sken.dokumenty:
        try:
            text = doc.zdroj.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as chyba:
            zpravy.append(f"Dokument nelze přečíst: {doc.rel}: {chyba}")
            continue
        if doc.zdroj.suffix.casefold() != ".md":
            continue
        vys = preved_markdown(text)
        for raw in vys.odkazy + vys.obrazky:
            raw = html.unescape(raw)
            if urlsplit(raw).scheme or raw.startswith("#"):
                continue
            cesta_text = unquote(raw.split("#", 1)[0].split("?", 1)[0])
            cil = (doc.zdroj.parent / cesta_text).resolve(strict=False)
            if not je_uvnitr(cil, KOREN):
                zpravy.append(f"Nepovolený odkaz: zdroj {doc.rel}, odkaz '{raw}', důvod: cíl opouští databázi.")
            elif not cil.exists():
                shody = [p for p in mapa if p.name.casefold() == Path(cesta_text).name.casefold()]
                navrh = f" Možný cíl: {shody[0]}" if len(shody) == 1 else (" Existuje více možných cílů." if len(shody) > 1 else "")
                zpravy.append(f"Neplatný odkaz: zdroj {doc.rel}, odkaz '{raw}', důvod: cíl neexistuje.{navrh}")
    for p in ZDROJE.rglob("*"):
        if p.is_symlink() and not je_uvnitr(p.resolve(strict=False), ZDROJE):
            zpravy.append(f"Nepovolený symbolický odkaz opouští zdroje: {p}")
    if not zpravy:
        zpravy.append("Kontrola dokončena: nebyly nalezeny žádné chyby ani varování.")
    log = zapis_log("kontrola", zpravy)
    return zpravy, log
