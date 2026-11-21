# Znalostní databáze

Lokální přenositelná znalostní databáze pro Windows a Linux. Zdrojové dokumenty zůstávají v `data/1. txt a md soubory`, Python z nich vytvoří statický web v `web/` a zpřístupní jej pouze na adrese `127.0.0.1`. Běžný provoz nepoužívá internet, účet, cloud ani telemetrii.

## První spuštění

### Windows

1. Otevřete kořenovou složku databáze.
2. Doporučeně spusťte `py -3 instalovat.py`. Vytvoří se pouze místní `.venv` uvnitř databáze; nic se neinstaluje globálně.
3. Spusťte `Spustit.bat`.
4. Průvodce se zeptá na název databáze, automatické galerie a kontrolu změn při startu. Enter zachová nabídnutou hodnotu.
5. V hlavním menu zvolte `3. Znovu vygenerovat celý web`.
6. Zvolte `1. Otevřít databázi v prohlížeči`.
7. Server ukončíte klávesami Ctrl+C; poté se vrátíte do menu.

`Spustit.bat` upřednostní `.venv\Scripts\python.exe`, potom hledá `py -3` a `python`. Instalátor vyžaduje Python 3.10 nebo novější, je bezpečně opakovatelný a používá pevný seznam `requirements.lock`. Tato verze nemá žádné externí balíčky, takže nic nestahuje. Případné budoucí závislosti se instalují výhradně do `.venv`; při běžném startu se balíčky nekontrolují ani neaktualizují. Kontrolu bez změn provede `py -3 instalovat.py --check`, opravu prostředí `py -3 instalovat.py --repair`.

### Linux a další platformy

Je vyžadován Python 3.10 nebo novější. Z kořene nejprve vytvořte izolované prostředí a poté spusťte aplikaci:

```text
python3 -B instalovat.py
.venv/bin/python -B skript/cms.py
```

Kořen aplikace se odvozuje od umístění `cms.py`, takže příkaz lze spustit i z jiné pracovní složky s úplnou cestou ke skriptu.

Pro neinteraktivní správu jsou k dispozici:

```text
.venv/bin/python -B skript/cms.py --init
.venv/bin/python -B skript/cms.py --build
.venv/bin/python -B skript/cms.py --full
.venv/bin/python -B skript/cms.py --check
```

`--build` převádí pouze změněné dokumenty; `--full` vynutí úplnou regeneraci.

Výstupy se nepřepisují přímo: každý nový soubor vznikne nejprve jako dočasný soubor ve stejné složce, zapíše se na disk a až potom se nejvýše třemi pokusy atomicky nahradí. Binární soubory se kopírují po blocích 1 MiB, takže ani velké video není celé v paměti; při chybě zůstane starý cíl zachován. Manifest se publikuje až po stránkách a fulltextu. Selhání jednoho dokumentu zachová jeho poslední platnou stránku i indexovou položku a nezastaví ostatní dokumenty.

Přírůstkový běh nejprve porovnává velikost a čas změny se dříve ověřeným SHA-256. Nezměněný dokument se vůbec neparsuje a jeho přílohy se nekopírují. Změna zdroje, přílohy, `popisky.json`, šablony, úvodního textu nebo konfigurace vyvolá odpovídající nové sestavení. Úplný běh `--full` znovu ověří obsahové otisky všech souborů. Textový dokument má bezpečnostní limit 64 milionů znaků a 256 MiB na vstupu; při překročení se nic netruncuje, ale soubor je uveden jako chyba s fází zpracování.

## Konzolové menu

Menu umožňuje otevřít web, inkrementální a úplný převod, správu nastavení, projektů, webových odkazů a popisků galerií, kontrolu zdrojů a odkazů, zobrazení protokolů a vytvoření čisté databáze. Podmenu používají `0 = Zpět`; odstranění a jiné významné operace vyžadují potvrzení.

