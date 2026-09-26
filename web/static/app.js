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
  // --- ultimo aggiornamento: "N minuti fa" e avviso se il prossimo non è arrivato -------
  // L'ora è scritta nella pagina quando viene generata: se il sito non si aggiorna, solo il
  // browser può accorgersene (vedi web/freshness.py e _freshness.html).
  function ago(minutes) {
    if (minutes < 2) return "poco fa";
    if (minutes < 60) return minutes + " minuti fa";
    var hours = Math.floor(minutes / 60);
    if (hours < 48) return hours === 1 ? "un'ora fa" : hours + " ore fa";
    return Math.floor(hours / 24) + " giorni fa";
  }

  document.querySelectorAll(".freshness[data-updated]").forEach(function (el) {
    var updated = Date.parse(el.dataset.updated);
    if (isNaN(updated)) return;
    var minutes = Math.max(0, Math.round((Date.now() - updated) / 60000));
    var slot = el.querySelector(".freshness-ago");
    if (slot) slot.textContent = " (" + ago(minutes) + ")";
    if (minutes > Number(el.dataset.lateAfter || 90)) {
      el.classList.add("late");
      el.appendChild(document.createTextNode(" L'aggiornamento previsto non è ancora arrivato: " +
        "le notizie più recenti potrebbero mancare, controlla anche i siti ufficiali."));
    }
  });

  // --- menù a tendina in cui si può scrivere (select[data-searchable]) -------------------
  // Il <select> resta nel form, nascosto: è lui che viene inviato e che i filtri leggono.
  // Sopra ci mettiamo un campo di testo che filtra le voci mentre scrivi ("bari", "emilia").
  function fold(text) {
    return (text || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  function searchableSelect(select) {
    var label = document.querySelector('label[for="' + select.id + '"]');
    var wrap = document.createElement("div");
    var input = document.createElement("input");
    var list = document.createElement("ul");
    var listId = select.id + "-list";
    wrap.className = "combo";
    input.type = "text";
    input.id = select.id + "-cerca";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.placeholder = select.dataset.searchable;
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", listId);
    list.id = listId;
    list.className = "combo-list";
    list.setAttribute("role", "listbox");
    list.hidden = true;
    if (label) label.htmlFor = input.id;
    select.hidden = true;
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(input);
    wrap.appendChild(list);
    wrap.appendChild(select);

    var options = Array.prototype.map.call(select.options, function (o, i) {
      return { value: o.value, text: o.textContent.trim(), key: fold(o.textContent),
               group: o.parentNode.tagName === "OPTGROUP" ? o.parentNode.label : "", id: listId + "-" + i };
    });
    var shown = [], active = -1;

    function current() { return options[select.selectedIndex] || options[0]; }
    function showCurrent() { input.value = current().value ? current().text : ""; }

    function draw() {
      var words = fold(input.value).split(/\s+/).filter(Boolean);
      shown = options.filter(function (o) {
        return words.every(function (w) { return o.key.indexOf(w) !== -1; });
      });
      var html = "", group = null;
      shown.forEach(function (o, i) {
        if (o.group && o.group !== group) {
          html += '<li class="combo-group" role="presentation">' + escapeHtml(o.group) + "</li>";
          group = o.group;
        }
        html += '<li role="option" id="' + o.id + '" data-i="' + i + '" aria-selected="' +
          (o === current()) + '">' + escapeHtml(o.text) + "</li>";
      });
      if (!shown.length) html = '<li class="combo-empty" role="presentation">Nessuna fonte con questo nome</li>';
      list.innerHTML = html;
      move(shown.length ? 0 : -1);
    }

    function move(i) {
      var old = list.querySelector(".active");
      if (old) old.classList.remove("active");
      active = i;
      var el = i >= 0 && document.getElementById(shown[i].id);
      if (el) { el.classList.add("active"); if (el.scrollIntoView) el.scrollIntoView({ block: "nearest" }); input.setAttribute("aria-activedescendant", el.id); }
      else input.removeAttribute("aria-activedescendant");
    }

    function open() {
      if (!list.hidden) return;
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      draw();
    }

    function close() {
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
    }

    function pick(o) {
      close();
      if (o && o.value !== select.value) {
        select.value = o.value;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
      showCurrent();
    }

    input.addEventListener("focus", function () { input.select(); open(); });
    input.addEventListener("click", open);
    input.addEventListener("input", function (e) { e.stopPropagation(); list.hidden ? open() : draw(); });
    input.addEventListener("blur", function () {
      if (!input.value.trim()) pick(options[0]);   // campo svuotato = «Tutte»
      else { close(); showCurrent(); }
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (list.hidden) return open();
        if (shown.length) move((active + (e.key === "ArrowDown" ? 1 : shown.length - 1)) % shown.length);
      } else if (e.key === "Enter") {
        if (list.hidden) return;   // a tendina chiusa, Invio invia il form come prima
        e.preventDefault();
        pick(shown[active]);
      } else if (e.key === "Escape" && !list.hidden) {
        e.preventDefault();
        close();
        showCurrent();
      }
    });
    list.addEventListener("mousedown", function (e) { e.preventDefault(); });   // non perdere il focus
    list.addEventListener("click", function (e) {
      var li = e.target.closest("[data-i]");
      if (li) { pick(shown[Number(li.dataset.i)]); input.blur(); }
    });
    select.addEventListener("change", showCurrent);   // se qualcuno lo cambia da codice
    showCurrent();
  }

  document.querySelectorAll("select[data-searchable]").forEach(searchableSelect);

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
    excluded: function () { return readCookie("sfm_escludi").slice(0, 30); },
    save: function (sources, keywords, excluded) {
      writeCookie("sfm_fonti", sources.map(String));
      writeCookie("sfm_parole", keywords);
      writeCookie("sfm_escludi", excluded || []);
    },
    forget: function () { prefs.save([], [], []); }
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
    if (text) {                         // UTF-8 a mano: niente TextEncoder, funziona ovunque
      var encoded = encodeURIComponent(text);
      for (var i = 0; i < encoded.length; i++) {
        if (encoded.charAt(i) === "%") { bytes.push(parseInt(encoded.substr(i + 1, 2), 16)); i += 2; }
        else bytes.push(encoded.charCodeAt(i));
      }
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
    var excluded = prefs.excluded();
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
        (excluded.length ? ", senza quelle che parlano di <strong>" + escapeHtml(excluded.join(", ")) + "</strong>" : "") +
        '. <a href="' + BASE + '/configura/">Modifica la selezione</a>.';
    });

    function apply() {
      data("news").then(function (all) {
        var items = filterNews(all.items, {
          query: (form.querySelector("[name=q]") || {}).value,
          days: Number((form.querySelector("[name=giorni]") || {}).value || 7),
          sources: chosen
        }).filter(function (i) { return !excluded.length || !matchedKeywords(i, excluded).length; });
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
  // Niente pulsante «Salva»: ogni clic finisce subito nei cookie. Resta solo «Porta su Telegram».
  function initConfigPage() {
    var formSources = document.getElementById("fonti");
    if (!formSources) return;
    var boxes = Array.prototype.slice.call(formSources.querySelectorAll("input[name=sources]"));
    var keywordsField = document.getElementById("keywords");
    var excludedField = document.getElementById("excluded");
    var status = document.getElementById("save-status");

    // 1. ripristina la scelta salvata nel browser
    var chosen = prefs.sources();
    boxes.forEach(function (b) { b.checked = chosen.indexOf(Number(b.value)) !== -1; });
    if (keywordsField) keywordsField.value = prefs.keywords().join(", ");
    if (excludedField) excludedField.value = prefs.excluded().join(", ");
    refreshGroups();
    data("sources").then(restoreAreas);

    function refreshGroups() {
      var total = document.getElementById("sources-selected");
      if (total) total.textContent = boxes.filter(function (b) { return b.checked; }).length;
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

    function words(field) {
      return (field ? field.value : "").split(",")
        .map(function (k) { return k.trim().slice(0, 60); }).filter(Boolean).slice(0, 30);
    }
    function currentKeywords() { return words(keywordsField); }
    function currentExcluded() { return words(excludedField); }

    // 2. salvataggio automatico
    function save() {
      var picked = selected();
      var keywords = currentKeywords();
      var excluded = currentExcluded();
      prefs.save(picked.map(function (b) { return Number(b.value); }), keywords, excluded);
      updateNav();
      if (status) {
        status.textContent = "✓ Salvato in questo browser: " + picked.length + " fonti" +
          (keywords.length ? ", " + keywords.length + " parole chiave" : "") +
          (excluded.length ? ", " + excluded.length + " parole escluse" : "") + ".";
        status.className = "save-status saved";
      }
    }

    var typing = null;
    formSources.addEventListener("change", function (e) {
      var name = e.target && e.target.name;
      if (name === "regions" || name === "provinces") { applyArea(e.target); return; }
      refreshGroups();          // anche i «tutte/nessuna» di un gruppo (sources.js), che non hanno name
      save();
    });
    [keywordsField, excludedField].forEach(function (field) {
      if (!field) return;
      field.addEventListener("input", function () {
        clearTimeout(typing);
        typing = setTimeout(save, 500);
      });
    });

    // 3. scorciatoia per area: tocca solo le fonti della regione cambiata, così i ritocchi
    //    fatti a mano sulle altre restano. Il Ministero si aggiunge alla prima area scelta.
    function wantedProvinces(region) {
      return Array.prototype.slice.call(formSources.querySelectorAll("input[name=provinces]:checked"))
        .map(function (b) { return b.value.split("|"); })
        .filter(function (p) { return p[0] === region; })
        .map(function (p) { return p[1]; });
    }

    function applyArea(input) {
      var region = input.value.split("|")[0];
      var regionBox = formSources.querySelector('input[name=regions][value="' + region.replace(/"/g, '\\"') + '"]');
      var on = !!(regionBox && regionBox.checked);
      data("sources").then(function (src) {
        var asked = on ? wantedProvinces(region) : [];
        var set = {};
        src.items.forEach(function (s) {
          if (s.region !== region || (s.kind !== "usr" && s.kind !== "usp")) return;
          var want = on && (s.kind === "usr" || !asked.length ||
            (s.province || "").split("|").some(function (p) { return asked.indexOf(p) !== -1; }));
          set[s.id] = want;
        });
        if (on) src.items.forEach(function (s) { if (s.kind === "mim" && !selected().length) set[s.id] = true; });
        var changed = 0;
        boxes.forEach(function (b) {
          var id = Number(b.value);
          if (id in set && b.checked !== set[id]) { b.checked = set[id]; changed++; }
        });
        refreshGroups();
        save();
        if (status && changed) {
          status.textContent += " " + (on ? "Aggiornate le fonti di " : "Tolte le fonti di ") + region + ".";
        }
      });
    }

    // alla riapertura rispunta le regioni (e le province) che corrispondono alle fonti salvate
    function restoreAreas(src) {
      var ids = prefs.sources();
      if (!ids.length) return;
      var byRegion = {};
      src.items.forEach(function (s) {
        if (!s.region || (s.kind !== "usr" && s.kind !== "usp")) return;
        var r = byRegion[s.region] || (byRegion[s.region] = { any: false, usp: [], picked: [] });
        if (ids.indexOf(s.id) !== -1) r.any = true;
        if (s.kind === "usp") {
          r.usp.push(s);
          if (ids.indexOf(s.id) !== -1) r.picked.push(s);
        }
      });
      Object.keys(byRegion).forEach(function (region) {
        var r = byRegion[region];
        var box = formSources.querySelector('input[name=regions][value="' + region.replace(/"/g, '\\"') + '"]');
        if (!box || !r.any) return;
        box.checked = true;
        box.dispatchEvent(new Event("change", { bubbles: false }));   // area.js mostra le province
        if (r.picked.length && r.picked.length < r.usp.length) {
          r.picked.forEach(function (s) {
            (s.province || "").split("|").forEach(function (p) {
              var pb = formSources.querySelector('input[name=provinces][value="' + (region + "|" + p).replace(/"/g, '\\"') + '"]');
              if (pb) pb.checked = true;
            });
          });
        }
      });
    }

    // 4. passaggio a Telegram
    formSources.addEventListener("submit", function (e) {
      e.preventDefault();
      save();
      var picked = selected();
      if (!picked.length) {
        flash("Scegli almeno una fonte prima di portare la configurazione su Telegram.", "error");
        return;
      }
      showTelegram(picked, currentKeywords(), currentExcluded());
    });

    function showTelegram(picked, keywords, excluded) {
      var out = document.getElementById("telegram-out");
      var hint = document.getElementById("telegram-hint");
      if (!out) return;
      data("sources").then(function (src) {
        var indexes = picked.map(function (b) { return Number(b.dataset.catalog); }).filter(function (i) { return i >= 0; });
        // le parole da escludere viaggiano con un "-" davanti (vedi sfm/config_link.py)
        var allWords = keywords.concat(excluded.map(function (w) { return "-" + w.replace(/^-+/, ""); }));
        var payload = encodePayload(indexes, src.catalog_size, allWords);
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
        if (!payload && allWords.length) {
          html += '<p class="muted">Le parole non stavano nel link: dopo aver aperto il bot incolla anche ' +
            (keywords.length && excluded.length ? "questi comandi" : "questo comando") + ".</p>";
          if (keywords.length) html += '<p><span class="code">/setkeywords ' + escapeHtml(keywords.join(", ")) + "</span></p>";
          if (excluded.length) html += '<p><span class="code">/exclude ' + escapeHtml(excluded.join(", ")) + "</span></p>";
        }
        html += '<p class="muted">Il link contiene solo le fonti e le parole che hai scelto: nessun dato tuo, niente salvato da nessuna parte.</p>';
        out.innerHTML = html;
        out.hidden = false;
        if (hint) hint.hidden = true;
        if (out.scrollIntoView) out.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }

    // 5. esporta e dimentica
    var exportBtn = document.getElementById("export-prefs");
    if (exportBtn) {
      exportBtn.addEventListener("click", function (e) {
        e.preventDefault();
        data("sources").then(function (src) {
          var chosenIds = prefs.sources();
          var payload = {
            fonti: src.items.filter(function (s) { return chosenIds.indexOf(s.id) !== -1; })
              .map(function (s) { return { id: s.id, nome: s.name }; }),
            parole_chiave: prefs.keywords(),
            parole_escluse: prefs.excluded()
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
        formSources.querySelectorAll("input[name=regions]:checked").forEach(function (b) {
          b.checked = false;
          b.dispatchEvent(new Event("change", { bubbles: false }));   // area.js nasconde le province
        });
        if (status) { status.textContent = "Preferenze cancellate da questo browser."; status.className = "save-status"; }
        if (keywordsField) keywordsField.value = "";
        if (excludedField) excludedField.value = "";
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
