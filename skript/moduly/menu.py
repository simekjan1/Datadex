from __future__ import annotations

import json
import time
from pathlib import Path

from .cesty import INTERNI, KOREN, LOGY, STAV, WEB, atomicky_kopiruj, nacti_json
from .galerie import dostupne_zalohy_popisku, obnov_popisky, uloz_popisky
from .konfigurace import SOUBORY, inicializuj, nacti_galerie, nacti_nastaveni, nacti_projekty, nacti_weby, uloz_kategorie, uloz_nastaveni, validuj_data
from .kontrola import zkontroluj
from .kopie import vytvor_cistou_kopii
from .markdown_bezpecny import bezpecna_url
from .model import skenuj
from .prevod import Souhrn, generuj
from .server import spust_server


def ano_ne(vyzva: str, vychozi: bool) -> bool:
    doplnek = "A/n" if vychozi else "a/N"
    while True:
        odpoved = input(f"{vyzva} [{doplnek}]: ").strip().casefold()
        if not odpoved:
            return vychozi
        if odpoved in {"a", "ano"}:
            return True
        if odpoved in {"n", "ne"}:
            return False
        print("Zadejte ano (a) nebo ne (n).")


def prvni_pruvodce() -> None:
    data = nacti_nastaveni()
    if data["pruvodce_dokoncen"]:
        return
    print("První spuštění znalostní databáze")
    print("Enter zachová uvedenou výchozí hodnotu.")
    nazev = input(f"Název databáze [{data['nazev']}]: ").strip()
    if nazev:
        data["nazev"] = nazev
    data["automaticke_galerie"] = ano_ne("Automaticky vytvářet galerie", data["automaticke_galerie"])
    data["kontrola_pri_startu"] = ano_ne("Při startu shrnout změny", data["kontrola_pri_startu"])
    data["pruvodce_dokoncen"] = True
    uloz_nastaveni(data)
    print("Průvodce byl dokončen. Identifikátor databáze zůstane při běžných převodech stejný.")


def spravuj_nastaveni() -> None:
    data = nacti_nastaveni()
    print(f"Aktuální název: {data['nazev']}")
    nazev = input("Nový název; Enter beze změny: ").strip()
    if nazev:
        data["nazev"] = nazev
    data["automaticke_galerie"] = ano_ne("Automatické galerie", data["automaticke_galerie"])
    data["kontrola_pri_startu"] = ano_ne("Kontrola změn při startu", data["kontrola_pri_startu"])
    uloz_nastaveni(data)
    print("Nastavení bylo bezpečně uloženo.")


def _bezpecna_adresa(text: str) -> str | None:
    return bezpecna_url(text)


def _vyber(seznam: list, vyzva: str) -> int | None:
    if not seznam:
        print("Seznam je prázdný.")
        return None
    for i, polozka in enumerate(seznam, 1):
        print(f"{i}. {polozka.get('nazev', '(bez názvu)')}")
    hodnota = input(f"{vyzva}; 0 = Zpět: ").strip()
    if hodnota == "0": return None
    try:
        index = int(hodnota) - 1
        if 0 <= index < len(seznam): return index
    except ValueError: pass
    print("Neplatná volba.")
    return None


def spravuj_kategorie(druh: str) -> None:
    while True:
        data = nacti_projekty() if druh == "projekty" else nacti_weby()
        print(f"\nSpráva: {'projekty a aplikace' if druh == 'projekty' else 'webové odkazy'}")
        print("1. Vypsat obsah\n2. Přidat kategorii\n3. Přejmenovat kategorii\n4. Odstranit kategorii\n5. Přidat položku\n6. Upravit položku\n7. Odstranit položku\n0. Zpět")
        volba = input("Volba: ").strip()
        if volba == "0": return
        if volba == "1":
            if not data["kategorie"]: print("Zatím nejsou žádné kategorie.")
            for kat in data["kategorie"]:
                print(f"Kategorie: {kat['nazev']}")
                for p in kat["polozky"]: print(f"  - {p['nazev']}")
        elif volba == "2":
            nazev=input("Název nové kategorie: ").strip()
            if nazev:data["kategorie"].append({"nazev":nazev,"polozky":[]});uloz_kategorie(druh,data);print("Kategorie přidána.")
        elif volba in {"3","4","5","6","7"}:
            ki=_vyber(data["kategorie"],"Vyberte kategorii")
            if ki is None:continue
            kat=data["kategorie"][ki]
            if volba=="3":
                n=input("Nový název; Enter beze změny: ").strip()
                if n:kat["nazev"]=n;uloz_kategorie(druh,data);print("Kategorie upravena.")
            elif volba=="4":
                if ano_ne(f"Opravdu odstranit kategorii '{kat['nazev']}' a její položky",False):del data["kategorie"][ki];uloz_kategorie(druh,data);print("Kategorie odstraněna.")
            elif volba=="5":
                p=_nacti_polozku(druh)
                if p:kat["polozky"].append(p);uloz_kategorie(druh,data);print("Položka přidána.")
            else:
                pi=_vyber(kat["polozky"],"Vyberte položku")
                if pi is None:continue
                if volba=="6":
                    p=_nacti_polozku(druh,kat["polozky"][pi])
                    if p:kat["polozky"][pi]=p;uloz_kategorie(druh,data);print("Položka upravena.")
                elif ano_ne(f"Opravdu odstranit '{kat['polozky'][pi]['nazev']}'",False):del kat["polozky"][pi];uloz_kategorie(druh,data);print("Položka odstraněna.")
        else: print("Neplatná volba.")


