from __future__ import annotations

import hashlib
import html
import json
import os
import re
import gc
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .cesty import DOCASNE, KOREN, SABLONY, STAV, SYSTEM_DATA, WEB, atomicky_kopiruj, atomicky_zapis, atomicky_zapis_json_pole, hash_souboru, je_uvnitr, nacti_json, priprav_adresare, zapis_json, zapis_log
from .galerie import SkupinaGalerie, aktualizuj_popisky, je_podporovany_obrazek, kopiruj_prilohu, priprav_galerie
from .konfigurace import inicializuj, nacti_galerie, nacti_nastaveni, nacti_projekty, nacti_weby
from .markdown_bezpecny import MAX_TEXT_CHARS, Nadpis, VysledekMarkdown, preved_markdown, preved_txt
from .model import BEZPECNE_SOUBORY, Dokument, OBRAZKY, SamostatnySoubor, Sken, lidsky_nazev, razeni, skenuj, stabilni_id


@dataclass
class Souhrn:
    prevedeno: int = 0
    nezmeneno: int = 0
    chyby: int = 0
    odstraneno: int = 0
    varovani: list[str] = field(default_factory=list)
    konflikty: list[str] = field(default_factory=list)
    log: Path | None = None


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def _nacti_manifest() -> dict:
    cesta = STAV / "manifest.json"
    if not cesta.exists():
        return {"verze": 2, "documents": {}, "failedDocuments": {}, "standalone": {}, "files": {}, "outputs": [], "trusted": False}
    try:
        data = nacti_json(cesta, dict)
        if data.get("verze") != 2:
            raise ValueError("Nepodporovaná verze manifestu.")
        data.setdefault("failedDocuments", {})
        for klic in ("documents", "failedDocuments", "standalone", "files"):
            if not isinstance(data.get(klic), dict):
                raise ValueError(f"Manifest neobsahuje platnou sekci {klic}.")
        if not isinstance(data.get("outputs"), list) or not all(isinstance(x, str) for x in data["outputs"]):
            raise ValueError("Manifest neobsahuje platný seznam výstupů.")
        data["trusted"] = True
        return data
    except (ValueError, OSError):
        return {"verze": 2, "documents": {}, "failedDocuments": {}, "standalone": {}, "files": {}, "outputs": [], "trusted": False}


def _klic_souboru(cesta: Path) -> str:
    return cesta.resolve(strict=False).relative_to(KOREN.resolve(strict=False)).as_posix()


def _otisk_souboru(cesta: Path, stary: dict, novy: dict, *, vynutit: bool = False) -> dict:
    if cesta.is_symlink() or not je_uvnitr(cesta, KOREN):
        raise ValueError(f"Nepovolený zdrojový soubor: {cesta}")
    stat = cesta.stat()
    klic = _klic_souboru(cesta)
    predchozi = stary.get(klic, {})
    if (
        not vynutit
        and isinstance(predchozi, dict)
        and predchozi.get("size") == stat.st_size
        and predchozi.get("mtime_ns") == stat.st_mtime_ns
        and isinstance(predchozi.get("sha256"), str)
        and len(predchozi["sha256"]) == 64
    ):
        otisk = dict(predchozi)
    else:
        otisk = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": hash_souboru(cesta)}
    novy[klic] = otisk
    return otisk


def _hash_stromu(cesta: Path | None, stare_soubory: dict, nove_soubory: dict, *, vynutit: bool = False) -> str:
    h = hashlib.sha256()
    if not cesta or not cesta.exists():
        return h.hexdigest()
    for p in sorted(cesta.rglob("*"), key=lambda x: x.as_posix()):
        if p.is_file() and not p.is_symlink():
            h.update(p.relative_to(cesta).as_posix().encode())
            try:
                h.update(bytes.fromhex(_otisk_souboru(p, stare_soubory, nove_soubory, vynutit=vynutit)["sha256"]))
            except OSError:
                h.update(b"ERROR")
    return h.hexdigest()


def _sdileny_hash(stare_soubory: dict, nove_soubory: dict, *, vynutit: bool = False) -> str:
    h = hashlib.sha256()
    for p in sorted(SABLONY.glob("*"), key=lambda x: x.name):
        if p.is_file():
            h.update(p.name.encode()); h.update(bytes.fromhex(_otisk_souboru(p, stare_soubory, nove_soubory, vynutit=vynutit)["sha256"]))
    for p in sorted((SYSTEM_DATA / "json").glob("*.json"), key=lambda x: x.name):
        if p.is_file():
            h.update(p.name.encode()); h.update(bytes.fromhex(_otisk_souboru(p, stare_soubory, nove_soubory, vynutit=vynutit)["sha256"]))
    uvod = SYSTEM_DATA / "uvod.md"
    if uvod.is_file():
        h.update(uvod.name.encode()); h.update(bytes.fromhex(_otisk_souboru(uvod, stare_soubory, nove_soubory, vynutit=vynutit)["sha256"]))
    return h.hexdigest()


