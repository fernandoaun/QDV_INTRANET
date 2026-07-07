(function () {
  "use strict";

  const editorCfg = window.SGI_ORG_EDITOR;
  const viewCfg = window.SGI_ORG_VIEW;
  const MIN_ZOOM = 0.35;
  const MAX_ZOOM = 1.8;
  const ZOOM_STEP = 0.1;
  const SOLID_STROKE = "#c45c26";
  const DASHED_STROKE = "#222222";
  const STROKE_WIDTH = 2.5;
  const DASH = "7 5";
  const NODE_W = 132;
  const NODE_GAP_X = 24;
  const NODE_GAP_Y = 88;
  const CANVAS_PAD = 48;

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

  function escHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function initials(name) {
    const parts = (name || "").trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return "?";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  function slugId(text, fallback) {
    const slug = String(text || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 48);
    return slug || fallback;
  }

  function nodeKindFromData(node) {
    const rawKind = (node.kind || "").toLowerCase();
    if (rawKind === "external" || rawKind === "externo") return "external";
    if (rawKind === "internal" || rawKind === "interno") return "internal";
    const sub = (node.subtitulo || "").toLowerCase();
    if (sub.includes("extern") || sub.includes("servicio")) return "external";
    return "internal";
  }

  function resolveEditorUsuarios(node, catalog) {
    const ids = Array.isArray(node.user_ids)
      ? node.user_ids
      : node.user_id
        ? [node.user_id]
        : [];
    const list = catalog || editorCfg?.usuarios || [];
    return ids
      .map((id) => list.find((u) => String(u.id) === String(id)))
      .filter(Boolean)
      .map((u) => ({
        id: u.id,
        nombre: u.label,
        username: "",
        rol: u.rol,
        puesto: u.puesto || "",
        area: "",
        email: "",
        telefono: "",
      }));
  }

  function renderDetail(usuarioOrList, titulo, subtitulo) {
    const box = qs("#sgiOrgDetail");
    if (!box) return;
    const sub = subtitulo ? `<p class="text-muted small mb-2">${subtitulo}</p>` : "";
    const usuarios = Array.isArray(usuarioOrList)
      ? usuarioOrList
      : usuarioOrList
        ? [usuarioOrList]
        : [];
    if (!usuarios.length) {
      box.innerHTML = `
        <p class="fw-semibold mb-1">${titulo || "Puesto"}</p>
        ${sub}
        <p class="text-muted mb-0">Sin usuario asignado en la intranet.</p>`;
      return;
    }
    if (usuarios.length === 1) {
      const usuario = usuarios[0];
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
      return;
    }
    const list = usuarios
      .map(
        (u) => `
        <li class="mb-2">
          <span class="fw-semibold">${u.nombre || ""}</span>
          ${u.rol ? `<span class="text-muted small"> · ${u.rol}</span>` : ""}
        </li>`
      )
      .join("");
    box.innerHTML = `
      <p class="fw-semibold mb-1">${titulo || "Puesto"}</p>
      ${sub}
      <p class="text-muted small mb-2">${usuarios.length} usuarios asignados</p>
      <ul class="list-unstyled mb-0 small">${list}</ul>`;
  }

  function parseNodeUsuarios(btn) {
    if (!btn) return [];
    if (btn.dataset.usuarios) {
      try {
        const parsed = JSON.parse(btn.dataset.usuarios);
        return Array.isArray(parsed) ? parsed : [];
      } catch {
        return [];
      }
    }
    if (btn.dataset.nombre) {
      return [
        {
          nombre: btn.dataset.nombre,
          username: btn.dataset.username || "",
          rol: btn.dataset.rol || "",
          puesto: btn.dataset.puesto || "",
          area: btn.dataset.area || "",
          email: btn.dataset.email || "",
          telefono: btn.dataset.telefono || "",
        },
      ];
    }
    return [];
  }

  /* —— Zoom / pan —— */
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
      if (ev.target.closest(".sgi-org-canvas-node, .sgi-org-node")) return;
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
    return { fitWidth, getScale: () => scale, getPan: () => ({ panX, panY }) };
  }

  /* —— SVG connectors —— */
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

  function orthoElbow(svg, x1, y1, x2, y2, style) {
    if (Math.abs(x1 - x2) < 1) {
      svgSeg(svg, x1, y1, x1, y2, style);
      return;
    }
    const midY = y1 + (y2 - y1) / 2;
    svgSeg(svg, x1, y1, x1, midY, style);
    svgSeg(svg, x1, midY, x2, midY, style);
    svgSeg(svg, x2, midY, x2, y2, style);
  }

  function nodeBoxEl(el, container) {
    const c = container.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    return {
      top: r.top - c.top,
      bottom: r.bottom - c.top,
      left: r.left - c.left,
      right: r.right - c.left,
      cx: r.left - c.left + r.width / 2,
      cy: r.top - c.top + r.height / 2,
      width: r.width,
      height: r.height,
    };
  }

  function inferNivel(nodeId, nodes, cache) {
    const memo = cache || {};
    if (memo[nodeId] !== undefined) return memo[nodeId];
    const node = nodes.find((n) => n.id === nodeId);
    if (!node) {
      memo[nodeId] = 0;
      return 0;
    }
    if (node.nivel !== null && node.nivel !== undefined && Number.isFinite(node.nivel)) {
      memo[nodeId] = Math.max(0, node.nivel);
      return memo[nodeId];
    }
    if (!node.parent_id || !nodes.some((n) => n.id === node.parent_id)) {
      memo[nodeId] = 0;
      return 0;
    }
    memo[nodeId] = inferNivel(node.parent_id, nodes, memo) + 1;
    return memo[nodeId];
  }

  function nodeLevels(nodes) {
    const cache = {};
    const out = {};
    nodes.forEach((n) => {
      out[n.id] = inferNivel(n.id, nodes, cache);
    });
    return out;
  }

  function seedFreePositions(nodes) {
    const levels = nodeLevels(nodes);
    const byLevel = {};
    nodes.forEach((n) => {
      const lvl = levels[n.id] ?? 0;
      (byLevel[lvl] ||= []).push(n);
    });
    Object.keys(byLevel)
      .map(Number)
      .sort((a, b) => a - b)
      .forEach((lvl) => {
        const row = byLevel[lvl].sort((a, b) => (a.orden || 0) - (b.orden || 0) || (a.titulo || "").localeCompare(b.titulo || ""));
        const rowW = row.length * NODE_W + Math.max(0, row.length - 1) * NODE_GAP_X;
        let x = CANVAS_PAD + Math.max(0, (900 - rowW) / 2);
        const y = CANVAS_PAD + lvl * (NODE_GAP_Y + 56);
        row.forEach((n) => {
          if (n.x == null || n.y == null) {
            n.x = x;
            n.y = y;
          }
          x += NODE_W + NODE_GAP_X;
        });
      });
  }

  function canvasSize(nodes) {
    let maxX = 640;
    let maxY = 420;
    nodes.forEach((n) => {
      maxX = Math.max(maxX, (n.x || 0) + NODE_W + CANVAS_PAD);
      maxY = Math.max(maxY, (n.y || 0) + 80 + CANVAS_PAD);
    });
    return { width: maxX, height: maxY };
  }

  function linkStyleForTarget(nodes, toId) {
    const node = nodes.find((n) => n.id === toId);
    return node && nodeKindFromData(node) === "external" ? "dashed" : "solid";
  }

  function drawFreeConnectors(canvas, nodes, links) {
    const svg = qs("#sgiOrgConnectors", canvas);
    if (!svg) return;
    const { width, height } = canvasSize(nodes);
    svg.style.width = `${width}px`;
    svg.style.height = `${height}px`;
    svg.setAttribute("width", String(width));
    svg.setAttribute("height", String(height));
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.innerHTML = "";

    const nodeLayer = qs(".sgi-org-canvas-nodes", canvas);
    if (!nodeLayer) return;

    links.forEach((link) => {
      const fromEl = qs(`[data-node-id="${link.from}"] .sgi-org-node`, nodeLayer);
      const toEl = qs(`[data-node-id="${link.to}"] .sgi-org-node`, nodeLayer);
      if (!fromEl || !toEl) return;
      const f = nodeBoxEl(fromEl, canvas);
      const t = nodeBoxEl(toEl, canvas);
      const style = link.style || linkStyleForTarget(nodes, link.to);
      orthoElbow(svg, f.cx, f.bottom, t.cx, t.top, style);
    });
  }

  function buildNodeHtml(n, usuarios, opts) {
    const kind = nodeKindFromData(n);
    const usersLabel = usuarios.map((u) => u.nombre).join(", ");
    const usersAttr = usuarios.length
      ? ` data-usuarios='${JSON.stringify(usuarios).replace(/'/g, "&#39;")}'`
      : "";
    const editable = opts?.editable;
    const selected = opts?.selectedId === n.id;
    const connectSource = opts?.connectSourceId === n.id;
    return `
      <div class="sgi-org-canvas-node${selected ? " is-selected" : ""}"
           data-node-id="${escHtml(n.id)}"
           style="left:${n.x || 0}px;top:${n.y || 0}px">
        <div class="sgi-org-node sgi-org-node--${kind}${connectSource ? " is-connect-source" : ""}"
             role="button"
             tabindex="0"
             data-node-id="${escHtml(n.id)}"${usersAttr}>
          <span class="sgi-org-node-title" ${editable ? 'contenteditable="true" spellcheck="false"' : ""}>${escHtml(n.titulo || "Nuevo puesto")}</span>
          ${usersLabel ? `<span class="sgi-org-node-users">${escHtml(usersLabel)}</span>` : ""}
        </div>
      </div>`;
  }

  function renderFreeCanvas(wrap, nodes, links, opts) {
    if (!wrap) return;
    const { width, height } = canvasSize(nodes);
    const catalog = editorCfg?.usuarios || [];
    let nodesHtml = "";
    nodes.forEach((n) => {
      const usuarios = resolveEditorUsuarios(n, catalog);
      nodesHtml += buildNodeHtml(n, usuarios, opts);
    });

    wrap.innerHTML = `
      <div class="sgi-org-canvas" id="sgiOrgCanvas" style="width:${width}px;height:${height}px">
        <svg class="sgi-org-connectors" id="sgiOrgConnectors" aria-hidden="true"></svg>
        <div class="sgi-org-canvas-nodes">${nodesHtml || `<p class="sgi-org-empty text-muted small mb-0">Agregá puestos con el botón <strong>Agregar puesto</strong>.</p>`}</div>
      </div>`;

    requestAnimationFrame(() => drawFreeConnectors(qs("#sgiOrgCanvas", wrap), nodes, links));
  }

  /* —— Legacy level-based view —— */
  function chartContainer(wrap) {
    return qs(".sgi-org-tree-chart", wrap) || qs(".sgi-org-qdv-grid", wrap);
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

  function orthoDown(svg, x, y1, y2, style) {
    svgSeg(svg, x, y1, x, y2, style);
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
    boxes.forEach((b, i) => {
      const btn = children[i];
      const cell = btn?.closest(".sgi-org-tree-slot, .sgi-org-grid-cell");
      const kind = cell?.dataset.kind || (btn?.classList.contains("sgi-org-node--external") ? "external" : "internal");
      const segStyle = kind === "external" ? "dashed" : style;
      orthoDown(svg, b.cx, junctionY, b.top, segStyle);
    });
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

  function drawStemSide(svg, wrap, origin, fromId, toId, busCache, style) {
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
    const lineStyle = style || "dashed";
    svgSeg(svg, f.cx, yBranch, t.left, yBranch, lineStyle);
    orthoDown(svg, t.left, yBranch, t.cy, lineStyle);
  }

  function drawBusTail(svg, wrap, origin, fromId, toId, busCache, style) {
    const bus = busCache[fromId];
    const to = nodeBtn(wrap, toId);
    if (!bus || !to) return;
    const t = nodeBox(to, origin);
    const y = bus.junctionY;
    const xStart = Math.max(bus.xMax, bus.parentCx);
    const lineStyle = style || "dashed";
    svgSeg(svg, xStart, y, t.cx, y, lineStyle);
    orthoDown(svg, t.cx, y, t.top, lineStyle);
  }

  function collectChartNodes(wrap) {
    const chart = chartContainer(wrap);
    if (!chart) return [];
    return qsa(".sgi-org-tree-slot, .sgi-org-grid-cell", chart)
      .map((cell) => {
        const btn = qs(".sgi-org-node", cell);
        if (!btn) return null;
        const level = parseInt(btn.dataset.level || cell.dataset.level || "0", 10);
        const kind = cell.dataset.kind || (btn.classList.contains("sgi-org-node--external") ? "external" : "internal");
        return {
          id: btn.dataset.nodeId || cell.dataset.nodeId || "",
          parentId: btn.dataset.parentId || "",
          level,
          kind,
        };
      })
      .filter(Boolean);
  }

  function linkStyle(child) {
    return child.kind === "external" ? "dashed" : "solid";
  }

  function buildLinksFromNodes(wrap) {
    const nodes = collectChartNodes(wrap);
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
      const downstream = children.filter((c) => c.level > parent.level);
      if (!downstream.length) return;
      const byLevel = {};
      downstream.forEach((c) => {
        (byLevel[c.level] ||= []).push(c);
      });
      const minLevel = Math.min(...Object.keys(byLevel).map(Number));
      const busChildren = byLevel[minLevel] || [];
      if (busChildren.length >= 2) {
        links.push({
          type: "bus",
          from: parentId,
          children: busChildren.map((c) => c.id),
          style: busChildren.every((c) => c.kind === "external") ? "dashed" : "solid",
        });
        busParents.add(parentId);
        downstream
          .filter((c) => c.level !== minLevel)
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
        .filter((c) => c.level <= parent.level)
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

  function drawLegacyConnectors() {
    const wrap = qs("#sgiOrgChart");
    if (!wrap) return;
    const chart = chartContainer(wrap);
    if (!chart) return;
    let svg = qs("#sgiOrgConnectors", chart);
    if (!svg) {
      svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.id = "sgiOrgConnectors";
      svg.classList.add("sgi-org-connectors");
      svg.setAttribute("aria-hidden", "true");
      chart.insertBefore(svg, chart.firstChild);
    }
    const w = Math.max(chart.scrollWidth, chart.offsetWidth);
    const h = Math.max(chart.scrollHeight, chart.offsetHeight);
    svg.style.width = `${w}px`;
    svg.style.height = `${h}px`;
    svg.setAttribute("width", String(w));
    svg.setAttribute("height", String(h));
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svg.innerHTML = "";
    const links = buildLinksFromNodes(wrap);
    const origin = chart;
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
        drawStemSide(svg, wrap, origin, link.from, link.to, busCache, link.style || "dashed");
      } else if (link.type === "bus-tail" && link.from && link.to) {
        drawBusTail(svg, wrap, origin, link.from, link.to, busCache, link.style || "dashed");
      }
    });
  }

  function initLegacyConnectors() {
    function scheduleRedraw() {
      requestAnimationFrame(drawLegacyConnectors);
    }
    const wrap = qs("#sgiOrgChart");
    const chart = wrap && chartContainer(wrap);
    if (chart && typeof ResizeObserver !== "undefined") {
      new ResizeObserver(scheduleRedraw).observe(chart);
    }
    window.addEventListener("resize", scheduleRedraw);
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(scheduleRedraw).catch(() => scheduleRedraw());
    }
    scheduleRedraw();
    setTimeout(scheduleRedraw, 120);
    setTimeout(scheduleRedraw, 400);
    return scheduleRedraw;
  }

  function bindChartClicks(chart) {
    qsa(".sgi-org-node", chart).forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        highlightPath(chart, btn.dataset.nodeId || "");
        renderDetail(
          parseNodeUsuarios(btn),
          btn.querySelector(".sgi-org-node-title")?.textContent || "",
          ""
        );
      });
    });
  }

  function initLegacyView() {
    const chart = qs("#sgiOrgChart");
    if (!chart) return;
    const redrawConnectors = initLegacyConnectors();
    initZoom(redrawConnectors);
    bindChartClicks(chart);
  }

  function initFreeView() {
    const wrap = qs("#sgiOrgChart");
    if (!wrap || !viewCfg) return;
    const nodes = JSON.parse(JSON.stringify(viewCfg.nodes || []));
    const links = JSON.parse(JSON.stringify(viewCfg.links || []));
    seedFreePositions(nodes);
    renderFreeCanvas(wrap, nodes, links, {});
    const redraw = () => {
      const canvas = qs("#sgiOrgCanvas", wrap);
      if (canvas) drawFreeConnectors(canvas, nodes, links);
    };
    initZoom(redraw);
    qsa(".sgi-org-node", wrap).forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        renderDetail(
          parseNodeUsuarios(btn),
          btn.querySelector(".sgi-org-node-title")?.textContent || "",
          ""
        );
      });
    });
  }

  /* —— Interactive canvas editor —— */
  function initEditor() {
    if (!editorCfg) return;

    const state = {
      nodes: JSON.parse(JSON.stringify(editorCfg.nodes || [])),
      links: JSON.parse(JSON.stringify(editorCfg.links || [])),
      selectedId: null,
      connectSourceId: null,
      tool: "select",
    };

    seedFreePositions(state.nodes);

    const wrap = qs("#sgiOrgChart");
    const propsPanel = qs("#sgiOrgPropsPanel");
    const toolHint = qs("#sgiOrgToolHint");

    function syncParentsFromLinks() {
      const parentByChild = {};
      state.links.forEach((link) => {
        if (!parentByChild[link.to]) parentByChild[link.to] = link.from;
      });
      state.nodes.forEach((n) => {
        n.parent_id = parentByChild[n.id] || null;
      });
    }

    function buildPayload() {
      syncParentsFromLinks();
      return {
        layout: "free",
        nodes: state.nodes.map((n, i) => ({
          id: n.id,
          titulo: n.titulo,
          subtitulo: n.subtitulo || "",
          kind: nodeKindFromData(n),
          parent_id: n.parent_id || null,
          user_ids: n.user_ids || [],
          user_id: n.user_id || null,
          orden: n.orden ?? i,
          x: Math.round(n.x || 0),
          y: Math.round(n.y || 0),
        })),
        links: state.links.map((l) => ({
          from: l.from,
          to: l.to,
          style: l.style || linkStyleForTarget(state.nodes, l.to),
        })),
      };
    }
    window.sgiOrgCollectPayload = () => buildPayload();

    function nodeById(id) {
      return state.nodes.find((n) => n.id === id);
    }

    function refreshCanvas() {
      renderFreeCanvas(wrap, state.nodes, state.links, {
        editable: true,
        selectedId: state.selectedId,
        connectSourceId: state.connectSourceId,
      });
      bindCanvasEvents();
      renderPropsPanel();
    }

    function setTool(tool) {
      state.tool = tool;
      state.connectSourceId = null;
      qs("#btnOrgToolSelect")?.classList.toggle("active", tool === "select");
      qs("#btnOrgToolConnect")?.classList.toggle("active", tool === "connect");
      if (toolHint) {
        toolHint.innerHTML =
          tool === "connect"
            ? "Modo conectar: hacé clic en el puesto <strong>superior</strong> y luego en el <strong>inferior</strong> para crear la línea."
            : "Arrastrá los recuadros para ubicarlos. Seleccioná un puesto para editar sus datos en el panel derecho.";
      }
      refreshCanvas();
    }

    function selectNode(id) {
      state.selectedId = id;
      refreshCanvas();
    }

    function addLink(from, to) {
      if (!from || !to || from === to) return;
      if (state.links.some((l) => l.from === from && l.to === to)) return;
      const style = linkStyleForTarget(state.nodes, to);
      state.links.push({ from, to, style });
      syncParentsFromLinks();
      refreshCanvas();
    }

    function removeLink(from, to) {
      state.links = state.links.filter((l) => !(l.from === from && l.to === to));
      syncParentsFromLinks();
      refreshCanvas();
    }

    function removeNode(id) {
      state.nodes = state.nodes.filter((n) => n.id !== id);
      state.links = state.links.filter((l) => l.from !== id && l.to !== id);
      if (state.selectedId === id) state.selectedId = null;
      if (state.connectSourceId === id) state.connectSourceId = null;
      syncParentsFromLinks();
      refreshCanvas();
    }

    function addNode() {
      const i = state.nodes.length;
      const id = `nuevo_${Date.now()}`;
      const viewport = qs("#sgiOrgViewport");
      const x = CANVAS_PAD + (i % 4) * (NODE_W + NODE_GAP_X);
      const y = CANVAS_PAD + Math.floor(i / 4) * (NODE_GAP_Y + 56);
      state.nodes.push({
        id,
        titulo: "NUEVO PUESTO",
        kind: "internal",
        parent_id: null,
        user_ids: [],
        orden: i,
        x: viewport ? x : 80,
        y: viewport ? y : 80,
      });
      state.selectedId = id;
      refreshCanvas();
    }

    function renderPropsPanel() {
      if (!propsPanel) return;
      const node = state.selectedId ? nodeById(state.selectedId) : null;
      if (!node) {
        propsPanel.innerHTML = `<p class="text-muted small mb-0">Seleccioná un recuadro del lienzo para editar nombre, tipo y usuarios.</p>`;
        return;
      }

      const incoming = state.links.filter((l) => l.to === node.id);
      const outgoing = state.links.filter((l) => l.from === node.id);
      const userIds = Array.isArray(node.user_ids)
        ? node.user_ids.map(String)
        : node.user_id
          ? [String(node.user_id)]
          : [];
      const kind = nodeKindFromData(node);

      const usersOptions = (editorCfg.usuarios || [])
        .map((u) => {
          const sel = userIds.includes(String(u.id)) ? " selected" : "";
          return `<option value="${u.id}"${sel}>${escHtml(u.label)} (${escHtml(u.rol)})</option>`;
        })
        .join("");

      const linkRow = (link, direction) => {
        const otherId = direction === "in" ? link.from : link.to;
        const other = nodeById(otherId);
        const label = other?.titulo || otherId;
        const delFrom = direction === "in" ? link.from : link.from;
        const delTo = direction === "in" ? link.to : link.to;
        return `
          <li class="d-flex justify-content-between align-items-start gap-2 mb-1">
            <span class="small">${escHtml(label)}</span>
            <button type="button" class="btn btn-link btn-sm text-danger p-0 org-link-del"
                    data-from="${escHtml(delFrom)}" data-to="${escHtml(delTo)}">Quitar</button>
          </li>`;
      };

      propsPanel.innerHTML = `
        <div class="mb-3">
          <label class="form-label small mb-1">Nombre del puesto</label>
          <input type="text" class="form-control form-control-sm" id="orgPropTitulo" value="${escHtml(node.titulo || "")}">
        </div>
        <div class="mb-3">
          <label class="form-label small mb-1">Tipo</label>
          <select class="form-select form-select-sm" id="orgPropKind">
            <option value="internal"${kind === "internal" ? " selected" : ""}>Interno</option>
            <option value="external"${kind === "external" ? " selected" : ""}>Servicio externo</option>
          </select>
        </div>
        <div class="mb-3">
          <label class="form-label small mb-1">Usuarios</label>
          <select class="form-select form-select-sm" id="orgPropUsers" multiple size="4">${usersOptions}</select>
          <div class="form-text">Ctrl + clic para varios</div>
        </div>
        ${
          incoming.length
            ? `<div class="mb-2"><span class="small fw-semibold">Depende de</span><ul class="list-unstyled mb-0 mt-1">${incoming.map((l) => linkRow(l, "in")).join("")}</ul></div>`
            : ""
        }
        ${
          outgoing.length
            ? `<div class="mb-3"><span class="small fw-semibold">Supervisa a</span><ul class="list-unstyled mb-0 mt-1">${outgoing.map((l) => linkRow(l, "out")).join("")}</ul></div>`
            : ""
        }
        <button type="button" class="btn btn-outline-danger btn-sm w-100" id="orgPropDelete">
          <i class="bi bi-trash me-1"></i>Eliminar puesto
        </button>`;

      qs("#orgPropTitulo", propsPanel)?.addEventListener("input", (ev) => {
        node.titulo = ev.target.value.trim().toUpperCase();
        refreshCanvas();
      });
      qs("#orgPropKind", propsPanel)?.addEventListener("change", (ev) => {
        node.kind = ev.target.value === "external" ? "external" : "internal";
        state.links.forEach((l) => {
          if (l.to === node.id) l.style = linkStyleForTarget(state.nodes, node.id);
        });
        refreshCanvas();
      });
      qs("#orgPropUsers", propsPanel)?.addEventListener("change", (ev) => {
        node.user_ids = Array.from(ev.target.selectedOptions)
          .map((opt) => parseInt(opt.value, 10))
          .filter((uid) => Number.isFinite(uid) && uid > 0);
        node.user_id = node.user_ids[0] || null;
        refreshCanvas();
      });
      qsa(".org-link-del", propsPanel).forEach((btn) => {
        btn.addEventListener("click", () => removeLink(btn.dataset.from, btn.dataset.to));
      });
      qs("#orgPropDelete", propsPanel)?.addEventListener("click", () => {
        if (confirm("¿Eliminar este puesto y sus vínculos?")) removeNode(node.id);
      });
    }

    function bindCanvasEvents() {
      const canvas = qs("#sgiOrgCanvas", wrap);
      if (!canvas) return;

      qsa(".sgi-org-canvas-node", canvas).forEach((slot) => {
        const id = slot.dataset.nodeId;
        const inner = qs(".sgi-org-node", slot);
        let drag = null;
        let didDrag = false;

        inner?.addEventListener("mousedown", (ev) => {
          if (state.tool !== "select") return;
          ev.preventDefault();
          ev.stopPropagation();
          const node = nodeById(id);
          if (!node) return;
          selectNode(id);
          didDrag = false;
          drag = {
            startX: ev.clientX,
            startY: ev.clientY,
            origX: node.x || 0,
            origY: node.y || 0,
          };

          function onMove(moveEv) {
            if (!drag) return;
            if (Math.abs(moveEv.clientX - drag.startX) > 3 || Math.abs(moveEv.clientY - drag.startY) > 3) {
              didDrag = true;
            }
            const zoomApi = zoomRef;
            const scale = zoomApi?.getScale?.() || 1;
            node.x = drag.origX + (moveEv.clientX - drag.startX) / scale;
            node.y = drag.origY + (moveEv.clientY - drag.startY) / scale;
            slot.style.left = `${node.x}px`;
            slot.style.top = `${node.y}px`;
            const { width, height } = canvasSize(state.nodes);
            canvas.style.width = `${width}px`;
            canvas.style.height = `${height}px`;
            drawFreeConnectors(canvas, state.nodes, state.links);
          }

          function onUp() {
            drag = null;
            window.removeEventListener("mousemove", onMove);
            window.removeEventListener("mouseup", onUp);
          }

          window.addEventListener("mousemove", onMove);
          window.addEventListener("mouseup", onUp);
        });

        inner?.addEventListener("click", (ev) => {
          ev.stopPropagation();
          if (didDrag) return;
          if (state.tool === "connect") {
            if (!state.connectSourceId) {
              state.connectSourceId = id;
              refreshCanvas();
              return;
            }
            if (state.connectSourceId === id) {
              state.connectSourceId = null;
              refreshCanvas();
              return;
            }
            addLink(state.connectSourceId, id);
            state.connectSourceId = null;
            selectNode(id);
            return;
          }
          selectNode(id);
        });

        const titleEl = qs(".sgi-org-node-title", inner);
        titleEl?.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter") {
            ev.preventDefault();
            titleEl.blur();
          }
        });
        titleEl?.addEventListener("blur", () => {
          const node = nodeById(id);
          if (node) node.titulo = titleEl.textContent.trim().toUpperCase() || node.titulo;
          renderPropsPanel();
        });
      });
    }

    const redraw = () => {
      const canvas = qs("#sgiOrgCanvas", wrap);
      if (canvas) drawFreeConnectors(canvas, state.nodes, state.links);
    };
    const zoomRef = initZoom(redraw);

    refreshCanvas();
    setTool("select");

    qs("#btnOrgToolSelect")?.addEventListener("click", () => setTool("select"));
    qs("#btnOrgToolConnect")?.addEventListener("click", () => setTool("connect"));
    qs("#btnOrgAddNode")?.addEventListener("click", addNode);

    qs("#btnGuardarOrganigrama")?.addEventListener("click", () => {
      const payload = buildPayload();
      fetch(editorCfg.guardarUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": editorCfg.csrf,
          "X-Requested-With": "XMLHttpRequest",
        },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      })
        .then((r) => r.json())
        .then((res) => flash(res.ok ? "success" : "danger", res.message || ""))
        .catch(() => flash("danger", "No se pudo guardar."));
    });
  }

  /* —— Boot —— */
  if (editorCfg) {
    initEditor();
  } else if (viewCfg && viewCfg.layout === "free") {
    initFreeView();
  } else {
    initLegacyView();
  }
})();
