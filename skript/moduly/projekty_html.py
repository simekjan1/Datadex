from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from .cesty import ZDROJE, je_uvnitr


# Jen tyto uživatelem schválené vstupní body lze publikovat jako HTML aplikace.
POVOLENE_VSTUPY = frozenset(
    {
        "Projekty/Aktivní/Adresář/adresar/index.html",
        "Projekty/Aktivní/Palpatius/index.html",
        "Projekty/Dokončené/knihovna/index.html",
        "Projekty/Dokončené/Phasmarium/index.html",
        "Projekty/Odložené/TextBox_dev/index.html",
        "Projekty/Weby/masazesimek.cz/index.html",
        "Projekty/Weby/vidimtojinak/index.html",
    }
)

VEREJNE_KORENY = tuple(
    sorted({PurePosixPath(vstup).parent.as_posix() for vstup in POVOLENE_VSTUPY})
)

POVOLENE_PRIPONY = frozenset(
    {
        ".html", ".htm", ".css", ".js", ".mjs", ".json", ".csv",
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".ico",
        ".woff", ".woff2", ".ttf", ".otf", ".webmanifest",
        ".mp3", ".wav", ".ogg", ".mp4", ".webm",
    }
)

NEVEREJNE_CASTI = frozenset(
    {
        ".git", ".github", ".idea", ".vscode", "__pycache__", "node_modules",
        "notes", "uživatel",
    }
)

NEVEREJNE_NAZVY = frozenset(
    {
        "popisky.json", "config.json", "settings.json", "secrets.json",
        "credentials.json", "package.json", "package-lock.json", "tsconfig.json",
        "appsettings.json",
    }
)

CITLIVE_VYRAZY = ("secret", "token", "password", "passwd", "credential", "private")
CITLIVE_PRIPONY = frozenset({".pem", ".key", ".pfx", ".p12", ".sqlite", ".sqlite3", ".db"})

# Dvě původní stránky Palpatius odkazují na stejné sdílené knihovny z kratší
# relativní cesty. Zdrojový projekt se nemění; bezpečné kopie dostanou i cíle,
# které již existující HTML očekává.
KOMPATIBILNI_CILE = {
    "Projekty/Aktivní/Palpatius/index.html": (
        ("assets/js/ui.js", "data/03._zaznamnik/assets/js/ui.js"),
        ("assets/js/utils.js", "data/03._zaznamnik/assets/js/utils.js"),
    )
}

POVOLENE_DATOVE_SOUBORY = {
    "Projekty/Aktivní/Palpatius/index.html": frozenset(
        {"data/06._dokumentace/Palpatius maps.txt"}
    )
}


@dataclass(frozen=True)
class ProjektovySoubor:
    zdroj: Path
    verejna_rel: Path
    vstup_url: str


@dataclass(frozen=True)
class VyberProjektovychSouboru:
    soubory: tuple[ProjektovySoubor, ...]
    uplny: bool


def _normalizuj_url(url: object) -> str | None:
    if not isinstance(url, str) or not url:
        return None
    rozbor = urlsplit(url)
    if rozbor.scheme or rozbor.netloc or rozbor.query or rozbor.fragment or "\\" in url:
        return None
    cesta = unquote(rozbor.path)
    if cesta.startswith("/"):
        return None
    casti = cesta.split("/")
    if not casti or any(cast in {"", ".", ".."} for cast in casti):
        return None
    return PurePosixPath(*casti).as_posix()


def _konfigurovane_vstupy(projekty: dict) -> set[str]:
    nalezene: set[str] = set()
    for kategorie in projekty.get("kategorie", []):
        for projekt in kategorie.get("polozky", []):
            for odkaz in projekt.get("odkazy", []):
                url = _normalizuj_url(odkaz.get("url"))
                if url in POVOLENE_VSTUPY:
                    nalezene.add(url)
    return nalezene


def _je_bezpecny_staticky_soubor(rel: Path) -> tuple[bool, bool]:
    """Vrátí (publikovat, citlivá nebo výslovně neveřejná cesta)."""
    casti = tuple(cast.casefold() for cast in rel.parts)
    if any(not cast or cast.startswith(".") for cast in casti):
        return False, True
    if any(cast in NEVEREJNE_CASTI for cast in casti[:-1]):
        return False, True
    nazev = rel.name.casefold()
    if nazev.startswith(".env") or nazev in NEVEREJNE_NAZVY:
        return False, True
    if any(vyraz in nazev for vyraz in CITLIVE_VYRAZY) or rel.suffix.casefold() in CITLIVE_PRIPONY:
        return False, True
    return rel.suffix.casefold() in POVOLENE_PRIPONY, False