def _zaznam_platny(zaznam: dict, *, index_soubor: Path | None = None) -> bool:
    if not isinstance(zaznam, dict) or not isinstance(zaznam.get("output"), str):
        return False
    vystupy = zaznam.get("outputs", [])
    if not isinstance(vystupy, list) or not all(isinstance(x, str) and x for x in vystupy):
        return False
    if not all(je_uvnitr(WEB / rel, WEB) and (WEB / rel).is_file() for rel in vystupy):
        return False
    return index_soubor is None or (je_uvnitr(index_soubor, STAV) and index_soubor.is_file())


def _index_cesta(ident: str) -> Path:
    return STAV / "index_entries" / f"{ident}.json"


def _uloz_index(ident: str, polozka: dict) -> Path:
    cesta = _index_cesta(ident)
    zapis_json(cesta, polozka, zaloha=False)
    return cesta


def _index_polozky(cesty: list[Path]):
    for cesta in cesty:
        yield nacti_json(cesta, dict)


def _vytvor_index(cesty: list[Path], projekty: dict, weby: dict, outputs: set[str], *, pocet_casti: int = 32) -> None:
    pracoviste = DOCASNE / f"search-{os.getpid()}-{time.time_ns()}"
    pracoviste.mkdir(parents=True, exist_ok=False)
    soubory = [pracoviste / f"{i:02d}.jsonl" for i in range(pocet_casti)]

    def uloz(polozka: dict) -> None:
        cast = int(hashlib.sha256(str(polozka.get("url", "")).encode("utf-8")).hexdigest()[:8], 16) % pocet_casti
        with soubory[cast].open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(polozka, ensure_ascii=False, separators=(",", ":")) + "\n")

    try:
        for polozka in _index_polozky(cesty):
            uloz(polozka)
        for kat in projekty["kategorie"]:
            for p in kat["polozky"]:
                for odkaz in p.get("odkazy", []) or [{}]:
                    uloz({"type":"project","typeLabel":"Projekt","title":p["nazev"],"headings":kat["nazev"],"text":p.get("popis","")+" "+odkaz.get("nazev",""),"url":odkaz.get("url","#"),"path":kat["nazev"],"snippet":p.get("popis","")})
        for kat in weby["kategorie"]:
            for p in kat["polozky"]:
                uloz({"type":"web","typeLabel":"Webový odkaz","title":p["nazev"],"headings":kat["nazev"],"text":p.get("popis","")+" "+p.get("url",""),"url":p.get("url","#"),"path":kat["nazev"],"snippet":p.get("popis","")})
        manifest_casti = []
        for cislo, jsonl in enumerate(soubory):
            rel = Path("search-data") / f"{cislo:02d}.json"
            def radky(cesta=jsonl):
                if not cesta.exists():
                    return
                with cesta.open("r", encoding="utf-8") as f:
                    for radek in f:
                        if radek.strip():
                            yield json.loads(radek)
            atomicky_zapis_json_pole(WEB / rel, radky())
            outputs.add(rel.as_posix())
            manifest_casti.append(rel.as_posix())
        zapis_json(WEB / "search-index.json", {"version": 2, "shards": manifest_casti}, zaloha=False)
    finally:
        for cesta in soubory:
            try:
                cesta.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            pracoviste.rmdir()
        except OSError:
            pass


def _root_for(vystup_rel: Path) -> str:
    return "../" * (len(vystup_rel.parts) - 1)


def _page(template: str, *, vystup_rel: Path, title: str, db: dict, content: str, sidebar: str, breadcrumbs: str = "", extra_head: str = "", search_query: str = "", top: bool = True) -> str:
    root = _root_for(vystup_rel)
    hodnoty = {
        "ROOT": root, "TITLE": _esc(title), "DB_NAME": _esc(db["nazev"]), "DB_ID": _esc(db["id_databaze"]),
        "CONTENT": content, "SIDEBAR": sidebar, "BREADCRUMBS": breadcrumbs, "EXTRA_HEAD": extra_head,
        "SEARCH_QUERY": _esc(search_query),
        "TOP_BUTTON": '<button type="button" class="na-zacatek">Na začátek stránky</button>' if top else "",
    }
    for klic, hodnota in hodnoty.items():
        template = template.replace("{{" + klic + "}}", hodnota)
    return template


def _stromova_data(sken: Sken) -> dict:
    koren = {"folders": {}, "items": []}
    for folder in sorted(sken.slozky, key=lambda x: razeni(x.as_posix())):
        if folder == Path("."):
            continue
        node = koren
        for part in folder.parts:
            node = node["folders"].setdefault(part, {"folders": {}, "items": [], "path": (node.get("path", Path(".")) / part)})
    for d in sken.dokumenty:
        node = koren
        for part in d.rel.parent.parts:
            if part != ".": node = node["folders"].setdefault(part, {"folders": {}, "items": [], "path": Path(part)})
        node["items"].append((d.nazev, d.vystup_rel.as_posix(), "Dokument"))
    for f in sken.soubory:
        node = koren
        for part in f.rel.parent.parts:
            if part != ".": node = node["folders"].setdefault(part, {"folders": {}, "items": [], "path": Path(part)})
        ext = f.zdroj.suffix.casefold()
        node["items"].append((f.nazev, (Path("files") / f"{f.id}{ext}").as_posix(), "Soubor"))
    return koren


