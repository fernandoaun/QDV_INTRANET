/**
 * Editor visual de procedimientos SGC (PG / PO / MSGC).
 */
(function () {
  "use strict";

  const cfg = window.SGI_PROC_CONFIG;
  if (!cfg) return;

  const initial = cfg.payload || {};
  const soloLectura = !!cfg.soloLectura;
  const puedeAsociarModulo = cfg.puedeAsociarModulo !== false;
  const puedeCrearRegistroDigital = !!cfg.puedeCrearRegistroDigital;
  const docId = cfg.docId;

  function qs(sel) {
    return document.querySelector(sel);
  }
  function qsa(sel) {
    return Array.from(document.querySelectorAll(sel));
  }

  const SECCION_NUMERO = {
    objeto: 1,
    alcance: 2,
    definiciones: 3,
    responsabilidades: 4,
    desarrollo: 5,
    referencias: 6,
  };

  function getSectionNum(bodyEl) {
    const sec = bodyEl.closest("[data-seccion]");
    const fromData = parseInt(sec?.dataset.seccionNum || "", 10);
    if (fromData > 0) return fromData;
    return SECCION_NUMERO[bodyEl.dataset.seccionBody] || 0;
  }

  const MAX_SUBAPARTADO_LEVEL = 3;

  /** Parsea "5.2.1." → [2, 1] (sin el número de sección). */
  function parseSubapartadoParts(text, secNum) {
    const cleaned = String(text || "")
      .trim()
      .replace(/\s+/g, "")
      .replace(/\.+$/, "");
    if (!cleaned) return null;
    const nums = cleaned.split(".").map((n) => parseInt(n, 10));
    if (nums.some((n) => !Number.isFinite(n) || n < 1)) return null;
    if (nums[0] !== secNum) return null;
    const parts = nums.slice(1);
    if (!parts.length || parts.length > MAX_SUBAPARTADO_LEVEL) return null;
    return parts;
  }

  function formatSubapartadoLabel(secNum, parts) {
    return `${secNum}.${parts.join(".")}.`;
  }

  function listSubapartados(bodyEl, secNum) {
    return Array.from(bodyEl.querySelectorAll(".sgi-proc-subapartado"))
      .map((el) => {
        const parts = parseSubapartadoParts(
          el.querySelector(".sgi-proc-sub-num")?.textContent,
          secNum
        );
        return parts ? { el, parts } : null;
      })
      .filter(Boolean);
  }

  function isDescendantOf(childParts, ancestorParts) {
    return (
      childParts.length > ancestorParts.length &&
      ancestorParts.every((v, i) => childParts[i] === v)
    );
  }

  function findAnchorSubapartado(bodyEl) {
    const sel = window.getSelection();
    if (!sel?.rangeCount) return null;
    let node = sel.anchorNode;
    if (node?.nodeType === Node.TEXT_NODE) node = node.parentElement;
    const sub = node?.closest?.(".sgi-proc-subapartado");
    if (!sub || !bodyEl.contains(sub)) return null;
    return sub;
  }

  /**
   * Punto de inserción: devolvemos el primer subapartado "no-descendiente"
   * que aparezca después de `rootEl`.
   *
   * Esto permite insertar el nuevo subapartado después del contenido
   * (tablas, texto, imágenes) que esté entre `rootEl` y el próximo subapartado.
   */
  function nextNonDescendantSubapartado(bodyEl, secNum, rootEl) {
    const all = listSubapartados(bodyEl, secNum);
    const rootParts = parseSubapartadoParts(
      rootEl.querySelector(".sgi-proc-sub-num")?.textContent,
      secNum
    );
    if (!rootParts) return null;
    const idx = all.findIndex((x) => x.el === rootEl);
    for (let i = idx + 1; i < all.length; i += 1) {
      if (!isDescendantOf(all[i].parts, rootParts)) return all[i].el;
    }
    return null;
  }

  function buildSubapartadoHtml(label, level) {
    return `<p class="sgi-proc-subapartado" data-sub-level="${level}"><span class="sgi-proc-sub-num">${escapeHtml(label)}</span>&nbsp;</p>`;
  }

  function syncSubapartadoLevels(bodyEl) {
    const secNum = getSectionNum(bodyEl);
    if (!secNum) return;
    bodyEl.querySelectorAll(".sgi-proc-subapartado").forEach((el) => {
      const parts = parseSubapartadoParts(
        el.querySelector(".sgi-proc-sub-num")?.textContent,
        secNum
      );
      if (parts?.length) el.dataset.subLevel = String(parts.length);
      else delete el.dataset.subLevel;
    });
  }

  function placeCursorAtEnd(el) {
    const range = document.createRange();
    range.selectNodeContents(el);
    range.collapse(false);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(range);
  }

  function shiftSiblingNumbering(bodyEl, secNum, parentParts, fromNumber) {
    const level = parentParts.length + 1;
    listSubapartados(bodyEl, secNum).forEach((item) => {
      if (item.parts.length < level) return;
      if (!parentParts.every((v, i) => item.parts[i] === v)) return;
      if (item.parts[level - 1] < fromNumber) return;
      const moved = item.parts.slice();
      moved[level - 1] += 1;
      const numEl = item.el.querySelector(".sgi-proc-sub-num");
      if (numEl) numEl.textContent = formatSubapartadoLabel(secNum, moved);
      item.el.dataset.subLevel = String(moved.length);
    });
  }

  function findSubapartadoByParts(bodyEl, secNum, parts) {
    return (
      listSubapartados(bodyEl, secNum).find(
        (x) =>
          x.parts.length === parts.length &&
          x.parts.every((v, i) => v === parts[i])
      )?.el || null
    );
  }

  function getPreviousSiblingParts(all, anchorParts) {
    const parent = anchorParts.slice(0, -1);
    const sameLevel = all.filter(
      (x) =>
        x.parts.length === anchorParts.length &&
        parent.every((v, i) => x.parts[i] === v)
    );
    const idx = sameLevel.findIndex(
      (x) =>
        x.parts.length === anchorParts.length &&
        x.parts.every((v, i) => v === anchorParts[i])
    );
    if (idx > 0) return sameLevel[idx - 1].parts;
    return null;
  }

  function getAnchorOrLast(bodyEl, secNum) {
    const anchor = findAnchorSubapartado(bodyEl);
    if (anchor) return anchor;
    const all = listSubapartados(bodyEl, secNum);
    return all.length ? all[all.length - 1].el : null;
  }

  function buildNewSubapartado(bodyEl, secNum, anchor, mode) {
    const all = listSubapartados(bodyEl, secNum);
    if (!anchor) {
      const level1 = all.filter((x) => x.parts.length === 1).map((x) => x.parts[0]);
      return { parts: [level1.length ? Math.max(...level1) + 1 : 1], ref: null };
    }

    const anchorParts = parseSubapartadoParts(
      anchor.querySelector(".sgi-proc-sub-num")?.textContent,
      secNum
    );
    if (!anchorParts) {
      const level1 = all.filter((x) => x.parts.length === 1).map((x) => x.parts[0]);
      return { parts: [level1.length ? Math.max(...level1) + 1 : 1], ref: null };
    }

    if (mode === "continuo") {
      const baseParts = getPreviousSiblingParts(all, anchorParts) || anchorParts;
      const baseEl = findSubapartadoByParts(bodyEl, secNum, baseParts) || anchor;
      if (baseParts.length >= MAX_SUBAPARTADO_LEVEL) {
        const parent = baseParts.slice(0, -1);
        const target = baseParts[baseParts.length - 1] + 1;
        shiftSiblingNumbering(bodyEl, secNum, parent, target);
        return {
          parts: [...parent, target],
          ref: nextNonDescendantSubapartado(bodyEl, secNum, baseEl),
        };
      }
      const level = baseParts.length;
      const children = all
        .filter(
          (x) =>
            x.parts.length === level + 1 &&
            baseParts.every((v, i) => x.parts[i] === v)
        )
        .map((x) => x.parts[level]);
      const next = children.length ? Math.max(...children) + 1 : 1;
      return { parts: [...baseParts, next], ref: nextNonDescendantSubapartado(bodyEl, secNum, baseEl) };
    }

    if (mode === "ascender") {
      if (anchorParts.length === 1) {
        const target = anchorParts[0] + 1;
        shiftSiblingNumbering(bodyEl, secNum, [], target);
        return {
          parts: [target],
          ref: nextNonDescendantSubapartado(bodyEl, secNum, anchor),
        };
      }
      const parentParts = anchorParts.slice(0, -1);
      const grandParent = anchorParts.slice(0, -2);
      const target = parentParts[parentParts.length - 1] + 1;
      shiftSiblingNumbering(bodyEl, secNum, grandParent, target);
      const parentEl = findSubapartadoByParts(bodyEl, secNum, parentParts);
      const refRoot = parentEl || anchor;
      return {
        parts: [...grandParent, target],
        ref: nextNonDescendantSubapartado(bodyEl, secNum, refRoot),
      };
    }

    const parent = anchorParts.slice(0, -1);
    const target =
      mode === "anterior"
        ? anchorParts[anchorParts.length - 1]
        : anchorParts[anchorParts.length - 1] + 1;
    shiftSiblingNumbering(bodyEl, secNum, parent, target);
    return {
      parts: [...parent, target],
      ref: mode === "anterior" ? anchor : nextNonDescendantSubapartado(bodyEl, secNum, anchor),
    };
  }

  function insertSubapartado(bodyEl, mode) {
    flushUndoDebounce();
    const secNum = getSectionNum(bodyEl);
    const anchor = getAnchorOrLast(bodyEl, secNum);

    const built = buildNewSubapartado(bodyEl, secNum, anchor, mode);
    const parts = built.parts;
    const label = formatSubapartadoLabel(secNum, parts);
    const ref = built.ref;

    const wrap = document.createElement("div");
    wrap.innerHTML = buildSubapartadoHtml(label, parts.length);
    const node = wrap.firstElementChild;
    if (!node) return;

    if (ref) {
      ref.before(node);
    } else {
      bodyEl.appendChild(node);
    }

    bodyEl.focus();
    placeCursorAtEnd(node);
    pushUndoState();
    scheduleAutoSaveHint();
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /** Normaliza HTML pegado o guardado: fuentes, floats y tablas/imágenes embebidas. */
  function normalizeProcedureHtml(html) {
    const raw = String(html || "").trim();
    if (!raw) return "";

    const doc = new DOMParser().parseFromString(`<div id="sgi-proc-root">${raw}</div>`, "text/html");
    const root = doc.getElementById("sgi-proc-root");
    if (!root) return raw;

    const layoutProps = [
      "font-family",
      "font",
      "float",
      "position",
      "left",
      "right",
      "top",
      "bottom",
      "z-index",
      "margin",
      "margin-top",
      "margin-bottom",
      "margin-left",
      "margin-right",
      "padding-top",
      "padding-bottom",
      "line-height",
      "height",
      "min-height",
      "max-height",
      "transform",
      "vertical-align",
    ];

    root.querySelectorAll("[style]").forEach((el) => {
      const tag = el.tagName;
      layoutProps.forEach((prop) => el.style.removeProperty(prop));
      // display/width heredados de Word suelen romper listas y párrafos en el editor.
      if (!el.closest("table") && ["P", "DIV", "LI", "UL", "OL", "SPAN"].includes(tag)) {
        el.style.removeProperty("display");
        el.style.removeProperty("width");
      }
      if (!el.getAttribute("style")?.trim()) el.removeAttribute("style");
    });
    root.querySelectorAll("font[face]").forEach((el) => el.removeAttribute("face"));
    root.querySelectorAll("span").forEach((el) => {
      const st = el.getAttribute("style") || "";
      if (/font-weight\s*:\s*(bold|700)/i.test(st) && !el.querySelector("*")) {
        const strong = doc.createElement("strong");
        strong.innerHTML = el.innerHTML;
        el.replaceWith(strong);
      }
    });

    function isEffectivelyEmpty(node) {
      if (!node) return true;
      if (node.nodeType === Node.TEXT_NODE) return !String(node.textContent || "").trim();
      if (node.nodeType !== Node.ELEMENT_NODE) return true;
      const html = (node.innerHTML || "")
        .replace(/&nbsp;/gi, " ")
        .replace(/<br\s*\/?>/gi, "")
        .trim();
      const txt = String(node.textContent || "").replace(/\u00a0/g, " ").trim();
      return !html && !txt;
    }

    function hasUsefulContent(node) {
      if (!node) return false;
      if (node.nodeType === Node.TEXT_NODE) return !!String(node.textContent || "").trim();
      if (node.nodeType !== Node.ELEMENT_NODE) return false;
      if (node.matches("img,table")) return true;
      if (node.querySelector("img,table")) return true;
      return !!String(node.textContent || "").replace(/\u00a0/g, " ").trim();
    }

    // Limpia viñetas vacías y fusiona listas consecutivas del mismo tipo.
    // No convierte párrafos intermedios en ítems: eso generaba solapamiento visual.
    root.querySelectorAll("ul,ol").forEach((list) => {
      list.querySelectorAll("li").forEach((li) => {
        if (!hasUsefulContent(li)) li.remove();
      });
      if (!list.querySelector("li")) list.remove();
    });

    root.querySelectorAll("*").forEach((parent) => {
      let node = parent.firstChild;
      while (node) {
        if (
          node.nodeType === Node.ELEMENT_NODE &&
          (node.tagName === "UL" || node.tagName === "OL")
        ) {
          const baseList = node;
          let cursor = baseList.nextSibling;
          while (cursor && isEffectivelyEmpty(cursor)) {
            const next = cursor.nextSibling;
            cursor.remove();
            cursor = next;
          }
          if (
            cursor &&
            cursor.nodeType === Node.ELEMENT_NODE &&
            cursor.tagName === baseList.tagName
          ) {
            Array.from(cursor.children)
              .filter((el) => el.tagName === "LI")
              .forEach((li) => {
                if (hasUsefulContent(li)) baseList.appendChild(li);
                else li.remove();
              });
            const next = cursor.nextSibling;
            cursor.remove();
            cursor = next;
          }
          node = cursor || baseList.nextSibling;
          continue;
        }
        node = node.nextSibling;
      }
    });

    root.querySelectorAll("table").forEach((el) => {
      el.classList.add("sgi-proc-content-table");
      el.removeAttribute("width");
      el.removeAttribute("height");
      el.removeAttribute("align");
      el.style.width = "100%";
      el.style.float = "none";
      el.style.tableLayout = "fixed";
    });
    root.querySelectorAll("img").forEach((el) => {
      el.classList.add("sgi-proc-content-img");
      el.removeAttribute("width");
      el.removeAttribute("height");
      el.removeAttribute("align");
      el.style.maxWidth = "100%";
      el.style.height = "auto";
      el.style.float = "none";
    });

    return root.innerHTML.trim();
  }

  function buildContentTable(cols, rows) {
    const c = Math.max(1, cols);
    const r = Math.max(1, rows);
    const pct = Math.round(100 / c);
    let html = '<table class="sgi-proc-content-table"><colgroup>';
    for (let col = 0; col < c; col += 1) {
      html += `<col style="width:${pct}%">`;
    }
    html += "</colgroup><tbody>";
    for (let row = 0; row < r; row += 1) {
      html += "<tr>";
      for (let col = 0; col < c; col += 1) {
        html += row === 0 ? "<th>&nbsp;</th>" : "<td>&nbsp;</td>";
      }
      html += "</tr>";
    }
    html += "</tbody></table>";
    return html;
  }

  function insertContentIntoSection(bodyEl, html) {
    flushUndoDebounce();
    bodyEl.focus();
    const sel = window.getSelection();
    if (sel?.rangeCount && bodyEl.contains(sel.anchorNode)) {
      insertHtmlAtCursor(html);
    } else {
      bodyEl.insertAdjacentHTML("beforeend", html);
    }
    bodyEl.innerHTML = normalizeProcedureHtml(bodyEl.innerHTML);
    setupAllContentTables(bodyEl);
    pushUndoState();
    scheduleAutoSaveHint();
  }

  function insertContentTable(bodyEl) {
    const cols = parseInt(window.prompt("Cantidad de columnas", "4") || "4", 10);
    const rows = parseInt(window.prompt("Cantidad de filas (incluye encabezado)", "4") || "4", 10);
    if (!Number.isFinite(cols) || !Number.isFinite(rows) || cols < 1 || rows < 1) return;
    insertContentIntoSection(bodyEl, buildContentTable(cols, rows));
  }

  let imageTargetBody = null;

  function insertContentImage(bodyEl) {
    imageTargetBody = bodyEl;
    const input = qs("#procImageInput");
    if (!input) return;
    input.value = "";
    input.click();
  }

  function handleImageSelected(e) {
    const file = e.target.files?.[0];
    const bodyEl = imageTargetBody;
    imageTargetBody = null;
    if (!file || !bodyEl) return;
    if (!file.type.startsWith("image/")) {
      flashMsg("danger", "Seleccioná un archivo de imagen.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const src = reader.result;
      insertContentIntoSection(
        bodyEl,
        `<img class="sgi-proc-content-img" src="${src}" alt="Imagen">`
      );
    };
    reader.readAsDataURL(file);
  }

  function insertHtmlAtCursor(html) {
    const sel = window.getSelection();
    if (!sel?.rangeCount) return;
    const range = sel.getRangeAt(0);
    range.deleteContents();
    const frag = range.createContextualFragment(html);
    range.insertNode(frag);
    range.collapse(false);
    sel.removeAllRanges();
    sel.addRange(range);
  }

  function handleSectionPaste(e) {
    const items = e.clipboardData?.items;
    if (items) {
      for (const item of items) {
        if (item.type?.startsWith("image/")) {
          e.preventDefault();
          const blob = item.getAsFile();
          if (!blob) return;
          const reader = new FileReader();
          reader.onload = () => {
            flushUndoDebounce();
            insertHtmlAtCursor(
              `<img class="sgi-proc-content-img" src="${reader.result}" alt="Imagen">`
            );
            pushUndoState();
            scheduleAutoSaveHint();
          };
          reader.readAsDataURL(blob);
          return;
        }
      }
    }

    e.preventDefault();
    flushUndoDebounce();
    const html = e.clipboardData?.getData("text/html") || "";
    const text = e.clipboardData?.getData("text/plain") || "";
    if (html) {
      insertHtmlAtCursor(normalizeProcedureHtml(html));
    } else if (text) {
      insertHtmlAtCursor(escapeHtml(text).replace(/\n/g, "<br>"));
    }
    pushUndoState();
    scheduleAutoSaveHint();
  }

  const MAX_UNDO = 40;
  let undoStack = [];
  let undoIndex = -1;
  let undoApplying = false;
  let undoDebounce = null;

  function captureUndoState() {
    const secciones = {};
    qsa("[data-seccion-body]").forEach((el) => {
      secciones[el.dataset.seccionBody] = el.innerHTML;
    });
    return { secciones, titulo: (qs("#procTituloInput")?.value || "").trim() };
  }

  function undoStatesEqual(a, b) {
    if (!a || !b) return false;
    if (a.titulo !== b.titulo) return false;
    const keys = new Set([
      ...Object.keys(a.secciones || {}),
      ...Object.keys(b.secciones || {}),
    ]);
    for (const k of keys) {
      if ((a.secciones[k] || "") !== (b.secciones[k] || "")) return false;
    }
    return true;
  }

  function syncTituloFromUndo(titulo) {
    const el = qs("#procTituloDisplay");
    if (el) {
      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") el.value = titulo;
      else el.textContent = titulo;
    }
    if (qs("#procHeaderTitulo")) qs("#procHeaderTitulo").textContent = titulo;
  }

  function applyUndoState(state) {
    undoApplying = true;
    qsa("[data-seccion-body]").forEach((el) => {
      const k = el.dataset.seccionBody;
      el.innerHTML = normalizeProcedureHtml(state.secciones[k] || "");
      syncSubapartadoLevels(el);
      if (!soloLectura) setupAllContentTables(el);
    });
    const tituloInput = qs("#procTituloInput");
    if (tituloInput && state.titulo !== undefined) {
      tituloInput.value = state.titulo;
      syncTituloFromUndo(state.titulo);
    }
    undoApplying = false;
    scheduleAutoSaveHint();
  }

  function pushUndoState() {
    if (soloLectura || undoApplying) return;
    const state = captureUndoState();
    const current = undoStack[undoIndex];
    if (current && undoStatesEqual(current, state)) return;

    undoStack = undoStack.slice(0, undoIndex + 1);
    undoStack.push(state);
    undoIndex = undoStack.length - 1;
    if (undoStack.length > MAX_UNDO) {
      undoStack.shift();
      undoIndex = undoStack.length - 1;
    }
  }

  function flushUndoDebounce() {
    clearTimeout(undoDebounce);
    undoDebounce = null;
    pushUndoState();
  }

  function scheduleUndoSnapshot() {
    if (soloLectura || undoApplying) return;
    clearTimeout(undoDebounce);
    undoDebounce = setTimeout(() => {
      undoDebounce = null;
      pushUndoState();
    }, 400);
  }

  function undoEdit() {
    if (undoIndex <= 0) return false;
    undoIndex -= 1;
    applyUndoState(undoStack[undoIndex]);
    return true;
  }

  function redoEdit() {
    if (undoIndex >= undoStack.length - 1) return false;
    undoIndex += 1;
    applyUndoState(undoStack[undoIndex]);
    return true;
  }

  function initUndoStack() {
    undoStack = [];
    undoIndex = -1;
    pushUndoState();
  }

  function isUndoTarget(el) {
    if (!el) return false;
    if (el.id === "procTituloInput") return true;
    return !!el.closest?.("[data-seccion-body]");
  }

  function bindUndoShortcuts() {
    document.addEventListener("keydown", (e) => {
      if (soloLectura) return;
      if (!(e.ctrlKey || e.metaKey)) return;
      const key = e.key.toLowerCase();
      if (key !== "z" && key !== "y") return;
      if (!isUndoTarget(e.target)) return;

      const redo = key === "y" || (key === "z" && e.shiftKey);
      if (!redo && key !== "z") return;

      e.preventDefault();
      flushUndoDebounce();
      if (redo) redoEdit();
      else undoEdit();
    });
  }

  function collectPayload() {
    const secciones = {};
    qsa("[data-seccion-body]").forEach((el) => {
      syncSubapartadoLevels(el);
      secciones[el.dataset.seccionBody] = normalizeProcedureHtml(el.innerHTML);
    });
    const registros = [];
    qsa("#procRegistrosBody tr").forEach((tr) => {
      const rid = tr.dataset.registroId ? parseInt(tr.dataset.registroId, 10) : null;
      registros.push({
        id: Number.isFinite(rid) ? rid : null,
        nombre: tr.querySelector(".rg-nombre")?.value || "",
        quien_archiva: tr.querySelector(".rg-quien")?.value || "",
        como: tr.querySelector(".rg-como")?.value || "",
        donde: tr.querySelector(".rg-donde")?.value || "",
        tiempo_guarda: tr.querySelector(".rg-tiempo")?.value || "",
        usuarios: tr.querySelector(".rg-usuarios")?.value || "",
        disposicion_final: tr.querySelector(".rg-disp")?.value || "",
        modulo: tr.dataset.hasDigital === "1" ? "" : tr.querySelector(".rg-modulo")?.value || "",
        record_definition_id: tr.dataset.recordDefinitionId
          ? parseInt(tr.dataset.recordDefinitionId, 10)
          : null,
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
      revisor_correo: qs("#procRevisorCorreo")?.value || "",
      aprobo: qs("#procAprobo")?.value || "",
      aprobador_correo: qs("#procAprobadorCorreo")?.value || "",
      fecha_elaboracion: qs("#procFechaElab")?.value || "",
      fecha_revision: qs("#procFechaRev")?.value || "",
      fecha_aprobacion: qs("#procFechaAprob")?.value || "",
      perfiles_aplica: qsa(".proc-perfil-check:checked").map((el) => el.value),
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
    if (row?.id) tr.dataset.registroId = String(row.id);
    if (row?.record_definition_id) {
      tr.dataset.recordDefinitionId = String(row.record_definition_id);
      tr.dataset.hasDigital = "1";
    } else {
      tr.dataset.hasDigital = "0";
    }
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

    const hasDigital = !!row?.has_digital_record || !!row?.record_definition_id;
    const modulos = cfg.modulosRegistro || {};
    const selectedModulo = (row?.modulo || "").trim();

    if (hasDigital) {
      const summary = row.record_summary || {};
      const recordUrl = row.record_url || summary.record_url || "";
      const origin = summary.origin_label || "Formulario editable";
      html += `<td colspan="1"><span class="badge text-bg-primary">${escapeHtml(summary.code || "REG")}</span>
        <div class="small text-muted">${escapeHtml(origin)} · v${escapeHtml(summary.version || 1)}</div></td>`;
      html += `<td class="sgi-proc-no-print text-nowrap">
        ${recordUrl ? `<a class="btn btn-sm btn-primary" href="${escapeHtml(recordUrl)}">Ir al registro</a>` : ""}
        ${
          puedeCrearRegistroDigital && !soloLectura
            ? `<button type="button" class="btn btn-sm btn-outline-warning rg-btn-unlink-digital">Desvincular</button>`
            : ""
        }
      </td>`;
    } else {
      let optionsHtml = `<option value="">— Sin módulo —</option>`;
      Object.keys(modulos).forEach((key) => {
        const label = (modulos[key] && modulos[key].label) || key;
        const sel = key === selectedModulo ? " selected" : "";
        optionsHtml += `<option value="${escapeHtml(key)}"${sel}>${escapeHtml(label)}</option>`;
      });
      if (selectedModulo && !modulos[selectedModulo]) {
        optionsHtml += `<option value="${escapeHtml(selectedModulo)}" selected>${escapeHtml(selectedModulo)}</option>`;
      }
      html += `<td><select class="form-select form-select-sm rg-modulo" ${soloLectura || !puedeAsociarModulo ? "disabled" : ""}>${optionsHtml}</select>
        ${
          !selectedModulo && puedeCrearRegistroDigital && !soloLectura && row?.id
            ? `<button type="button" class="btn btn-sm btn-success mt-1 rg-btn-crear-registro">Crear registro</button>`
            : ""
        }
      </td>`;

      const meta = modulos[selectedModulo] || {};
      const blankUrl = meta.blank_url || row?.blank_url || "";
      const filledUrl = meta.filled_url || row?.filled_url || "";
      const blankDisabled = blankUrl ? "" : ' disabled aria-disabled="true"';
      const filledDisabled = filledUrl ? "" : ' disabled aria-disabled="true"';
      html += `<td class="sgi-proc-no-print text-nowrap">
        <a class="btn btn-sm btn-outline-secondary rg-btn-blank"${blankUrl ? ` href="${escapeHtml(blankUrl)}" target="_blank" rel="noopener"` : ""}${blankDisabled}>Ver en blanco</a>
        <a class="btn btn-sm btn-outline-primary rg-btn-filled"${filledUrl ? ` href="${escapeHtml(filledUrl)}" target="_blank" rel="noopener"` : ""}${filledDisabled}>Ir al módulo</a>
      </td>`;
    }

    if (!soloLectura) {
      html +=
        '<td class="sgi-proc-no-print text-center"><button type="button" class="btn btn-sm btn-link text-danger btn-del-reg">×</button></td>';
    }
    tr.innerHTML = html;
    tbody.appendChild(tr);
    tr.querySelector(".btn-del-reg")?.addEventListener("click", () => tr.remove());
    tr.querySelector(".rg-modulo")?.addEventListener("change", () => syncRegistroModuloLinks(tr));
    tr.querySelector(".rg-btn-crear-registro")?.addEventListener("click", () => {
      if (!window.SgiCreateRecordWizard || !row?.id || !docId) return;
      const slug = cfg.slug;
      window.SgiCreateRecordWizard({
        csrf: cfg.csrf,
        defaultName: tr.querySelector(".rg-nombre")?.value || "",
        analyzeUrl: `/sgi/${slug}/procedimientos/${docId}/registro/${row.id}/import/analyze`,
        createUrl: `/sgi/${slug}/procedimientos/${docId}/registro/${row.id}/import/create`,
        onCreated: (registro) => {
          // Reemplazar fila con datos nuevos
          tr.remove();
          addRegistroRow(registro || row);
        },
      });
    });
    tr.querySelector(".rg-btn-unlink-digital")?.addEventListener("click", () => {
      if (!row?.id || !docId) return;
      if (!confirm("¿Desvincular el registro digital?")) return;
      const slug = cfg.slug;
      fetch(`/sgi/${slug}/procedimientos/${docId}/registro/${row.id}/unlink-digital`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": cfg.csrf || "",
        },
        credentials: "same-origin",
        body: "{}",
      })
        .then((r) => r.json())
        .then((res) => {
          if (!res.ok) {
            alert(res.message || "No se pudo desvincular.");
            return;
          }
          tr.remove();
          addRegistroRow(res.registro || { ...row, has_digital_record: false, record_definition_id: null, record_url: "" });
        })
        .catch(() => alert("No se pudo desvincular."));
    });
  }

  function syncRegistroModuloLinks(tr) {
    const key = (tr.querySelector(".rg-modulo")?.value || "").trim();
    const meta = (cfg.modulosRegistro || {})[key] || {};
    const blank = tr.querySelector(".rg-btn-blank");
    const filled = tr.querySelector(".rg-btn-filled");
    function apply(el, url) {
      if (!el) return;
      if (url) {
        el.href = url;
        el.removeAttribute("aria-disabled");
        el.classList.remove("disabled");
        el.removeAttribute("disabled");
        el.setAttribute("target", "_blank");
        el.setAttribute("rel", "noopener");
      } else {
        el.removeAttribute("href");
        el.setAttribute("aria-disabled", "true");
        el.classList.add("disabled");
        el.setAttribute("disabled", "disabled");
      }
    }
    apply(blank, meta.blank_url || "");
    apply(filled, meta.filled_url || "");
  }

  let activeSectionBody = null;
  let tableResizeState = null;
  let savedSelectionRange = null;
  let savedSelectionBody = null;

  function getBodyFromSelection() {
    const sel = window.getSelection();
    if (!sel?.rangeCount) return null;
    let node = sel.anchorNode;
    if (node?.nodeType === Node.TEXT_NODE) node = node.parentElement;
    return node?.closest?.("[data-seccion-body]") || null;
  }

  function saveSelectionFromDocument() {
    const sel = window.getSelection();
    if (!sel?.rangeCount) return;
    const range = sel.getRangeAt(0);
    const body = getBodyFromSelection();
    if (!body || !body.contains(range.commonAncestorContainer)) return;
    savedSelectionRange = range.cloneRange();
    savedSelectionBody = body;
    activeSectionBody = body;
  }

  function restoreSelectionForFormat() {
    if (!savedSelectionRange || !savedSelectionBody) return false;
    if (!document.contains(savedSelectionBody)) {
      savedSelectionRange = null;
      savedSelectionBody = null;
      return false;
    }
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(savedSelectionRange);
    return true;
  }

  function bindFormatToolbarAction(element, handler) {
    if (!element) return;
    element.addEventListener("mousedown", (e) => {
      e.preventDefault();
      saveSelectionFromDocument();
    });
    element.addEventListener("click", (e) => {
      e.preventDefault();
      handler();
    });
  }

  function getActiveSectionBody() {
    if (activeSectionBody && document.contains(activeSectionBody)) return activeSectionBody;
    const fromSel = getBodyFromSelection();
    if (fromSel) return fromSel;
    if (savedSelectionBody && document.contains(savedSelectionBody)) return savedSelectionBody;
    return null;
  }

  function getSectionDisplayName(bodyEl) {
    const sec = bodyEl?.closest?.("[data-seccion]");
    const titulo = sec?.querySelector(".sgi-proc-seccion-titulo")?.textContent?.trim();
    return titulo || "Sección";
  }

  function getActiveTableContext() {
    const body = getActiveSectionBody();
    if (!body) return null;
    const sel = window.getSelection();
    if (!sel?.rangeCount) return null;
    let node = sel.anchorNode;
    if (node?.nodeType === Node.TEXT_NODE) node = node.parentElement;
    const cell = node?.closest?.("td, th");
    const table = cell?.closest?.("table.sgi-proc-content-table, table");
    if (!table || !body.contains(table)) return null;
    return { body, table, cell, colIndex: cell.cellIndex };
  }

  function getTableColumnCount(table) {
    const row = table.querySelector("tr");
    return row ? row.cells.length : 0;
  }

  function parseColWidthPct(colEl, fallback) {
    const w = colEl?.style?.width || colEl?.getAttribute("width") || "";
    const m = String(w).match(/([\d.]+)\s*%/);
    if (m) return Math.round(parseFloat(m[1]));
    return fallback;
  }

  function ensureTableColgroup(table) {
    const n = getTableColumnCount(table);
    if (!n) return null;
    let cg = table.querySelector("colgroup");
    if (!cg) {
      cg = document.createElement("colgroup");
      table.insertBefore(cg, table.firstChild);
    }
    while (cg.children.length < n) {
      const col = document.createElement("col");
      col.style.width = `${Math.round(100 / n)}%`;
      cg.appendChild(col);
    }
    while (cg.children.length > n) cg.removeChild(cg.lastChild);
    const pct = Math.round(100 / n);
    Array.from(cg.children).forEach((col, i) => {
      if (!col.style.width) col.style.width = `${pct}%`;
      col.dataset.colIndex = String(i);
    });
    return cg;
  }

  function setTableColumnWidthPct(table, colIndex, pct) {
    const cg = ensureTableColgroup(table);
    if (!cg || colIndex < 0 || colIndex >= cg.children.length) return;
    const clamped = Math.max(8, Math.min(85, Math.round(pct)));
    cg.children[colIndex].style.width = `${clamped}%`;
    const lbl = qs("#fmtTableColWidthLbl");
    const range = qs("#fmtTableColWidth");
    if (lbl) lbl.textContent = `${clamped}%`;
    if (range) range.value = String(clamped);
  }

  function equalizeTableColumns(table) {
    const n = getTableColumnCount(table);
    if (!n) return;
    const cg = ensureTableColgroup(table);
    const pct = Math.round(100 / n);
    Array.from(cg.children).forEach((col) => {
      col.style.width = `${pct}%`;
    });
    updateFormatBar();
  }

  function setupTableColResizers(table) {
    if (soloLectura || !table) return;
    table.classList.add("sgi-proc-table-editable");
    ensureTableColgroup(table);
    table.querySelectorAll(".sgi-proc-col-resizer").forEach((el) => el.remove());
    const headerRow = table.querySelector("tr");
    if (!headerRow) return;
    Array.from(headerRow.cells).forEach((cell, idx) => {
      if (idx >= headerRow.cells.length - 1) return;
      const handle = document.createElement("span");
      handle.className = "sgi-proc-col-resizer";
      handle.dataset.colIndex = String(idx);
      handle.title = "Arrastrá para cambiar el ancho de la columna";
      cell.appendChild(handle);
    });
  }

  function setupAllContentTables(root) {
    const scope = root || document;
    scope.querySelectorAll(".sgi-proc-content-table, .sgi-proc-seccion-cuerpo table").forEach((table) => {
      if (!table.querySelector("colgroup")) ensureTableColgroup(table);
      setupTableColResizers(table);
    });
  }

  function unwrapBoldInSelection(body) {
    const sel = window.getSelection();
    if (!sel?.rangeCount) return;
    const range = sel.getRangeAt(0);
    const candidates = [];
    body.querySelectorAll("strong,b,span").forEach((el) => {
      if (el.tagName === "SPAN") {
        const fw = el.style.fontWeight || "";
        if (!/^(bold|[6-9]00)$/i.test(String(fw).trim())) return;
      }
      try {
        if (range.intersectsNode(el)) candidates.push(el);
      } catch {
        /* navegador sin intersectsNode */
      }
    });
    candidates
      .sort((a, b) => {
        if (a.contains(b)) return 1;
        if (b.contains(a)) return -1;
        return 0;
      })
      .forEach((el) => {
        const parent = el.parentNode;
        if (!parent) return;
        while (el.firstChild) parent.insertBefore(el.firstChild, el);
        el.remove();
      });
    saveSelectionFromDocument();
  }

  function execTextFormat(command) {
    const body = getActiveSectionBody();
    if (!body) {
      flashMsg("warning", "Hacé clic en una sección del documento para aplicar formato.");
      return;
    }
    restoreSelectionForFormat();
    body.focus();
    const wasBold = command === "bold" ? document.queryCommandState("bold") : false;
    try {
      document.execCommand(command, false, null);
    } catch {
      /* navegador sin soporte */
    }
    if (command === "bold" && wasBold && document.queryCommandState("bold")) {
      unwrapBoldInSelection(body);
    }
    saveSelectionFromDocument();
    pushUndoState();
    scheduleAutoSaveHint();
    updateFormatBar();
  }

  function getNodeFontSizeInPt(node) {
    if (!node) return null;
    const px = window.getComputedStyle(node).fontSize || "";
    const num = parseFloat(px);
    if (!Number.isFinite(num)) return null;
    return Math.round((num * 72) / 96);
  }

  function applyFontSizeToCellSelection(cell, pt) {
    const size = Math.max(8, Math.min(32, parseInt(pt, 10)));
    if (!Number.isFinite(size) || !cell) return;
    const body = getActiveSectionBody();
    if (!body) return;
    flushUndoDebounce();
    body.focus();
    const sel = window.getSelection();
    const hasSelectionInCell =
      sel &&
      sel.rangeCount &&
      !sel.isCollapsed &&
      cell.contains(sel.anchorNode) &&
      cell.contains(sel.focusNode);

    if (hasSelectionInCell) {
      const range = sel.getRangeAt(0);
      const span = document.createElement("span");
      span.style.fontSize = `${size}pt`;
      try {
        range.surroundContents(span);
      } catch {
        const content = range.extractContents();
        span.appendChild(content);
        range.insertNode(span);
      }
      range.selectNodeContents(span);
      sel.removeAllRanges();
      sel.addRange(range);
    } else {
      // Sin selección: aplicar al contenido de texto de la celda
      // (manteniendo el cambio limitado al texto dentro de la tabla).
      const span = document.createElement("span");
      span.style.fontSize = `${size}pt`;
      span.innerHTML = cell.innerHTML;
      cell.innerHTML = "";
      cell.appendChild(span);
    }
    pushUndoState();
    scheduleAutoSaveHint();
    updateFormatBar();
  }

  function normalizeTextAlign(align) {
    const v = String(align || "").toLowerCase();
    if (v === "start") return "left";
    if (v === "end") return "right";
    if (["left", "center", "right", "justify"].includes(v)) return v;
    return "left";
  }

  function getCellTextAlign(cell) {
    if (!cell) return "left";
    return normalizeTextAlign(window.getComputedStyle(cell).textAlign || cell.style.textAlign || "left");
  }

  function setCellTextAlign(cell, align) {
    if (!cell) return;
    const value = normalizeTextAlign(align);
    flushUndoDebounce();
    cell.style.textAlign = value;
    pushUndoState();
    scheduleAutoSaveHint();
    updateFormatBar();
  }

  function updateFormatBar() {
    if (soloLectura) return;
    const hint = qs("#fmtContextHint");
    const body = getActiveSectionBody();
    if (hint) {
      hint.textContent = body
        ? `Editando: ${getSectionDisplayName(body)}`
        : "Hacé clic en una sección del documento para editar.";
    }

    const fmtBold = qs("#fmtBold");
    const fmtItalic = qs("#fmtItalic");
    const fmtUnderline = qs("#fmtUnderline");
    const fmtBullets = qs("#fmtBullets");
    const fmtNumbered = qs("#fmtNumbered");
    try {
      if (fmtBold) fmtBold.setAttribute("aria-pressed", document.queryCommandState("bold") ? "true" : "false");
      if (fmtItalic) fmtItalic.setAttribute("aria-pressed", document.queryCommandState("italic") ? "true" : "false");
      if (fmtUnderline) {
        fmtUnderline.setAttribute("aria-pressed", document.queryCommandState("underline") ? "true" : "false");
      }
      if (fmtBullets) {
        fmtBullets.setAttribute("aria-pressed", document.queryCommandState("insertUnorderedList") ? "true" : "false");
      }
      if (fmtNumbered) {
        fmtNumbered.setAttribute("aria-pressed", document.queryCommandState("insertOrderedList") ? "true" : "false");
      }
    } catch {
      /* selection fuera del documento */
    }

    const ctx = getActiveTableContext();
    const tools = qs("#fmtTableTools");
    const colSel = qs("#fmtTableCol");
    if (!tools || !colSel) return;
    if (!ctx) {
      tools.hidden = true;
      return;
    }
    tools.hidden = false;
    const n = getTableColumnCount(ctx.table);
    const prev = parseInt(colSel.value || "0", 10);
    colSel.innerHTML = "";
    for (let i = 0; i < n; i += 1) {
      const opt = document.createElement("option");
      opt.value = String(i);
      opt.textContent = String(i + 1);
      colSel.appendChild(opt);
    }
    const colIndex = prev >= 0 && prev < n ? prev : ctx.colIndex;
    colSel.value = String(colIndex);
    const cg = ensureTableColgroup(ctx.table);
    const pct = parseColWidthPct(cg?.children[colIndex], Math.round(100 / n));
    const range = qs("#fmtTableColWidth");
    const lbl = qs("#fmtTableColWidthLbl");
    const tableFontSize = qs("#fmtTableFontSize");
    if (range) range.value = String(pct);
    if (lbl) lbl.textContent = `${pct}%`;
    if (tableFontSize) {
      const size = getNodeFontSizeInPt(ctx.cell) || 10;
      tableFontSize.value = String(size);
    }
    const align = getCellTextAlign(ctx.cell);
    const alignLeft = qs("#fmtTableAlignLeft");
    const alignCenter = qs("#fmtTableAlignCenter");
    const alignRight = qs("#fmtTableAlignRight");
    if (alignLeft) alignLeft.setAttribute("aria-pressed", align === "left" ? "true" : "false");
    if (alignCenter) alignCenter.setAttribute("aria-pressed", align === "center" ? "true" : "false");
    if (alignRight) alignRight.setAttribute("aria-pressed", align === "right" ? "true" : "false");
  }

  function bindTableColumnResize() {
    document.addEventListener("mousedown", (e) => {
      const handle = e.target.closest?.(".sgi-proc-col-resizer");
      if (!handle || soloLectura) return;
      e.preventDefault();
      const table = handle.closest("table");
      const colIndex = parseInt(handle.dataset.colIndex || "0", 10);
      const cg = ensureTableColgroup(table);
      if (!cg) return;
      tableResizeState = {
        table,
        colIndex,
        startX: e.clientX,
        startPct: parseColWidthPct(cg.children[colIndex], 25),
      };
    });

    document.addEventListener("mousemove", (e) => {
      if (!tableResizeState) return;
      const { table, colIndex, startX, startPct } = tableResizeState;
      const width = table.getBoundingClientRect().width || 1;
      const deltaPct = ((e.clientX - startX) / width) * 100;
      setTableColumnWidthPct(table, colIndex, startPct + deltaPct);
    });

    document.addEventListener("mouseup", () => {
      if (!tableResizeState) return;
      tableResizeState = null;
      pushUndoState();
      scheduleAutoSaveHint();
      updateFormatBar();
    });
  }

  function bindFormatBar() {
    bindFormatToolbarAction(qs("#fmtBold"), () => execTextFormat("bold"));
    bindFormatToolbarAction(qs("#fmtItalic"), () => execTextFormat("italic"));
    bindFormatToolbarAction(qs("#fmtUnderline"), () => execTextFormat("underline"));
    bindFormatToolbarAction(qs("#fmtBullets"), () => execTextFormat("insertUnorderedList"));
    bindFormatToolbarAction(qs("#fmtNumbered"), () => execTextFormat("insertOrderedList"));

    function runSubapartadoInsert(mode) {
      const body = getActiveSectionBody();
      if (!body) {
        flashMsg("warning", "Hacé clic en la sección donde querés el subapartado.");
        return;
      }
      insertSubapartado(body, mode);
      updateFormatBar();
    }

    qs("#fmtSubapartadoNext")?.addEventListener("click", () => runSubapartadoInsert("siguiente"));
    qs("#fmtSubapartadoChild")?.addEventListener("click", () => runSubapartadoInsert("continuo"));
    qs("#fmtSubapartadoUp")?.addEventListener("click", () => runSubapartadoInsert("ascender"));

    qs("#fmtTable")?.addEventListener("click", () => {
      const body = getActiveSectionBody();
      if (!body) {
        flashMsg("warning", "Hacé clic en la sección donde querés la tabla.");
        return;
      }
      insertContentTable(body);
      updateFormatBar();
    });

    qs("#fmtImage")?.addEventListener("click", () => {
      const body = getActiveSectionBody();
      if (!body) {
        flashMsg("warning", "Hacé clic en la sección donde querés la imagen.");
        return;
      }
      insertContentImage(body);
    });

    qs("#fmtTableCol")?.addEventListener("change", (e) => {
      const ctx = getActiveTableContext();
      if (!ctx) return;
      const idx = parseInt(e.target.value, 10);
      const cg = ensureTableColgroup(ctx.table);
      const pct = parseColWidthPct(cg?.children[idx], 25);
      const range = qs("#fmtTableColWidth");
      if (range) range.value = String(pct);
      updateFormatBar();
    });

    qs("#fmtTableColWidth")?.addEventListener("input", (e) => {
      const ctx = getActiveTableContext();
      if (!ctx) return;
      const colSel = qs("#fmtTableCol");
      const idx = parseInt(colSel?.value || String(ctx.colIndex), 10);
      setTableColumnWidthPct(ctx.table, idx, parseInt(e.target.value, 10));
      scheduleUndoSnapshot();
      scheduleAutoSaveHint();
    });

    qs("#fmtTableColsEqual")?.addEventListener("click", () => {
      const ctx = getActiveTableContext();
      if (!ctx) return;
      equalizeTableColumns(ctx.table);
      pushUndoState();
      scheduleAutoSaveHint();
    });

    qs("#fmtTableAlignLeft")?.addEventListener("click", () => {
      const ctx = getActiveTableContext();
      if (!ctx) return;
      setCellTextAlign(ctx.cell, "left");
    });
    qs("#fmtTableAlignCenter")?.addEventListener("click", () => {
      const ctx = getActiveTableContext();
      if (!ctx) return;
      setCellTextAlign(ctx.cell, "center");
    });
    qs("#fmtTableAlignRight")?.addEventListener("click", () => {
      const ctx = getActiveTableContext();
      if (!ctx) return;
      setCellTextAlign(ctx.cell, "right");
    });

    qs("#fmtTableFontSize")?.addEventListener("change", (e) => {
      const ctx = getActiveTableContext();
      if (!ctx) return;
      applyFontSizeToCellSelection(ctx.cell, e.target.value);
    });

    document.addEventListener("focusin", (e) => {
      const body = e.target.closest?.("[data-seccion-body]");
      if (!body) return;
      activeSectionBody = body;
      qsa("[data-seccion-body]").forEach((el) => {
        el.classList.toggle("sgi-proc-section-active", el === body);
      });
      updateFormatBar();
    });

    let selectionSaveTimer = null;
    document.addEventListener("selectionchange", () => {
      if (soloLectura) return;
      clearTimeout(selectionSaveTimer);
      selectionSaveTimer = setTimeout(() => {
        selectionSaveTimer = null;
        saveSelectionFromDocument();
        updateFormatBar();
      }, 50);
    });

    document.addEventListener("keydown", (e) => {
      if (soloLectura) return;
      if (!(e.ctrlKey || e.metaKey)) return;
      const key = e.key.toLowerCase();
      if (!["b", "i", "u", "8", "7"].includes(key)) return;
      if (!e.target.closest?.("[data-seccion-body]")) return;
      if (["8", "7"].includes(key) && !e.shiftKey) return;
      e.preventDefault();
      saveSelectionFromDocument();
      if (key === "b") execTextFormat("bold");
      else if (key === "i") execTextFormat("italic");
      else if (key === "u") execTextFormat("underline");
      else if (key === "8") execTextFormat("insertUnorderedList");
      else execTextFormat("insertOrderedList");
    });

    bindTableColumnResize();
    updateFormatBar();
  }

  function anexoCodigoAuto(idx) {
    if ((cfg.tipo || "").toUpperCase() === "MSGC") {
      const romans = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];
      const n = idx + 1;
      if (n >= 1 && n <= romans.length) return `QDV-ANEXO ${romans[n - 1]}`;
      return `QDV-ANEXO ${n}`;
    }
    return `${cfg.codigo}-A${String(idx + 1).padStart(2, "0")}`;
  }

  function addAnexoCard(ax, idx) {
    const container = qs("#procAnexosContainer");
    if (!container) return;
    const card = document.createElement("div");
    card.className = "sgi-proc-anexo-card";
    if (ax?.id) card.dataset.anexoId = String(ax.id);
    const codigoAuto = ax?.codigo || anexoCodigoAuto(idx);
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
        <div class="col-md-8 ax-archivo-wrap">
          <label class="form-label small fw-bold">Archivo del anexo</label>
          <div class="ax-archivo-status small mb-1">${ax?.tiene_archivo ? '<span class="badge text-bg-success">Archivo adjunto</span>' : '<span class="text-muted">Sin archivo</span>'}${ax?.archivo_nombre ? ` <span class="text-muted">${ax.archivo_nombre.replace(/</g, "&lt;")}</span>` : ""}</div>
          ${soloLectura || !ax?.id ? "" : `<input type="file" class="form-control form-control-sm ax-archivo-input" accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.doc,.docx,.ppt,.pptx">`}
          ${!soloLectura && !ax?.id ? '<div class="form-text">Guardá el borrador para poder adjuntar un archivo.</div>' : ""}
        </div>
      </div>
      ${soloLectura ? "" : '<button type="button" class="btn btn-sm btn-link text-danger float-end btn-del-anexo">Quitar anexo</button>'}
    `;
    container.appendChild(card);
    card.querySelector(".btn-del-anexo")?.addEventListener("click", () => card.remove());
    card.querySelector(".ax-archivo-input")?.addEventListener("change", (ev) => {
      const input = ev.target;
      const file = input.files && input.files[0];
      if (!file || !card.dataset.anexoId) return;
      uploadAnexoArchivo(parseInt(card.dataset.anexoId, 10), file, card);
      input.value = "";
    });
  }

  function uploadAnexoArchivo(anexoId, file, card) {
    const fd = new FormData();
    fd.append("archivo", file);
    fd.append("csrf_token", cfg.csrf);
    const status = card.querySelector(".ax-archivo-status");
    if (status) status.innerHTML = '<span class="text-muted">Subiendo…</span>';
    fetch(`/sgi/${cfg.slug}/procedimientos/anexo/${anexoId}/archivo`, {
      method: "POST",
      body: fd,
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin",
    })
      .then((r) => r.json())
      .then((res) => {
        if (!status) return;
        if (res.ok) {
          const name = (res.archivo_nombre || file.name || "").replace(/</g, "&lt;");
          status.innerHTML = `<span class="badge text-bg-success">Archivo adjunto</span> <span class="text-muted">${name}</span>`;
          flashMsg("success", res.message || "Archivo guardado.");
        } else {
          status.innerHTML = '<span class="text-danger">Error al subir</span>';
          flashMsg("danger", res.message || "No se pudo subir el archivo.");
        }
      })
      .catch(() => {
        if (status) status.innerHTML = '<span class="text-danger">Error al subir</span>';
        flashMsg("danger", "No se pudo subir el archivo.");
      });
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
      el.innerHTML = normalizeProcedureHtml(secs[k] || "");
      syncSubapartadoLevels(el);
      if (!soloLectura) setupAllContentTables(el);
    });

    renderControlCambios(initial.control_cambios || []);

    (initial.registros || []).forEach((r) => addRegistroRow(r));
    (initial.anexos || []).forEach((a, i) => addAnexoCard(a, i));

    qsa("[data-seccion-body]").forEach((el) => {
      if (!soloLectura) {
        el.addEventListener("input", () => {
          scheduleUndoSnapshot();
          scheduleAutoSaveHint();
        });
        el.addEventListener("blur", () => {
          el.innerHTML = normalizeProcedureHtml(el.innerHTML);
          syncSubapartadoLevels(el);
          if (!soloLectura) setupAllContentTables(el);
          flushUndoDebounce();
          scheduleAutoSaveHint();
        });
        el.addEventListener("paste", handleSectionPaste);
      }
    });

    if (!soloLectura) initUndoStack();

    qs("#procImageInput")?.addEventListener("change", handleImageSelected);
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
    if (
      cfg.soloLectura &&
      accion !== "marcar_revisado" &&
      accion !== "aprobar" &&
      accion !== "reenviar_aviso"
    ) {
      flashMsg("danger", "No tenés permiso para esta acción.");
      return;
    }
    if (accion === "enviar_revision") {
      const perfiles = qsa(".proc-perfil-check:checked");
      if (!perfiles.length) {
        flashMsg("danger", "Seleccioná al menos un sector/perfil al que aplica el procedimiento.");
        return;
      }
      const revisorCorreo = (qs("#procRevisorCorreo")?.value || "").trim();
      const revisoTexto = (qs("#procReviso")?.value || "").trim();
      const tieneEmail = /[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}/.test(`${revisorCorreo} ${revisoTexto}`);
      if (!tieneEmail) {
        flashMsg(
          "danger",
          "Completá el campo «Correo del revisor» en la carátula para enviar el aviso automático."
        );
        return;
      }
    }
    if (accion === "marcar_revisado") {
      const aprobadorCorreo = (qs("#procAprobadorCorreo")?.value || "").trim();
      const aproboTexto = (qs("#procAprobo")?.value || "").trim();
      const tieneEmail = /[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}/.test(`${aprobadorCorreo} ${aproboTexto}`);
      if (!tieneEmail) {
        flashMsg(
          "danger",
          "Completá el campo «Correo del aprobador» en la carátula para enviar el aviso automático."
        );
        return;
      }
    }
    if (accion === "reenviar_aviso") {
      const esRevision = (cfg.revEstado || "") === "en_revision";
      const correo = (qs(esRevision ? "#procRevisorCorreo" : "#procAprobadorCorreo")?.value || "").trim();
      const texto = (qs(esRevision ? "#procReviso" : "#procAprobo")?.value || "").trim();
      const tieneEmail = /[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}/.test(`${correo} ${texto}`);
      if (!tieneEmail) {
        flashMsg(
          "danger",
          esRevision
            ? "Completá «Correo del revisor» en la carátula antes de reenviar."
            : "Completá «Correo del aprobador» en la carátula antes de reenviar."
        );
        return;
      }
    }
    if (!cfg.soloLectura) {
      await guardarBorrador();
    } else if (accion === "marcar_revisado") {
      const data = collectPayload();
      const res = await postJson(cfg.urls.guardar, data);
      if (!res.ok) {
        // El endpoint workflow también persiste la carátula; no bloquear si falló el guardado previo.
        console.warn("Guardado previo de carátula:", res.message || res.error);
      }
    }
    const token = qs('meta[name="csrf-token"]')?.content || cfg.csrf || "";
    const body = { accion };
    if (accion === "reenviar_aviso" || accion === "marcar_revisado") {
      body.revisor_correo = qs("#procRevisorCorreo")?.value || "";
      body.aprobador_correo = qs("#procAprobadorCorreo")?.value || "";
    }
    if (accion === "marcar_revisado") {
      body.aprobo = qs("#procAprobo")?.value || "";
    }
    const res = await fetch(cfg.urls.workflow, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": token },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.ok) {
      const kind = accion === "reenviar_aviso" && data.message && !/notificó/i.test(data.message) ? "warning" : "success";
      flashMsg(kind, data.message);
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
      scheduleUndoSnapshot();
      scheduleAutoSaveHint();
    });
    bindUndoShortcuts();
    bindFormatBar();
    qs("#btnGuardarBorrador")?.addEventListener("click", guardarBorrador);
    qs("#btnEnviarRevision")?.addEventListener("click", () => workflow("enviar_revision"));
    qs("#btnMarcarRevisado")?.addEventListener("click", () => workflow("marcar_revisado"));
    qs("#btnReenviarAviso")?.addEventListener("click", () => workflow("reenviar_aviso"));
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
    qs("#procFirmaGerenteInput")?.addEventListener("change", uploadFirmaGerente);
  }

  async function uploadFirmaGerente(ev) {
    const input = ev.target;
    const file = input.files?.[0];
    if (!file || !cfg.urls?.firmaGerente) return;
    const fd = new FormData();
    fd.append("firma", file);
    fd.append("csrf_token", cfg.csrf || "");
    try {
      const res = await fetch(cfg.urls.firmaGerente, {
        method: "POST",
        body: fd,
        credentials: "same-origin",
      });
      if (res.ok && res.redirected) {
        window.location.reload();
        return;
      }
      flashMsg(res.ok ? "success" : "danger", res.ok ? "Firma guardada." : "No se pudo guardar la firma.");
    } catch {
      flashMsg("Error al subir la firma.", "danger");
    }
    input.value = "";
  }

  document.addEventListener("DOMContentLoaded", () => {
    hydrate();
    bind();
  });
})();