JSON se zapisuje přes dočasný soubor ve stejné složce a atomické nahrazení. Před změnou běžné konfigurace vzniká `.bak`. Poškozený JSON se automaticky nepřepíše; interaktivní menu nabídne obnovu pouze z platné zálohy a poškozenou verzi zachová v `interni/zalohy_poskozenych_json`. Popisky obrázků mají samostatné historické zálohy v `interni/zalohy_popisku`.

## Dokumenty, přílohy a soubory

- `.md` a `.txt` vkládejte do `data/1. txt a md soubory`, libovolně do podsložek.
- TXT se zobrazuje jako prostý text s odstavci. Nevytvářejí se z něj falešné kapitoly.
- Dokument `Klasická masáž.md` může mít vedle sebe složku `Klasická masáž`. Ta je jeho složkou příloh. Vnořené TXT a MD jsou přílohy, nikoli samostatné články.
- Samostatné soubory patří do běžné hierarchie nebo do `data/ostatní`. Zobrazí se ve společné knihovně, nikoli ve čtvrtém panelu.
- Povolené veřejné typy příloh zahrnují běžné dokumenty, kancelářské soubory, archivy, obrázky, zvuk a video. Aktivní typy jako HTML, JavaScript, SVG, spustitelné a skriptové soubory se z bezpečnostních důvodů nepublikují.
- Zdrojové soubory se při převodu nepřejmenovávají, nepřesouvají ani obsahově neupravují.

### Lokální HTML aplikace v panelu projektů

Výjimkou z obecného zákazu aktivních příloh je sedm výslovně schválených HTML aplikací uvedených v `projekty.json`: Adresář, Palpatius, Knihovna, Phasmarium, TextBox, masazesimek.cz a vidimtojinak. Při inkrementálním i úplném převodu se jejich bezpečné statické soubory kopírují do stejné relativní cesty pod `web/`, takže fungují místní HTML stránky, CSS, JavaScript, obrázky, ikony, fonty a bezpečné datové JSON/CSV soubory. Zdrojové projekty se nemění.

Publikátor nepřenáší vývojové poznámky, uživatelské složky, `popisky.json`, soukromé konfigurace, databáze, klíče, archivy, Markdown/TXT dokumentaci ani `.bat`, `.cmd`, `.exe`, `.py` a jiné programové soubory. Jiné HTML projekty se automaticky nezveřejní. Po změně souborů schválené aplikace stačí spustit „Převést pouze změněné dokumenty“; úplná regenerace není nutná.

Lokální server nespouští backend a odmítá HTTP POST. Část webu, která závisí na Netlify formuláři, vzdáleném CDN, analytice, komentářové službě nebo jiném internetu, proto nemusí lokálně fungovat; vlastní místní stránky a soubory zůstávají dostupné. Databáze kvůli tomu žádnou vzdálenou službu sama nekontaktuje a vzdálené skripty jsou její bezpečnostní politikou blokované.

Převodník ze standardní knihovny podporuje ATX nadpisy H1–H6, odstavce, bezpečné odkazy a obrázky, tučné a kurzívní písmo, inline i oplocené bloky kódu, jednoduché číslované a nečíslované seznamy, citace a běžné pipe tabulky. Surové HTML se úmyslně escapuje. V první verzi nejsou plně podporovány vnořené seznamy, referenční odkazy, poznámky pod čarou, rozšíření jednotlivých Markdown implementací ani složité tabulky s escapovanými svislítky.

Interní relativní odkazy se otevírají ve stejné kartě. HTTP, HTTPS a e-mailové odkazy se otevírají v nové kartě s přístupným upozorněním. Nebezpečné protokoly a cesty opouštějící povolený kořen jsou odmítnuty.

## Galerie

Obrázky JPG/JPEG, PNG, GIF a WebP se rozpoznávají podle přípony i skutečné hlavičky souboru. Název složky nerozhoduje.