def _render_tree(node: dict, root: str) -> str:
    casti = ["<ul>"]
    for name, child in sorted(node["folders"].items(), key=lambda x: razeni(x[0])):
        path = child.get("path", Path(name))
        fid = stabilni_id(Path(path), "folder")
        casti.append(f'<li><details data-pref="nav:{_esc(fid)}"><summary>{_esc(name)}</summary><a href="{root}folders/{fid}.html">Otevřít stránku složky {_esc(name)}</a>{_render_tree(child, root)}</details></li>')
    for name, url, typ in sorted(node["items"], key=lambda x: razeni(x[0])):
        casti.append(f'<li><a href="{root}{_esc(url)}">{_esc(name)}</a> <span class="jen-odecitac">({typ})</span></li>')
    casti.append("</ul>")
    return "".join(casti)


def _externi(url: str) -> tuple[str, str]:
    scheme = urlsplit(url).scheme.casefold()
    if scheme in {"http", "https", "mailto"}:
        return ' target="_blank" rel="noopener noreferrer"', '<span class="jen-odecitac"> (otevře se v nové kartě)</span>'
    if scheme or url.startswith(("/", "\\")) or ".." in Path(url.replace("\\", "/")).parts:
        return "", ""
    return "", ""


def _sidebar(sken: Sken, projekty: dict, weby: dict, root: str) -> str:
    panel1 = '<section class="panel" aria-labelledby="panel-dokumenty"><h2 id="panel-dokumenty">Znalostní dokumenty a soubory</h2>' + _render_tree(_stromova_data(sken), root) + "</section>"
    projekty_html = []
    for ki, kat in enumerate(projekty["kategorie"]):
        polozky = []
        for p in kat["polozky"]:
            odkazy = []
            for odkaz in p.get("odkazy", []):
                url = odkaz.get("url", "")
                attrs, note = _externi(url)
                if not urlsplit(url).scheme and not url.startswith(("/", "\\")):
                    url = root + url
                odkazy.append(f'<li><a href="{_esc(url)}"{attrs}>{_esc(odkaz.get("nazev", "Otevřít"))}{note}</a></li>')
            popis = f'<p>{_esc(p["popis"])}</p>' if p.get("popis") else ""
            seznam = "<ul>" + "".join(odkazy) + "</ul>" if odkazy else ""
            polozky.append(f'<article class="projekt"><h3>{_esc(p["nazev"])}</h3>{popis}{seznam}</article>')
        projekty_html.append(f'<details data-pref="projects:{ki}"><summary>{_esc(kat["nazev"])}</summary>{"".join(polozky)}</details>')
    panel2 = '<section class="panel" aria-labelledby="panel-projekty"><h2 id="panel-projekty">Aplikace a projekty</h2>' + ("".join(projekty_html) or "<p>Zatím nejsou přidány žádné projekty.</p>") + "</section>"
    web_html = []
    for ki, kat in enumerate(weby["kategorie"]):
        odkazy=[]
        for p in kat["polozky"]:
            url=p.get("url","");attrs,note=_externi(url)
            popis=f' – {_esc(p["popis"])}' if p.get("popis") else ""
            odkazy.append(f'<li><a href="{_esc(url)}"{attrs}>{_esc(p["nazev"])}{note}</a>{popis}</li>')
        web_html.append(f'<details data-pref="webs:{ki}"><summary>{_esc(kat["nazev"])}</summary><ul>{"".join(odkazy)}</ul></details>')
    panel3='<section class="panel" aria-labelledby="panel-weby"><h2 id="panel-weby">Webové odkazy</h2>' + ("".join(web_html) or "<p>Zatím nejsou přidány žádné webové odkazy.</p>") + "</section>"
    return panel1+panel2+panel3


def _breadcrumbs(rel: Path, aktualni: str, root: str) -> str:
    polozky=[f'<li><a href="{root}index.html">Úvod</a></li>']
    postup=Path()
    for part in rel.parent.parts:
        if part==".":continue
        postup/=part;fid=stabilni_id(postup,"folder")
        polozky.append(f'<li><a href="{root}folders/{fid}.html">{_esc(part)}</a></li>')
    polozky.append(f'<li aria-current="page">{_esc(aktualni)}</li>')
    return '<nav class="drobecky" aria-label="Drobečková navigace"><ol>'+"".join(polozky)+"</ol></nav>"


def _kapitoly(vysledek: VysledekMarkdown) -> tuple[str, bool]:
    meaningful = len(vysledek.nadpisy) >= 2
    if not meaningful:
        return vysledek.html, False
    pat = re.compile(r'(<h([1-6]) id="([^"]+)">.*?</h\2>)', re.DOTALL)
    parts=pat.split(vysledek.html)
    if len(parts)<5:return vysledek.html,False
    out=[parts[0]];i=1
    while i<len(parts):
        heading,level,ident=parts[i],parts[i+1],parts[i+2];body=parts[i+3] if i+3<len(parts) else ""
        out.append(f'<section class="kapitola" id="kapitola-{_esc(ident)}" data-section-id="{_esc(ident)}" data-open="false">{heading}<div class="kapitola-ovladani"><button type="button" class="kapitola-prepinac" aria-controls="telo-{_esc(ident)}" aria-expanded="false" hidden>Rozbalit kapitolu</button><button type="button" class="precist-kapitolu" data-target="telo-{_esc(ident)}">Přečíst kapitolu</button></div><div class="kapitola-telo" id="telo-{_esc(ident)}">{body}</div></section>')
        i+=4
    return "".join(out),True


