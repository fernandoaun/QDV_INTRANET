/**
 * Wizard: crear registro digital desde Word/Excel + UI de asociación en listado/editor.
 */
(function (global) {
  "use strict";

  const FIELD_TYPE_OPTIONS = [
    ["text", "Texto corto"],
    ["textarea", "Texto largo"],
    ["integer", "Número entero"],
    ["decimal", "Número decimal"],
    ["date", "Fecha"],
    ["datetime", "Fecha y hora"],
    ["time", "Hora"],
    ["email", "Correo"],
    ["phone", "Teléfono"],
    ["percent", "Porcentaje"],
    ["currency", "Moneda"],
    ["yes_no", "Sí / No"],
    ["checkbox", "Casilla"],
    ["select", "Selección / lista"],
    ["signature", "Firma"],
    ["editable_table", "Tabla editable"],
    ["calculated", "Calculado"],
    ["system_user", "Usuario del sistema"],
    ["area", "Área"],
    ["equipment", "Equipo"],
    ["observations", "Observaciones"],
  ];

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function ensureModal() {
    let modal = document.getElementById("sgiCreateRecordModal");
    if (modal) return modal;
    const wrap = document.createElement("div");
    wrap.innerHTML = `
<div class="modal fade" id="sgiCreateRecordModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog modal-xl modal-dialog-scrollable">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">Crear registro</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button>
      </div>
      <div class="modal-body">
        <div id="sgiCrStepUpload">
          <p class="text-muted small">Adjunte un archivo Word (.docx) o Excel (.xlsx / .xls). Tamaño máximo 15 MB.</p>
          <input type="file" class="form-control" id="sgiCrFile" accept=".docx,.xlsx,.xls">
          <div id="sgiCrFileMeta" class="small text-muted mt-2"></div>
          <div id="sgiCrAnalyzing" class="d-none mt-3">
            <div class="progress" role="status">
              <div class="progress-bar progress-bar-striped progress-bar-animated" style="width:100%">Analizando archivo…</div>
            </div>
            <p class="small mt-2 mb-0" id="sgiCrAnalyzingName"></p>
          </div>
          <div id="sgiCrError" class="alert alert-danger d-none mt-3"></div>
        </div>
        <div id="sgiCrStepEdit" class="d-none">
          <div class="row g-2 mb-3">
            <div class="col-md-4"><label class="form-label">Código</label><input type="text" class="form-control" id="sgiCrCode"></div>
            <div class="col-md-8"><label class="form-label">Nombre</label><input type="text" class="form-control" id="sgiCrName"></div>
            <div class="col-12"><label class="form-label">Descripción</label><textarea class="form-control" id="sgiCrDesc" rows="2"></textarea></div>
          </div>
          <div id="sgiCrWarnings" class="mb-2"></div>
          <div class="table-responsive" style="max-height:360px">
            <table class="table table-sm align-middle">
              <thead><tr><th>Etiqueta</th><th>Tipo</th><th>Obligatorio</th><th>Sección</th><th></th></tr></thead>
              <tbody id="sgiCrFieldsBody"></tbody>
            </table>
          </div>
          <button type="button" class="btn btn-sm btn-outline-secondary" id="sgiCrAddField">Agregar campo</button>
        </div>
        <div id="sgiCrStepPreview" class="d-none">
          <div class="btn-group mb-3" role="group">
            <button type="button" class="btn btn-sm btn-outline-secondary active" data-preview-vp="desktop">Escritorio</button>
            <button type="button" class="btn btn-sm btn-outline-secondary" data-preview-vp="tablet">Tablet</button>
            <button type="button" class="btn btn-sm btn-outline-secondary" data-preview-vp="mobile">Móvil</button>
          </div>
          <div id="sgiCrPreviewFrame" class="border rounded p-3 mx-auto" style="max-width:100%"></div>
        </div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancelar</button>
        <button type="button" class="btn btn-outline-primary d-none" id="sgiCrBack">Volver</button>
        <button type="button" class="btn btn-primary" id="sgiCrNext">Analizar</button>
        <button type="button" class="btn btn-success d-none" id="sgiCrCreate">Crear registro</button>
        <button type="button" class="btn btn-outline-secondary d-none" id="sgiCrDraft">Guardar como borrador</button>
      </div>
    </div>
  </div>
</div>`;
    document.body.appendChild(wrap.firstElementChild);
    return document.getElementById("sgiCreateRecordModal");
  }

  function CreateRecordWizard(options) {
    const opts = options || {};
    const modalEl = ensureModal();
    const modal = global.bootstrap ? new global.bootstrap.Modal(modalEl) : null;
    let step = 1;
    let analyzing = false;
    let analysis = null;
    let fields = [];
    let file = null;

    const qs = (sel) => modalEl.querySelector(sel);

    function showError(msg) {
      const box = qs("#sgiCrError");
      if (!box) return;
      if (!msg) {
        box.classList.add("d-none");
        box.textContent = "";
        return;
      }
      box.textContent = msg;
      box.classList.remove("d-none");
    }

    function setStep(n) {
      step = n;
      qs("#sgiCrStepUpload").classList.toggle("d-none", n !== 1);
      qs("#sgiCrStepEdit").classList.toggle("d-none", n !== 2);
      qs("#sgiCrStepPreview").classList.toggle("d-none", n !== 3);
      qs("#sgiCrBack").classList.toggle("d-none", n === 1);
      qs("#sgiCrNext").classList.toggle("d-none", n === 3);
      qs("#sgiCrCreate").classList.toggle("d-none", n !== 3);
      qs("#sgiCrDraft").classList.toggle("d-none", n !== 3);
      qs("#sgiCrNext").textContent = n === 1 ? "Analizar" : n === 2 ? "Previsualizar" : "Analizar";
    }

    function renderFields() {
      const body = qs("#sgiCrFieldsBody");
      body.innerHTML = "";
      fields.forEach((f, idx) => {
        const tr = document.createElement("tr");
        const typeOpts = FIELD_TYPE_OPTIONS.map(
          ([v, l]) => `<option value="${v}"${f.type === v ? " selected" : ""}>${escapeHtml(l)}</option>`
        ).join("");
        tr.innerHTML = `
          <td><input class="form-control form-control-sm cr-label" value="${escapeHtml(f.label || "")}"></td>
          <td><select class="form-select form-select-sm cr-type">${typeOpts}</select></td>
          <td class="text-center"><input type="checkbox" class="form-check-input cr-req"${f.required ? " checked" : ""}></td>
          <td><input class="form-control form-control-sm cr-section" value="${escapeHtml(f.section || "")}"></td>
          <td><button type="button" class="btn btn-sm btn-link text-danger cr-del">×</button></td>`;
        tr.querySelector(".cr-label").addEventListener("input", (ev) => {
          fields[idx].label = ev.target.value;
        });
        tr.querySelector(".cr-type").addEventListener("change", (ev) => {
          fields[idx].type = ev.target.value;
        });
        tr.querySelector(".cr-req").addEventListener("change", (ev) => {
          fields[idx].required = ev.target.checked;
        });
        tr.querySelector(".cr-section").addEventListener("input", (ev) => {
          fields[idx].section = ev.target.value;
        });
        tr.querySelector(".cr-del").addEventListener("click", () => {
          fields.splice(idx, 1);
          renderFields();
        });
        body.appendChild(tr);
      });
    }

    function renderPreview(vp) {
      const frame = qs("#sgiCrPreviewFrame");
      const widths = { desktop: "100%", tablet: "768px", mobile: "390px" };
      frame.style.maxWidth = widths[vp] || "100%";
      const bySec = {};
      fields.forEach((f) => {
        const s = f.section || "Datos generales";
        (bySec[s] || (bySec[s] = [])).push(f);
      });
      let html = "";
      Object.keys(bySec).forEach((sec) => {
        html += `<h6>${escapeHtml(sec)}</h6>`;
        bySec[sec].forEach((f) => {
          html += `<div class="mb-2"><label class="form-label small">${escapeHtml(f.label || f.name)}${f.required ? " *" : ""}</label>`;
          if (f.type === "textarea" || f.type === "observations") html += `<textarea class="form-control form-control-sm" rows="2" disabled></textarea>`;
          else if (f.type === "yes_no" || f.type === "select") html += `<select class="form-select form-select-sm" disabled><option>—</option></select>`;
          else if (f.type === "editable_table") html += `<div class="border rounded p-2 small text-muted">Tabla editable</div>`;
          else html += `<input class="form-control form-control-sm" disabled>`;
          html += `</div>`;
        });
      });
      frame.innerHTML = html || '<p class="text-muted">Sin campos</p>';
    }

    function collectSchema() {
      return {
        sections: (analysis && analysis.sections) || [{ id: "sec_general", title: "Datos generales", order: 0 }],
        fields: fields.map((f, i) => ({ ...f, order: i + 1 })),
        warnings: (analysis && analysis.warnings) || [],
        formulas: (analysis && analysis.formulas) || [],
        detectedType: (analysis && analysis.detectedType) || "",
        confidence: (analysis && analysis.confidence) || 0,
      };
    }

    function analyze() {
      if (!file || analyzing) return;
      analyzing = true;
      showError("");
      qs("#sgiCrAnalyzing").classList.remove("d-none");
      qs("#sgiCrAnalyzingName").textContent = file.name;
      qs("#sgiCrFile").disabled = true;
      qs("#sgiCrNext").disabled = true;
      const fd = new FormData();
      fd.append("file", file);
      fetch(opts.analyzeUrl, {
        method: "POST",
        headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": opts.csrf || "" },
        credentials: "same-origin",
        body: fd,
      })
        .then((r) => r.json())
        .then((res) => {
          analyzing = false;
          qs("#sgiCrAnalyzing").classList.add("d-none");
          qs("#sgiCrFile").disabled = false;
          qs("#sgiCrNext").disabled = false;
          if (!res.ok) {
            showError(res.message || "No se pudo analizar el archivo.");
            return;
          }
          analysis = res.analysis || {};
          fields = Array.isArray(analysis.fields) ? analysis.fields.map((f) => ({ ...f })) : [];
          qs("#sgiCrName").value = analysis.suggestedName || opts.defaultName || "Registro";
          qs("#sgiCrCode").value = analysis.suggestedCode || "";
          const w = qs("#sgiCrWarnings");
          w.innerHTML = (analysis.warnings || [])
            .map((x) => `<div class="alert alert-warning py-1 px-2 small mb-1">${escapeHtml(x)}</div>`)
            .join("");
          renderFields();
          setStep(2);
        })
        .catch(() => {
          analyzing = false;
          qs("#sgiCrAnalyzing").classList.add("d-none");
          qs("#sgiCrFile").disabled = false;
          qs("#sgiCrNext").disabled = false;
          showError("Error de red al analizar el archivo.");
        });
    }

    function create(status) {
      const body = {
        sourceFileId: analysis && analysis.sourceFileId,
        name: qs("#sgiCrName").value.trim(),
        code: qs("#sgiCrCode").value.trim(),
        description: qs("#sgiCrDesc").value.trim(),
        originType: (analysis && analysis.originType) || "",
        status: status || "activo",
        schema: collectSchema(),
      };
      qs("#sgiCrCreate").disabled = true;
      qs("#sgiCrDraft").disabled = true;
      fetch(opts.createUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": opts.csrf || "",
        },
        credentials: "same-origin",
        body: JSON.stringify(body),
      })
        .then((r) => r.json())
        .then((res) => {
          qs("#sgiCrCreate").disabled = false;
          qs("#sgiCrDraft").disabled = false;
          if (!res.ok) {
            showError(res.message || "No se pudo crear el registro.");
            setStep(2);
            return;
          }
          if (modal) modal.hide();
          if (typeof opts.onCreated === "function") opts.onCreated(res.registro, res.message);
        })
        .catch(() => {
          qs("#sgiCrCreate").disabled = false;
          qs("#sgiCrDraft").disabled = false;
          showError("Error de red al crear el registro.");
        });
    }

    qs("#sgiCrFile").onchange = (ev) => {
      file = ev.target.files && ev.target.files[0] ? ev.target.files[0] : null;
      qs("#sgiCrFileMeta").textContent = file ? `Seleccionado: ${file.name}` : "";
      showError("");
      analysis = null;
    };
    qs("#sgiCrAddField").onclick = () => {
      fields.push({
        id: `field_${Date.now()}`,
        name: `campo_${fields.length + 1}`,
        label: `Campo ${fields.length + 1}`,
        type: "text",
        required: false,
        order: fields.length + 1,
        section: "Datos generales",
        options: [],
        mode: "editable",
      });
      renderFields();
    };
    qs("#sgiCrBack").onclick = () => {
      if (step === 3) setStep(2);
      else if (step === 2) setStep(1);
    };
    qs("#sgiCrNext").onclick = () => {
      if (step === 1) analyze();
      else if (step === 2) {
        setStep(3);
        renderPreview("desktop");
      }
    };
    qs("#sgiCrCreate").onclick = () => create("activo");
    qs("#sgiCrDraft").onclick = () => create("borrador");
    modalEl.querySelectorAll("[data-preview-vp]").forEach((btn) => {
      btn.addEventListener("click", () => {
        modalEl.querySelectorAll("[data-preview-vp]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        renderPreview(btn.getAttribute("data-preview-vp"));
      });
    });

    setStep(1);
    showError("");
    qs("#sgiCrFile").value = "";
    qs("#sgiCrFileMeta").textContent = "";
    file = null;
    analysis = null;
    fields = [];
    if (modal) modal.show();
  }

  global.SgiCreateRecordWizard = CreateRecordWizard;
})(window);
