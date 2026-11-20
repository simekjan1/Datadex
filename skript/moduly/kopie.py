from __future__ import annotations

import os
import re
import shutil
import time
import uuid
from pathlib import Path

from .cesty import KOREN, atomicky_kopiruj, je_uvnitr
from .konfigurace import vytvor_vychozi_json_v


POVOLENE_SOUBORY = [
    Path("Spustit.bat"), Path("README.md"), Path("instalovat.py"), Path("requirements.lock"), Path("skript/cms.py"),
    *[Path("skript/moduly") / jmeno for jmeno in (
        "__init__.py", "cesty.py", "konfigurace.py", "markdown_bezpecny.py", "model.py",
        "galerie.py", "prevod.py", "server.py", "kontrola.py", "kopie.py", "menu.py",
    )],
    *[Path("data/2. soubory pro skript/sablony") / jmeno for jmeno in ("zaklad.html", "style.css", "app.js", "search.js")],
]


def vytvor_cistou_kopii(nazev: str, *, cilovy_rodic: Path | None = None, testovaci_rezim: bool = False) -> Path:
    nazev = nazev.strip()
    if not nazev or nazev in {".", ".."} or re.search(r'[<>:"/\\|?*\x00-\x1f]', nazev):
        raise ValueError("Název nové složky je prázdný nebo obsahuje nepovolené znaky.")
    rodic = cilovy_rodic.resolve(strict=False) if cilovy_rodic else KOREN.parent.resolve(strict=False)
    if testovaci_rezim:
        if not je_uvnitr(rodic, KOREN):
            raise ValueError("Testovací kopie musí zůstat uvnitř pracovního kořene.")
    elif rodic != KOREN.parent.resolve(strict=False):
        raise ValueError("Čistou kopii lze vytvořit pouze vedle aktuální databáze.")
    cil = rodic / nazev
    if cil.exists():
        raise FileExistsError(f"Cílová složka již existuje: {cil}")
    staging = rodic / f".{nazev}.priprava-{uuid.uuid4().hex[:10]}"
    if staging.exists():
        raise FileExistsError("Dočasná cílová složka neočekávaně existuje.")
    try:
        staging.mkdir(parents=False)
        for rel in POVOLENE_SOUBORY:
            src = KOREN / rel
            if src.is_file():
                if src.is_symlink():
                    raise ValueError(f"Programový soubor je symbolický odkaz a nebude kopírován: {rel}")
                dst = staging / rel; dst.parent.mkdir(parents=True, exist_ok=True); atomicky_kopiruj(src, dst, zdrojovy_koren=KOREN, cilovy_koren=staging)
        for rel in (Path("data/1. txt a md soubory"), Path("data/ostatní"), Path("web"), Path("interni/logy"), Path("interni/stav"), Path("interni/docasne")):
            (staging / rel).mkdir(parents=True, exist_ok=True)
        vytvor_vychozi_json_v(staging / "data/2. soubory pro skript/json", pruvodce_dokoncen=False)
        uvod = staging / "data/2. soubory pro skript/uvod.md"
        with uvod.open("x", encoding="utf-8", newline="\n") as f:
            f.write("# Vítejte ve znalostní databázi\n\nVložte dokumenty do zdrojové složky a spusťte převod.\n")
        instrukce = staging / "data/2. soubory pro skript/json/instrukce.md"
        with instrukce.open("x", encoding="utf-8", newline="\n") as f:
            f.write("# Interní instrukce\n\nTento soubor se na webu nepublikuje.\n")
        posledni = None
        for cislo in range(3):
            try:
                os.replace(staging, cil)
                posledni = None
                break
            except OSError as chyba:
                posledni = chyba
                if cislo < 2:
                    time.sleep(0.15)
        if posledni is not None:
            raise OSError(f"Čistou kopii se nepodařilo bezpečně dokončit: {posledni}")
        return cil
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