def _galerie_html(skupiny: list[SkupinaGalerie], root: str) -> str:
    out=[]
    for g in skupiny:
        buttons=[]
        for o in g.obrazky:
            src=root+o.verejna_rel.as_posix()
            buttons.append(f'<button type="button" class="nahled" data-gallery="{g.klic}" data-full="{_esc(src)}" data-alt="{_esc(o.popis)}"><img src="{_esc(src)}" alt="" loading="lazy"><span>{_esc(o.popis)}. Otevřít zvětšený obrázek.</span></button>')
        out.append(f'<section aria-labelledby="gal-{g.klic}"><h2 id="gal-{g.klic}">{_esc(g.nazev)}</h2><div class="galerie-mrizka">{"".join(buttons)}</div></section>')
    return "".join(out)


def _resolve_tokens(vysledek: VysledekMarkdown, doc: Dokument, mapa_doc: dict[Path, Dokument], publikovane: dict[Path, Path], varovani: list[str]) -> tuple[str, set[Path], set[str]]:
    root="../";referenced: set[Path]=set();token_outputs: set[str]=set()
    def media(m: re.Match) -> str:
        raw=html.unescape(m.group(1));pathpart=unquote(raw.split("#",1)[0].split("?",1)[0])
        cil=(doc.zdroj.parent/pathpart).resolve(strict=False)
        if doc.priloha_slozka and je_uvnitr(cil,doc.priloha_slozka):
            rel=cil.relative_to(doc.priloha_slozka);referenced.add(rel)
            verejna=publikovane.get(rel)
            if verejna:token_outputs.add(verejna.as_posix());return root+verejna.as_posix()
        if je_uvnitr(cil, KOREN) and je_podporovany_obrazek(cil):
            rel=Path("media")/doc.id/"explicit"/(hashlib.sha256(str(cil).encode()).hexdigest()[:10]+cil.suffix.casefold())
            kopiruj_prilohu(cil,rel);token_outputs.add(rel.as_posix());return root+rel.as_posix()
        varovani.append(f"Obrázek v dokumentu {doc.rel} nelze bezpečně publikovat: {raw}")
        return ""
    def link(m: re.Match) -> str:
        raw=html.unescape(m.group(1));ifrag=""
        if "#" in raw: raw,frag=raw.split("#",1);ifrag="#"+frag
        if not raw:return ifrag or "#"
        cil=(doc.zdroj.parent/unquote(raw)).resolve(strict=False)
        if cil in mapa_doc:return root+mapa_doc[cil].vystup_rel.as_posix()+ifrag
        if doc.priloha_slozka and je_uvnitr(cil,doc.priloha_slozka) and cil.is_file() and not cil.is_symlink():
            if cil.suffix.casefold() not in BEZPECNE_SOUBORY:
                varovani.append(f"Aktivní nebo nepodporovaný typ přílohy nebyl publikován: {cil}")
                return "#"
            rel=cil.relative_to(doc.priloha_slozka);referenced.add(rel);pub=Path("attachments")/doc.id/rel
            try:kopiruj_prilohu(cil,pub);token_outputs.add(pub.as_posix());return root+pub.as_posix()+ifrag
            except OSError as e:varovani.append(f"Přílohu nelze publikovat {cil}: {e}")
        varovani.append(f"Neplatný interní odkaz v {doc.rel}: {raw}")
        return "#"
    text=re.sub(r"\{\{MEDIA:(.*?)\}\}",media,vysledek.html)
    text=re.sub(r"\{\{LINK:(.*?)\}\}",link,text)
    return text,referenced,token_outputs


def _prilohy(doc: Dokument, explicit_refs: set[Path], root: str, outputs: set[str], varovani: list[str]) -> str:
    if not doc.priloha_slozka:return ""
    links=[]
    for p in sorted(doc.priloha_slozka.rglob("*"),key=lambda x:razp(x)):
        if not p.is_file() or p.is_symlink() or p.name.casefold()=="popisky.json" or p.suffix.casefold() in OBRAZKY:continue
        if p.suffix.casefold() not in BEZPECNE_SOUBORY:
            varovani.append(f"Aktivní nebo nepodporovaný typ přílohy nebyl publikován: {p}")
            continue
        rel=p.relative_to(doc.priloha_slozka)
        if rel in explicit_refs:continue
        pub=Path("attachments")/doc.id/rel
        try:kopiruj_prilohu(p,pub);outputs.add(pub.as_posix());links.append(f'<li><a href="{root}{_esc(pub.as_posix())}">{_esc(rel.as_posix())}</a></li>')
        except OSError as e:varovani.append(f"Přílohu nelze zkopírovat {p}: {e}")
    return '<section><h2>Přílohy</h2><ul>'+"".join(links)+"</ul></section>" if links else ""


def razp(p: Path) -> str:return razeni(p.as_posix())


