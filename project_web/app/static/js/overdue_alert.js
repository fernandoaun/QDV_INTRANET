/**
 * Alerta global de cronómetro vencido: titileo de pantalla + modal.
 * Se activa solo si window.QDV_OVERDUE_ALERT_ENABLED es true (operador en turno).
 */
(function () {
  "use strict";

  if (!window.QDV_OVERDUE_ALERT_ENABLED) return;

  var POLL_MS = 5000;
  var CHECK_URL = "/produccion/cronometros/estado";
  var overdueKeys = {};
  var localOverdue = {};
  var modalOpen = false;
  var pendingLabels = [];

  function overlay() {
    return document.getElementById("qdvOverdueOverlay");
  }

  function modalEl() {
    return document.getElementById("qdvOverdueModal");
  }

  function modalText() {
    return document.getElementById("qdvOverdueModalText");
  }

  function setFlashing(on) {
    document.body.classList.toggle("qdv-overdue-active", !!on);
    var ov = overlay();
    if (ov) ov.hidden = !on;
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
        ? "El cronómetro de " + unique[0] + " llegó a cero. Registrá el análisis lo antes posible."
        : "Hay cronómetros vencidos: " + unique.join(", ") + ". Registrá el análisis lo antes posible.";
    el.hidden = false;
    modalOpen = true;
  }

  function hideModal() {
    var el = modalEl();
    if (el) el.hidden = true;
    modalOpen = false;
    pendingLabels = [];
  }

  function report(key, label, fromLocal) {
    if (!key) return;
    if (fromLocal) localOverdue[key] = true;
    var wasNew = !overdueKeys[key];
    overdueKeys[key] = label || key;
    refreshFlash();
    if (wasNew) {
      if (modalOpen) {
        pendingLabels.push(label || key);
        var txt = modalText();
        if (txt) {
          var names = Object.keys(overdueKeys).map(function (k) {
            return overdueKeys[k];
          });
          txt.textContent = "Hay cronómetros vencidos: " + names.join(", ") + ". Registrá el análisis lo antes posible.";
        }
      } else {
        showModal([label || key]);
      }
    }
  }

  function resolve(key) {
    if (!key) return;
    delete localOverdue[key];
    if (!overdueKeys[key]) {
      refreshFlash();
      return;
    }
    delete overdueKeys[key];
    refreshFlash();
    if (!Object.keys(overdueKeys).length) hideModal();
  }

  function clearAll() {
    overdueKeys = {};
    localOverdue = {};
    refreshFlash();
    hideModal();
  }

  function applyServerOverdue(items) {
    var incoming = {};
    (items || []).forEach(function (t) {
      incoming[t.key] = t.label || t.key;
    });
    Object.keys(overdueKeys).forEach(function (k) {
      if (!incoming[k]) resolve(k);
    });
    Object.keys(incoming).forEach(function (k) {
      report(k, incoming[k], false);
    });
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
    poll();
    setInterval(poll, POLL_MS);
    refreshFlash();
    var labels = Object.keys(overdueKeys).map(function (k) {
      return overdueKeys[k];
    });
    if (pendingLabels.length) {
      labels = labels.concat(pendingLabels);
    }
    if (labels.length && !modalOpen) {
      showModal(labels);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
