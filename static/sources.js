// Elenco fonti in preferenze: ricerca istantanea e "tutte/nessuna" per gruppo.
(function () {
  var box = document.getElementById("sources-search");
  var groups = document.querySelectorAll("details.source-group");
  if (!groups.length) return;
  if (box) {
    box.addEventListener("input", function () {
      var q = box.value.trim().toLowerCase();
      groups.forEach(function (g) {
        var visible = 0;
        g.querySelectorAll("li").forEach(function (li) {
          var hit = !q || li.textContent.toLowerCase().indexOf(q) !== -1;
          li.hidden = !hit;
          if (hit) visible++;
        });
        g.hidden = visible === 0;
        if (q && visible) g.open = true;
      });
    });
  }
  document.querySelectorAll("[data-group-all]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var g = btn.closest("details");
      var on = btn.getAttribute("data-group-all") === "1";
      g.querySelectorAll("input[type=checkbox]").forEach(function (c) { c.checked = on; });
      var count = g.querySelector(".group-count");
      if (count) count.textContent = (on ? g.querySelectorAll("input[type=checkbox]").length : 0) + " selezionate";
      g.dispatchEvent(new Event("change", { bubbles: true }));   // il sito statico salva a ogni cambio
    });
  });
  groups.forEach(function (g) {
    g.addEventListener("change", function () {
      var count = g.querySelector(".group-count");
      if (count) count.textContent = g.querySelectorAll("input[type=checkbox]:checked").length + " selezionate";
    });
  });
})();
