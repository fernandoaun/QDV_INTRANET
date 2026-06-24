(function () {
  "use strict";

  const editorCfg = window.SGI_ORG_EDITOR;
  const MIN_ZOOM = 0.4;
  const MAX_ZOOM = 1.6;
  const ZOOM_STEP = 0.1;
  const SOLID_STROKE = "#c45c26";
  const DASHED_STROKE = "#222222";
  const STROKE_WIDTH = 2.5;
  const DASH = "7 5";

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }
  function qsa(sel, root) {
    return Array.from((root || document).querySelectorAll(sel));
  }

  function flash(kind, msg) {
    const el = qs("#sgiOrgFlash");
    if (!el) return;
    el.className = `alert alert-${kind}`;
    el.textContent = msg;
    el.classList.remove("d-none");
  }

  function initials(name) {
    const parts = (name || "").trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return "?";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  function renderDetail(usuario, titulo, subtitulo) {
    const box = qs("#sgiOrgDetail");
    if (!box) return;
    const sub = subtitulo ? `<p class="text-muted small mb-2">${subtitulo}</p>` : "";
    if (!usuario) {
      box.innerHTML = `
        <p class="fw-semibold mb-1">${titulo || "Puesto"}</p>
        ${sub}
        <p class="text-muted mb-0">Sin usuario asignado en la intranet.</p>`;
      return;
    }
    const rows = [
      ["Nombre", usuario.nombre],
      ["Usuario", usuario.username],
      ["Perfil", usuario.rol],
      ["Puesto", usuario.puesto],
      ["Área", usuario.area],
      ["Email", usuario.email],
      ["Teléfono", usuario.telefono],
    ]
      .filter(([, v]) => v)
      .map(([k, v]) => `<dt class="col-sm-5">${k}</dt><dd class="col-sm-7">${v}</dd>`)
      .join("");
    box.innerHTML = `
      <div class="d-flex align-items-center gap-2 mb-3">
        <div class="sgi-org-detail-avatar" aria-hidden="true">${initials(usuario.nombre)}</div>
        <div>
          <p class="fw-semibold mb-0">${usuario.nombre}</p>
          <p class="text-muted small mb-0">${usuario.rol || ""}</p>
        </div>
      </div>
      <p class="fw-semibold mb-1">${titulo || ""}</p>
      ${sub}
      <dl class="row mb-0 small">${rows}</dl>`;
  }

  function clearPath(chart) {
    qsa(".sgi-org-node", chart).forEach((b) => b.classList.remove("is-path", "is-active"));
  }

  function highlightPath(chart, nodeId) {
    clearPath(chart);
    let current = qs(`.sgi-org-node[data-node-id="${nodeId}"]`, chart);
    while (current) {
      current.classList.add("is-path");
      const parentId = current.dataset.parentId;
      if (!parentId) break;
      current = qs(`.sgi-org-node[data-node-id="${parentId}"]`, chart);
    }
    const active = qs(`.sgi-org-node[data-node-id="${nodeId}"]`, chart);
    if (active) active.classList.add("is-active");
  }

  function nodeBtn(wrap, nodeId) {
    return qs(`.sgi-org-node[data-node-id="${nodeId}"]`, wrap);
  }

  function nodeBox(btn, container) {
    const c = container.getBoundingClientRect();
    const r = btn.getBoundingClientRect();
    return {
      top: r.top - c.top,
      bottom: r.bottom - c.top,
      left: r.left - c.left,
      right: r.right - c.left,
      cx: r.left - c.left + r.width / 2,
      cy: r.top - c.top + r.height / 2,
    };
  }

  function strokeAttrs(style) {
    return {
      stroke: style === "dashed" ? DASHED_STROKE : SOLID_STROKE,
      dash: style === "dashed" ? DASH : null,
    };
  }

  function svgSeg(svg, x1, y1, x2, y2, style) {
    const { stroke, dash } = strokeAttrs(style);
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", String(x1));
    line.setAttribute("y1", String(y1));
    line.setAttribute("x2", String(x2));
    line.setAttribute("y2", String(y2));
    line.setAttribute("stroke", stroke);
    line.setAttribute("stroke-width", String(STROKE_WIDTH));
    line.setAttribute("stroke-linecap", "square");
    if (dash) line.setAttribute("stroke-dasharray", dash);
    svg.appendChild(line);
  }

  function orthoDown(svg, x, y1, y2, style) {
    svgSeg(svg, x, y1, x, y2, style);
  }

  function orthoElbow(svg, x1, y1, x2, y2, style) {
    if (Math.abs(x1 - x2) < 1) {
      orthoDown(svg, x1, y1, y2, style);
      return;
    }
    const midY = y1 + (y2 - y1) / 2;
    svgSeg(svg, x1, y1, x1, midY, style);
    svgSeg(svg, x1, midY, x2, midY, style);
    svgSeg(svg, x2, midY, x2, y2, style);
  }

  function drawBus(svg, wrap, origin, parentId, childIds, style, busCache) {
    const parent = nodeBtn(wrap, parentId);
    if (!parent) return null;
    const children = childIds.map((id) => nodeBtn(wrap, id)).filter(Boolean);
    if (!children.length) return null;

    const p = nodeBox(parent, origin);
    const boxes = children.map((btn) => nodeBox(btn, origin));
    const junctionY = p.bottom + Math.max(16, (boxes[0].top - p.bottom) * 0.5);

    orthoDown(svg, p.cx, p.bottom, junctionY, style);
    const xs = boxes.map((b) => b.cx);
    const xMin = Math.min(...xs);
    const xMax = Math.max(...xs);
    svgSeg(svg, xMin, junctionY, xMax, junctionY, style);
    boxes.forEach((b) => orthoDown(svg, b.cx, junctionY, b.top, style));

    const info = { junctionY, xMin, xMax, parentCx: p.cx };
    busCache[parentId] = info;
    return info;
  }

  function drawDirect(svg, wrap, origin, fromId, toId, style) {
    const from = nodeBtn(wrap, fromId);
    const to = nodeBtn(wrap, toId);
    if (!from || !to) return;
    const f = nodeBox(from, origin);
    const t = nodeBox(to, origin);
    orthoElbow(svg, f.cx, f.bottom, t.cx, t.top, style);
  }

  function drawStemSide(svg, wrap, origin, fromId, toId, busCache) {
    const from = nodeBtn(wrap, fromId);
    const to = nodeBtn(wrap, toId);
    if (!from || !to) return;
    const f = nodeBox(from, origin);
    const t = nodeBox(to, origin);
    const bus = busCache[fromId];
    let yBranch = f.bottom + 22;
    if (bus) {
      yBranch = f.bottom + (bus.junctionY - f.bottom) * 0.45;
    } else {
      yBranch = f.bottom + Math.max(18, (t.cy - f.bottom) * 0.42);
    }
    svgSeg(svg, f.cx, yBranch, t.left, yBranch, "dashed");
    orthoDown(svg, t.left, yBranch, t.cy, "dashed");
  }

  function drawBusTail(svg, wrap, origin, fromId, toId, busCache) {
    const bus = busCache[fromId];
    const to = nodeBtn(wrap, toId);
    if (!bus || !to) return;
    const t = nodeBox(to, origin);
    const y = bus.junctionY;
    const xStart = Math.max(bus.xMax, bus.parentCx);
    svgSeg(svg, xStart, y, t.cx, y, "dashed");
    orthoDown(svg, t.cx, y, t.top, "dashed");
  }

  function collectGridNodes(wrap) {
    return qsa(".sgi-org-grid-cell", wrap)
      .map((cell) => {
        const btn = qs(".sgi-org-node", cell);
        if (!btn) return null;
        return {
          id: btn.dataset.nodeId || cell.dataset.nodeId || "",
          parentId: btn.dataset.parentId || "",
          row: parseInt(cell.dataset.row || "0", 10),
          col: parseInt(cell.dataset.col || "0", 10),
          kind: cell.classList.contains("sgi-org-grid-cell--external") ? "external" : "internal",
        };
      })
      .filter(Boolean);
  }

  function isLateral(parent, child) {
    if (child.row < parent.row) return true;
    return Math.abs(child.col - parent.col) >= 4;
  }

  function linkStyle(child) {
    return child.kind === "external" ? "dashed" : "solid";
  }

  function buildLinksFromNodes(wrap) {
    const nodes = collectGridNodes(wrap);
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const childrenByParent = {};
    nodes.forEach((n) => {
      if (!n.parentId || !byId[n.parentId]) return;
      (childrenByParent[n.parentId] ||= []).push(n);
    });

    const links = [];
    const busParents = new Set();

    Object.entries(childrenByParent).forEach(([parentId, children]) => {
      const parent = byId[parentId];
      const downstream = children.filter((c) => c.row > parent.row && !isLateral(parent, c));
      if (!downstream.length) return;

      const byRow = {};
      downstream.forEach((c) => {
        (byRow[c.row] ||= []).push(c);
      });
      const minRow = Math.min(...Object.keys(byRow).map(Number));
      const busChildren = byRow[minRow] || [];

      if (busChildren.length >= 2) {
        links.push({
          type: "bus",
          from: parentId,
          children: busChildren.map((c) => c.id),
          style: busChildren.every((c) => c.kind === "external") ? "dashed" : "solid",
        });
        busParents.add(parentId);
        downstream
          .filter((c) => c.row !== minRow)
          .forEach((c) => {
            links.push({ type: "direct", from: parentId, to: c.id, style: linkStyle(c) });
          });
      } else {
        downstream.forEach((c) => {
          links.push({ type: "direct", from: parentId, to: c.id, style: linkStyle(c) });
        });
      }
    });

    Object.entries(childrenByParent).forEach(([parentId, children]) => {
      const parent = byId[parentId];
      children
        .filter((c) => isLateral(parent, c))
        .forEach((c) => {
          links.push({
            type: busParents.has(parentId) ? "bus-tail" : "stem-side",
            from: parentId,
            to: c.id,
            style: linkStyle(c),
          });
        });
    });

    return links;
  }

  function drawConnectors() {
    const wrap = qs("#sgiOrgChart");
    if (!wrap) return;
    const grid = qs(".sgi-org-qdv-grid", wrap);
    if (!grid) return;
    let svg = qs("#sgiOrgConnectors", grid);
    if (!svg) {
      svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.id = "sgiOrgConnectors";
      svg.classList.add("sgi-org-connectors");
      svg.setAttribute("aria-hidden", "true");
      grid.insertBefore(svg, grid.firstChild);
    }

    const w = Math.max(grid.scrollWidth, grid.offsetWidth);
    const h = Math.max(grid.scrollHeight, grid.offsetHeight);
    svg.style.width = `${w}px`;
    svg.style.height = `${h}px`;
    svg.setAttribute("width", String(w));
    svg.setAttribute("height", String(h));
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svg.innerHTML = "";

    const links = buildLinksFromNodes(wrap);
    const origin = grid;
    const busCache = {};

    links.forEach((link) => {
      if (link.type === "bus" && link.from && link.children) {
        drawBus(svg, wrap, origin, link.from, link.children, link.style || "solid", busCache);
      }
    });
    links.forEach((link) => {
      if (link.type === "direct" && link.from && link.to) {
        drawDirect(svg, wrap, origin, link.from, link.to, link.style || "solid");
      } else if (link.type === "stem-side" && link.from && link.to) {
        drawStemSide(svg, wrap, origin, link.from, link.to, busCache);
      } else if (link.type === "bus-tail" && link.from && link.to) {
        drawBusTail(svg, wrap, origin, link.from, link.to, busCache);
      }
    });
  }

  function initConnectors() {
    function scheduleRedraw() {
      requestAnimationFrame(drawConnectors);
    }
    const wrap = qs("#sgiOrgChart");
    const grid = wrap && qs(".sgi-org-qdv-grid", wrap);
    if (grid && typeof ResizeObserver !== "undefined") {
      new ResizeObserver(scheduleRedraw).observe(grid);
    }
    window.addEventListener("resize", scheduleRedraw);
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(scheduleRedraw).catch(() => scheduleRedraw());
    }
    scheduleRedraw();
    setTimeout(scheduleRedraw, 120);
    setTimeout(scheduleRedraw, 400);
    setTimeout(scheduleRedraw, 900);
    return scheduleRedraw;
  }

  function initZoom(onLayout) {
    const viewport = qs("#sgiOrgViewport");
    const stage = qs("#sgiOrgStage");
    const label = qs("#sgiOrgZoomLabel");
    if (!viewport || !stage) return null;

    let scale = 1;
    let panX = 0;
    let panY = 0;
    let dragging = false;
    let startX = 0;
    let startY = 0;
    let originX = 0;
    let originY = 0;

    function applyTransform() {
      stage.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
      if (label) label.textContent = `${Math.round(scale * 100)}%`;
    }

    function setScale(next) {
      scale = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, next));
      applyTransform();
    }

    function fitWidth() {
      scale = 1;
      panX = 0;
      panY = 0;
      const chart = qs("#sgiOrgChart");
      if (chart && viewport.clientWidth > 0) {
        const contentW = chart.scrollWidth;
        if (contentW > viewport.clientWidth) {
          scale = Math.max(MIN_ZOOM, (viewport.clientWidth - 24) / contentW);
        }
      }
      applyTransform();
      onLayout?.();
    }

    qs("#sgiOrgZoomIn")?.addEventListener("click", () => setScale(scale + ZOOM_STEP));
    qs("#sgiOrgZoomOut")?.addEventListener("click", () => setScale(scale - ZOOM_STEP));
    qs("#sgiOrgZoomReset")?.addEventListener("click", fitWidth);

    viewport.addEventListener(
      "wheel",
      (ev) => {
        if (!ev.ctrlKey) return;
        ev.preventDefault();
        setScale(scale + (ev.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP));
      },
      { passive: false }
    );

    viewport.addEventListener("mousedown", (ev) => {
      if (ev.button !== 0) return;
      dragging = true;
      viewport.classList.add("is-panning");
      startX = ev.clientX;
      startY = ev.clientY;
      originX = panX;
      originY = panY;
    });

    window.addEventListener("mousemove", (ev) => {
      if (!dragging) return;
      panX = originX + (ev.clientX - startX);
      panY = originY + (ev.clientY - startY);
      applyTransform();
    });

    window.addEventListener("mouseup", () => {
      dragging = false;
      viewport.classList.remove("is-panning");
    });

    window.addEventListener("resize", () => {
      fitWidth();
      onLayout?.();
    });
    fitWidth();
    onLayout?.();
    return { fitWidth };
  }

  function initView() {
    const chart = qs("#sgiOrgChart");
    if (!chart) return;
    const redrawConnectors = initConnectors();
    initZoom(redrawConnectors);

    qsa(".sgi-org-node", chart).forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        highlightPath(chart, btn.dataset.nodeId || "");
        const usuario = btn.dataset.nombre
          ? {
              nombre: btn.dataset.nombre,
              username: btn.dataset.username || "",
              rol: btn.dataset.rol || "",
              puesto: btn.dataset.puesto || "",
              area: btn.dataset.area || "",
              email: btn.dataset.email || "",
              telefono: btn.dataset.telefono || "",
            }
          : null;
        renderDetail(usuario, btn.querySelector(".sgi-org-node-title")?.textContent || "", "");
      });
    });
  }

  function findTableRow(nodeId) {
    return qsa("#sgiOrgEditorTable tbody tr").find((tr) => tr.querySelector(".org-id")?.value?.trim() === nodeId);
  }

  function syncChartParent(nodeId, parentId) {
    const chart = qs("#sgiOrgChart");
    if (!chart) return;
    const btn = qs(`.sgi-org-node[data-node-id="${nodeId}"]`, chart);
    if (btn) btn.dataset.parentId = parentId || "";
  }

  function syncTableParent(nodeId, parentId) {
    const tr = findTableRow(nodeId);
    const input = tr?.querySelector(".org-parent");
    if (input) input.value = parentId || "";
  }

  function initEditorConnect(redrawConnectors) {
    const chart = qs("#sgiOrgChart");
    if (!chart || chart.dataset.mode !== "edit") return;

    let connectSourceId = null;

    function clearConnectVisual() {
      qsa(".sgi-org-node", chart).forEach((b) => b.classList.remove("is-connect-source"));
    }

    function clearConnectState() {
      connectSourceId = null;
      clearConnectVisual();
    }

    qsa(".sgi-org-node", chart).forEach((btn) => {
      btn.addEventListener("mousedown", (ev) => ev.stopPropagation());
      btn.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const nodeId = btn.dataset.nodeId || "";
        if (!nodeId) return;

        if (!connectSourceId) {
          clearConnectVisual();
          connectSourceId = nodeId;
          btn.classList.add("is-connect-source");
          flash("info", `Origen: ${btn.querySelector(".sgi-org-node-title")?.textContent || nodeId}. Clic en el puesto dependiente.`);
          return;
        }

        if (connectSourceId === nodeId) {
          clearConnectState();
          flash("secondary", "Conexión cancelada.");
          return;
        }

        syncChartParent(nodeId, connectSourceId);
        syncTableParent(nodeId, connectSourceId);
        clearConnectState();
        redrawConnectors?.();
        flash("success", "Dependencia asignada. Las líneas se actualizaron.");
      });
    });

    qs("#btnOrgClearConnect")?.addEventListener("click", () => {
      clearConnectState();
      const el = qs("#sgiOrgFlash");
      if (el) el.classList.add("d-none");
    });

    qsa("#sgiOrgEditorTable tbody").forEach((tbody) => {
      tbody.addEventListener("input", (ev) => {
        if (!ev.target.classList.contains("org-parent")) return;
        const tr = ev.target.closest("tr");
        const nodeId = tr?.querySelector(".org-id")?.value?.trim();
        if (!nodeId) return;
        syncChartParent(nodeId, ev.target.value.trim());
        redrawConnectors?.();
      });
    });
  }

  function buildRow(node, idx) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input type="text" class="form-control form-control-sm org-id" value="${(node.id || "").replace(/"/g, "&quot;")}"></td>
      <td><input type="text" class="form-control form-control-sm org-titulo" value="${(node.titulo || "").replace(/"/g, "&quot;")}"></td>
      <td><input type="text" class="form-control form-control-sm org-sub" value="${(node.subtitulo || "").replace(/"/g, "&quot;")}"></td>
      <td><input type="text" class="form-control form-control-sm org-parent" value="${(node.parent_id || "").replace(/"/g, "&quot;")}" placeholder="id padre"></td>
      <td><select class="form-select form-select-sm org-user"><option value="">—</option></select></td>
      <td><input type="number" class="form-control form-control-sm org-orden" value="${node.orden ?? idx}"></td>
      <td><button type="button" class="btn btn-sm btn-link text-danger org-del">Quitar</button></td>
    `;
    const sel = qs(".org-user", tr);
    (editorCfg.usuarios || []).forEach((u) => {
      const opt = document.createElement("option");
      opt.value = String(u.id);
      opt.textContent = `${u.label} (${u.rol})`;
      if (String(node.user_id || "") === String(u.id)) opt.selected = true;
      sel.appendChild(opt);
    });
    tr.querySelector(".org-del")?.addEventListener("click", () => tr.remove());
    return tr;
  }

  function collectNodes() {
    return qsa("#sgiOrgEditorTable tbody tr").map((tr, i) => ({
      id: tr.querySelector(".org-id")?.value?.trim() || `n${i}`,
      titulo: tr.querySelector(".org-titulo")?.value?.trim() || "",
      subtitulo: tr.querySelector(".org-sub")?.value?.trim() || "",
      parent_id: tr.querySelector(".org-parent")?.value?.trim() || null,
      user_id: tr.querySelector(".org-user")?.value || null,
      orden: parseInt(tr.querySelector(".org-orden")?.value || String(i), 10),
    }));
  }

  function initEditor() {
    const tbody = qs("#sgiOrgEditorTable tbody");
    if (!tbody || !editorCfg) return;
    const redrawConnectors = initConnectors();
    initZoom(redrawConnectors);
    initEditorConnect(redrawConnectors);
    (editorCfg.nodes || []).forEach((n, i) => tbody.appendChild(buildRow(n, i)));
    qs("#btnOrgAddRow")?.addEventListener("click", () => {
      const i = qsa("#sgiOrgEditorTable tbody tr").length;
      tbody.appendChild(buildRow({ id: `nuevo_${i}`, orden: i }, i));
    });
    qs("#btnGuardarOrganigrama")?.addEventListener("click", () => {
      fetch(editorCfg.guardarUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": editorCfg.csrf,
          "X-Requested-With": "XMLHttpRequest",
        },
        credentials: "same-origin",
        body: JSON.stringify({ nodes: collectNodes() }),
      })
        .then((r) => r.json())
        .then((res) => flash(res.ok ? "success" : "danger", res.message || ""))
        .catch(() => flash("danger", "No se pudo guardar."));
    });
  }

  if (editorCfg) initEditor();
  else initView();
})();
