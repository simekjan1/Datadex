from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from .cesty import INTERNI, KOREN, WEB, atomicky_kopiruj, je_uvnitr, nacti_json, over_uvnitr, zapis_json
from .model import OBRAZKY, razeni


@dataclass
class Obrazek:
    zdroj: Path
    rel_v_prilohach: Path
    verejna_rel: Path
    popis: str
    zobrazit: bool


@dataclass
class SkupinaGalerie:
    nazev: str
    klic: str
    obrazky: list[Obrazek]


def je_podporovany_obrazek(cesta: Path) -> bool:
    if cesta.suffix.casefold() not in OBRAZKY or not cesta.is_file() or cesta.is_symlink():
        return False
    try:
        with cesta.open("rb") as soubor:
            hlavicka = soubor.read(16)
        ext = cesta.suffix.casefold()
        if ext in {".jpg", ".jpeg"}:
            return hlavicka.startswith(b"\xff\xd8\xff")
        if ext == ".png":
            return hlavicka.startswith(b"\x89PNG\r\n\x1a\n")
        if ext == ".gif":
            return hlavicka.startswith((b"GIF87a", b"GIF89a"))
        if ext == ".webp":
            return hlavicka.startswith(b"RIFF") and hlavicka[8:12] == b"WEBP"
        return False
    except OSError:
        return False


def vychozi_popis(nazev: str) -> str:
    return Path(nazev).stem.replace("_", " ").replace("-", " ").strip().capitalize() or nazev


def _zaloha_popisku(cesta: Path) -> None:
    if not cesta.exists():
        return
    rel = cesta.parent.relative_to(KOREN)
    klic = hashlib.sha256(rel.as_posix().encode()).hexdigest()[:16]
    cil_dir = INTERNI / "zalohy_popisku" / klic
    cil_dir.mkdir(parents=True, exist_ok=True)
    cil = cil_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns()}.json"
    atomicky_kopiruj(cesta, cil)


def aktualizuj_popisky(slozka: Path, obrazky: list[Path], varovani: list[str]) -> dict[str, dict]:
    over_uvnitr(slozka, KOREN)
    cesta = slozka / "popisky.json"
    existoval = cesta.exists()
    if existoval:
        try:
            data = nacti_json(cesta, dict)
        except (ValueError, OSError) as chyba:
            varovani.append(f"Popisky nebyly změněny, soubor je poškozený: {cesta}: {chyba}")
            return {p.name: {"popis": vychozi_popis(p.name), "zobrazit": False} for p in obrazky}
    else:
        data = {}
    zmena = False
    for obrazek in obrazky:
        polozka = data.get(obrazek.name)
        if polozka is None:
            data[obrazek.name] = {"popis": vychozi_popis(obrazek.name), "zobrazit": True}
            zmena = True
        elif not isinstance(polozka, dict) or not isinstance(polozka.get("popis"), str) or not isinstance(polozka.get("zobrazit"), bool):
            varovani.append(f"Neplatná položka '{obrazek.name}' v {cesta}; obrázek nebude automaticky publikován.")
            data[obrazek.name] = {"popis": vychozi_popis(obrazek.name), "zobrazit": False}
    if zmena or not existoval:
        if existoval:
            _zaloha_popisku(cesta)
        zapis_json(cesta, data, zaloha=False)
    return data


def uloz_popisky(cesta: Path, data: dict[str, dict]) -> None:
    over_uvnitr(cesta, KOREN)
    if cesta.name.casefold() != "popisky.json" or not isinstance(data, dict):
        raise ValueError("Neplatný soubor nebo obsah popisků.")
    for nazev, polozka in data.items():
        if not isinstance(nazev, str) or not isinstance(polozka, dict) or not isinstance(polozka.get("popis"), str) or not isinstance(polozka.get("zobrazit"), bool):
            raise ValueError(f"Neplatná položka popisku: {nazev}")
    if cesta.exists():
        _zaloha_popisku(cesta)
    zapis_json(cesta, data, zaloha=False)


def dostupne_zalohy_popisku(cesta: Path) -> list[Path]:
    over_uvnitr(cesta, KOREN)
    rel = cesta.parent.relative_to(KOREN)
    klic = hashlib.sha256(rel.as_posix().encode()).hexdigest()[:16]
    adresar = INTERNI / "zalohy_popisku" / klic
    if not adresar.exists():
        return []
    platne: list[Path] = []
    for zaloha in sorted(adresar.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = nacti_json(zaloha, dict)
            for nazev, polozka in data.items():
                if not isinstance(nazev, str) or not isinstance(polozka, dict) or not isinstance(polozka.get("popis"), str) or not isinstance(polozka.get("zobrazit"), bool):
                    raise ValueError("Neplatná položka")
            platne.append(zaloha)
        except (ValueError, OSError):
            continue
    return platne


def obnov_popisky(cesta: Path, zaloha: Path) -> None:
    over_uvnitr(cesta, KOREN)
    if zaloha not in dostupne_zalohy_popisku(cesta):
        raise ValueError("Vybraná záloha není platná záloha tohoto souboru popisků.")
    if cesta.exists():
        _zaloha_popisku(cesta)
    atomicky_kopiruj(zaloha, cesta)


def priprav_galerie(priloha: Path, doc_id: str, explicitni: set[Path], povoleno: bool, varovani: list[str]) -> tuple[list[SkupinaGalerie], dict[Path, Path]]:
    skupiny: list[SkupinaGalerie] = []
    publikovane: dict[Path, Path] = {}
    if not priloha or not priloha.is_dir() or not je_uvnitr(priloha, KOREN):
        return skupiny, publikovane
    podle_slozky: dict[Path, list[Path]] = {}
    for cesta in sorted(priloha.rglob("*"), key=lambda p: razeni(p.as_posix())):
        if je_podporovany_obrazek(cesta):
            podle_slozky.setdefault(cesta.parent, []).append(cesta)
    for slozka, obrazky in sorted(podle_slozky.items(), key=lambda x: razeni(x[0].as_posix())):
        popisky = aktualizuj_popisky(slozka, obrazky, varovani)
        rel_slozka = slozka.relative_to(priloha)
        nazev = "Ostatní obrázky" if rel_slozka == Path(".") else rel_slozka.as_posix().replace("/", " / ")
        polozky: list[Obrazek] = []
        for cesta in obrazky:
            rel = cesta.relative_to(priloha)
            nast = popisky.get(cesta.name, {})
            je_explicitni = rel in explicitni
            zobrazit = bool(nast.get("zobrazit", False))
            if not je_explicitni and (not povoleno or not zobrazit):
                continue
            verejna = Path("media") / doc_id / rel
            cil = WEB / verejna
            cil.parent.mkdir(parents=True, exist_ok=True)
            atomicky_kopiruj(cesta, cil, cilovy_koren=WEB)
            publikovane[rel] = verejna
            if povoleno and zobrazit and not je_explicitni:
                polozky.append(Obrazek(cesta, rel, verejna, str(nast.get("popis", vychozi_popis(cesta.name))), True))
        if polozky:
            skupiny.append(SkupinaGalerie(nazev, hashlib.sha256((doc_id + rel_slozka.as_posix()).encode()).hexdigest()[:12], polozky))
    return skupiny, publikovane


def kopiruj_prilohu(zdroj: Path, verejna_rel: Path) -> None:
    if zdroj.is_symlink() or not je_uvnitr(zdroj, KOREN):
        raise ValueError(f"Nepovolená příloha: {zdroj}")
    cil = WEB / verejna_rel
    over_uvnitr(cil, WEB)
    atomicky_kopiruj(zdroj, cil, cilovy_koren=WEB)
