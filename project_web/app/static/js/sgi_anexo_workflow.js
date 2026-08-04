(function () {
  "use strict";

  const cfg = window.SGI_ANEXO_WORKFLOW;
  if (!cfg) return;

  function qs(sel) {
    return document.querySelector(sel);
  }
  function qsa(sel) {
    return Array.from(document.querySelectorAll(sel));
  }

  function flash(kind, msg) {
    const el = qs("#sgiAnexoFlash") || qs("#sgiOrgFlash");
    if (!el) return;
    el.className = `alert alert-${kind} sgi-proc-no-print`;
    el.textContent = msg;
    el.classList.remove("d-none");
  }

  function collectCaratula() {
    return {
      elaboro: qs("#anexoElaboro")?.value || "",
      elaboro_puesto_id: qs("#anexoElaboroPuesto")?.value || "",
      reviso: qs("#anexoReviso")?.value || "",
      reviso_puesto_id: qs("#anexoRevisoPuesto")?.value || "",
      aprobo: qs("#anexoAprobo")?.value || "",
      aprobo_puesto_id: qs("#anexoAproboPuesto")?.value || "",
      revisor_correo: qs("#anexoRevisorCorreo")?.value || "",
      aprobador_correo: qs("#anexoAprobadorCorreo")?.value || "",
      perfiles_aplica: qsa(".anexo-perfil-check:checked").map((el) => el.value),
    };
  }

  function applyPuestoSelect(selectEl) {
    if (!selectEl) return;
    const opt = selectEl.options[selectEl.selectedIndex];
    const titulo = (opt?.dataset?.titulo || "").trim();
    const emails = (opt?.dataset?.emails || "").trim();
    const labelSel = selectEl.dataset.labelTarget;
    const emailSel = selectEl.dataset.emailTarget;
    if (labelSel) {
      const labelEl = qs(labelSel);
      if (labelEl && titulo) labelEl.value = titulo.toUpperCase();
    }
    if (emailSel) {
      const emailEl = qs(emailSel);
      if (emailEl) emailEl.value = emails;
    }
  }

  function bindPuestoSelects() {
    qsa(".anexo-puesto-select").forEach((sel) => {
      sel.addEventListener("change", () => applyPuestoSelect(sel));
      if (sel.value) applyPuestoSelect(sel);
    });
  }

  async function postJson(url, data) {
    const token = qs('meta[name="csrf-token"]')?.content || cfg.csrf || "";
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": token,
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
      body: JSON.stringify(data),
    });
    return res.json();
  }

  async function guardarCaratula() {
    const res = await postJson(cfg.urls.guardar, collectCaratula());
    if (!res.ok) flash("danger", res.message || res.error || "No se pudo guardar.");
    return res;
  }

  async function guardarContenidoSiHay() {
    if (typeof cfg.onGuardarContenido === "function") {
      return cfg.onGuardarContenido();
    }
    return { ok: true };
  }

  async function workflow(accion) {
    if (accion === "enviar_revision") {
      const perfiles = qsa(".anexo-perfil-check:checked");
      if (!perfiles.length) {
        flash("danger", "Seleccioná al menos un puesto del organigrama al que aplica el documento.");
        return;
      }
      const revisorCorreo = (qs("#anexoRevisorCorreo")?.value || "").trim();
      const revisoTexto = (qs("#anexoReviso")?.value || "").trim();
      const puestoEmails = (qs("#anexoRevisoPuesto")?.selectedOptions?.[0]?.dataset?.emails || "").trim();
      if (!/[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}/.test(`${revisorCorreo} ${revisoTexto} ${puestoEmails}`)) {
        flash("danger", "Elegí el puesto revisor con email en personal, o completá el correo del revisor.");
        return;
      }
    }
    if (accion === "marcar_revisado") {
      const aprobadorCorreo = (qs("#anexoAprobadorCorreo")?.value || "").trim();
      const aproboTexto = (qs("#anexoAprobo")?.value || "").trim();
      const puestoEmails = (qs("#anexoAproboPuesto")?.selectedOptions?.[0]?.dataset?.emails || "").trim();
      if (!/[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}/.test(`${aprobadorCorreo} ${aproboTexto} ${puestoEmails}`)) {
        flash("danger", "Elegí el puesto aprobador con email en personal, o completá el correo del aprobador.");
        return;
      }
    }

    if (!cfg.soloLectura) {
      const contenido = await guardarContenidoSiHay();
      if (!contenido.ok) return;
      const caratula = await guardarCaratula();
      if (!caratula.ok && accion !== "marcar_revisado") return;
    } else if (accion === "marcar_revisado") {
      await guardarCaratula();
    }

    const body = { accion };
    if (accion === "reenviar_aviso" || accion === "marcar_revisado") {
      body.revisor_correo = qs("#anexoRevisorCorreo")?.value || "";
      body.aprobador_correo = qs("#anexoAprobadorCorreo")?.value || "";
    }
    if (accion === "marcar_revisado") {
      body.aprobo = qs("#anexoAprobo")?.value || "";
      body.aprobo_puesto_id = qs("#anexoAproboPuesto")?.value || "";
    }

    const res = await postJson(cfg.urls.workflow, body);
    if (res.ok) {
      flash("success", res.message || "Listo.");
      if (res.redirect) {
        window.location.href = res.redirect;
      } else {
        window.location.reload();
      }
    } else {
      flash("danger", res.message || res.error || "No se pudo completar la acción.");
    }
  }

  bindPuestoSelects();

  qs("#btnAnexoGuardarCaratula")?.addEventListener("click", async () => {
    const contenido = await guardarContenidoSiHay();
    if (!contenido.ok) return;
    const res = await guardarCaratula();
    flash(res.ok ? "success" : "danger", res.message || (res.ok ? "Guardado." : "Error."));
  });
  qs("#btnAnexoEnviarRevision")?.addEventListener("click", () => workflow("enviar_revision"));
  qs("#btnAnexoMarcarRevisado")?.addEventListener("click", () => workflow("marcar_revisado"));
  qs("#btnAnexoReenviarAviso")?.addEventListener("click", () => workflow("reenviar_aviso"));
  qs("#btnAnexoAprobar")?.addEventListener("click", () => workflow("aprobar"));
  qs("#btnAnexoNuevaRevision")?.addEventListener("click", () => workflow("nueva_revision"));

  qs("#anexoFirmaGerenteInput")?.addEventListener("change", async (ev) => {
    const input = ev.target;
    const file = input.files?.[0];
    if (!file || !cfg.urls?.firmaGerente) return;
    const fd = new FormData();
    fd.append("firma", file);
    fd.append("csrf_token", cfg.csrf || "");
    const token = qs('meta[name="csrf-token"]')?.content || cfg.csrf || "";
    try {
      const res = await fetch(cfg.urls.firmaGerente, {
        method: "POST",
        headers: { "X-CSRFToken": token, "X-Requested-With": "XMLHttpRequest" },
        body: fd,
        credentials: "same-origin",
      });
      if (res.redirected || res.ok) {
        flash("success", "Firma guardada.");
        window.location.reload();
        return;
      }
      flash("danger", "No se pudo guardar la firma.");
    } catch {
      flash("danger", "Error al subir la firma.");
    }
    input.value = "";
  });
})();
