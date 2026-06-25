/**
 * Parada de planta: toggle vía POST /produccion/parada-planta y lógica de cronómetro pausado.
 */
(function () {
  "use strict";

  const PARADA_URL = "/produccion/parada-planta";

  function csrfToken() {
    const inp = document.querySelector('input[name="csrf_token"]');
    return inp ? inp.value : "";
  }

  function parseIsoLocal(iso) {
    const d = new Date(iso);
    if (!isNaN(d.getTime())) return d;
    return new Date((iso || "").replace(" ", "T"));
  }

  function fmtHhmmss(totalSeconds) {
    const s = Math.max(0, Math.floor(totalSeconds));
    const h = String(Math.floor(s / 3600)).padStart(2, "0");
    const m = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
    const ss = String(s % 60).padStart(2, "0");
    return `${h}:${m}:${ss}`;
  }

  function applyTimerState(ctx, plantStop) {
    const { timerText, timerSub, timerState, intervalSec, lastCreatedIso, clockOffsetMs } = ctx;
    if (!timerText || !timerSub || !timerState) return;

    if (plantStop && plantStop.active) {
      const frozen = Number(plantStop.frozen_remaining_sec);
      timerText.textContent = fmtHhmmss(Number.isFinite(frozen) ? frozen : 0);
      timerSub.textContent = `Parada de planta desde ${plantStop.started_at_iso || "—"}`;
      timerState.className = "badge text-bg-warning app-badge-soft";
      timerState.textContent = "Parada";
      return;
    }

    const pauseExtra = plantStop && plantStop.pause_extra_seconds ? Number(plantStop.pause_extra_seconds) : 0;
    if (!lastCreatedIso) {
      if (ctx._emptyAnchorMs == null) {
        ctx._emptyAnchorMs = Date.now() + (clockOffsetMs || 0);
      }
      const now = Date.now() + (clockOffsetMs || 0);
      const dueMs = ctx._emptyAnchorMs + intervalSec * 1000;
      const diffSec = (dueMs - now) / 1000;
      if (diffSec >= 0) {
        timerText.textContent = fmtHhmmss(diffSec);
        timerSub.textContent = ctx.emptySub || "Sin registros en la fecha seleccionada.";
        timerState.className = "badge text-bg-secondary app-badge-soft";
        timerState.textContent = "En tiempo";
      } else {
        const due = new Date(dueMs);
        timerText.textContent = fmtHhmmss(-diffSec);
        timerSub.textContent = `Vencido desde: ${due.toISOString().slice(0, 19).replace("T", " ")}`;
        timerState.className = "badge text-bg-danger app-badge-soft";
        timerState.textContent = "Atrasado";
      }
      return;
    }
    const last = parseIsoLocal(lastCreatedIso);
    const due = new Date(last.getTime() + intervalSec * 1000 + pauseExtra * 1000);
    const now = new Date(Date.now() + (clockOffsetMs || 0));
    const diffSec = (due.getTime() - now.getTime()) / 1000;
    if (diffSec >= 0) {
      timerText.textContent = fmtHhmmss(diffSec);
      timerSub.textContent = `Último registro: ${lastCreatedIso}`;
      timerState.className = "badge text-bg-success app-badge-soft";
      timerState.textContent = "En tiempo";
    } else {
      timerText.textContent = fmtHhmmss(-diffSec);
      timerSub.textContent = `Vencido desde: ${due.toISOString().slice(0, 19).replace("T", " ")}`;
      timerState.className = "badge text-bg-danger app-badge-soft";
      timerState.textContent = "Atrasado";
    }
  }

  function updateToggleButton(btn, plantStop, eventPayload) {
    if (!btn) return;
    const active = !!(plantStop && plantStop.active);
    btn.dataset.active = active ? "1" : "0";
    btn.setAttribute("aria-pressed", active ? "true" : "false");
    btn.textContent = active ? "Reanudar análisis" : "Parada de planta";
    btn.classList.toggle("btn-outline-warning", !active);
    btn.classList.toggle("btn-outline-success", active);
    const wrap = btn.closest("[data-plant-stop-wrap]");
    const hint = wrap ? wrap.querySelector(".js-plant-stop-hint") : null;
    const motivoWrap = wrap ? wrap.querySelector(".js-plant-stop-motivo-wrap") : null;
    const motivoShown = wrap ? wrap.querySelector(".js-plant-stop-motivo-shown") : null;
    const motivoText = wrap ? wrap.querySelector(".js-plant-stop-motivo-text") : null;
    const motivoInp = wrap ? wrap.querySelector(".js-plant-stop-motivo") : null;
    const isReactor = btn.dataset.circuitKey === "reactor";
    const scope = wrap && wrap.dataset.plantStopScope ? wrap.dataset.plantStopScope : "main";
    if (hint) {
      let base = active
        ? `Cronómetro detenido por parada desde ${plantStop.started_at_iso || "—"}.`
        : "Usá este botón cuando la planta esté detenida y no puedas registrar análisis.";
      if (isReactor) {
        if (scope === "analisis8") {
          base += active
            ? " También se detiene el cronómetro del registro principal."
            : " Detiene este cronómetro y el del registro principal.";
        } else {
          base += active
            ? " También se detiene el cronómetro del análisis 8 hs."
            : " Incluye el cronómetro del análisis 8 hs.";
        }
      }
      hint.textContent = base;
    }
    if (motivoWrap) {
      motivoWrap.classList.toggle("d-none", active);
    }
    const motivoVal =
      (eventPayload && eventPayload.event && (eventPayload.event.observaciones || eventPayload.event.motivo)) ||
      "";
    if (motivoShown && motivoText) {
      if (active && motivoVal) {
        motivoText.textContent = motivoVal;
        motivoShown.classList.remove("d-none");
      } else {
        motivoShown.classList.add("d-none");
        motivoText.textContent = "";
      }
    }
    if (!active && motivoInp) {
      motivoInp.value = "";
    }
  }

  function motivoFromWrap(wrap) {
    if (!wrap) return "";
    const inp = wrap.querySelector(".js-plant-stop-motivo");
    return inp ? String(inp.value || "").trim() : "";
  }

  function motivoForCircuit(circuitKey, preferredWrap) {
    const fromPreferred = motivoFromWrap(preferredWrap);
    if (fromPreferred) return fromPreferred;
    const key = String(circuitKey || "");
    if (!key) return "";
    for (const w of document.querySelectorAll(`[data-plant-stop-wrap="${key}"]`)) {
      const m = motivoFromWrap(w);
      if (m) return m;
    }
    return "";
  }

  async function postToggle(circuitKey, fechaIso, action, observaciones) {
    const headers = {
      "Content-Type": "application/json",
      Accept: "application/json",
      "X-Requested-With": "XMLHttpRequest",
    };
    const token = csrfToken();
    if (token) headers["X-CSRFToken"] = token;
    const body = {
      circuit_key: circuitKey,
      fecha_iso: fechaIso,
      action,
    };
    if (observaciones) {
      body.observaciones = observaciones;
    }
    const resp = await fetch(PARADA_URL, {
      method: "POST",
      headers,
      credentials: "same-origin",
      body: JSON.stringify(body),
    });
    const raw = await resp.text();
    let payload = null;
    try {
      payload = raw ? JSON.parse(raw) : null;
    } catch (_) {
      payload = null;
    }
    if (!resp.ok || !payload || !payload.ok) {
      const msg =
        (payload && (payload.error || payload.message)) ||
        `No se pudo registrar la parada (${resp.status}).`;
      throw new Error(msg);
    }
    return payload;
  }

  function bindToggleButtons(timerContextsByCircuit, options) {
    const opts = options || {};
    document.querySelectorAll(".js-plant-stop-toggle").forEach((btn) => {
      if (btn.dataset.plantStopBound === "1") return;
      btn.dataset.plantStopBound = "1";
      btn.addEventListener("click", async () => {
        const circuitKey = btn.dataset.circuitKey;
        const fechaIso = btn.dataset.fechaIso || "";
        const active = btn.dataset.active === "1";
        const action = active ? "end" : "start";
        const wrap = btn.closest("[data-plant-stop-wrap]");
        const errEl = wrap ? wrap.querySelector(".js-plant-stop-error") : null;
        if (errEl) {
          errEl.classList.add("d-none");
          errEl.textContent = "";
        }
        btn.disabled = true;
        try {
          const fechaHoy = wrap && wrap.dataset.fechaHoy ? String(wrap.dataset.fechaHoy).trim() : "";
          if (fechaHoy && fechaIso && fechaIso !== fechaHoy) {
            throw new Error(
              "La parada de planta solo puede declararse o reanudarse en la fecha operativa de hoy."
            );
          }
          if (!active && !window.confirm("¿Declarar parada de planta? El cronómetro se detendrá.")) {
            return;
          }
          const motivo = !active ? motivoForCircuit(circuitKey, wrap) : "";
          const payload = await postToggle(circuitKey, fechaIso, action, motivo);
          const ps = payload.plant_stop;
          document
            .querySelectorAll(`.js-plant-stop-toggle[data-circuit-key="${CSS.escape(circuitKey)}"]`)
            .forEach((b) => updateToggleButton(b, ps, payload));
          const ctx = timerContextsByCircuit[circuitKey];
          if (ctx) {
            ctx.plantStop = ps;
            if (ctx.timerRow) {
              ctx.timerRow.plant_stop = ps;
            }
            applyTimerState(ctx, ps);
          }
          if (typeof opts.onAfterToggle === "function") {
            opts.onAfterToggle(payload, { circuitKey, action, btn, wrap });
          }
        } catch (e) {
          if (errEl) {
            errEl.textContent = e.message || "Error al registrar parada.";
            errEl.classList.remove("d-none");
          }
        } finally {
          btn.disabled = false;
        }
      });
    });
  }

  window.QdvPlantStop = {
    parseIsoLocal,
    fmtHhmmss,
    applyTimerState,
    bindToggleButtons,
  };
})();
