// Logica del sito. Due modalità:
//  - servito da Flask: qui serve solo il service worker, il resto lo fa il server;
//  - sito statico su GitHub Pages (body[data-static]): preferenze, filtri, configuratore
//    e link a Telegram girano tutti nel browser, sui dati di data/*.json.
(function () {
  var body = document.body;
  var BASE = (body && body.dataset.base) || "";
  var STATIC = !!(body && body.dataset.static);
  var BOT = (body && body.dataset.bot) || "";

  // --- service worker (PWA): richiede HTTPS, su http://IP viene ignorato ---------------
  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register(BASE + "/sw.js").catch(function () { /* niente PWA, pazienza */ });
    });
  }
  if (!STATIC) return;

  // --- preferenze nei cookie (stessi nomi del server: sfm_fonti, sfm_parole) ------------
  var YEAR = 60 * 60 * 24 * 365;

  function readCookie(name) {
    var hit = document.cookie.split("; ").find(function (c) { return c.indexOf(name + "=") === 0; });
    if (!hit) return [];
    var raw = hit.slice(name.length + 1).replace(/^"|"$/g, "");
    return raw.split(",").map(function (v) {
      try { return decodeURIComponent(v.replace(/\\054/g, ",")).trim(); } catch (e) { return v.trim(); }
    }).filter(Boolean);
  }

  function writeCookie(name, values) {
    var secure = location.protocol === "https:" ? "; Secure" : "";
    if (!values.length) {
      document.cookie = name + "=; Max-Age=0; Path=/; SameSite=Lax" + secure;
      return;
    }
    var value = values.map(function (v) { return encodeURIComponent(v); }).join(",");
    document.cookie = name + "=" + value + "; Max-Age=" + YEAR + "; Path=/; SameSite=Lax" + secure;
  }

  var prefs = {
    sources: function () { return readCookie("sfm_fonti").map(Number).filter(function (n) { return !isNaN(n); }); },
    keywords: function () { return readCookie("sfm_parole").slice(0, 30); },
    save: function (sources, keywords) {
      writeCookie("sfm_fonti", sources.map(String));
      writeCookie("sfm_parole", keywords);
    },
    forget: function () { prefs.save([], []); }
  };

  // --- dati -----------------------------------------------------------------------------
  var cache = {};
  function data(name) {
    if (!cache[name]) {
      cache[name] = fetch(BASE + "/data/" + name + ".json", { cache: "no-cache" }).then(function (r) { return r.json(); });
    }
    return cache[name];
  }

  // --- link a Telegram: la configurazione viaggia dentro il payload di /start ------------
  // Formato "C1" + base64url(<n fonti del catalogo><bitmap><parole chiave>) — vedi sfm/config_link.py
  var MAX_PAYLOAD = 64;

  function encodePayload(catalogIndexes, catalogSize, keywords) {
    if (!catalogIndexes.length || !catalogSize || catalogSize > 255) return null;
    var bytes = [catalogSize];
    var bitmap = new Array(Math.ceil(catalogSize / 8)).fill(0);
    catalogIndexes.forEach(function (i) {
      if (i >= 0 && i < catalogSize) bitmap[Math.floor(i / 8)] |= 1 << (7 - (i % 8));
    });
    bytes = bytes.concat(bitmap);
    var text = keywords.join(",");
    if (text) {
      new TextEncoder().encode(text).forEach(function (b) { bytes.push(b); });
    }
    var binary = bytes.map(function (b) { return String.fromCharCode(b); }).join("");
    var payload = "C1" + btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    return payload.length <= MAX_PAYLOAD ? payload : null;
  }

  // --- notizie: filtri e rendering (stesso markup di _news_list.html) --------------------
  function escapeHtml(text) {
    return String(text == null ? "" : text).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function wordRegex(word) {
    var escaped = word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/['\u2019]/g, "['\u2019]");
    try {
      return new RegExp("(?<![\\p{L}\\p{N}])" + escaped + "(?![\\p{L}\\p{N}])", "giu");
    } catch (e) {
      return new RegExp("\\b" + escaped + "\\b", "gi");     // browser senza lookbehind
    }
  }

  function matchedKeywords(item, keywords) {
    var haystack = (item.t || "") + " " + (item.p || "");
    return keywords.filter(function (k) { return wordRegex(k).test(haystack); });
  }

  function formatDate(iso) {
    if (!iso) return "";
    var d = new Date(iso.replace(" ", "T"));
    if (isNaN(d)) return iso.slice(0, 16).replace("T", " ");
    var pad = function (n) { return String(n).padStart(2, "0"); };
    return pad(d.getDate()) + "/" + pad(d.getMonth() + 1) + "/" + d.getFullYear() + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  function newsCard(item, keywords) {
    var hits = keywords.length ? matchedKeywords(item, keywords) : [];
    var meta = '<span class="news-source">' + escapeHtml(item.n || "Fonte") + "</span>";
    if (item.d) meta += '<time datetime="' + escapeHtml(item.d.slice(0, 10)) + '">' + escapeHtml(formatDate(item.d)) + "</time>";
    if (hits.length) meta += '<span class="badge">' + escapeHtml(hits.join(", ")) + "</span>";
    return '<li class="news-card' + (hits.length ? " matched" : "") + '">' +
      '<div class="news-meta">' + meta + "</div>" +
      '<h3 class="news-title"><a href="' + escapeHtml(item.l) + '" rel="noopener nofollow" target="_blank">' +
      escapeHtml(item.t || "Titolo non disponibile") + "</a></h3>" +
      (item.p ? '<p class="news-preview">' + escapeHtml(item.p) + "</p>" : "") + "</li>";
  }

  function renderNews(container, items, keywords, emptyMessage) {
    if (!items.length) {
      container.innerHTML = '<p class="empty">' + escapeHtml(emptyMessage || "Nessuna notizia trovata.") + "</p>";
      return;
    }
    container.innerHTML = '<ol class="news-list">' + items.map(function (i) { return newsCard(i, keywords); }).join("") + "</ol>";
  }

  function filterNews(all, options) {
    var q = (options.query || "").trim().toLowerCase();
    var ids = options.sources && options.sources.length ? options.sources : null;
    var limit = options.days ? Date.now() - options.days * 86400000 : null;
    return all.filter(function (item) {
      if (ids && ids.indexOf(item.s) === -1) return false;
      if (limit) {
        var when = Date.parse((item.d || "").replace(" ", "T"));
        if (!isNaN(when) && when < limit) return false;
      }
      if (q && ((item.t || "") + " " + (item.p || "")).toLowerCase().indexOf(q) === -1) return false;
      return true;
    });
  }

  // --- navigazione: le voci che dipendono dalle preferenze ------------------------------
  function updateNav() {
    var has = prefs.sources().length || prefs.keywords().length;
    var mine = document.getElementById("nav-mine");
    if (mine) mine.hidden = !has;
    var label = document.getElementById("nav-config-label");
    if (label) label.textContent = has ? "Le mie fonti" : "Scegli le fonti";
  }

  function flash(message, kind) {
    var main = document.getElementById("main");
    if (!main) return;
    var old = main.querySelector(".flashes");
    if (old) old.remove();
    var ul = document.createElement("ul");
    ul.className = "flashes";
    ul.setAttribute("role", "status");
    ul.innerHTML = '<li class="flash ' + (kind || "success") + '">' + escapeHtml(message) + "</li>";
    main.insertBefore(ul, main.firstChild);
  }

  // --- pagina /notizie -------------------------------------------------------------------
  var PAGE = 20;

  function initNewsPage() {
    var form = document.getElementById("news-filters");
    var results = document.getElementById("news-results");
    if (!form || !results || !form.dataset.live) return;
    var count = document.getElementById("news-count");
    var more = document.getElementById("news-more");
    var shown = PAGE;
    var current = [];

    function draw() {
      renderNews(results, current.slice(0, shown), prefs.keywords());
      if (count) count.textContent = current.length + " notizie" + (current.length > shown ? " · ne vedi " + shown : "");
      if (more) more.hidden = current.length <= shown;
    }

    function apply() {
      data("news").then(function (all) {
        var source = form.querySelector("[name=fonte]");
        current = filterNews(all.items, {
          query: (form.querySelector("[name=q]") || {}).value,
          days: Number((form.querySelector("[name=giorni]") || {}).value || 7),
          sources: source && source.value ? [Number(source.value)] : null
        });
        shown = PAGE;
        draw();
      });
    }

    form.addEventListener("submit", function (e) { e.preventDefault(); apply(); });
    form.addEventListener("input", apply);
    form.addEventListener("change", apply);
    if (more) more.addEventListener("click", function () { shown += PAGE; draw(); });
    apply();
  }

  // --- pagina /le-mie-notizie -------------------------------------------------------------
  function initMinePage() {
    var empty = document.getElementById("mine-empty");
    var bodyEl = document.getElementById("mine-body");
    if (!empty || !bodyEl) return;
    var chosen = prefs.sources();
    var keywords = prefs.keywords();
    if (!chosen.length) return;
    empty.hidden = true;
    bodyEl.hidden = false;

    var intro = document.getElementById("mine-intro");
    var form = document.getElementById("mine-filters");
    var results = document.getElementById("mine-results");
    var count = document.getElementById("mine-count");

    data("sources").then(function (src) {
      if (!intro) return;
      var names = src.items.filter(function (s) { return chosen.indexOf(s.id) !== -1; }).length;
      intro.innerHTML = "Dalle <strong>" + names + " fonti</strong> che hai scelto in questo browser" +
        (keywords.length ? ", con evidenziate le tue parole chiave: <strong>" + escapeHtml(keywords.join(", ")) + "</strong>" : "") +
        '. <a href="' + BASE + '/configura">Modifica la selezione</a>.';
    });

    function apply() {
      data("news").then(function (all) {
        var items = filterNews(all.items, {
          query: (form.querySelector("[name=q]") || {}).value,
          days: Number((form.querySelector("[name=giorni]") || {}).value || 7),
          sources: chosen
        });
        var matched = keywords.length ? items.filter(function (i) { return matchedKeywords(i, keywords).length; }).length : 0;
        renderNews(results, items.slice(0, 200), keywords, "Nessuna notizia dalle tue fonti in questo periodo.");
        if (count) count.textContent = items.length + " notizie" + (matched ? ", " + matched + " con le tue parole chiave" : "");
      });
    }

    form.addEventListener("submit", function (e) { e.preventDefault(); apply(); });
    form.addEventListener("input", apply);
    form.addEventListener("change", apply);
    apply();
  }

  // --- pagina /configura -------------------------------------------------------------------
  function initConfigPage() {
    var formSources = document.getElementById("fonti");
    if (!formSources) return;
    var boxes = Array.prototype.slice.call(formSources.querySelectorAll("input[name=sources]"));
    var keywordsField = document.getElementById("keywords");

    // 1. ripristina la scelta salvata nel browser
    var chosen = prefs.sources();
    boxes.forEach(function (b) { b.checked = chosen.indexOf(Number(b.value)) !== -1; });
    if (keywordsField) keywordsField.value = prefs.keywords().join(", ");
    refreshGroups();

    function refreshGroups() {
      document.querySelectorAll("details.source-group").forEach(function (g) {
        var n = g.querySelectorAll("input[type=checkbox]:checked").length;
        var label = g.querySelector(".group-count");
        if (label) label.textContent = n + " selezionate";
        if (n) g.open = true;
      });
    }

    function selected() {
      return boxes.filter(function (b) { return b.checked; });
    }

    function currentKeywords() {
      return (keywordsField ? keywordsField.value : "").split(",")
        .map(function (k) { return k.trim().slice(0, 60); }).filter(Boolean).slice(0, 30);
    }

    // 2. scorciatoia per area (regioni/province) — stessa regola del server
    var formArea = document.getElementById("form-area");
    if (formArea) {
      formArea.addEventListener("submit", function (e) {
        e.preventDefault();
        var regions = Array.prototype.slice.call(formArea.querySelectorAll("input[name=regions]:checked")).map(function (b) { return b.value; });
        if (!regions.length) { flash("Scegli almeno una regione.", "error"); return; }
        var wanted = {};
        regions.forEach(function (r) { wanted[r] = []; });
        formArea.querySelectorAll("input[name=provinces]:checked").forEach(function (b) {
          var parts = b.value.split("|");
          if (wanted[parts[0]]) wanted[parts[0]].push(parts[1]);
        });
        data("sources").then(function (src) {
          var ids = src.items.filter(function (s) {
            if (s.kind === "mim") return true;
            if (!s.region || !wanted[s.region]) return false;
            if (s.kind === "usr") return true;
            if (s.kind !== "usp") return false;
            var asked = wanted[s.region];
            return !asked.length || (s.province || "").split("|").some(function (p) { return asked.indexOf(p) !== -1; });
          }).map(function (s) { return s.id; });
          boxes.forEach(function (b) { b.checked = ids.indexOf(Number(b.value)) !== -1; });
          refreshGroups();
          flash("Selezionate " + ids.length + " fonti per: " + regions.join(", ") + ". Aggiungi le parole chiave e salva.");
          location.hash = "#fonti";
        });
      });
    }

    // 3. salvataggio nel browser e passaggio a Telegram
    formSources.addEventListener("submit", function (e) {
      e.preventDefault();
      var wantTelegram = e.submitter && e.submitter.value === "telegram";
      var picked = selected();
      var keywords = currentKeywords();
      prefs.save(picked.map(function (b) { return Number(b.value); }), keywords);
      updateNav();
      if (!wantTelegram) {
        flash("Fatto: " + picked.length + " fonti e " + keywords.length + " parole chiave, salvate in questo browser.");
        location.href = BASE + "/le-mie-notizie";
        return;
      }
      if (!picked.length) {
        flash("Scegli almeno una fonte prima di portare la configurazione su Telegram.", "error");
        return;
      }
      showTelegram(picked, keywords);
    });

    function showTelegram(picked, keywords) {
      var out = document.getElementById("telegram-out");
      var hint = document.getElementById("telegram-hint");
      if (!out) return;
      data("sources").then(function (src) {
        var indexes = picked.map(function (b) { return Number(b.dataset.catalog); }).filter(function (i) { return i >= 0; });
        var payload = encodePayload(indexes, src.catalog_size, keywords);
        var withoutKeywords = payload ? null : encodePayload(indexes, src.catalog_size, []);
        var code = payload || withoutKeywords;
        if (!code) {
          out.innerHTML = "<p>Con così tante fonti il link diventa troppo lungo: apri il bot" +
            (BOT ? ' <a href="https://t.me/' + BOT + '" rel="noopener" target="_blank">@' + BOT + "</a>" : "") +
            " e usa <span class=\"code\">/sources</span> per scegliere le fonti.</p>";
          out.hidden = false;
          if (hint) hint.hidden = true;
          return;
        }
        var link = BOT ? "https://t.me/" + BOT + "?start=" + code : "";
        var html = "<p>La tua configurazione è pronta: apri il bot e viene applicata da sola.</p>";
        if (link) html += '<p><a class="button primary" href="' + link + '" rel="noopener" target="_blank">Apri il bot e configura</a></p>';
        html += '<p class="muted">Oppure scrivi al bot questo comando:</p><p><span class="code">/start ' + escapeHtml(code) + "</span></p>";
        if (!payload && keywords.length) {
          html += '<p class="muted">Le parole chiave non stavano nel link: dopo aver aperto il bot incolla anche questo comando.</p>' +
            '<p><span class="code">/setkeywords ' + escapeHtml(keywords.join(", ")) + "</span></p>";
        }
        html += '<p class="muted">Il link contiene solo le fonti e le parole che hai scelto: nessun dato tuo, niente salvato da nessuna parte.</p>';
        out.innerHTML = html;
        out.hidden = false;
        if (hint) hint.hidden = true;
        out.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }

    // 4. esporta e dimentica
    var exportBtn = document.getElementById("export-prefs");
    if (exportBtn) {
      exportBtn.addEventListener("click", function (e) {
        e.preventDefault();
        data("sources").then(function (src) {
          var chosenIds = prefs.sources();
          var payload = {
            fonti: src.items.filter(function (s) { return chosenIds.indexOf(s.id) !== -1; })
              .map(function (s) { return { id: s.id, nome: s.name }; }),
            parole_chiave: prefs.keywords()
          };
          var blob = new Blob([JSON.stringify(payload, null, 1)], { type: "application/json" });
          var a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = "school-feed-monitor-preferenze.json";
          a.click();
          URL.revokeObjectURL(a.href);
        });
      });
    }

    var formForget = document.getElementById("form-forget");
    if (formForget) {
      formForget.addEventListener("submit", function (e) {
        e.preventDefault();
        prefs.forget();
        boxes.forEach(function (b) { b.checked = false; });
        if (keywordsField) keywordsField.value = "";
        refreshGroups();
        updateNav();
        flash("Preferenze cancellate da questo browser.", "info");
      });
    }
  }

  updateNav();
  initNewsPage();
  initMinePage();
  initConfigPage();
})();
