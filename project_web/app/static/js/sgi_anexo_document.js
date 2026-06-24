(function () {
  "use strict";

  const cfg = window.SGI_ANEXO_DOC_CONFIG;
  if (!cfg) return;

  const initial = cfg.payload || {};

  function qs(sel) {
    return document.querySelector(sel);
  }
  function qsa(sel) {
    return Array.from(document.querySelectorAll(sel));
  }

  function flash(kind, msg) {
    const el = qs("#sgiAnexoFlash");
    if (!el) return;
    el.className = `alert alert-${kind} sgi-proc-no-print`;
    el.textContent = msg;
    el.classList.remove("d-none");
  }

  function hydrate() {
    const titulo = initial.titulo || "";
    const tituloInput = qs("#anexoDocTitulo");
    if (tituloInput) tituloInput.value = titulo;
    const secs = initial.secciones || {};
    qsa("[data-seccion-body]").forEach((el) => {
      el.innerHTML = secs[el.dataset.seccionBody] || "";
    });
  }

  function collect() {
    const secciones = {};
    qsa("[data-seccion-body]").forEach((el) => {
      secciones[el.dataset.seccionBody] = el.innerHTML;
    });
    return {
      titulo: (qs("#anexoDocTitulo")?.value || "").trim(),
      secciones,
    };
  }

  qs("#btnGuardarAnexoDoc")?.addEventListener("click", () => {
    fetch(cfg.guardarUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": cfg.csrf,
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
      body: JSON.stringify(collect()),
    })
      .then((r) => r.json())
      .then((res) => {
        flash(res.ok ? "success" : "danger", res.message || (res.ok ? "Guardado." : "Error."));
      })
      .catch(() => flash("danger", "No se pudo guardar."));
  });

  hydrate();
})();
