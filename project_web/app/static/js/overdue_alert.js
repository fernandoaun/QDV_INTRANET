/**
 * Alerta global de cronómetro vencido: titileo de pantalla + modal.
 * Se activa solo si window.QDV_OVERDUE_ALERT_ENABLED es true (operador en turno).
 *
 * Reglas:
 * - El poll del servidor enciende avisos de circuitos que no están en esta pantalla.
 * - Si el cronómetro visible de la página dice «En tiempo» / no vencido, ese circuito
 *   no se alerta (evita falso positivo por desfase servidor vs UI).
 * - Al guardar un análisis se limpia ese circuito de inmediato.
 */
(function () {
  "use strict";

  if (!window.QDV_OVERDUE_ALERT_ENABLED) return;

  var POLL_MS = 4000;
  var CHECK_URL = "/produccion/cronometros/estado";
  var overdueKeys = {};
  var localOverdue = {};
  /** Circuitos cuyo cronómetro en pantalla está en tiempo / no vencido. */
  var localOkKeys = {};
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

  function messageForKeys(keys) {
    var labels = [];
    (keys || []).forEach(function (k) {
      if (!k) return;
      var lab = overdueKeys[k] || k;
      if (labels.indexOf(lab) < 0) labels.push(lab);
    });
    if (!labels.length) return "";
    if (labels.length === 1) {
      return (
        "El cronómetro de " +
        labels[0] +
        " está vencido. Registrá ese análisis para apagar el aviso."
      );
    }
    return "Cronómetros vencidos: " + labels.join(", ") + ". Registrá cada análisis pendiente.";
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
    if (!keys.length) {
      keys = Object.keys(overdueKeys);
    }
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

  function scrollToOverdueTarget() {
    var keys = Object.keys(overdueKeys);
    var target = null;
    if (keys.indexOf("reactor") >= 0) {
      target = document.getElementById("reactorMainForm");
    } else if (keys.indexOf("analisis_8hs") >= 0) {
      target = document.getElementById("analisis8hsSalmuera") || document.getElementById("analisis8Form");
    }
    if (target && typeof target.scrollIntoView === "function") {
      try {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (_) {
        target.scrollIntoView(true);
      }
    }
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

  function dropKey(key) {
    delete overdueKeys[key];
    delete localOverdue[key];
    refreshFlash();
    if (!Object.keys(overdueKeys).length) closeModalOnly();
  }

  function report(key, label, fromLocal) {
    if (!key) return;
    if (fromLocal) {
      delete localOkKeys[key];
      localOverdue[key] = true;
    } else if (localOkKeys[key]) {
      // Cronómetro de esta página: en tiempo → no alertar aunque el poll diga vencido.
      dropKey(key);
      return;
    }
    var wasNew = !overdueKeys[key];
    overdueKeys[key] = label || key;
    refreshFlash();
    if (!wasNew) return;
    if (dismissedKeys[key]) return;
    if (modalOpen) {
      pendingLabels.push(key);
      var txt = modalText();
      if (txt) {
        txt.textContent = messageForKeys(Object.keys(overdueKeys));
      }
    } else {
      showModal([key]);
    }
  }

  /**
   * @param {string} key
   * @param {boolean|{fromLocal?: boolean}} [opts] true o {fromLocal:true} = tick de cronómetro en pantalla
   */
  function resolve(key, opts) {
    if (!key) return;
    var fromLocal = opts === true || (opts && opts.fromLocal);
    delete localOverdue[key];
    if (fromLocal) {
      localOkKeys[key] = true;
    } else {
      delete localOkKeys[key];
      delete dismissedKeys[key];
    }
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
    localOkKeys = {};
    dismissedKeys = {};
    closeModalOnly();
    setFlashing(false);
  }

  function applyServerOverdue(items) {
    var list = items || [];
    if (!list.length) {
      // Sin vencidos en servidor: apagar todo salvo lo que el tick local marcó vencido hace un instante.
      var keepLocal = {};
      Object.keys(localOverdue).forEach(function (k) {
        if (overdueKeys[k]) keepLocal[k] = overdueKeys[k];
      });
      overdueKeys = keepLocal;
      dismissedKeys = {};
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
      var k = t.key;
      if (!k) return;
      if (localOkKeys[k]) {
        dropKey(k);
        return;
      }
      incoming[k] = t.label || k;
    });
    Object.keys(overdueKeys).forEach(function (k) {
      if (!incoming[k] && !localOverdue[k]) {
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
        scrollToOverdueTarget();
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