- Každá obrázková podsložka příloh je samostatná galerie.
- Obrázky přímo v hlavní složce příloh jsou v galerii „Ostatní obrázky“.
- Samostatné obrázky v běžné složce se zobrazí jako galerie na stránce této složky.
- Obrázek vložený přímo v Markdownu se v automatické galerii neopakuje.
- Frontmatter `galerie: false` vypne automatické galerie konkrétního článku, ne však výslovně vložené obrázky.
- Globální automatické galerie lze vypnout v nastavení.

V každé složce s obrázky vzniká `popisky.json`. Nová položka dostane pouze popis odvozený z názvu souboru a `zobrazit: true`. Ruční text i viditelnost se zachovávají. `zobrazit: false` skryje nepoužitý obrázek a takový obrázek se nekopíruje do `web/`. Poškozený `popisky.json` se nepřepíše a bez spolehlivé informace o viditelnosti se jeho automatické obrázky nepublikují.

Lightbox se ovládá Enterem, Escapem, šipkami, kolečkem a tlačítky. Escape vrací fokus na původní náhled. `Ctrl+kolečko` zůstává prohlížeči. Zoom lightboxu mění jen obrázek.

## Čtení, kapitoly a hlas

Kompletní dokument je vždy výchozí a celý zůstává čitelný i bez JavaScriptu. U Markdownu s více skutečnými nadpisy lze zapnout režim „Podle kapitol“ a otevřít více kapitol současně. Stav se ukládá zvlášť pro každý dokument.

Tlačítko „Přečíst dokument“ používá standardní `SpeechSynthesis` prohlížeče. U kapitol je „Přečíst kapitolu“. Lze zvolit hlas, rychlost, pauzu, pokračování a zastavení. Čtení probíhá po kratších úsecích a nečte navigaci ani ovládací prvky. Zvolený hlas a rychlost se pamatují. Dostupnost hlasu a jeho skutečný offline provoz určuje prohlížeč a operační systém; aplikace nepoužívá cloudovou syntézu a neslibuje offline dostupnost konkrétního hlasu.

## Hledání

Pole v hlavičce hledá po Enteru nebo tlačítku. Index zahrnuje dokumenty, nadpisy, celý text, samostatné soubory, projekty a webové odkazy. Je rozdělen do 32 částí v `web/search-data`; prohlížeč je načítá a prohledává postupně, takže nedochází k nouzovému omezení pouze na názvy. Hledání nerozlišuje velikost písmen ani českou diakritiku. Výsledky mají typové filtry, řazení podle názvu, nadpisu, těla a počtu výskytů a stránkování po 20 položkách. Dotaz, filtr a stránka jsou v URL, takže funguje přirozená historie prohlížeče.

Po otevření dokumentu z hledání se zvýrazní všechny výskyty. Tlačítka „Předchozí výskyt“ a „Další výskyt“ procházejí cyklicky, otevřou potřebnou kapitolu a nastaví fokus na výskyt. Cesta dokumentu v pravém stromu se rozbalí, ostatní větve zůstanou beze změny.

## Motivy, IndexedDB a přenos preferencí

K dispozici je automatický, světlý a tmavý motiv. IndexedDB uchovává pouze uživatelské preference rozhraní: motiv, rozbalení panelů, režimy a kapitoly dokumentů, hlas a rychlost čtení. Zdrojové dokumenty v ní nejsou.

Každá databáze má vlastní UUID; klíče IndexedDB jsou tímto ID oddělené i při stejném portu. Pod pravými panely jsou tlačítka pro export a import čitelného JSON. Import ověří formát, verzi, velikost, typy a ID. Před nahrazením vyžádá potvrzení; cizí ID vyžaduje ještě samostatný souhlas. Změny probíhají v jedné transakci. Když IndexedDB není dostupná, web zůstává čitelný a oznámí, že se preference neuloží.

Zkopírování složky databáze nepřenese profil prohlížeče ani IndexedDB. Preference přeneste samostatným exportem a importem.