def _speech_controls() -> str:
    return '<section class="cteni-ovladani" aria-labelledby="nadpis-cteni"><h2 id="nadpis-cteni">Hlasové čtení</h2><label for="hlas">Hlas</label><select id="hlas"><option value="">Výchozí hlas prohlížeče</option></select><label for="rychlost">Rychlost řeči</label><input id="rychlost" type="number" min="0.5" max="2" step="0.1" value="1"><div class="cteni-tlacitka"><button type="button" id="precist-dokument">Přečíst dokument</button><button type="button" id="pozastavit-cteni">Pozastavit</button><button type="button" id="obnovit-cteni">Obnovit</button><button type="button" id="zastavit-cteni">Zastavit</button></div><p id="stav-cteni" role="status" aria-live="polite">Čtení je připraveno.</p></section>'


def _over_utf8(cesta: Path) -> None:
    with cesta.open("r", encoding="utf-8") as soubor:
        while soubor.read(1024 * 1024):
            pass


def generuj(*, uplne: bool = False, vypis=print) -> Souhrn:
    inicializuj(); priprav_adresare(); souhrn=Souhrn(); logradky=["Generování znalostní databáze"]
    zacatek = time.perf_counter()
    try:
        db=nacti_nastaveni(); projekty=nacti_projekty(); weby=nacti_weby(); nacti_galerie()
    except (ValueError, OSError, MemoryError) as e:
        souhrn.chyby=1; souhrn.varovani.append(f"Načtení konfigurace selhalo: {type(e).__name__}: {e}"); souhrn.log=zapis_log("prevod",souhrn.varovani); return souhrn
    old=_nacti_manifest(); stare_soubory=old.get("files",{}) if old.get("trusted") else {}; nove_soubory={}
    if not old.get("trusted") and (STAV/"manifest.json").exists():
        souhrn.varovani.append("Předchozí manifest nebyl platný nebo měl starší verzi; proběhne bezpečné nové sestavení.")
    try:
        shared=_sdileny_hash(stare_soubory,nove_soubory,vynutit=uplne or not old.get("trusted"))
        template=(SABLONY/"zaklad.html").read_text(encoding="utf-8")
        sken=skenuj(); souhrn.konflikty.extend(sken.konflikty)
    except (OSError, UnicodeError, ValueError, MemoryError) as e:
        souhrn.chyby=1; souhrn.varovani.append(f"Příprava převodu selhala: {type(e).__name__}: {e}"); souhrn.log=zapis_log("prevod",souhrn.varovani); return souhrn

    samostatne_popisky: dict[str, str] = {}
    obrazky_podle_slozky: dict[Path, list[SamostatnySoubor]] = {}
    for f in sken.soubory:
        if f.zdroj.suffix.casefold() in OBRAZKY:
            obrazky_podle_slozky.setdefault(f.zdroj.parent, []).append(f)
    povolene_soubory: list[SamostatnySoubor] = []
    for slozka, obrazky in obrazky_podle_slozky.items():
        platne = [f for f in obrazky if je_podporovany_obrazek(f.zdroj)]
        for f in obrazky:
            if f not in platne:
                souhrn.varovani.append(f"Soubor má obrazovou příponu, ale neplatný obsah a nebyl publikován: {f.rel}")
        popisky = aktualizuj_popisky(slozka, [f.zdroj for f in platne], souhrn.varovani) if platne else {}
        for f in platne:
            nast = popisky.get(f.zdroj.name, {})
            if bool(nast.get("zobrazit", False)):
                samostatne_popisky[f.id] = str(nast.get("popis", f.nazev)); povolene_soubory.append(f)
    for f in sken.soubory:
        if f.zdroj.suffix.casefold() in OBRAZKY: continue
        if f.zdroj.suffix.casefold() in BEZPECNE_SOUBORY: povolene_soubory.append(f)
        else: souhrn.varovani.append(f"Aktivní nebo nepodporovaný samostatný soubor nebyl publikován: {f.rel}")
    sken.soubory=sorted(povolene_soubory,key=lambda f:razeni(f.rel.as_posix()))
    vsechny_dokumenty=list(sken.dokumenty); doc_stavy=[]; publikovane_dokumenty=[]
    for doc in vsechny_dokumenty:
        prev=old.get("documents",{}).get(doc.rel.as_posix(),{}); idx_path=_index_cesta(doc.id)
        prev_platny=old.get("trusted") and _zaznam_platny(prev,index_soubor=idx_path)
        stav={"doc":doc,"prev":prev,"idx":idx_path,"prev_platny":prev_platny,"faze":"zjišťování změn","chyba":None}
        try:
            stav["zdroj_otisk"]=_otisk_souboru(doc.zdroj,stare_soubory,nove_soubory,vynutit=uplne or not old.get("trusted"))
            stav["strom_hash"]=_hash_stromu(doc.priloha_slozka,stare_soubory,nove_soubory,vynutit=uplne or not old.get("trusted"))
            if stav["zdroj_otisk"]["size"] > MAX_TEXT_CHARS * 4:
                raise ValueError(f"textový soubor překračuje bezpečný limit {MAX_TEXT_CHARS*4} bajtů")
            if not prev_platny:
                stav["faze"]="předběžné ověření UTF-8"; _over_utf8(doc.zdroj)
        except (OSError,UnicodeError,ValueError,MemoryError) as e:
            stav["chyba"]=e
        if stav["chyba"] is None or prev_platny:
            publikovane_dokumenty.append(doc)
        doc_stavy.append(stav)
    sken.dokumenty=publikovane_dokumenty
    struktura="\n".join([*("D:"+d.rel.as_posix() for d in sken.dokumenty),*("F:"+f.rel.as_posix() for f in sken.soubory)])
    shared_effective=hashlib.sha256((shared+struktura).encode()).hexdigest()
    sidebar_hash=hashlib.sha256((shared_effective+"\n".join(d.rel.as_posix() for d in sken.dokumenty)).encode()).hexdigest()
    page_hash=hashlib.sha256((sidebar_hash+json.dumps(samostatne_popisky,ensure_ascii=False,sort_keys=True)).encode()).hexdigest()
    sidebar_cache={}; get_sidebar=lambda root:sidebar_cache.setdefault(root,_sidebar(sken,projekty,weby,root))
    outputs={"css/style.css","js/app.js","js/search.js","index.html","search.html","search-index.json"}
    sablony_zmeneny=uplne or shared_effective!=old.get("sharedHash") or sidebar_hash!=old.get("sidebarHash")
    for name in ("style.css","app.js","search.js"):
        rel=Path("css/style.css") if name=="style.css" else Path("js")/name
        if sablony_zmeneny or not (WEB/rel).is_file(): atomicky_kopiruj(SABLONY/name,WEB/rel,cilovy_koren=WEB)

    newdocs={}; failed_docs={}; newstandalone={}; index_cesty=[]; index_zmenen=sablony_zmeneny or not old.get("trusted")
    mapa={d.zdroj.resolve(strict=False):d for d in sken.dokumenty}; total=max(1,len(doc_stavy))
    for num,stav in enumerate(doc_stavy,1):
        doc=stav["doc"]; prev=stav["prev"]; faze=stav["faze"]
        try:
            if stav["chyba"] is not None:
                raise stav["chyba"]
            zdroj_otisk=stav["zdroj_otisk"]; strom_hash=stav["strom_hash"]
            podpis=hashlib.sha256((zdroj_otisk["sha256"]+strom_hash+shared_effective).encode()).hexdigest()
            idx_path=stav["idx"]
            if not uplne and old.get("trusted") and old.get("sidebarHash")==sidebar_hash and prev.get("signature")==podpis and stav["prev_platny"]:
                vypis(f"Přeskakuji {num}/{total}: {doc.rel} (beze změny)")
                newdocs[doc.rel.as_posix()]=prev; outputs.update(prev["outputs"]); index_cesty.append(idx_path); souhrn.nezmeneno+=1
                continue
            vypis(f"Zpracovávám {num}/{total}: {doc.rel} ({zdroj_otisk['size']/1024/1024:.2f} MiB)")
            faze="načítání UTF-8"; raw=doc.zdroj.read_text(encoding="utf-8")
            faze="převod Markdown/TXT"; vys=preved_markdown(raw) if doc.zdroj.suffix.casefold()==".md" else preved_txt(raw)
            faze="vyhodnocení odkazů"; explicit=set()
            if doc.priloha_slozka:
                for url in vys.obrazky:
                    c=(doc.zdroj.parent/unquote(url.split("#",1)[0])).resolve(strict=False)
                    if je_uvnitr(c,doc.priloha_slozka): explicit.add(c.relative_to(doc.priloha_slozka))
            faze="publikace galerie"; groups,published=priprav_galerie(doc.priloha_slozka,doc.id,explicit,db["automaticke_galerie"] and vys.galerie_povolena,souhrn.varovani)
            doc_outputs={p.as_posix() for p in published.values()}
            faze="publikace odkazovaných příloh"; html_body,refs,token_outputs=_resolve_tokens(vys,doc,mapa,published,souhrn.varovani); doc_outputs.update(token_outputs)
            vys.html=html_body; chapters,haschap=_kapitoly(vys)
            original=Path("original")/(doc.id+doc.zdroj.suffix.casefold()); faze="kopie původního dokumentu"; atomicky_kopiruj(doc.zdroj,WEB/original,cilovy_koren=WEB); doc_outputs.add(original.as_posix())
            root="../"; faze="publikace ostatních příloh"; attachments=_prilohy(doc,refs|explicit,root,doc_outputs,souhrn.varovani)
            mode=f'<div class="nastroje-dokumentu"><label for="rezim-dokumentu">Režim čtení</label><select id="rezim-dokumentu"><option value="full">Kompletní dokument</option><option value="chapters">Podle kapitol</option></select></div>' if haschap else ""
            finds='<section id="nalezy" class="nalezy" hidden><h2>Nalezené výskyty</h2><output>Výskyt</output><div><button type="button" class="predchozi-nalez">Předchozí výskyt</button><button type="button" class="dalsi-nalez">Další výskyt</button></div></section>'
            content=f'<article data-document-id="{doc.id}"><h1>{_esc(doc.nazev)}</h1><p><a href="{root}{original.as_posix()}">Otevřít původní zdrojový soubor</a></p>{mode}{_speech_controls()}{finds}<div class="obsah-dokumentu">{chapters}</div>{_galerie_html(groups,root)}{attachments}</article>'
            nav_ids=[]; postup=Path()
            for cast in doc.rel.parent.parts:
                if cast != ".": postup/=cast; nav_ids.append(stabilni_id(postup,"folder"))
            extra='<meta name="current-nav-path" content="'+_esc(",".join(nav_ids))+'">'
            faze="atomické zveřejnění HTML"; page=_page(template,vystup_rel=doc.vystup_rel,title=doc.nazev,db=db,content=content,sidebar=get_sidebar(root),breadcrumbs=_breadcrumbs(doc.rel,doc.nazev,root),extra_head=extra); atomicky_zapis(WEB/doc.vystup_rel,page); doc_outputs.add(doc.vystup_rel.as_posix())
            idx_item={"type":"document","typeLabel":"Dokument","title":doc.nazev,"headings":" ".join(h.text for h in vys.nadpisy),"text":vys.prosty_text,"url":doc.vystup_rel.as_posix(),"path":doc.rel.as_posix(),"snippet":vys.prosty_text.replace("\n"," ")[:240]}
            faze="uložení položky fulltextu"; idx_path=_uloz_index(doc.id,idx_item); index_cesty.append(idx_path)
            # Automaticky vzniklý popisky.json musí být součástí konečného podpisu.
            strom_hash=_hash_stromu(doc.priloha_slozka,stare_soubory,nove_soubory,vynutit=False)
            podpis=hashlib.sha256((zdroj_otisk["sha256"]+strom_hash+shared_effective).encode()).hexdigest()
            newdocs[doc.rel.as_posix()]={"signature":podpis,"output":doc.vystup_rel.as_posix(),"outputs":sorted(doc_outputs),"index":idx_path.relative_to(STAV).as_posix()}
            outputs.update(doc_outputs); souhrn.prevedeno+=1; index_zmenen=True
            del raw, vys, page, content, chapters
        except (OSError, UnicodeError, ValueError, MemoryError) as e:
            souhrn.chyby+=1
            zprava=f"Dokument {doc.rel} ({doc.zdroj.suffix.casefold() or 'bez přípony'}) selhal ve fázi '{faze}': {type(e).__name__}: {e}"
            souhrn.varovani.append(zprava); logradky.append(zprava); vypis(zprava)
            idx_path=_index_cesta(doc.id)
            if old.get("trusted") and _zaznam_platny(prev,index_soubor=idx_path):
                newdocs[doc.rel.as_posix()]=prev; outputs.update(prev["outputs"]); index_cesty.append(idx_path)
            else:
                failed_docs[doc.rel.as_posix()]={"type":doc.zdroj.suffix.casefold() or "bez přípony","phase":faze,"error":type(e).__name__,"sourceSha256":stav.get("zdroj_otisk",{}).get("sha256","")}
            if isinstance(e,MemoryError): gc.collect()

    for f in sken.soubory:
        prev=old.get("standalone",{}).get(f.rel.as_posix(),{}); faze="zjišťování změn"
        try:
            otisk=_otisk_souboru(f.zdroj,stare_soubory,nove_soubory,vynutit=uplne or not old.get("trusted")); pub=Path("files")/(f.id+f.zdroj.suffix.casefold()); idx_path=_index_cesta(f.id)
            if not uplne and old.get("trusted") and prev.get("sha256")==otisk["sha256"] and _zaznam_platny(prev,index_soubor=idx_path):
                newstandalone[f.rel.as_posix()]=prev; outputs.update(prev["outputs"]); index_cesty.append(idx_path); continue
            faze="blokové kopírování"; atomicky_kopiruj(f.zdroj,WEB/pub,cilovy_koren=WEB)
            idx={"type":"file","typeLabel":"Soubor","title":f.nazev,"headings":"","text":f.nazev,"url":pub.as_posix(),"path":f.rel.as_posix(),"snippet":f"Samostatný soubor {f.nazev}"}
            faze="uložení položky fulltextu"; _uloz_index(f.id,idx); index_cesty.append(idx_path)
            zaznam={"sha256":otisk["sha256"],"output":pub.as_posix(),"outputs":[pub.as_posix()],"index":idx_path.relative_to(STAV).as_posix()}; newstandalone[f.rel.as_posix()]=zaznam; outputs.add(pub.as_posix()); index_zmenen=True
        except (OSError,ValueError,MemoryError) as e:
            zprava=f"Soubor {f.rel} selhal ve fázi '{faze}': {type(e).__name__}: {e}"; souhrn.varovani.append(zprava); logradky.append(zprava)
            idx_path=_index_cesta(f.id)
            if old.get("trusted") and _zaznam_platny(prev,index_soubor=idx_path): newstandalone[f.rel.as_posix()]=prev; outputs.update(prev["outputs"]); index_cesty.append(idx_path)
            if isinstance(e,MemoryError): gc.collect()
    page_outputs={"index.html","search.html",*(f"folders/{stabilni_id(folder,'folder')}.html" for folder in sken.slozky)}
    pages_changed=uplne or old.get("pageHash")!=page_hash or not all((WEB/rel).is_file() for rel in page_outputs)
    if pages_changed:
        # Stránky složek
        for folder in sorted(sken.slozky,key=razp):
            fid=stabilni_id(folder,"folder");relout=Path("folders")/f"{fid}.html";root="../";subs=sorted({p for p in sken.slozky if p.parent==folder and p!=folder},key=razp);docs=[d for d in sken.dokumenty if d.rel.parent==folder];files=[f for f in sken.soubory if f.rel.parent==folder]
            sec=[]
            if subs:sec.append('<section><h2>Podsložky</h2><ul>'+"".join(f'<li><a href="{stabilni_id(s,"folder")}.html">{_esc(s.name)}</a></li>' for s in subs)+"</ul></section>")
            obrazkove=[f for f in files if f.zdroj.suffix.casefold() in OBRAZKY]
            if obrazkove:
                tlacitka=[]
                for f in obrazkove:
                    pub=Path("files")/(f.id+f.zdroj.suffix.casefold());popis=samostatne_popisky.get(f.id,f.nazev);src=root+pub.as_posix()
                    tlacitka.append(f'<button type="button" class="nahled" data-gallery="{fid}" data-full="{_esc(src)}" data-alt="{_esc(popis)}"><img src="{_esc(src)}" alt="" loading="lazy"><span>{_esc(popis)}. Otevřít zvětšený obrázek.</span></button>')
                sec.append(f'<section><h2>Galerie</h2><div class="galerie-mrizka">{"".join(tlacitka)}</div></section>')
            items=[(d.nazev,root+d.vystup_rel.as_posix()) for d in docs]+[(f.nazev,root+(Path("files")/(f.id+f.zdroj.suffix.casefold())).as_posix()) for f in files if f.zdroj.suffix.casefold() not in OBRAZKY]
            if items:sec.append('<section><h2>Dokumenty a soubory</h2><ul>'+"".join(f'<li><a href="{_esc(u)}">{_esc(n)}</a></li>' for n,u in sorted(items,key=lambda x:razeni(x[0])))+"</ul></section>")
            title="Znalostní dokumenty" if folder==Path(".") else folder.name;content=f'<h1>{_esc(title)}</h1>'+"".join(sec)
            atomicky_zapis(WEB/relout,_page(template,vystup_rel=relout,title=title,db=db,content=content,sidebar=get_sidebar(root),breadcrumbs=_breadcrumbs(folder,title,root)))
        uvod_vys=preved_markdown((SYSTEM_DATA/"uvod.md").read_text(encoding="utf-8"));uvod=uvod_vys.html.replace("{{LINK:","").replace("}}","")
        atomicky_zapis(WEB/"index.html",_page(template,vystup_rel=Path("index.html"),title="Úvod",db=db,content=f'<article>{uvod}</article>',sidebar=get_sidebar(""),top=True))
        filters='<form id="filtry-hledani" action="search.html" method="get"><label for="dotaz-hledani">Hledaný výraz</label><input id="dotaz-hledani" name="q" type="search"><label for="typ-hledani">Typ výsledku</label><select id="typ-hledani" name="type"><option value="all">Vše</option><option value="document">Dokumenty</option><option value="file">Soubory</option><option value="project">Projekty</option><option value="web">Webové odkazy</option></select><button type="submit">Hledat</button></form><p id="souhrn-hledani" role="status" aria-live="polite"></p><div id="vysledky-hledani"></div><nav id="strankovani" class="strankovani" aria-label="Stránkování výsledků"></nav>'
        atomicky_zapis(WEB/"search.html",_page(template,vystup_rel=Path("search.html"),title="Výsledky hledání",db=db,content=f'<h1>Výsledky hledání</h1>{filters}',sidebar=get_sidebar(""),extra_head='<script defer src="js/search.js"></script>'))
    outputs.update(page_outputs)
    search_outputs={"search-index.json",*(f"search-data/{i:02d}.json" for i in range(32))}
    if index_zmenen or not all((WEB/p).is_file() for p in search_outputs):
        vypis("Sestavuji dělený fulltextový index..."); _vytvor_index(index_cesty,projekty,weby,outputs)
    else: outputs.update(search_outputs)
    manifest={"verze":2,"sharedHash":shared_effective,"sidebarHash":sidebar_hash,"pageHash":page_hash,"documents":newdocs,"failedDocuments":failed_docs,"standalone":newstandalone,"files":nove_soubory,"outputs":sorted(outputs)}
    zapis_json(STAV/"manifest.json",manifest,zaloha=False)
    if sken.uplny:
        for rel in set(old.get("outputs",[]))-outputs:
            if not rel:continue
            p=WEB/rel
            try:
                if je_uvnitr(p,WEB) and p.is_file():p.unlink();souhrn.odstraneno+=1
            except OSError as e:souhrn.varovani.append(f"Zastaralý výstup nelze odstranit {rel}: {e}")
    trvani=time.perf_counter()-zacatek
    logradky.extend(sken.konflikty+souhrn.varovani);logradky.append(f"Převedeno: {souhrn.prevedeno}; nezměněno: {souhrn.nezmeneno}; chyby: {souhrn.chyby}; odstraněno: {souhrn.odstraneno}; varování: {len(souhrn.varovani)+len(souhrn.konflikty)}; čas: {trvani:.2f} s")
    souhrn.log=zapis_log("prevod",logradky);return souhrn
