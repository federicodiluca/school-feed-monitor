// Prova il sito statico come lo vedrebbe un browser: filtri delle notizie, scorciatoia per
// area, form unico del configuratore, cookie e link a Telegram. Lo lancia tests/test_site_js.py
// (che si salta se node o jsdom non ci sono).
//
//   node tests/site_check.js <cartella del sito generato>
const { JSDOM, VirtualConsole } = require("jsdom");
const fs = require("fs");
const path = require("path");

const SITE = process.argv[2];
const BASE = "https://esempio.github.io/school-feed-monitor";
const read = (p) => fs.readFileSync(path.join(SITE, p), "utf8");
const scripts = ["static/app.js", "static/area.js", "static/sources.js"].map(read);

function open(pagePath, url) {
  // jsdom non sa navigare: il salvataggio fa location.href = ... ed è normale che protesti
  const quiet = new VirtualConsole();
  quiet.on("jsdomError", (e) => { if (!/Not implemented: navigation/.test(e.message)) console.error(e.message); });
  const dom = new JSDOM(read(pagePath), { url, runScripts: "outside-only", pretendToBeVisual: true,
                                          virtualConsole: quiet });
  const w = dom.window;
  w.fetch = (u) => {
    const name = u.endsWith("news.json") ? "data/news.json" : "data/sources.json";
    return Promise.resolve({ json: () => Promise.resolve(JSON.parse(read(name))) });
  };
  const errors = [];
  w.addEventListener("error", (e) => errors.push(e.message));
  scripts.forEach((js) => { try { w.eval(js); } catch (e) { errors.push("eval: " + e.message); } });
  return { w, errors, doc: w.document };
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const click = (w, el) => el.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true }));

(async () => {
  let ok = true;
  const check = (name, cond, extra) => { console.log((cond ? "  OK   " : "  FALLITO ") + name + (extra ? " — " + extra : "")); if (!cond) ok = false; };

  // --- /notizie: filtri
  console.log("pagina /notizie");
  { const { w, errors, doc } = open("notizie/index.html", BASE + "/notizie");
    await wait(200);
    check("nessun errore JS", errors.length === 0, errors.join("; "));
    const count = doc.getElementById("news-count"), results = doc.getElementById("news-results");
    check("elenco renderizzato", results.querySelectorAll("li.news-card").length > 0, count.textContent);
    const before = results.querySelectorAll("li.news-card").length;
    const q = doc.querySelector("#news-filters [name=q]");
    q.value = "convocazione"; q.dispatchEvent(new w.Event("input", { bubbles: true }));
    await wait(200);
    const after = results.querySelectorAll("li.news-card").length;
    check("la ricerca filtra", after > 0 && after < before, `prima ${before}, dopo ${after} (${count.textContent})`);
    const sel = doc.querySelector("#news-filters [name=fonte]");
    const palermo = Array.from(sel.options).find(o => o.textContent.includes("Palermo"));
    q.value = ""; sel.value = palermo.value; sel.dispatchEvent(new w.Event("change", { bubbles: true }));
    await wait(200);
    const onlyOne = Array.from(results.querySelectorAll(".news-source")).every(e => e.textContent.includes("Palermo"));
    check("il filtro per fonte funziona", onlyOne && results.querySelectorAll("li.news-card").length > 0, count.textContent);
  }

  // --- /configura: area -> fonti -> salva -> telegram
  console.log("pagina /configura");
  { const { w, errors, doc } = open("configura/index.html", BASE + "/configura");
    await wait(100);
    check("nessun errore JS", errors.length === 0, errors.join("; "));
    const region = doc.querySelector('input[name=regions][value="Sicilia"]');
    region.checked = true; region.dispatchEvent(new w.Event("change", { bubbles: true }));
    const provFieldset = doc.querySelector('fieldset.provinces[data-region="Sicilia"]');
    check("le province della regione si mostrano", provFieldset && !provFieldset.hidden);
    const areaBtn = doc.querySelector('button[value="area"]');
    areaBtn.click ? areaBtn.click() : click(w, areaBtn);
    await wait(200);
    const checked = doc.querySelectorAll('input[name=sources]:checked').length;
    check("il pulsante area spunta le fonti", checked > 0, checked + " fonti");
    check("il contatore si aggiorna", doc.getElementById("sources-selected").textContent === String(checked));
    doc.getElementById("keywords").value = "A041, sostegno";
    doc.querySelector('button.primary[type=submit]').click();
    await wait(200);
    check("le preferenze finiscono nei cookie", /sfm_fonti=/.test(doc.cookie) && /sfm_parole=/.test(doc.cookie), doc.cookie.slice(0, 80));
    const tg = doc.querySelector('button[value="telegram"]');
    tg.click();
    await wait(200);
    const out = doc.getElementById("telegram-out");
    check("il link a Telegram compare", !out.hidden && /t\.me\/SfmBot\?start=C1/.test(out.innerHTML),
          (out.textContent.match(/\/start \S+/) || [""])[0]);
  }
  process.exit(ok ? 0 : 1);
})();