## Server a bezpečnost

Server zkouší pouze `127.0.0.1` a porty 8765 až 8769. Servíruje výhradně `web/`, nevypisuje složky, nepřijímá uploady a kontroluje traversal i symlink únik. Posílá restriktivní CSP, `nosniff` a další bezpečnostní hlavičky. Zdrojové `data/`, kód, konfigurace, `pokyny.md`, logy a cesty nad `web/` nejsou dostupné.

## Přenos celé databáze a čistá kopie

Pro přenos stejné databáze zastavte server a celý kořen ručně zkopírujte. Zachová se stejné ID, dokumenty i konfigurace. IndexedDB přeneste zvlášť.

Volba „Vytvořit čistou kopii databáze“ vytvoří po potvrzení novou složku vedle aktuální databáze. Kopíruje pouze pevně vyjmenovaný programový kód a šablony, vytvoří prázdné zdroje a výchozí JSON s novým ID. Nekopíruje dokumenty, projekty, odkazy, galerie, logy, index ani preference. Existující cílovou složku nikdy nepřepíše. Nejde o zálohu.

## Protokoly, kontrola a řešení potíží

Textové protokoly jsou v `interni/logy`. Volba kontroly ověřuje JSON, čitelnost zdrojů, konflikty příloh, interní odkazy, chybějící cíle a symlink úniky. Zdrojové dokumenty neopravuje.

- Pokud jsou porty 8765–8769 obsazené, ukončete jiný místní server a zkuste otevření znovu.
- Poškozený JSON neopravujte naslepo. V menu použijte nabízenou platnou zálohu; není-li dostupná, obnovte vlastní kopii.
- Pokud převod jednoho dokumentu selže, ostatní pokračují a poslední platná stránka problematického dokumentu zůstane zachována. Podrobnost je v protokolu.
- Protokol uvádí relativní cestu, typ souboru a fázi selhání, nikoli obsah dokumentu. `MemoryError` se zachytí stejně jako chyba disku, oprávnění nebo UTF-8.
- Neplatné UTF-8 uložte z editoru znovu jako UTF-8. Program zdroj automaticky nepřekóduje.
- Když se prohlížeč neotevře, zkopírujte vypsanou adresu `http://127.0.0.1:PORT/`.
- Po přerušeném sestavení spusťte `--build` znovu. Dočasné soubory patří pouze do projektu a starý manifest i hotové cíle zůstávají použitelné. Pokud je manifest poškozený, další běh jej nedůvěryhodně nepoužije a bezpečně jej znovu vytvoří.
- Když `.venv` chybí nebo je poškozené, spusťte `instalovat.py --repair`. Instalátor nemaže uživatelská data. Ruční odstranění `.venv` je možné až po ukončení aplikace; jde pouze o odvoditelné programové prostředí.

## Testy

Automatické testy používají pouze `unittest` ze standardní knihovny a izolovanou kopii v `testy/_pracovni`. Na Windows PowerShell je spusťte z kořene takto:

```text
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPYCACHEPREFIX="$PWD\interni\pycache"
$env:TEMP="$PWD\interni\docasne"
$env:TMP=$env:TEMP
python -B -m unittest discover -s testy -p 'test_*.py' -v
```

Testy navíc pokrývají prázdné značky seznamu, 50 000 položek, velké tabulky a bloky kódu, blokovou kopii velkého binárního souboru, zachování cíle při simulované chybě, přírůstkovost zdrojů/příloh/popisků, poškozený manifest, dělený fulltext, zachycení `MemoryError` a vytvoření `.venv`. Manuální scénáře pro NVDA, fokus, zoom, lightbox, SpeechSynthesis, import a vypnutý JavaScript jsou v `testy/MANUALNI_TESTY.md`. Automatické testy nenahrazují skutečné ověření NVDA, různých prohlížečů, hlasů ani Lupy Windows.