def _nacti_polozku(druh: str, puvodni: dict | None = None) -> dict | None:
    puvodni=puvodni or {};nazev=input(f"Název [{puvodni.get('nazev','')}]: ").strip() or puvodni.get("nazev","")
    if not nazev:print("Název je povinný.");return None
    popis=input(f"Krátký popis [{puvodni.get('popis','')}]: ").strip() or puvodni.get("popis","")
    if druh=="weby":
        url=input(f"URL [{puvodni.get('url','')}]: ").strip() or puvodni.get("url","")
        if _bezpecna_adresa(url) is None:print("URL není bezpečná. Povoleno je http, https, mailto nebo bezpečná relativní cesta.");return None
        return {"nazev":nazev,"url":url,"popis":popis}
    odkazy=[]
    if puvodni.get("odkazy") and ano_ne("Zachovat dosavadní odkazy",True):odkazy=list(puvodni["odkazy"])
    while True:
        if odkazy and not ano_ne("Přidat další odkaz",False):break
        url=input("URL nebo relativní cesta odkazu; Enter dokončí: ").strip()
        if not url:break
        if _bezpecna_adresa(url) is None:print("Adresa není bezpečná.");continue
        on=input("Název odkazu [Otevřít]: ").strip() or "Otevřít";odkazy.append({"nazev":on,"url":url})
        if len(odkazy)==1 and not ano_ne("Přidat další odkaz",False):break
    return {"nazev":nazev,"popis":popis,"odkazy":odkazy}


def spravuj_galerie() -> None:
    soubory=sorted([*(KOREN/"data/1. txt a md soubory").rglob("popisky.json"),*(KOREN/"data/ostatní").rglob("popisky.json")],key=lambda p:p.as_posix())
    idx=_vyber([{"nazev":str(p.relative_to(KOREN))} for p in soubory],"Vyberte soubor popisků")
    if idx is None:return
    cesta=soubory[idx]
    try:data=nacti_json(cesta,dict)
    except ValueError as e:
        print(e);zalohy=dostupne_zalohy_popisku(cesta)
        if not zalohy:print("Soubor nebyl změněn a není dostupná žádná platná záloha.");return
        print(f"Nalezena platná záloha: {zalohy[0]}")
        if ano_ne("Obnovit popisky z této zálohy a poškozený soubor zachovat v zálohách",False):
            obnov_popisky(cesta,zalohy[0]);print("Popisky byly obnoveny.")
        return
    polozky=list(data.items());pi=_vyber([{"nazev":k} for k,_ in polozky],"Vyberte obrázek")
    if pi is None:return
    nazev,nast=polozky[pi];popis=input(f"Popis [{nast.get('popis','')}]: ").strip()
    if popis:nast["popis"]=popis
    nast["zobrazit"]=ano_ne("Zobrazit v automatické galerii",bool(nast.get("zobrazit",True)))
    uloz_popisky(cesta,data);print("Popisek byl bezpečně uložen a původní verze zálohována.")


def zobraz_souhrn(s: Souhrn) -> None:
    print(f"Převedené: {s.prevedeno}")
    print(f"Nezměněné: {s.nezmeneno}")
    print(f"Chybové: {s.chyby}")
    print(f"Odstraněné výstupy: {s.odstraneno}")
    print(f"Varování a konflikty: {len(s.varovani)+len(s.konflikty)}")
    for text in s.konflikty+s.varovani:print(f"Varování: {text}")
    if s.log:print(f"Podrobný protokol: {s.log}")


