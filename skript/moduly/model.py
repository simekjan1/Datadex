from __future__ import annotations

import hashlib
import locale
from dataclasses import dataclass, field
from pathlib import Path

from .cesty import OSTATNI, ZDROJE, je_uvnitr


TEXTOVE = {".md", ".txt"}
OBRAZKY = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
BEZPECNE_SOUBORY = {
    ".pdf", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".rtf",
    ".csv", ".tsv", ".zip", ".7z", ".rar", ".txt", ".md",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp3", ".wav", ".ogg", ".mp4", ".webm",
}
NEPUBLIKOVAT = {"popisky.json"}


def stabilni_id(rel: Path, prefix: str = "p") -> str:
    return f"{prefix}-{hashlib.sha256(rel.as_posix().encode('utf-8')).hexdigest()[:16]}"


def lidsky_nazev(cesta: Path) -> str:
    return cesta.stem.replace("_", " ").strip() or cesta.name


def razeni(text: str) -> str:
    try:
        locale.setlocale(locale.LC_COLLATE, "Czech_Czechia.utf8")
        return locale.strxfrm(text.casefold())
    except locale.Error:
        return text.casefold()


@dataclass
class Dokument:
    zdroj: Path
    rel: Path
    nazev: str
    id: str
    vystup_rel: Path
    priloha_slozka: Path | None = None


@dataclass
class SamostatnySoubor:
    zdroj: Path
    rel: Path
    nazev: str
    id: str
    knihovna: bool = False


@dataclass
class Sken:
    dokumenty: list[Dokument] = field(default_factory=list)
    soubory: list[SamostatnySoubor] = field(default_factory=list)
    slozky: set[Path] = field(default_factory=lambda: {Path(".")})
    konflikty: list[str] = field(default_factory=list)
    uplny: bool = True


def _skenuj_koren(koren: Path, *, knihovna: bool, sken: Sken) -> None:
    try:
        vse = sorted(koren.rglob("*"), key=lambda p: razeni(p.as_posix()))
    except OSError as chyba:
        sken.uplny = False
        sken.konflikty.append(f"Kořen nelze úplně prohledat: {koren}: {chyba}")
        return
    if any(p.is_symlink() and not je_uvnitr(p.resolve(strict=False), koren) for p in vse):
        sken.konflikty.append(f"Některý symbolický odkaz opouští zdrojový kořen {koren}; byl přeskočen.")
    dokumenty = [p for p in vse if p.is_file() and not p.is_symlink() and p.suffix.casefold() in TEXTOVE]
    attachment_dirs: set[Path] = set()
    podle_klice: dict[tuple[Path, str], list[Path]] = {}
    for doc in dokumenty:
        podle_klice.setdefault((doc.parent, doc.stem.casefold()), []).append(doc)
    for (rodic, _), kandidati in podle_klice.items():
        slozka = rodic / kandidati[0].stem
        if slozka.is_dir() and not slozka.is_symlink():
            attachment_dirs.add(slozka)
            if len(kandidati) > 1:
                sken.konflikty.append(
                    f"Nejednoznačná složka příloh '{slozka}': odpovídá více dokumentům: "
                    + ", ".join(str(p) for p in kandidati)
                    + ". Dokumenty budou převedeny bez automatického přiřazení této složky."
                )
    for doc in dokumenty:
        if any(rodic == doc or rodic in doc.parents for rodic in attachment_dirs):
            continue
        rel = Path("ostatní") / doc.relative_to(koren) if knihovna else doc.relative_to(koren)
        kandidati = podle_klice[(doc.parent, doc.stem.casefold())]
        priloha = doc.parent / doc.stem
        if not (priloha.is_dir() and len(kandidati) == 1):
            priloha = None
        did = stabilni_id(rel, "doc")
        sken.dokumenty.append(Dokument(doc, rel, lidsky_nazev(doc), did, Path("articles") / f"{did}.html", priloha))
        for rodic in [rel.parent, *rel.parents]:
            if str(rodic) != ".":
                sken.slozky.add(rodic)
    doc_set = {d.zdroj for d in sken.dokumenty}
    for soubor in vse:
        if not soubor.is_file() or soubor.is_symlink() or soubor.name.casefold() in NEPUBLIKOVAT:
            continue
        if soubor in doc_set or soubor.suffix.casefold() in TEXTOVE:
            continue
        if any(rodic == soubor or rodic in soubor.parents for rodic in attachment_dirs):
            continue
        rel = Path("ostatní") / soubor.relative_to(koren) if knihovna else soubor.relative_to(koren)
        sken.soubory.append(SamostatnySoubor(soubor, rel, soubor.name, stabilni_id(rel, "file"), knihovna))
        for rodic in [rel.parent, *rel.parents]:
            if str(rodic) != ".":
                sken.slozky.add(rodic)


def skenuj() -> Sken:
    sken = Sken()
    _skenuj_koren(ZDROJE, knihovna=False, sken=sken)
    _skenuj_koren(OSTATNI, knihovna=True, sken=sken)
    sken.dokumenty.sort(key=lambda d: razeni(d.rel.as_posix()))
    sken.soubory.sort(key=lambda s: razeni(s.rel.as_posix()))
    return sken
