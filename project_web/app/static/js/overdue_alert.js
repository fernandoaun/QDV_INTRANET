/**
 * Alerta global de cronómetro vencido: titileo de pantalla + modal.
 * Se activa solo si window.QDV_OVERDUE_ALERT_ENABLED es true (operador en turno).
 *
 * Reglas:
 * - El poll del servidor alimenta el modal/titileo (lista overdue).
 * - El cronómetro de la pantalla lo pinta solo plant_stop.js (1 s); el poll no pisa el DOM.
 * - «Entendido» se recuerda en sessionStorage para no reabrir el modal al cambiar de página
 *   (el banner/titileo siguen hasta registrar el análisis).
 * - Al guardar un análisis se limpia ese circuito de inmediato.
 */
(function () {
  "use strict";

  if (!window.QDV_OVERDUE_ALERT_ENABLED) return;

  var POLL_MS = 4000;
  var CHECK_URL = "/produccion/cronometros/estado";
  var DISMISS_STORE = "qdvOverdueDismissedV2";
  var overdueKeys = {};
  var overdueMeta = {};
  var localOverdue = {};
  var dismissedMap = {};
  var modalOpen = false;
  var pendingLabels = [];

  function overlay() {
    return document.getElementById("qdvOverdueOverlay");
  }

  function banner() {
    return document.getElementById("qdvOverdueBanner");
  }

  function modalEl() {
    return document.getElementById("qdvOverdueModal");
  }

  function modalText() {
    return document.getElementById("qdvOverdueModalText");
  }

  function loadDismissed() {
    try {
      var raw = sessionStorage.getItem(DISMISS_STORE);
      var parsed = raw ? JSON.parse(raw) : {};
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (e) {
      return {};
    }
  }

  function saveDismissed() {
    try {
      sessionStorage.setItem(DISMISS_STORE, JSON.stringify(dismissedMap));
    } catch (e) {}
  }

  function dismissToken(key) {
    var meta = overdueMeta[key] || {};
    // Solo el ancla: el atraso cambia cada segundo y no debe reabrir el modal.
    return String(meta.last_created_at_iso || key);
  }

  function isDismissed(key) {
    if (!dismissedMap[key]) return false;
    return dismissedMap[key] === dismissToken(key);
  }

  function fmtAtraso(remaining) {
    var s = Math.abs(Math.floor(Number(remaining) || 0));
    var h = String(Math.floor(s / 3600)).padStart(2, "0");
    var m = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
    var ss = String(s % 60).padStart(2, "0");
    return h + ":" + m + ":" + ss;
  }

  function fmtLast(iso) {
    if (!iso) return "sin registro";
    return String(iso).replace("T", " ").slice(0, 19);
  }

  function overdueLabels() {
    return Object.keys(overdueKeys).map(function (k) {
      return overdueKeys[k];
    });
  }

  function updateBanner() {
    var b = banner();
    if (!b) return;
    var labels = overdueLabels();
    if (!labels.length) {
      b.textContent = "";
      return;
    }
    b.textContent = "Vencido: " + labels.join(" · ");
  }

  function setFlashing(on) {
    if (on) {
      document.body.classList.add("qdv-overdue-active");
    } else {
      document.body.classList.remove("qdv-overdue-active");
    }
    var ov = overlay();
    if (ov) {
      ov.hidden = !on;
      ov.setAttribute("aria-hidden", on ? "false" : "true");
    }
    updateBanner();
  }

  function refreshFlash() {
    setFlashing(Object.keys(overdueKeys).length > 0);
  }

  function messageForKeys(keys) {
    var parts = [];
    (keys || []).forEach(function (k) {
      if (!k || !overdueKeys[k]) return;
      var meta = overdueMeta[k] || {};
      var line =
        overdueKeys[k] +
        " (último " +
        fmtLast(meta.last_created_at_iso) +
        ", atraso " +
        fmtAtraso(meta.remaining) +
        ")";
      if (parts.indexOf(line) < 0) parts.push(line);
    });
    if (!parts.length) return "";
    if (parts.length === 1) {
      return (
        "El cronómetro de " +
        parts[0] +
        " está vencido. Registrá ese análisis para apagar el aviso."
      );
    }
    return "Cronómetros vencidos: " + parts.join("; ") + ". Registrá cada análisis pendiente.";
  }

  function showModal(keysOrLabels) {
    var keys = [];
    (keysOrLabels || []).forEach(function (item) {
      if (!item) return;
      if (Object.prototype.hasOwnProperty.call(overdueKeys, item)) {
        if (keys.indexOf(item) < 0) keys.push(item);
        return;
      }
      var found = null;
      Object.keys(overdueKeys).forEach(function (k) {
        if (overdueKeys[k] === item) found = k;
      });
      if (found && keys.indexOf(found) < 0) keys.push(found);
      else if (!found && keys.indexOf(item) < 0) keys.push(item);
    });
    if (!keys.length) keys = Object.keys(overdueKeys);
    if (!keys.length) return;
    var el = modalEl();
    var txt = modalText();
    var msg = messageForKeys(keys);
    if (!el || !txt) {
      pendingLabels = keys.slice();
      return;
    }
    txt.textContent = msg;
    el.hidden = false;
    modalOpen = true;
  }

  function moduleUrlForKey(key) {
    if (key === "reactor" || key === "analisis_8hs") return "/produccion/reactor";
    if (key === "agua") return "/produccion/agua";
    if (key === "filtro" || key.indexOf("salmuera_") === 0) return "/produccion/salmuera";
    return null;
  }

  function goToOverdueModule() {
    var keys = Object.keys(overdueKeys);
    var preferred = null;
    if (keys.indexOf("reactor") >= 0) preferred = "reactor";
    else if (keys.length) preferred = keys[0];
    if (!preferred) return false;
    var url = moduleUrlForKey(preferred);
    if (!url) return false;
    if (window.location.pathname.indexOf(url) === 0) {
      var target = null;
      if (preferred === "reactor") target = document.getElementById("reactorMainForm");
      if (preferred === "analisis_8hs") {
        target = document.getElementById("analisis8hsSalmuera") || document.getElementById("analisis8Form");
      }
      if (target && typeof target.scrollIntoView === "function") {
        try {
          target.scrollIntoView({ behavior: "smooth", block: "start" });
        } catch (e) {
          target.scrollIntoView(true);
        }
      }
      return false;
    }
    window.location.href = url;
    return true;
  }

  function closeModalOnly() {
    var el = modalEl();
    if (el) el.hidden = true;
    modalOpen = false;
    pendingLabels = [];
  }

  function hideModal() {
    Object.keys(overdueKeys).forEach(function (k) {
      dismissedMap[k] = dismissToken(k);
    });
    saveDismissed();
    closeModalOnly();
  }

  function dropKey(key) {
    delete overdueKeys[key];
    delete overdueMeta[key];
    delete localOverdue[key];
    refreshFlash();
    if (!Object.keys(overdueKeys).length) closeModalOnly();
  }

  function report(key, label, fromLocal, meta) {
    if (!key) return;
    var rem = meta && typeof meta === "object" ? Number(meta.remaining) : NaN;
    var last = meta && typeof meta === "object" ? String(meta.last_created_at_iso || "").trim() : "";
    // Ignorar avisos falsos: sin ancla o still En tiempo (remaining >= 0).
    // Evita el modal «último sin registro, atraso 00:00:00».
    if (fromLocal) {
      if (!last) return;
      if (!Number.isFinite(rem) || rem >= 0) return;
    } else if (meta && typeof meta === "object") {
      if (!last) return;
      if (Number.isFinite(rem) && rem >= 0) return;
    }
    // Si el cronómetro de esta página ya está En tiempo con ancla más nueva, no reabrir.
    var pageCtx = (window.QdvPageTimers || {})[key];
    if (pageCtx && pageCtx.lastCreatedIso && Number(pageCtx.intervalSec) > 0) {
      var pageLast = String(pageCtx.lastCreatedIso || "").trim();
      if (pageLast && (!last || pageLast > last)) {
        var pageLastDt = Date.parse(pageLast);
        var pageDue = pageLastDt + Number(pageCtx.intervalSec) * 1000;
        var pageNow = Date.now() + Number(pageCtx.clockOffsetMs || 0);
        if (Number.isFinite(pageLastDt) && pageDue - pageNow >= 0) {
          return;
        }
      }
    }
    if (fromLocal) localOverdue[key] = true;
    var wasNew = !overdueKeys[key];
    overdueKeys[key] = label || key;
    if (meta && typeof meta === "object") {
      overdueMeta[key] = {
        last_created_at_iso: meta.last_created_at_iso || null,
        remaining: meta.remaining,
      };
    } else if (!overdueMeta[key]) {
      overdueMeta[key] = { last_created_at_iso: null, remaining: null };
    }
    refreshFlash();
    if (!wasNew) return;
    if (isDismissed(key)) return;
    if (modalOpen) {
      pendingLabels.push(key);
      var txt = modalText();
      if (txt) txt.textContent = messageForKeys(Object.keys(overdueKeys));
    } else {
      showModal([key]);
    }
  }

  /**
   * @param {string} key
   * @param {boolean|{fromLocal?: boolean}} [opts]
   */
  function resolve(key, opts) {
    if (!key) return;
    var fromLocal = opts === true || (opts && opts.fromLocal);
    delete localOverdue[key];
    if (!fromLocal) {
      delete dismissedMap[key];
      saveDismissed();
    }
    // En tiempo (local o guardado): apagar este circuito. El poll solo lo reabre si sigue vencido de verdad.
    dropKey(key);
  }

  function clearAll() {
    overdueKeys = {};
    overdueMeta = {};
    localOverdue = {};
    closeModalOnly();
    setFlashing(false);
  }

  function hasLastAnchor(t) {
    return !!(t && String(t.last_created_at_iso || "").trim());
  }

  function syncPageTimerFromServer(t) {
    if (!t || !t.key) return;
    if (!window.QdvPlantStop || typeof window.QdvPlantStop.applyServerSnapshot !== "function") {
      return;
    }
    window.QdvPlantStop.applyServerSnapshot(t);
  }

  function applyServerOverdue(items, timers) {
    var list = items || [];
    (timers || []).forEach(function (t) {
      syncPageTimerFromServer(t);
    });
    if (!list.length) {
      var keepLocal = {};
      var keepMeta = {};
      Object.keys(localOverdue).forEach(function (k) {
        if (overdueKeys[k]) {
          keepLocal[k] = overdueKeys[k];
          keepMeta[k] = overdueMeta[k];
        }
      });
      overdueKeys = keepLocal;
      overdueMeta = keepMeta;
      if (!Object.keys(overdueKeys).length) {
        closeModalOnly();
        setFlashing(false);
      } else {
        refreshFlash();
      }
      return;
    }
    var incoming = {};
    list.forEach(function (t) {
      if (!t || !t.key) return;
      if (!hasLastAnchor(t)) return;
      // Solo vencidos reales (remaining < 0). remaining == 0 no es atraso.
      if (!(Number(t.remaining) < 0)) return;
      incoming[t.key] = t;
    });
    Object.keys(overdueKeys).forEach(function (k) {
      if (!incoming[k] && !localOverdue[k]) {
        delete overdueKeys[k];
        delete overdueMeta[k];
      }
    });
    Object.keys(incoming).forEach(function (k) {
      var t = incoming[k];
      report(k, t.label || k, false, t);
    });
    if (!Object.keys(overdueKeys).length) closeModalOnly();
    refreshFlash();
  }

  function poll() {
    fetch(CHECK_URL, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) return null;
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.ok) return;
        applyServerOverdue(data.overdue || [], data.timers || []);
      })
      .catch(function () {});
  }

  function bindModal() {
    var ack = document.getElementById("qdvOverdueModalAck");
    if (ack) {
      ack.addEventListener("click", function () {
        hideModal();
        goToOverdueModule();
      });
    }
  }

  window.QdvOverdueAlert = {
    report: report,
    resolve: resolve,
    clearAll: clearAll,
  };

  function init() {
    dismissedMap = loadDismissed();
    bindModal();
    clearAll();
    poll();
    setInterval(poll, POLL_MS);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