def zmeny_pri_startu() -> None:
    data=nacti_nastaveni()
    if not data["kontrola_pri_startu"]:return
    sken=skenuj();manifest=STAV/"manifest.json"
    if not manifest.exists():print(f"Kontrola změn: nalezeno {len(sken.dokumenty)} dokumentů; web zatím nebyl vygenerován.")
    else:
        try:
            stav=nacti_json(manifest,dict);old=set(stav.get("documents",{}))|set(stav.get("failedDocuments",{}));current={d.rel.as_posix() for d in sken.dokumenty};print(f"Kontrola změn: nové nebo dosud neevidované {len(current-old)}, odstraněné {len(old-current)}. Změněný obsah se ověří při převodu.")
        except ValueError as e:print(f"Manifest nelze přečíst: {e}")
    if ano_ne("Chcete nyní převést změněné dokumenty",False):zobraz_souhrn(generuj())


def zobraz_logy() -> None:
    logs=sorted(LOGY.glob("*.txt"),key=lambda p:p.stat().st_mtime,reverse=True)
    if not logs:print("Zatím nejsou žádné protokoly.")
    else:
        for i,p in enumerate(logs[:10],1):print(f"{i}. {p.name}")
        idx=_vyber([{"nazev":p.name} for p in logs[:10]],"Vyberte protokol k zobrazení")
        if idx is not None:print(logs[idx].read_text(encoding="utf-8"))
    print("Nápověda a manuální testovací scénáře jsou v README.md.")


def hlavni_menu() -> None:
    inicializuj();over_konfigurace_interaktivne();prvni_pruvodce();zmeny_pri_startu()
    while True:
        print("\nHlavní menu")
        print("1. Otevřít databázi v prohlížeči.\n2. Převést pouze změněné dokumenty.\n3. Znovu vygenerovat celý web.\n4. Spravovat nastavení.\n5. Spravovat projekty a aplikace.\n6. Spravovat webové odkazy.\n7. Spravovat galerie a popisky.\n8. Zkontrolovat zdroje, odkazy a konfiguraci.\n9. Zobrazit protokoly a nápovědu.\n10. Vytvořit čistou kopii databáze.\n11. Ukončit.")
        volba=input("Volba: ").strip()
        try:
            if volba=="1":
                if not (WEB/"index.html").exists():print("Web ještě není vygenerován; nejprve proběhne úplné vytvoření.");zobraz_souhrn(generuj(uplne=True))
                spust_server()
            elif volba=="2":zobraz_souhrn(generuj())
            elif volba=="3":zobraz_souhrn(generuj(uplne=True))
            elif volba=="4":spravuj_nastaveni()
            elif volba=="5":spravuj_kategorie("projekty")
            elif volba=="6":spravuj_kategorie("weby")
            elif volba=="7":spravuj_galerie()
            elif volba=="8":
                zpravy,log=zkontroluj()
                for z in zpravy:print(z)
                print(f"Protokol: {log}")
            elif volba=="9":zobraz_logy()
            elif volba=="10":
                print("Čistá kopie je nová prázdná databáze, nikoli záloha současných dat.")
                nazev=input("Název nové složky vedle této databáze; Enter zruší: ").strip()
                if nazev and ano_ne(f"Vytvořit prázdnou databázi '{nazev}'",False):print(f"Čistá kopie byla vytvořena: {vytvor_cistou_kopii(nazev)}")
            elif volba=="11":print("Program byl ukončen.");return
            else:print("Neplatná volba.")
        except (OSError,ValueError,FileExistsError,MemoryError) as e:print(f"Operaci nelze dokončit ({type(e).__name__}): {e}")


def over_konfigurace_interaktivne() -> None:
    nacitace={"nastaveni":nacti_nastaveni,"projekty":nacti_projekty,"weby":nacti_weby,"galerie":nacti_galerie}
    for druh,nacitac in nacitace.items():
        try:
            nacitac();continue
        except (ValueError,OSError) as chyba:
            print(f"Konfigurace '{druh}' je poškozená: {chyba}")
        cesta=SOUBORY[druh];zaloha=cesta.with_suffix(cesta.suffix+".bak")
        try:
            data=nacti_json(zaloha,dict);validuj_data(druh,data)
        except (ValueError,OSError,FileNotFoundError):
            print("Platná automatická záloha není dostupná. Soubor zůstal beze změny.")
            raise ValueError(f"Konfiguraci {cesta} je nutné opravit nebo obnovit z vlastní zálohy.")
        if not ano_ne(f"Obnovit '{cesta.name}' z platné zálohy '{zaloha.name}'",False):
            raise ValueError(f"Obnova {cesta.name} byla zrušena; poškozený soubor zůstal beze změny.")
        archiv=INTERNI/"zalohy_poskozenych_json"/(time.strftime("%Y%m%d-%H%M%S")+f"-{druh}.json")
        if cesta.exists():atomicky_kopiruj(cesta,archiv)
        atomicky_kopiruj(zaloha,cesta);nacitac();print(f"Konfigurace '{druh}' byla obnovena; poškozená verze je v {archiv}.")
