/**
 * Editor visual de procedimientos SGI (PG / PO).
 */
(function () {
  "use strict";

  const cfg = window.SGI_PROC_CONFIG;
  if (!cfg) return;

  const initial = cfg.payload || {};
  const soloLectura = !!cfg.soloLectura;

  function qs(sel) {
    return document.querySelector(sel);
  }
  function qsa(sel) {
    return Array.from(document.querySelectorAll(sel));
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function collectPayload() {
    const secciones = {};
    qsa("[data-seccion-body]").forEach((el) => {
      secciones[el.dataset.seccionBody] = el.innerHTML.trim();
    });
    const registros = [];
    qsa("#procRegistrosBody tr").forEach((tr) => {
      registros.push({
        nombre: tr.querySelector(".rg-nombre")?.value || "",
        quien_archiva: tr.querySelector(".rg-quien")?.value || "",
        como: tr.querySelector(".rg-como")?.value || "",
        donde: tr.querySelector(".rg-donde")?.value || "",
        tiempo_guarda: tr.querySelector(".rg-tiempo")?.value || "",
        usuarios: tr.querySelector(".rg-usuarios")?.value || "",
        disposicion_final: tr.querySelector(".rg-disp")?.value || "",
      });
    });
    const anexos = [];
    qsa(".sgi-proc-anexo-card").forEach((card) => {
      anexos.push({
        id: card.dataset.anexoId ? parseInt(card.dataset.anexoId, 10) : null,
        nombre: card.querySelector(".ax-nombre")?.value || "",
        codigo: card.querySelector(".ax-codigo")?.value || "",
        revision: card.querySelector(".ax-rev")?.value || "",
        fecha_vigencia: card.querySelector(".ax-fecha")?.value || "",
      });
    });
    const tituloEl = qs("#procTituloInput") || qs("#procTituloDisplay");
    const titulo =
      (qs("#procTituloInput")?.value || tituloEl?.textContent || tituloEl?.value || "") + "";
    return {
      titulo: titulo.trim(),
      secciones,
      registros,
      anexos,
      fecha_vigencia: qs("#procFechaVigencia")?.value || "",
      elaboro: qs("#procElaboro")?.value || "",
      reviso: qs("#procReviso")?.value || "",
      aprobo: qs("#procAprobo")?.value || "",
      fecha_elaboracion: qs("#procFechaElab")?.value || "",
      fecha_revision: qs("#procFechaRev")?.value || "",
      fecha_aprobacion: qs("#procFechaAprob")?.value || "",
    };
  }

  function renderControlCambios(rows) {
    const tbody = qs("#procCambiosBody");
    if (!tbody) return;
    tbody.innerHTML = "";
    (rows || []).forEach((row) => addCambioRow(row));
    if (!(rows || []).length) {
      addCambioRow({
        revision_ref: cfg.revisionRef || "00",
        descripcion: "Emisión inicial del documento.",
        fecha_aprobacion: "",
        readonly: true,
      });
    }
  }

  function addCambioRow(row) {
    const tbody = qs("#procCambiosBody");
    if (!tbody) return;
    const ro = soloLectura || !!row?.readonly;
    const tr = document.createElement("tr");
    if (row?.auto_generado) tr.classList.add("sgi-cc-auto");
    tr.innerHTML = `
      <td><input type="text" class="cc-rev" value="${escapeHtml(row?.revision_ref || "")}" readonly tabindex="-1"></td>
      <td><textarea class="cc-desc" rows="2" readonly tabindex="-1">${escapeHtml(row?.descripcion || "")}</textarea></td>
      <td><input type="date" class="cc-fecha" value="${escapeHtml(row?.fecha_aprobacion || "")}" ${ro ? "readonly" : ""} tabindex="-1"></td>
    `;
    tbody.appendChild(tr);
  }

  function addRegistroRow(row) {
    const tbody = qs("#procRegistrosBody");
    if (!tbody) return;
    const tr = document.createElement("tr");
    const fields = [
      ["rg-nombre", row?.nombre],
      ["rg-quien", row?.quien_archiva],
      ["rg-como", row?.como],
      ["rg-donde", row?.donde],
      ["rg-tiempo", row?.tiempo_guarda],
      ["rg-usuarios", row?.usuarios],
      ["rg-disp", row?.disposicion_final],
    ];
    let html = "";
    fields.forEach(([cls, val]) => {
      html += `<td><input type="text" class="${cls}" value="${(val || "").replace(/"/g, "&quot;")}" ${soloLectura ? "readonly" : ""}></td>`;
    });
    if (!soloLectura) {
      html +=
        '<td class="sgi-proc-no-print text-center"><button type="button" class="btn btn-sm btn-link text-danger btn-del-reg">×</button></td>';
    }
    tr.innerHTML = html;
    tbody.appendChild(tr);
    tr.querySelector(".btn-del-reg")?.addEventListener("click", () => tr.remove());
  }

  function addAnexoCard(ax, idx) {
    const container = qs("#procAnexosContainer");
    if (!container) return;
    const card = document.createElement("div");
    card.className = "sgi-proc-anexo-card";
    if (ax?.id) card.dataset.anexoId = String(ax.id);
    const codigoAuto = ax?.codigo || `${cfg.codigo}-A${String(idx + 1).padStart(2, "0")}`;
    card.innerHTML = `
      <div class="row g-2">
        <div class="col-md-6">
          <label class="form-label small fw-bold">Nombre del anexo</label>
          <input type="text" class="form-control form-control-sm ax-nombre" value="${(ax?.nombre || "").replace(/"/g, "&quot;")}" ${soloLectura ? "readonly" : ""}>
        </div>
        <div class="col-md-3">
          <label class="form-label small fw-bold">Código</label>
          <input type="text" class="form-control form-control-sm ax-codigo" value="${codigoAuto.replace(/"/g, "&quot;")}" ${soloLectura ? "readonly" : ""}>
        </div>
        <div class="col-md-3">
          <label class="form-label small fw-bold">Revisión</label>
          <input type="text" class="form-control form-control-sm ax-rev" value="${(ax?.revision || "Rev. 00").replace(/"/g, "&quot;")}" ${soloLectura ? "readonly" : ""}>
        </div>
        <div class="col-md-4">
          <label class="form-label small fw-bold">Fecha de vigencia</label>
          <input type="date" class="form-control form-control-sm ax-fecha" value="${ax?.fecha_vigencia || ""}" ${soloLectura ? "readonly" : ""}>
        </div>
        <div class="col-md-8">
          ${ax?.tiene_archivo ? '<span class="badge text-bg-success">Archivo adjunto</span>' : ""}
        </div>
      </div>
      ${soloLectura ? "" : '<button type="button" class="btn btn-sm btn-link text-danger float-end btn-del-anexo">Quitar anexo</button>'}
    `;
    container.appendChild(card);
    card.querySelector(".btn-del-anexo")?.addEventListener("click", () => card.remove());
  }

  function hydrate() {
    const titulo = initial.titulo || "";
    const tituloInput = qs("#procTituloInput");
    if (tituloInput) tituloInput.value = titulo;
    const tituloDisp = qs("#procTituloDisplay");
    if (tituloDisp) tituloDisp.textContent = titulo;
    const headerTit = qs("#procHeaderTitulo");
    if (headerTit) headerTit.textContent = titulo;

    const secs = initial.secciones || {};
    qsa("[data-seccion-body]").forEach((el) => {
      const k = el.dataset.seccionBody;
      el.innerHTML = secs[k] || "";
    });

    renderControlCambios(initial.control_cambios || []);

    (initial.registros || []).forEach((r) => addRegistroRow(r));
    (initial.anexos || []).forEach((a, i) => addAnexoCard(a, i));

    qsa("[data-seccion-body]").forEach((el) => {
      if (!soloLectura) {
        el.addEventListener("input", scheduleAutoSaveHint);
        el.addEventListener("blur", scheduleAutoSaveHint);
      }
    });
  }

  let saveHintTimer = null;
  function scheduleAutoSaveHint() {
    if (soloLectura) return;
    const hint = qs("#procCcHint");
    if (hint) {
      hint.textContent =
        "Hay cambios sin guardar. Al guardar el borrador se actualizará automáticamente la descripción de la revisión vigente.";
      hint.classList.add("text-warning");
    }
    clearTimeout(saveHintTimer);
    saveHintTimer = setTimeout(() => {
      if (hint) hint.classList.remove("text-warning");
    }, 8000);
  }

  async function postJson(url, body) {
    const token = qs('meta[name="csrf-token"]')?.content || cfg.csrf || "";
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": token,
      },
      body: JSON.stringify(body),
    });
    return res.json();
  }

  async function guardarBorrador() {
    const data = collectPayload();
    const res = await postJson(cfg.urls.guardar, data);
    if (res.ok) {
      flashMsg("success", res.message || "Guardado.");
      if (res.control_cambios) renderControlCambios(res.control_cambios);
      const el = qs("#procTituloDisplay");
      if (el) {
        if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") el.value = data.titulo;
        else el.textContent = data.titulo;
      }
      if (qs("#procHeaderTitulo")) qs("#procHeaderTitulo").textContent = data.titulo;
      const hint = qs("#procCcHint");
      if (hint) {
        hint.textContent =
          "Las filas se generan automáticamente al guardar, según las revisiones del documento y los cambios detectados en el contenido.";
        hint.classList.remove("text-warning");
      }
    } else {
      flashMsg("danger", res.message || "Error al guardar.");
    }
  }

  async function workflow(accion) {
    await guardarBorrador();
    const token = qs('meta[name="csrf-token"]')?.content || cfg.csrf || "";
    const res = await fetch(cfg.urls.workflow, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": token },
      body: JSON.stringify({ accion }),
    });
    const data = await res.json();
    if (data.ok) {
      flashMsg("success", data.message);
      if (data.rev_id) {
        window.location.href = cfg.urls.editorBase + data.rev_id;
      } else {
        window.location.reload();
      }
    } else {
      flashMsg("danger", data.message || "No se pudo completar la acción.");
    }
  }

  function flashMsg(kind, text) {
    const el = qs("#sgiProcFlash");
    if (!el) return;
    el.className = `alert alert-${kind} py-2 mb-2`;
    el.textContent = text;
    el.classList.remove("d-none");
    setTimeout(() => el.classList.add("d-none"), 4000);
  }

  function bind() {
    qs("#procTituloInput")?.addEventListener("input", (e) => {
      const t = e.target.value;
      const el = qs("#procTituloDisplay");
      if (el) {
        if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") el.value = t;
        else el.textContent = t;
      }
      if (qs("#procHeaderTitulo")) qs("#procHeaderTitulo").textContent = t;
      scheduleAutoSaveHint();
    });
    qs("#btnGuardarBorrador")?.addEventListener("click", guardarBorrador);
    qs("#btnEnviarRevision")?.addEventListener("click", () => workflow("enviar_revision"));
    qs("#btnAprobar")?.addEventListener("click", () => workflow("aprobar"));
    qs("#btnNuevaRevision")?.addEventListener("click", () => workflow("nueva_revision"));
    qs("#btnAddRegistro")?.addEventListener("click", () => addRegistroRow({}));
    qs("#btnAddAnexo")?.addEventListener("click", () => {
      const n = qsa(".sgi-proc-anexo-card").length;
      addAnexoCard({}, n);
    });
    qs("#btnExportPdf")?.addEventListener("click", () => {
      window.open(cfg.urls.exportPdf, "_blank");
    });
    qs("#btnExportWord")?.addEventListener("click", () => {
      window.location.href = cfg.urls.exportWord;
    });
    qsa("#procRegistrosBody input, .sgi-proc-anexo-card input").forEach((el) => {
      el.addEventListener("input", scheduleAutoSaveHint);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    hydrate();
    if (!soloLectura) bind();
  });
})();
