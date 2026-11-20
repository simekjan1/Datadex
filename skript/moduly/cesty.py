from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, BinaryIO, Iterable


KOREN = Path(__file__).resolve().parents[2]
DATA = KOREN / "data"
ZDROJE = DATA / "1. txt a md soubory"
SYSTEM_DATA = DATA / "2. soubory pro skript"
JSON_DIR = SYSTEM_DATA / "json"
SABLONY = SYSTEM_DATA / "sablony"
OSTATNI = DATA / "ostatní"
WEB = KOREN / "web"
INTERNI = KOREN / "interni"
LOGY = INTERNI / "logy"
STAV = INTERNI / "stav"
DOCASNE = INTERNI / "docasne"
VELIKOST_BLOKU = 1024 * 1024


class BezpecnostniChyba(ValueError):
    pass


def je_uvnitr(cesta: Path, koren: Path, *, povolit_koren: bool = True) -> bool:
    try:
        cil = cesta.resolve(strict=False)
        zaklad = koren.resolve(strict=False)
        rel = cil.relative_to(zaklad)
        return povolit_koren or rel != Path(".")
    except (OSError, ValueError):
        return False


def over_uvnitr(cesta: Path, koren: Path, *, povolit_koren: bool = True) -> Path:
    if not je_uvnitr(cesta, koren, povolit_koren=povolit_koren):
        raise BezpecnostniChyba(f"Cesta opouští povolený kořen: {cesta}")
    return cesta


def bezpecne_spoj(koren: Path, relativni: str | Path) -> Path:
    rel = Path(relativni)
    if rel.is_absolute() or ".." in rel.parts:
        raise BezpecnostniChyba(f"Nepovolená relativní cesta: {relativni}")
    return over_uvnitr(koren / rel, koren)


def priprav_adresare() -> None:
    for cesta in (ZDROJE, JSON_DIR, SABLONY, OSTATNI, WEB, LOGY, STAV, DOCASNE):
        over_uvnitr(cesta, KOREN)
        cesta.mkdir(parents=True, exist_ok=True)


def _docasny_soubor(cil: Path) -> Path:
    token = hashlib.sha256(f"{os.getpid()}:{time.time_ns()}:{cil.name}".encode()).hexdigest()[:12]
    return cil.with_name(f".{cil.name}.{token}.tmp")


def _bezpecny_zdroj(cesta: Path, koren: Path) -> Path:
    over_uvnitr(cesta, koren)
    if cesta.is_symlink():
        raise BezpecnostniChyba(f"Symbolický odkaz nelze kopírovat: {cesta}")
    if not cesta.is_file():
        raise FileNotFoundError(f"Zdrojový soubor neexistuje: {cesta}")
    return cesta


def _zapis_bloky(zdroj: BinaryIO, cil: BinaryIO, *, velikost_bloku: int) -> None:
    if not 64 * 1024 <= velikost_bloku <= 8 * 1024 * 1024:
        raise ValueError("Velikost kopírovacího bloku musí být mezi 64 KiB a 8 MiB.")
    buffer = bytearray(velikost_bloku)
    pohled = memoryview(buffer)
    while True:
        pocet = zdroj.readinto(buffer)
        if not pocet:
            return
        cil.write(pohled[:pocet])


def atomicky_kopiruj(
    zdroj: Path,
    cil: Path,
    *,
    zdrojovy_koren: Path = KOREN,
    cilovy_koren: Path = KOREN,
    velikost_bloku: int = VELIKOST_BLOKU,
    pokusy: int = 3,
) -> None:
    """Bezpečně zkopíruje soubor s konstantní pamětí a zachováním starého cíle při chybě."""
    _bezpecny_zdroj(zdroj, zdrojovy_koren)
    over_uvnitr(cil, cilovy_koren)
    if cil.exists() and cil.is_symlink():
        raise BezpecnostniChyba(f"Cílem nesmí být symbolický odkaz: {cil}")
    cil.parent.mkdir(parents=True, exist_ok=True)
    docasny = _docasny_soubor(cil)
    over_uvnitr(docasny, cilovy_koren)
    try:
        with zdroj.open("rb", buffering=0) as vstup, docasny.open("xb", buffering=0) as vystup:
            _zapis_bloky(vstup, vystup, velikost_bloku=velikost_bloku)
            vystup.flush()
            os.fsync(vystup.fileno())
        posledni: OSError | None = None
        for cislo in range(pokusy):
            try:
                os.replace(docasny, cil)
                return
            except OSError as chyba:
                posledni = chyba
                if cislo + 1 < pokusy:
                    time.sleep(0.15)
        raise OSError(f"Soubor se nepodařilo bezpečně nahradit: {cil}: {posledni}")
    finally:
        try:
            if docasny.exists():
                docasny.unlink()
        except OSError:
            pass


