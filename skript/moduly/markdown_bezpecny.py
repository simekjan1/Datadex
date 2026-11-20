from __future__ import annotations

import html
import io
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit


BEZPECNE_EXTERNI = {"http", "https", "mailto"}
BEZPECNE_OBRAZKY = {""}
MAX_TEXT_CHARS = 64 * 1024 * 1024
REZERVOVANA_HTML_ID = {
    "app-zacatek", "hlavni-obsah", "bocni-navigace", "globalni-dotaz", "globalni-stav",
    "volba-motivu", "export-preferenci", "import-preferenci", "soubor-preferenci",
    "lightbox", "lightbox-obrazek", "lightbox-obrazek-obal", "lightbox-popis", "lightbox-poradi",
    "lightbox-predchozi", "lightbox-dalsi", "lightbox-priblizit", "lightbox-oddalit",
    "lightbox-obnovit", "lightbox-zavrit", "rezim-dokumentu", "nadpis-cteni", "hlas",
    "rychlost", "precist-dokument", "pozastavit-cteni", "obnovit-cteni", "zastavit-cteni",
    "stav-cteni", "nalezy", "panel-dokumenty", "panel-projekty", "panel-weby",
}


def odstran_diakritiku(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()


def slug(text: str) -> str:
    zaklad = re.sub(r"[^a-z0-9]+", "-", odstran_diakritiku(text)).strip("-")
    return zaklad or "sekce"


def bezpecna_url(url: str, *, obrazek: bool = False) -> str | None:
    url = html.unescape(url).strip()
    if not url or any(ord(c) < 32 for c in url):
        return None
    casti = urlsplit(url)
    povolene = BEZPECNE_OBRAZKY if obrazek else BEZPECNE_EXTERNI | {""}
    if casti.scheme.casefold() not in povolene or casti.netloc and casti.scheme == "":
        return None
    if casti.scheme == "" and (url.startswith(("/", "\\", "//")) or ".." in PurePosixPath(url.replace("\\", "/").split("#", 1)[0]).parts):
        return None
    return url


@dataclass
class Nadpis:
    uroven: int
    text: str
    identifikator: str


@dataclass
class VysledekMarkdown:
    html: str
    prosty_text: str
    nadpisy: list[Nadpis] = field(default_factory=list)
    obrazky: list[str] = field(default_factory=list)
    odkazy: list[str] = field(default_factory=list)
    galerie_povolena: bool = True


INLINE_TOKEN = re.compile(r"(!?\[[^\]\n]*\]\([^\)\n]+\)|`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|(?<!\*)\*[^*\n]+\*(?!\*)|(?<!_)_[^_\n]+_(?!_))")


def _inline(text: str, vysledek: VysledekMarkdown) -> str:
    casti = io.StringIO()
    pozice = 0
    for shoda in INLINE_TOKEN.finditer(text):
        casti.write(html.escape(text[pozice:shoda.start()]))
        token = shoda.group(0)
        if token.startswith("!["):
            m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", token)
            if m:
                alt, url = m.groups()
                bezpecna = bezpecna_url(url, obrazek=True)
                if bezpecna is not None and urlsplit(bezpecna).scheme == "":
                    vysledek.obrazky.append(bezpecna.split("#", 1)[0])
                    casti.write(f'<img src="{{{{MEDIA:{html.escape(bezpecna, quote=True)}}}}}" alt="{html.escape(alt, quote=True)}" loading="lazy">')
                elif bezpecna is not None:
                    casti.write(f'<img src="{html.escape(bezpecna, quote=True)}" alt="{html.escape(alt, quote=True)}" loading="lazy">')
                else:
                    casti.write(f'<span class="chyba-odkazu">[Nepovolený obrázek: {html.escape(alt)}]</span>')
        elif token.startswith("["):
            m = re.match(r"\[([^\]]*)\]\(([^)]+)\)", token)
            if m:
                popis, url = m.groups()
                bezpecna = bezpecna_url(url)
                if bezpecna is None:
                    casti.write(f'<span class="chyba-odkazu">{html.escape(popis)} (nepovolený odkaz)</span>')
                else:
                    vysledek.odkazy.append(bezpecna)
                    externi = urlsplit(bezpecna).scheme in BEZPECNE_EXTERNI
                    doplnek = ' target="_blank" rel="noopener noreferrer"' if externi else ""
                    upozorneni = '<span class="jen-odecitac"> (otevře se v nové kartě)</span>' if externi else ""
                    href = html.escape(bezpecna, quote=True) if externi else f"{{{{LINK:{html.escape(bezpecna, quote=True)}}}}}"
                    casti.write(f'<a href="{href}"{doplnek}>{html.escape(popis)}{upozorneni}</a>')
        elif token.startswith("`"):
            casti.write(f"<code>{html.escape(token[1:-1])}</code>")
        elif token.startswith(("**", "__")):
            casti.write(f"<strong>{html.escape(token[2:-2])}</strong>")
        else:
            casti.write(f"<em>{html.escape(token[1:-1])}</em>")
        pozice = shoda.end()
    casti.write(html.escape(text[pozice:]))
    return casti.getvalue()


def _frontmatter(text: str) -> tuple[str, bool]:
    if not text.startswith("---\n"):
        return text, True
    konec = text.find("\n---\n", 4)
    if konec < 0:
        return text, True
    hlavicka = text[4:konec]
    galerie = True
    for radek in hlavicka.splitlines():
        if ":" not in radek:
            continue
        klic, hodnota = (cast.strip().casefold() for cast in radek.split(":", 1))
        if klic == "galerie" and hodnota in {"false", "ne", "0"}:
            galerie = False
    return text[konec + 5 :], galerie


def preved_markdown(text: str) -> VysledekMarkdown:
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"Text je příliš velký pro bezpečný převod ({len(text)} znaků; limit {MAX_TEXT_CHARS}).")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text, galerie = _frontmatter(text)
    vysledek = VysledekMarkdown(html="", prosty_text="", galerie_povolena=galerie)
    radky = text.split("\n")
    vystup = io.StringIO()
    texty = io.StringIO()
    prvni_html = True
    prvni_text = True

    def html_radek(hodnota: str) -> None:
        nonlocal prvni_html
        if not prvni_html:
            vystup.write("\n")
        vystup.write(hodnota)
        prvni_html = False

    def prosty_radek(hodnota: str) -> None:
        nonlocal prvni_text
        if not prvni_text:
            texty.write("\n")
        texty.write(hodnota)
        prvni_text = False
    pouzite_id: dict[str, int] = {}
    obsazena_id = set(REZERVOVANA_HTML_ID)
    i = 0
    v_kodu = False
    kod = io.StringIO()
    jazyk = ""
    while i < len(radky):
        radek = radky[i]
        if radek.startswith("```"):
            if not v_kodu:
                v_kodu = True
                jazyk = re.sub(r"[^a-zA-Z0-9_-]", "", radek[3:].strip())
                kod = io.StringIO()
            else:
                cls = f' class="language-{jazyk}"' if jazyk else ""
                obsah_kodu = kod.getvalue()
                html_radek(f'<div class="obal-kodu"><pre><code{cls}>{html.escape(obsah_kodu)}</code></pre></div>')
                for kodovy_radek in obsah_kodu.split("\n"):
                    prosty_radek(kodovy_radek)
                v_kodu = False
            i += 1
            continue
        if v_kodu:
            if kod.tell():
                kod.write("\n")
            kod.write(radek)
            i += 1
            continue
        if i + 1 < len(radky) and "|" in radek and re.match(r"^\s*\|?\s*:?-{3,}", radky[i + 1]):
            hlavicky = [b.strip() for b in radek.strip().strip("|").split("|")]
            i += 2
            tab = io.StringIO()
            tab.write('<div class="obal-tabulky"><table><thead><tr>')
            for bunka in hlavicky:
                tab.write(f'<th scope="col">{_inline(bunka, vysledek)}</th>')
                prosty_radek(bunka)
            tab.write("</tr></thead><tbody>")
            while i < len(radky) and "|" in radky[i] and radky[i].strip():
                tab.write("<tr>")
                for bunka in (b.strip() for b in radky[i].strip().strip("|").split("|")):
                    tab.write(f"<td>{_inline(bunka, vysledek)}</td>")
                    prosty_radek(bunka)
                tab.write("</tr>")
                i += 1
            tab.write("</tbody></table></div>")
            html_radek(tab.getvalue())
            continue
        h = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", radek)
        if h:
            uroven = len(h.group(1))
            nazev = h.group(2)
            zaklad = slug(nazev)
            poradi = pouzite_id.get(zaklad, 0) + 1
            while True:
                ident = zaklad if poradi == 1 else f"{zaklad}-{poradi}"
                souvisejici = {ident, f"kapitola-{ident}", f"telo-{ident}"}
                if obsazena_id.isdisjoint(souvisejici):
                    obsazena_id.update(souvisejici)
                    break
                poradi += 1
            pouzite_id[zaklad] = poradi
            vysledek.nadpisy.append(Nadpis(uroven, re.sub(r"[*_`]", "", nazev), ident))
            html_radek(f'<h{uroven} id="{ident}">{_inline(nazev, vysledek)}</h{uroven}>')
            prosty_radek(nazev)
            i += 1
            continue
        if re.match(r"^\s*[-*+]\s+", radek):
            seznam = io.StringIO(); seznam.write("<ul>")
            while i < len(radky):
                m = re.match(r"^\s*[-*+]\s+(.*)$", radky[i])
                if not m:
                    break
                polozka = m.group(1)
                seznam.write(f"<li>{_inline(polozka, vysledek)}</li>")
                prosty_radek(polozka)
                i += 1
            seznam.write("</ul>")
            html_radek(seznam.getvalue())
            continue
        if re.match(r"^\s*\d+[.)]\s+", radek):
            seznam = io.StringIO(); seznam.write("<ol>")
            while i < len(radky):
                m = re.match(r"^\s*\d+[.)]\s+(.*)$", radky[i])
                if not m:
                    break
                polozka = m.group(1)
                seznam.write(f"<li>{_inline(polozka, vysledek)}</li>")
                prosty_radek(polozka)
                i += 1
            seznam.write("</ol>")
            html_radek(seznam.getvalue())
            continue
        if radek.startswith(">"):
            citace = []
            while i < len(radky) and radky[i].startswith(">"):
                citace.append(radky[i][1:].lstrip()); i += 1
            html_radek(f"<blockquote><p>{_inline(' '.join(citace), vysledek)}</p></blockquote>")
            for cast in citace:
                prosty_radek(cast)
            continue
        if not radek.strip():
            i += 1
            continue
        odstavec = [radek.strip()]
        i += 1
        while i < len(radky) and radky[i].strip() and not re.match(r"^(#{1,6})\s+|^\s*([-*+]\s+|\d+[.)]\s+|>|```)", radky[i]):
            if i + 1 < len(radky) and "|" in radky[i] and re.match(r"^\s*\|?\s*:?-{3,}", radky[i + 1]):
                break
            odstavec.append(radky[i].strip()); i += 1
        spojeny = " ".join(odstavec)
        html_radek(f"<p>{_inline(spojeny, vysledek)}</p>")
        prosty_radek(spojeny)
    if v_kodu:
        obsah_kodu = kod.getvalue()
        html_radek(f'<div class="obal-kodu"><pre><code>{html.escape(obsah_kodu)}</code></pre></div>')
        for kodovy_radek in obsah_kodu.split("\n"):
            prosty_radek(kodovy_radek)
    vysledek.html = vystup.getvalue()
    vysledek.prosty_text = texty.getvalue()
    return vysledek


def preved_txt(text: str) -> VysledekMarkdown:
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"Text je příliš velký pro bezpečný převod ({len(text)} znaků; limit {MAX_TEXT_CHARS}).")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    odstavce = re.split(r"\n\s*\n", text)
    html_casti = io.StringIO()
    prvni = True
    for odstavec in odstavce:
        if odstavec.strip():
            if not prvni:
                html_casti.write("\n")
            html_casti.write(f'<p>{html.escape(odstavec.strip()).replace(chr(10), "<br>")}</p>')
            prvni = False
    return VysledekMarkdown(html=html_casti.getvalue(), prosty_text=text)
