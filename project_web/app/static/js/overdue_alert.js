/**
 * Alerta global de cronómetro vencido: titileo de pantalla + modal.
 * Se activa solo si window.QDV_OVERDUE_ALERT_ENABLED es true (operador en turno).
 * El poll del servidor es la fuente de verdad para apagar el rojo.
 */
(function () {
  "use strict";

  if (!window.QDV_OVERDUE_ALERT_ENABLED) return;

  var POLL_MS = 4000;
  var CHECK_URL = "/produccion/cronometros/estado";
  var overdueKeys = {};
  var localOverdue = {};
  var dismissedKeys = {};
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

  function showModal(labels) {
    var unique = [];
    labels.forEach(function (l) {
      if (l && unique.indexOf(l) < 0) unique.push(l);
    });
    if (!unique.length) return;
    var el = modalEl();
    var txt = modalText();
    if (!el || !txt) {
      pendingLabels = unique.slice();
      return;
    }
    txt.textContent =
      unique.length === 1
        ? "El cronómetro de " +
          unique[0] +
          " está vencido. Registrá ese análisis para apagar el aviso."
        : "Cronómetros vencidos: " +
          unique.join(", ") +
          ". Registrá cada uno. En Reactor hay dos independientes: registro principal y Análisis 8 hs.";
    el.hidden = false;
    modalOpen = true;
  }

  function closeModalOnly() {
    var el = modalEl();
    if (el) el.hidden = true;
    modalOpen = false;
    pendingLabels = [];
  }

  function hideModal() {
    Object.keys(overdueKeys).forEach(function (k) {
      dismissedKeys[k] = true;
    });
    closeModalOnly();
  }

  function report(key, label, fromLocal) {
    if (!key) return;
    if (fromLocal) localOverdue[key] = true;
    var wasNew = !overdueKeys[key];
    overdueKeys[key] = label || key;
    refreshFlash();
    if (!wasNew) return;
    if (dismissedKeys[key]) return;
    if (modalOpen) {
      pendingLabels.push(label || key);
      var txt = modalText();
      if (txt) {
        txt.textContent = "Cronómetros vencidos: " + overdueLabels().join(", ") + ".";
      }
    } else {
      showModal([label || key]);
    }
  }

  function resolve(key) {
    if (!key) return;
    delete localOverdue[key];
    delete dismissedKeys[key];
    if (!overdueKeys[key]) {
      refreshFlash();
      return;
    }
    delete overdueKeys[key];
    refreshFlash();
    if (!Object.keys(overdueKeys).length) closeModalOnly();
  }

  function clearAll() {
    overdueKeys = {};
    localOverdue = {};
    dismissedKeys = {};
    closeModalOnly();
    setFlashing(false);
  }

  function applyServerOverdue(items) {
    var list = items || [];
    if (!list.length) {
      // Fuente de verdad: si el servidor no reporta vencidos, apagar sí o sí.
      clearAll();
      return;
    }
    var incoming = {};
    list.forEach(function (t) {
      incoming[t.key] = t.label || t.key;
    });
    Object.keys(overdueKeys).forEach(function (k) {
      if (!incoming[k]) {
        delete localOverdue[k];
        delete dismissedKeys[k];
        delete overdueKeys[k];
      }
    });
    Object.keys(incoming).forEach(function (k) {
      report(k, incoming[k], false);
    });
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
        applyServerOverdue(data.overdue || []);
      })
      .catch(function () {});
  }

  function bindModal() {
    var ack = document.getElementById("qdvOverdueModalAck");
    if (ack) {
      ack.addEventListener("click", function () {
        hideModal();
      });
    }
  }

  window.QdvOverdueAlert = {
    report: report,
    resolve: resolve,
    clearAll: clearAll,
  };

  function init() {
    bindModal();
    // Arrancar apagado; el poll enciende solo si hay vencidos reales.
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