def atomicky_zapis(cil: Path, obsah: str | bytes, *, encoding: str = "utf-8", pokusy: int = 3) -> None:
    over_uvnitr(cil, KOREN)
    cil.parent.mkdir(parents=True, exist_ok=True)
    docasny = _docasny_soubor(cil)
    over_uvnitr(docasny, KOREN)
    try:
        if isinstance(obsah, bytes):
            with docasny.open("wb") as soubor:
                soubor.write(obsah)
                soubor.flush()
                os.fsync(soubor.fileno())
        else:
            with docasny.open("w", encoding=encoding, newline="\n") as soubor:
                soubor.write(obsah)
                soubor.flush()
                os.fsync(soubor.fileno())
        posledni: OSError | None = None
        for cislo in range(pokusy):
            try:
                os.replace(docasny, cil)
                return
            except OSError as chyba:
                posledni = chyba
                if cislo + 1 < pokusy:
                    time.sleep(0.15)
        raise OSError(f"Soubor se nepodařilo bezpečně nahradit: {cil}: {posledni}")
    finally:
        try:
            if docasny.exists():
                docasny.unlink()
        except OSError:
            pass


def zapis_json(cil: Path, data: Any, *, zaloha: bool = True) -> None:
    over_uvnitr(cil, KOREN)
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    json.loads(text)
    if zaloha and cil.exists():
        zaloha_cesta = cil.with_suffix(cil.suffix + ".bak")
        atomicky_kopiruj(cil, zaloha_cesta)
    atomicky_zapis(cil, text)


def atomicky_zapis_json_pole(cil: Path, polozky: Iterable[Any], *, pokusy: int = 3) -> None:
    """Zapíše velké JSON pole po položkách, aniž by je drželo celé v paměti."""
    over_uvnitr(cil, KOREN)
    cil.parent.mkdir(parents=True, exist_ok=True)
    docasny = _docasny_soubor(cil)
    try:
        with docasny.open("x", encoding="utf-8", newline="\n") as soubor:
            soubor.write("[\n")
            prvni = True
            for polozka in polozky:
                if not prvni:
                    soubor.write(",\n")
                json.dump(polozka, soubor, ensure_ascii=False, separators=(",", ":"))
                prvni = False
            soubor.write("\n]\n")
            soubor.flush()
            os.fsync(soubor.fileno())
        posledni: OSError | None = None
        for cislo in range(pokusy):
            try:
                os.replace(docasny, cil)
                return
            except OSError as chyba:
                posledni = chyba
                if cislo + 1 < pokusy:
                    time.sleep(0.15)
        raise OSError(f"Soubor se nepodařilo bezpečně nahradit: {cil}: {posledni}")
    finally:
        try:
            if docasny.exists():
                docasny.unlink()
        except OSError:
            pass


def nacti_json(cesta: Path, ocekavany_typ: type) -> Any:
    over_uvnitr(cesta, KOREN)
    try:
        data = json.loads(cesta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (UnicodeError, json.JSONDecodeError) as chyba:
        raise ValueError(f"Poškozený JSON {cesta}: {chyba}") from chyba
    if not isinstance(data, ocekavany_typ):
        raise ValueError(f"JSON {cesta} má chybný kořenový typ; očekává se {ocekavany_typ.__name__}.")
    return data


def hash_souboru(cesta: Path) -> str:
    _bezpecny_zdroj(cesta, KOREN)
    h = hashlib.sha256()
    with cesta.open("rb") as soubor:
        for blok in iter(lambda: soubor.read(VELIKOST_BLOKU), b""):
            h.update(blok)
    return h.hexdigest()


def zapis_log(nazev: str, radky: list[str]) -> Path:
    priprav_adresare()
    cas = time.strftime("%Y-%m-%d_%H-%M-%S")
    cil = LOGY / f"{cas}_{nazev}.txt"
    if cil.exists():
        cil = LOGY / f"{cas}_{time.time_ns() % 1_000_000_000:09d}_{nazev}.txt"
    atomicky_zapis(cil, "\n".join(radky).rstrip() + "\n")
    return cil
