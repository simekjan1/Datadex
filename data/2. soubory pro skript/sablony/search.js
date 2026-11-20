(() => {
  "use strict";
  const form = document.getElementById("filtry-hledani");
  const results = document.getElementById("vysledky-hledani");
  const summary = document.getElementById("souhrn-hledani");
  const pages = document.getElementById("strankovani");
  if (!form) return;

  const params = new URLSearchParams(location.search);
  const q = params.get("q") || "";
  const type = params.get("type") || "all";
  const page = Math.max(1, Number(params.get("page")) || 1);
  form.elements.q.value = q;
  form.elements.type.value = type;
  const fold = value => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("cs");
  const escape = value => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const makeUrl = p => {
    const url = new URL(location.href);
    url.search = p.toString();
    return url.pathname + "?" + url.searchParams.toString();
  };
  const terms = fold(q).trim().split(/\s+/).filter(Boolean);
  if (!terms.length) {
    summary.textContent = "Zadejte hledaný výraz.";
    return;
  }

  const found = [];
  const scoreItem = item => {
    if (type !== "all" && item.type !== type) return;
    const title = fold(item.title);
    const headings = fold(item.headings);
    const body = fold(item.text);
    const all = `${title} ${headings} ${body}`;
    if (!terms.every(term => all.includes(term))) return;
    let score = 0;
    let count = 0;
    for (const term of terms) {
      const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const occurrences = (all.match(new RegExp(escaped, "g")) || []).length;
      count += occurrences;
      score += (title.includes(term) ? 100 : 0) + (headings.includes(term) ? 30 : 0) + occurrences;
    }
    found.push({...item, score, count});
  };

  const render = () => {
    found.sort((a, b) => b.score - a.score || b.count - a.count || a.title.localeCompare(b.title, "cs"));
    const total = Math.ceil(found.length / 20);
    const current = Math.min(page, Math.max(1, total));
    const start = (current - 1) * 20;
    const slice = found.slice(start, start + 20);
    summary.textContent = `Nalezeno ${found.length} výsledků. Stránka ${current} z ${Math.max(1, total)}.`;
    results.innerHTML = slice.map(item => {
      const external = /^(https?:|mailto:)/i.test(item.url);
      const attrs = external ? ' target="_blank" rel="noopener noreferrer"' : "";
      const note = external ? '<span class="jen-odecitac"> (otevře se v nové kartě)</span>' : "";
      const documentQuery = item.type === "document" ? "?q=" + encodeURIComponent(q) : "";
      return `<article class="vysledek"><h2><a href="${escape(item.url)}${documentQuery}"${attrs}>${escape(item.title)}${note}</a></h2><p><strong>Typ:</strong> ${escape(item.typeLabel)}. <strong>Cesta:</strong> ${escape(item.path)}</p><p>${escape(item.snippet)}</p><p>Počet výskytů: ${item.count}</p></article>`;
    }).join("") || "<p>Žádný výsledek neodpovídá dotazu a filtru.</p>";
    pages.innerHTML = "";
    const add = (label, number, currentPage = false) => {
      const element = document.createElement(currentPage ? "span" : "a");
      element.textContent = label;
      if (currentPage) element.setAttribute("aria-current", "page");
      else {
        const p = new URLSearchParams(params);
        p.set("page", String(number));
        element.href = makeUrl(p);
      }
      pages.append(element);
    };
    if (current > 1) add("Předchozí", current - 1);
    for (let number = 1; number <= total; number++) add(String(number), number, number === current);
    if (current < total) add("Další", current + 1);
  };

  (async () => {
    const response = await fetch("search-index.json", {cache: "no-store"});
    if (!response.ok) throw new Error("Index hledání není dostupný.");
    const index = await response.json();
    if (index.version !== 2 || !Array.isArray(index.shards)) throw new Error("Index hledání má nepodporovaný formát.");
    for (let number = 0; number < index.shards.length; number++) {
      summary.textContent = `Prohledávám část ${number + 1} z ${index.shards.length}…`;
      const shardResponse = await fetch(index.shards[number], {cache: "no-store"});
      if (!shardResponse.ok) throw new Error(`Část indexu ${number + 1} není dostupná.`);
      const items = await shardResponse.json();
      if (!Array.isArray(items)) throw new Error(`Část indexu ${number + 1} je poškozená.`);
      for (const item of items) scoreItem(item);
    }
    render();
  })().catch(error => {
    summary.textContent = "Hledání selhalo: " + error.message;
    summary.classList.add("chyba");
  });
})();
