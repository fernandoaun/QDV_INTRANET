/**
 * Editor visual de procedimientos SGI (PG / PO).
 */
(function () {
  "use strict";

  const cfg = window.SGI_PROC_CONFIG;
  if (!cfg) return;

  const initial = cfg.payload || {};
  const soloLectura = !!cfg.soloLectura;

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

  function chooseSubapartadoMode(bodyEl, secNum, anchor) {
    if (!anchor) return "continuo";
    const all = listSubapartados(bodyEl, secNum);
    const idx = all.findIndex((x) => x.el === anchor);
    const anchorParts = parseSubapartadoParts(
      anchor.querySelector(".sgi-proc-sub-num")?.textContent,
      secNum
    );
    const prev = idx > 0 ? all[idx - 1] : null;
    const actual = anchorParts ? formatSubapartadoLabel(secNum, anchorParts) : "(sin detectar)";
    const anterior = prev ? formatSubapartadoLabel(secNum, prev.parts) : "No hay";
    const suggestion = anchorParts?.length >= MAX_SUBAPARTADO_LEVEL ? "s" : "c";
    const answer = (window.prompt(
      [
        `Subapartado actual: ${actual}`,
        `Subapartado anterior: ${anterior}`,
        "",
        "Elegí cómo insertar el nuevo subapartado:",
        "a = anterior (antes del actual, mismo nivel)",
        "s = siguiente (después del actual, mismo nivel)",
        "c = continuo (como hijo del actual)",
      ].join("\n"),
      suggestion
    ) || "").trim().toLowerCase();
    if (answer === "a") return "anterior";
    if (answer === "s") return "siguiente";
    if (answer === "c") return "continuo";
    return null;
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
      if (anchorParts.length >= MAX_SUBAPARTADO_LEVEL) {
        const parent = anchorParts.slice(0, -1);
        const target = anchorParts[anchorParts.length - 1] + 1;
        shiftSiblingNumbering(bodyEl, secNum, parent, target);
        return {
          parts: [...parent, target],
          ref: nextNonDescendantSubapartado(bodyEl, secNum, anchor),
        };
      }
      const level = anchorParts.length;
      const children = all
        .filter(
          (x) =>
            x.parts.length === level + 1 &&
            anchorParts.every((v, i) => x.parts[i] === v)
        )
        .map((x) => x.parts[level]);
      const next = children.length ? Math.max(...children) + 1 : 1;
      return { parts: [...anchorParts, next], ref: nextNonDescendantSubapartado(bodyEl, secNum, anchor) };
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

  function insertSubapartado(bodyEl) {
    flushUndoDebounce();
    const secNum = getSectionNum(bodyEl);
    const anchor = findAnchorSubapartado(bodyEl);
    const mode = chooseSubapartadoMode(bodyEl, secNum, anchor);
    if (!mode) return;

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
      "margin-left",
      "margin-right",
    ];

    root.querySelectorAll("[style]").forEach((el) => {
      layoutProps.forEach((prop) => el.style.removeProperty(prop));
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
      registros.push({
        nombre: tr.querySelector(".rg-nombre")?.value || "",
        quien_archiva: tr.querySelector(".rg-quien")?.value || "",
        como: tr.querySelector(".rg-como")?.value || "",
        donde: tr.querySelector(".rg-donde")?.value || "",
        tiempo_guarda: tr.querySelector(".rg-tiempo")?.value || "",
        usuarios: tr.querySelector(".rg-usuarios")?.value || "",
        disposicion_final: tr.querySelector(".rg-disp")?.value || "",
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
      aprobo: qs("#procAprobo")?.value || "",
      fecha_elaboracion: qs("#procFechaElab")?.value || "",
      fecha_revision: qs("#procFechaRev")?.value || "",
      fecha_aprobacion: qs("#procFechaAprob")?.value || "",
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
    if (!soloLectura) {
      html +=
        '<td class="sgi-proc-no-print text-center"><button type="button" class="btn btn-sm btn-link text-danger btn-del-reg">×</button></td>';
    }
    tr.innerHTML = html;
    tbody.appendChild(tr);
    tr.querySelector(".btn-del-reg")?.addEventListener("click", () => tr.remove());
  }

  let activeSectionBody = null;
  let tableResizeState = null;

  function getActiveSectionBody() {
    if (activeSectionBody && document.contains(activeSectionBody)) return activeSectionBody;
    const sel = window.getSelection();
    if (sel?.rangeCount) {
      let node = sel.anchorNode;
      if (node?.nodeType === Node.TEXT_NODE) node = node.parentElement;
      const body = node?.closest?.("[data-seccion-body]");
      if (body) return body;
    }
    return qsa("[data-seccion-body]")[0] || null;
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

  function execTextFormat(command) {
    const body = getActiveSectionBody();
    if (!body) {
      flashMsg("warning", "Hacé clic en una sección del documento para aplicar formato.");
      return;
    }
    body.focus();
    try {
      document.execCommand(command, false, null);
    } catch {
      /* navegador sin soporte */
    }
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
    try {
      if (fmtBold) fmtBold.setAttribute("aria-pressed", document.queryCommandState("bold") ? "true" : "false");
      if (fmtItalic) fmtItalic.setAttribute("aria-pressed", document.queryCommandState("italic") ? "true" : "false");
      if (fmtUnderline) {
        fmtUnderline.setAttribute("aria-pressed", document.queryCommandState("underline") ? "true" : "false");
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
    if (range) range.value = String(pct);
    if (lbl) lbl.textContent = `${pct}%`;
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
    qs("#fmtBold")?.addEventListener("click", () => execTextFormat("bold"));
    qs("#fmtItalic")?.addEventListener("click", () => execTextFormat("italic"));
    qs("#fmtUnderline")?.addEventListener("click", () => execTextFormat("underline"));

    qs("#fmtSubapartado")?.addEventListener("click", () => {
      const body = getActiveSectionBody();
      if (!body) {
        flashMsg("warning", "Hacé clic en la sección donde querés el subapartado.");
        return;
      }
      insertSubapartado(body);
      updateFormatBar();
    });

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

    document.addEventListener("focusin", (e) => {
      const body = e.target.closest?.("[data-seccion-body]");
      if (!body) return;
      activeSectionBody = body;
      qsa("[data-seccion-body]").forEach((el) => {
        el.classList.toggle("sgi-proc-section-active", el === body);
      });
      updateFormatBar();
    });

    document.addEventListener("selectionchange", () => {
      if (!soloLectura) updateFormatBar();
    });

    document.addEventListener("keydown", (e) => {
      if (soloLectura) return;
      if (!(e.ctrlKey || e.metaKey)) return;
      const key = e.key.toLowerCase();
      if (!["b", "i", "u"].includes(key)) return;
      if (!e.target.closest?.("[data-seccion-body]")) return;
      e.preventDefault();
      if (key === "b") execTextFormat("bold");
      else if (key === "i") execTextFormat("italic");
      else execTextFormat("underline");
    });

    bindTableColumnResize();
    updateFormatBar();
  }

  function addAnexoCard(ax, idx) {
    const container = qs("#procAnexosContainer");
    if (!container) return;
    const card = document.createElement("div");
    card.className = "sgi-proc-anexo-card";
    if (ax?.id) card.dataset.anexoId = String(ax.id);
    const codigoAuto = ax?.codigo || `${cfg.codigo}-A${String(idx + 1).padStart(2, "0")}`;
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
        <div class="col-md-8">
          ${ax?.tiene_archivo ? '<span class="badge text-bg-success">Archivo adjunto</span>' : ""}
        </div>
      </div>
      ${soloLectura ? "" : '<button type="button" class="btn btn-sm btn-link text-danger float-end btn-del-anexo">Quitar anexo</button>'}
    `;
    container.appendChild(card);
    card.querySelector(".btn-del-anexo")?.addEventListener("click", () => card.remove());
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
          syncSubapartadoLevels(el);
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
    await guardarBorrador();
    const token = qs('meta[name="csrf-token"]')?.content || cfg.csrf || "";
    const res = await fetch(cfg.urls.workflow, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": token },
      body: JSON.stringify({ accion }),
    });
    const data = await res.json();
    if (data.ok) {
      flashMsg("success", data.message);
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
  }

  document.addEventListener("DOMContentLoaded", () => {
    hydrate();
    if (!soloLectura) bind();
  });
})();
