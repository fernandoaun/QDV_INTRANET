/*
 * Muestra todas las fechas en pantalla como día/mes/año (dd/mm/aaaa [HH:MM]).
 * La base y los formularios siguen usando ISO (aaaa-mm-dd): esto solo cambia el texto visible,
 * también el que se agrega después con JavaScript (chat, cronómetros, tablas dinámicas).
 * No toca campos de carga, scripts, ni los editores de procedimientos (contenido que se guarda).
 * Misma expresión regular que app/utils/fechas.py. Para excluir una zona: atributo data-fechas-iso.
 */
(function () {
  "use strict";
  var RE = /(^|[^\w\/-])(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?(?![\w-])/g;
  var EXCLUIR = "script,style,textarea,input,select,code,pre,[contenteditable],.sgi-proc-sheet,[data-fechas-iso]";

  function convertir(txt) {
    return txt.replace(RE, function (m, pre, y, mo, d, hh, mm) {
      if (+mo < 1 || +mo > 12 || +d < 1 || +d > 31) return m;
      return pre + d + "/" + mo + "/" + y + (hh !== undefined ? " " + hh + ":" + mm : "");
    });
  }
  function tieneFecha(txt) { RE.lastIndex = 0; return RE.test(txt); }
  function excluido(el) { return !el || (el.closest && el.closest(EXCLUIR)); }

  function procesarTexto(nodo) {
    var v = nodo.nodeValue;
    if (!v || v.length < 10 || !tieneFecha(v) || excluido(nodo.parentElement)) return;
    var nuevo = convertir(v);
    if (nuevo !== v) nodo.nodeValue = nuevo;
  }
  function procesarTitle(el) {
    var t = el.getAttribute && el.getAttribute("title");
    if (t && tieneFecha(t) && !excluido(el)) el.setAttribute("title", convertir(t));
  }
  function procesar(raiz) {
    if (!raiz) return;
    if (raiz.nodeType === 3) { procesarTexto(raiz); return; }
    if (raiz.nodeType !== 1 || excluido(raiz)) return;
    procesarTitle(raiz);
    var w = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {
      acceptNode: function (n) {
        if (n.nodeType === 1) return n.matches(EXCLUIR) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var n;
    while ((n = w.nextNode())) {
      if (n.nodeType === 3) procesarTexto(n); else procesarTitle(n);
    }
  }

  function iniciar() {
    procesar(document.body);
    new MutationObserver(function (cambios) {
      cambios.forEach(function (c) {
        if (c.type === "characterData") procesarTexto(c.target);
        else if (c.type === "attributes") procesarTitle(c.target);
        else c.addedNodes.forEach(procesar);
      });
    }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["title"] });
  }
  window.qdvFechaAr = convertir;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
  else iniciar();
})();
