// Prova il sito statico come lo vedrebbe un browser: filtri delle notizie, scorciatoia per
// area, form unico del configuratore, cookie e link a Telegram. Lo lancia tests/test_site_js.py
// (che si salta se node o jsdom non ci sono).
//
//   node tests/site_check.js <cartella del sito generato>
const { JSDOM, VirtualConsole, CookieJar } = require("jsdom");
const fs = require("fs");
const path = require("path");

const SITE = process.argv[2];
const BASE = "https://esempio.github.io/school-feed-monitor";
const read = (p) => fs.readFileSync(path.join(SITE, p), "utf8");
const scripts = ["static/app.js", "static/area.js", "static/sources.js"].map(read);

function open(pagePath, url, cookieJar) {
  // jsdom non sa navigare: il salvataggio fa location.href = ... ed è normale che protesti
  const quiet = new VirtualConsole();
  quiet.on("jsdomError", (e) => { if (!/Not implemented: navigation/.test(e.message)) console.error(e.message); });
  const dom = new JSDOM(read(pagePath), { url, runScripts: "outside-only", pretendToBeVisual: true, cookieJar,
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
  const jar = new CookieJar();
  { const { w, errors, doc } = open("configura/index.html", BASE + "/configura/", jar);
    await wait(100);
    check("nessun errore JS", errors.length === 0, errors.join("; "));
    check("niente pulsanti «Salva» né «Spunta»: si salva da solo",
          !doc.querySelector('button[value="area"]') && doc.querySelectorAll("#fonti button[type=submit]").length === 1);
    const region = doc.querySelector('input[name=regions][value="Sicilia"]');
    region.checked = true; region.dispatchEvent(new w.Event("change", { bubbles: true }));
    const provFieldset = doc.querySelector('fieldset.provinces[data-region="Sicilia"]');
    check("le province della regione si mostrano", provFieldset && !provFieldset.hidden);
    await wait(200);
    const checked = doc.querySelectorAll('input[name=sources]:checked').length;
    check("spuntare la regione spunta subito le sue fonti", checked > 0, checked + " fonti");
    check("il contatore si aggiorna", doc.getElementById("sources-selected").textContent === String(checked));
    check("e le salva nei cookie senza premere nulla", /sfm_fonti=/.test(doc.cookie), doc.cookie.slice(0, 60));
    check("lo stato dice che è salvato", /Salvato/.test(doc.getElementById("save-status").textContent));

    const palermo = doc.querySelector('input[name=provinces][value="Sicilia|Palermo"]');
    palermo.checked = true; palermo.dispatchEvent(new w.Event("change", { bubbles: true }));
    await wait(200);
    const names = Array.from(doc.querySelectorAll('input[name=sources]:checked')).map(b => b.parentNode.textContent);
    check("scegliere una provincia lascia solo il suo USP", names.some(n => /Palermo/.test(n)) && !names.some(n => /USP Catania/.test(n)),
          names.length + " fonti");

    const one = doc.querySelector('input[name=sources]:not(:checked)');
    one.checked = true; one.dispatchEvent(new w.Event("change", { bubbles: true }));
    await wait(50);
    check("un clic su una fonte si salva subito", decodeURIComponent(doc.cookie).includes(one.value));

    const kw = doc.getElementById("keywords");
    kw.value = "A041, sostegno"; kw.dispatchEvent(new w.Event("input", { bubbles: true }));
    await wait(700);
    check("le parole chiave si salvano mentre scrivi", /sfm_parole=A041/.test(doc.cookie), doc.cookie.slice(0, 120));
    const ex = doc.getElementById("excluded");
    ex.value = "Convocazione"; ex.dispatchEvent(new w.Event("input", { bubbles: true }));
    await wait(700);
    check("anche le parole da escludere", /sfm_escludi=Convocazione/.test(doc.cookie));

    const group = Array.from(doc.querySelectorAll("details.source-group"))
      .find(g => g.querySelector("input[name=sources]:not(:checked)"));
    const before = doc.cookie;
    group.querySelector('[data-group-all="1"]').click();
    await wait(50);
    check("«tutte» di un gruppo si salva", doc.cookie !== before);

    const tg = doc.querySelector('button[value="telegram"]');
    tg.click();
    await wait(200);
    const out = doc.getElementById("telegram-out");
    check("il link a Telegram compare", !out.hidden && /t\.me\/SfmBot\?start=C1/.test(out.innerHTML),
          (out.textContent.match(/\/start \S+/) || [""])[0]);
    const code = (out.textContent.match(/\/start (\S+)/) || [])[1] || "";
    const raw = Buffer.from(code.slice(2).replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("latin1");
    check("le parole escluse viaggiano nel link o come comando", /-Convocazione/.test(raw) || /\/exclude Convocazione/.test(out.textContent));
  }

  // riaprendo la pagina (stessi cookie), fonti, parole e aree salvate tornano com'erano
  { const { errors, doc } = open("configura/index.html", BASE + "/configura/", jar);
    await wait(200);
    check("nessun errore JS alla riapertura", errors.length === 0, errors.join("; "));
    check("le parole chiave tornano", doc.getElementById("keywords").value === "A041, sostegno");
    check("e le parole escluse", doc.getElementById("excluded").value === "Convocazione");
    check("la regione torna spuntata", doc.querySelector('input[name=regions][value="Sicilia"]').checked);
    check("e anche la provincia scelta", doc.querySelector('input[name=provinces][value="Sicilia|Palermo"]').checked &&
          !doc.querySelector('input[name=provinces][value="Sicilia|Catania"]').checked);
  }
  // /le-mie-notizie con le stesse preferenze: niente notizie con parole escluse
  console.log("pagina /le-mie-notizie");
  { const { errors, doc } = open("le-mie-notizie/index.html", BASE + "/le-mie-notizie/", jar);
    await wait(200);
    check("nessun errore JS", errors.length === 0, errors.join("; "));
    const titles = Array.from(doc.querySelectorAll("#mine-results .news-title")).map(e => e.textContent);
    check("ci sono le notizie delle fonti scelte", titles.length > 0, titles.length + " notizie");
    check("ma non quelle con parole escluse", !titles.some(t => /Convocazione/.test(t)));
    check("e l'intro lo dice", /senza quelle che parlano di/.test(doc.getElementById("mine-intro").textContent));
  }
  process.exit(ok ? 0 : 1);
})();