def vyber_projektove_soubory(projekty: dict, varovani: list[str]) -> VyberProjektovychSouboru:
    vysledek: list[ProjektovySoubor] = []
    uplny = True
    pouzite_cile: set[str] = set()

    for vstup_url in sorted(_konfigurovane_vstupy(projekty)):
        vstup_rel = PurePosixPath(vstup_url)
        zdrojovy_koren = ZDROJE.joinpath(*vstup_rel.parent.parts)
        vstup = zdrojovy_koren / vstup_rel.name
        if not je_uvnitr(zdrojovy_koren, ZDROJE) or not je_uvnitr(vstup, zdrojovy_koren):
            varovani.append(f"HTML projekt má nepovolenou cestu a nebyl publikován: {vstup_url}")
            uplny = False
            continue
        if not vstup.is_file() or vstup.is_symlink():
            varovani.append(f"Vstupní soubor HTML projektu není bezpečně dostupný: {vstup_url}")
            uplny = False
            continue

        blokovane = 0
        try:
            kandidati = sorted(zdrojovy_koren.rglob("*"), key=lambda p: p.as_posix().casefold())
        except OSError as chyba:
            varovani.append(f"HTML projekt nelze úplně prohledat {vstup_url}: {chyba}")
            uplny = False
            continue

        for zdroj in kandidati:
            try:
                if not zdroj.is_file():
                    continue
                rel = zdroj.relative_to(zdrojovy_koren)
                publikovat, citlive = _je_bezpecny_staticky_soubor(rel)
                if rel.as_posix() in POVOLENE_DATOVE_SOUBORY.get(vstup_url, ()):
                    publikovat, citlive = True, False
                if zdroj.is_symlink() or not je_uvnitr(zdroj, zdrojovy_koren):
                    blokovane += 1
                    continue
                if not publikovat:
                    if citlive:
                        blokovane += 1
                    continue
                verejna_rel = Path(*vstup_rel.parent.parts) / rel
                klic = verejna_rel.as_posix().casefold()
                if klic in pouzite_cile:
                    varovani.append(f"Kolize cílové cesty HTML projektu; soubor byl přeskočen: {verejna_rel.as_posix()}")
                    uplny = False
                    continue
                pouzite_cile.add(klic)
                vysledek.append(ProjektovySoubor(zdroj, verejna_rel, vstup_url))
            except OSError as chyba:
                varovani.append(f"Soubor HTML projektu nelze ověřit {zdroj}: {chyba}")
                uplny = False

        for zdroj_rel_text, cil_rel_text in KOMPATIBILNI_CILE.get(vstup_url, ()):
            zdroj_rel = Path(*PurePosixPath(zdroj_rel_text).parts)
            zdroj = zdrojovy_koren / zdroj_rel
            cil_rel = Path(*PurePosixPath(cil_rel_text).parts)
            verejna_rel = Path(*vstup_rel.parent.parts) / cil_rel
            klic = verejna_rel.as_posix().casefold()
            if not zdroj.is_file() or zdroj.is_symlink() or not je_uvnitr(zdroj, zdrojovy_koren):
                varovani.append(f"Kompatibilní soubor HTML projektu není dostupný: {zdroj_rel_text}")
                uplny = False
            elif klic in pouzite_cile:
                varovani.append(f"Kolize kompatibilní cílové cesty HTML projektu: {verejna_rel.as_posix()}")
                uplny = False
            else:
                pouzite_cile.add(klic)
                vysledek.append(ProjektovySoubor(zdroj, verejna_rel, vstup_url))

        if blokovane:
            varovani.append(
                f"HTML projekt {vstup_url}: {blokovane} citlivých nebo výslovně neveřejných souborů nebylo publikováno."
            )

    vysledek.sort(key=lambda polozka: polozka.verejna_rel.as_posix().casefold())
    return VyberProjektovychSouboru(tuple(vysledek), uplny)


def je_projektova_cesta(url: str) -> bool:
    cesta = unquote(urlsplit(url).path)
    if "\\" in cesta:
        return False
    casti = cesta.lstrip("/").split("/")
    if not casti or any(cast in {"", ".", ".."} for cast in casti):
        return False
    rel = PurePosixPath(*casti)
    return any(rel == PurePosixPath(koren) or PurePosixPath(koren) in rel.parents for koren in VEREJNE_KORENY)
