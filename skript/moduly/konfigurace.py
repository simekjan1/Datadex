from __future__ import annotations

import copy
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .cesty import JSON_DIR, SYSTEM_DATA, atomicky_zapis, nacti_json, priprav_adresare, zapis_json


SOUBORY = {
    "nastaveni": JSON_DIR / "nastaveni.json",
    "projekty": JSON_DIR / "projekty.json",
    "weby": JSON_DIR / "weby.json",
    "galerie": JSON_DIR / "galerie.json",
}


def vychozi_nastaveni(*, nove_id: bool = True) -> dict[str, Any]:
    return {
        "verze": 1,
        "id_databaze": str(uuid.uuid4()) if nove_id else "",
        "nazev": "Moje znalostní databáze",
        "automaticke_galerie": True,
        "kontrola_pri_startu": True,
        "pruvodce_dokoncen": False,
    }


VYCHOZI: dict[str, Any] = {
    "projekty": {"verze": 1, "kategorie": []},
    "weby": {"verze": 1, "kategorie": []},
    "galerie": {"verze": 1},
}


def _validuj_nastaveni(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Nastavení musí být objekt JSON.")
    typy = {
        "verze": int,
        "id_databaze": str,
        "nazev": str,
        "automaticke_galerie": bool,
        "kontrola_pri_startu": bool,
        "pruvodce_dokoncen": bool,
    }
    for klic, typ in typy.items():
        if klic not in data or not isinstance(data[klic], typ):
            raise ValueError(f"Nastavení: položka '{klic}' chybí nebo má chybný typ.")
    try:
        uuid.UUID(data["id_databaze"])
    except (ValueError, AttributeError) as chyba:
        raise ValueError("Nastavení obsahuje neplatné ID databáze.") from chyba
    if data["verze"] != 1 or not data["nazev"].strip():
        raise ValueError("Nastavení obsahuje nepodporovanou verzi nebo prázdný název.")
    return data


def _validuj_kategorie(data: Any, druh: str) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("verze") != 1 or not isinstance(data.get("kategorie"), list):
        raise ValueError(f"{druh}: očekává se objekt s verzí 1 a seznamem kategorií.")
    for kat in data["kategorie"]:
        if not isinstance(kat, dict) or not isinstance(kat.get("nazev"), str) or not isinstance(kat.get("polozky"), list):
            raise ValueError(f"{druh}: neplatná kategorie.")
        for polozka in kat["polozky"]:
            if not isinstance(polozka, dict) or not isinstance(polozka.get("nazev"), str):
                raise ValueError(f"{druh}: neplatná položka.")
            odkazy = polozka.get("odkazy", []) if druh == "projekty" else [polozka]
            if druh == "projekty" and not isinstance(odkazy, list):
                raise ValueError("projekty: odkazy musí být seznam.")
            for odkaz in odkazy:
                if not isinstance(odkaz, dict) or not isinstance(odkaz.get("url"), str):
                    raise ValueError(f"{druh}: odkaz nemá platnou URL.")
                url = odkaz["url"].strip()
                casti = urlsplit(url)
                if not url or casti.scheme.casefold() not in {"", "http", "https", "mailto"}:
                    raise ValueError(f"{druh}: odkaz '{url}' používá nepovolený protokol.")
                if casti.scheme == "" and (url.startswith(("/", "\\", "//")) or ".." in Path(url.replace("\\", "/").split("#", 1)[0]).parts):
                    raise ValueError(f"{druh}: relativní odkaz '{url}' opouští veřejný web.")
    return data


def inicializuj() -> list[str]:
    priprav_adresare()
    vytvorene: list[str] = []
    if not SOUBORY["nastaveni"].exists():
        zapis_json(SOUBORY["nastaveni"], vychozi_nastaveni(), zaloha=False)
        vytvorene.append(str(SOUBORY["nastaveni"]))
    for jmeno in ("projekty", "weby", "galerie"):
        if not SOUBORY[jmeno].exists():
            zapis_json(SOUBORY[jmeno], copy.deepcopy(VYCHOZI[jmeno]), zaloha=False)
            vytvorene.append(str(SOUBORY[jmeno]))
    uvod = SYSTEM_DATA / "uvod.md"
    if not uvod.exists():
        atomicky_zapis(
            uvod,
            "# Vítejte ve znalostní databázi\n\n"
            "Dokumenty vložte do složky `data/1. txt a md soubory`. "
            "Potom v konzolovém menu spusťte převod.\n",
        )
        vytvorene.append(str(uvod))
    instrukce = JSON_DIR / "instrukce.md"
    if not instrukce.exists():
        atomicky_zapis(instrukce, "# Interní instrukce\n\nTento soubor se na webu nepublikuje.\n")
        vytvorene.append(str(instrukce))
    return vytvorene


def nacti_nastaveni() -> dict[str, Any]:
    return _validuj_nastaveni(nacti_json(SOUBORY["nastaveni"], dict))


def nacti_projekty() -> dict[str, Any]:
    return _validuj_kategorie(nacti_json(SOUBORY["projekty"], dict), "projekty")


def nacti_weby() -> dict[str, Any]:
    return _validuj_kategorie(nacti_json(SOUBORY["weby"], dict), "weby")


def nacti_galerie() -> dict[str, Any]:
    return validuj_data("galerie", nacti_json(SOUBORY["galerie"], dict))


def uloz_nastaveni(data: dict[str, Any]) -> None:
    zapis_json(SOUBORY["nastaveni"], _validuj_nastaveni(data))


def uloz_kategorie(druh: str, data: dict[str, Any]) -> None:
    if druh not in {"projekty", "weby"}:
        raise ValueError("Neznámý druh kategorií.")
    zapis_json(SOUBORY[druh], _validuj_kategorie(data, druh))


def validuj_data(druh: str, data: Any) -> dict[str, Any]:
    if druh == "nastaveni":
        return _validuj_nastaveni(data)
    if druh in {"projekty", "weby"}:
        return _validuj_kategorie(data, druh)
    if druh == "galerie":
        if not isinstance(data, dict) or data.get("verze") != 1:
            raise ValueError("galerie: očekává se objekt s verzí 1.")
        return data
    raise ValueError(f"Neznámý druh konfigurace: {druh}")


def vytvor_vychozi_json_v(cil_json: Path, *, pruvodce_dokoncen: bool = False) -> None:
    cil_json.mkdir(parents=True, exist_ok=True)
    nastaveni = vychozi_nastaveni()
    nastaveni["pruvodce_dokoncen"] = pruvodce_dokoncen
    for jmeno, data in {
        "nastaveni.json": nastaveni,
        "projekty.json": copy.deepcopy(VYCHOZI["projekty"]),
        "weby.json": copy.deepcopy(VYCHOZI["weby"]),
        "galerie.json": copy.deepcopy(VYCHOZI["galerie"]),
    }.items():
        text = __import__("json").dumps(data, ensure_ascii=False, indent=2) + "\n"
        soubor = cil_json / jmeno
        with soubor.open("x", encoding="utf-8", newline="\n") as f:
            f.write(text)
