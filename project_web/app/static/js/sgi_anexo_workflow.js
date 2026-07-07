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
      reviso: qs("#anexoReviso")?.value || "",
      aprobo: qs("#anexoAprobo")?.value || "",
      revisor_correo: qs("#anexoRevisorCorreo")?.value || "",
      aprobador_correo: qs("#anexoAprobadorCorreo")?.value || "",
      perfiles_aplica: qsa(".anexo-perfil-check:checked").map((el) => el.value),
    };
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
        flash("danger", "Seleccioná al menos un sector/perfil al que aplica el documento.");
        return;
      }
      const revisorCorreo = (qs("#anexoRevisorCorreo")?.value || "").trim();
      const revisoTexto = (qs("#anexoReviso")?.value || "").trim();
      if (!/[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}/.test(`${revisorCorreo} ${revisoTexto}`)) {
        flash("danger", "Completá el correo del revisor en la carátula.");
        return;
      }
    }
    if (accion === "marcar_revisado") {
      const aprobadorCorreo = (qs("#anexoAprobadorCorreo")?.value || "").trim();
      const aproboTexto = (qs("#anexoAprobo")?.value || "").trim();
      if (!/[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}/.test(`${aprobadorCorreo} ${aproboTexto}`)) {
        flash("danger", "Completá el correo del aprobador en la carátula.");
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
})();
