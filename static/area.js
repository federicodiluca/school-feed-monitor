// "Dove insegni?": mostra le province solo delle regioni spuntate (senza JS restano tutte visibili).
(function () {
  var boxes = document.querySelectorAll('input[name="regions"]');
  if (!boxes.length) return;
  function update() {
    var chosen = {};
    boxes.forEach(function (b) { if (b.checked) chosen[b.value] = true; });
    document.querySelectorAll("fieldset.provinces").forEach(function (fs) {
      var on = !!chosen[fs.getAttribute("data-region")];
      fs.hidden = !on;
      if (!on) fs.querySelectorAll("input[type=checkbox]").forEach(function (c) { c.checked = false; });
    });
    document.querySelectorAll(".region-note").forEach(function (n) { n.hidden = !chosen[n.getAttribute("data-note")]; });
  }
  boxes.forEach(function (b) { b.addEventListener("change", update); });
  update();
})();
