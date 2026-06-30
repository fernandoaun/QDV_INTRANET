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

  function drawConnectors() {
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

  function initConnectors() {
    function scheduleRedraw() {
      requestAnimationFrame(drawConnectors);
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

  function nodeKindFromData(node) {
    const rawKind = (node.kind || "").toLowerCase();
    if (rawKind === "external" || rawKind === "externo") return "external";
    if (rawKind === "internal" || rawKind === "interno") return "internal";
    const sub = (node.subtitulo || "").toLowerCase();
    if (sub.includes("extern") || sub.includes("servicio")) return "external";
    return "internal";
  }

  function resolveEditorUsuarios(node) {
    const ids = Array.isArray(node.user_ids)
      ? node.user_ids
      : node.user_id
        ? [node.user_id]
        : [];
    const catalog = editorCfg?.usuarios || [];
    return ids
      .map((id) => catalog.find((u) => String(u.id) === String(id)))
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

  function renderChartFromNodes(nodes, wrap, onReady) {
    if (!wrap) return;
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const levels = nodeLevels(nodes);
    const byLevel = {};
    nodes.forEach((n) => {
      const lvl = levels[n.id] ?? 0;
      (byLevel[lvl] ||= []).push(n);
    });

    const levelKeys = Object.keys(byLevel)
      .map(Number)
      .sort((a, b) => a - b);
    if (!levelKeys.length) {
      wrap.innerHTML = `<div class="sgi-org-empty alert alert-light mb-0">Agregá puestos en la tabla para ver el organigrama.</div>`;
      onReady?.();
      return;
    }

    let html = `<div class="sgi-org-tree-chart" role="tree" aria-label="Organigrama QDV">`;
    levelKeys.forEach((lvl) => {
      html += `<div class="sgi-org-tree-level" data-level="${lvl}">`;
      byLevel[lvl]
        .sort((a, b) => (a.orden || 0) - (b.orden || 0) || (a.titulo || "").localeCompare(b.titulo || ""))
        .forEach((n) => {
          const kind = nodeKindFromData(n);
          const usuarios = resolveEditorUsuarios(n);
          const isRoot = !n.parent_id || !byId[n.parent_id];
          const usersLabel = usuarios.map((u) => u.nombre).join(", ");
          const usersAttr = usuarios.length
            ? ` data-usuarios='${JSON.stringify(usuarios).replace(/'/g, "&#39;")}'`
            : "";
          html += `
            <div class="sgi-org-tree-slot" data-node-id="${escHtml(n.id)}" data-level="${lvl}" data-kind="${kind}">
              <button type="button"
                      class="sgi-org-node${isRoot ? " sgi-org-node--root" : ""} sgi-org-node--${kind}"
                      data-node-id="${escHtml(n.id)}"
                      data-parent-id="${escHtml(n.parent_id || "")}"
                      data-level="${lvl}"${usersAttr}>
                <span class="sgi-org-node-title">${escHtml(n.titulo || n.id)}</span>
                ${usersLabel ? `<span class="sgi-org-node-users">${escHtml(usersLabel)}</span>` : ""}
              </button>
            </div>`;
        });
      html += `</div>`;
    });
    html += `</div>
      <div class="sgi-org-qdv-footer">
        <div class="sgi-org-legend">
          <span class="sgi-org-legend-swatch sgi-org-legend-swatch--external" aria-hidden="true"></span>
          <span>Servicios Externos</span>
        </div>
      </div>`;
    wrap.innerHTML = html;
    bindChartClicks(wrap);
    onReady?.();
  }

  function initView() {
    const chart = qs("#sgiOrgChart");
    if (!chart) return;
    const redrawConnectors = initConnectors();
    initZoom(redrawConnectors);
    bindChartClicks(chart);
  }

  function escHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
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

  function collectNodesFromTable() {
    return qsa("#sgiOrgEditorTable tbody tr").map((tr, i) => {
      const titulo = tr.querySelector(".org-titulo")?.value?.trim() || "";
      const idInput = tr.querySelector(".org-id");
      const id = idInput?.value?.trim() || slugId(titulo, `n${i}`);
      if (idInput && !idInput.value.trim()) idInput.value = id;
      const userIds = Array.from(tr.querySelector(".org-users")?.selectedOptions || [])
        .map((opt) => parseInt(opt.value, 10))
        .filter((uid) => Number.isFinite(uid) && uid > 0);
      const nivelRaw = tr.querySelector(".org-nivel")?.value;
      const nivelParsed = nivelRaw === "" || nivelRaw === undefined ? null : parseInt(nivelRaw, 10);
      const nivel = Number.isFinite(nivelParsed) ? Math.max(0, nivelParsed) : null;
      return {
        id,
        titulo,
        subtitulo: tr.dataset.subtitulo || "",
        kind: tr.querySelector(".org-kind")?.value === "external" ? "external" : "internal",
        parent_id: tr.querySelector(".org-parent")?.value?.trim() || null,
        user_ids: userIds,
        user_id: userIds[0] || null,
        orden: parseInt(tr.dataset.orden || String(i), 10),
        nivel,
      };
    });
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

  function childIds(nodeId, nodes) {
    return nodes.filter((n) => n.parent_id === nodeId).map((n) => n.id);
  }

  function syncChildrenFromSelect(tr, nodeId) {
    const selected = Array.from(tr.querySelector(".org-children")?.selectedOptions || []).map((opt) => opt.value);
    const nodes = collectNodesFromTable();
    const levels = nodeLevels(nodes);
    const parentNivel = levels[nodeId] ?? 0;
    qsa("#sgiOrgEditorTable tbody tr").forEach((otherTr) => {
      const otherId = otherTr.querySelector(".org-id")?.value?.trim() || "";
      if (!otherId || otherId === nodeId) return;
      const parentSel = otherTr.querySelector(".org-parent");
      if (!parentSel) return;
      const childNivel = otherTr.querySelector(".org-nivel");
      if (selected.includes(otherId)) {
        parentSel.value = nodeId;
        if (childNivel) childNivel.value = String(parentNivel + 1);
      } else if (parentSel.value === nodeId) {
        parentSel.value = "";
        if (childNivel) childNivel.value = "0";
      }
    });
  }

  function refreshEditorTable() {
    const nodes = collectNodesFromTable();
    const levels = nodeLevels(nodes);
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));

    qsa("#sgiOrgEditorTable tbody tr").forEach((tr) => {
      const nodeId = tr.querySelector(".org-id")?.value?.trim() || "";
      const parentSel = tr.querySelector(".org-parent");
      const childrenSel = tr.querySelector(".org-children");
      const nivelInput = tr.querySelector(".org-nivel");
      const currentParent = parentSel?.value || "";
      const currentChildren = childIds(nodeId, nodes);

      if (parentSel) {
        const selected = currentParent;
        parentSel.innerHTML = `<option value="">— Sin superior —</option>`;
        nodes.forEach((n) => {
          if (n.id === nodeId) return;
          const opt = document.createElement("option");
          opt.value = n.id;
          opt.textContent = n.titulo || n.id;
          if (n.id === selected) opt.selected = true;
          parentSel.appendChild(opt);
        });
      }

      if (childrenSel) {
        const hadFocus = document.activeElement === childrenSel;
        childrenSel.innerHTML = "";
        nodes.forEach((n) => {
          if (n.id === nodeId) return;
          const opt = document.createElement("option");
          opt.value = n.id;
          opt.textContent = n.titulo || n.id;
          if (currentChildren.includes(n.id)) opt.selected = true;
          childrenSel.appendChild(opt);
        });
        if (!childrenSel.options.length) {
          const empty = document.createElement("option");
          empty.value = "";
          empty.textContent = "— Sin puestos —";
          empty.disabled = true;
          childrenSel.appendChild(empty);
        }
        if (hadFocus) childrenSel.focus();
      }

      if (nivelInput && document.activeElement !== nivelInput) {
        const node = byId[nodeId];
        if (node?.nivel !== null && node?.nivel !== undefined) {
          nivelInput.value = String(node.nivel);
        } else {
          nivelInput.value = String(levels[nodeId] ?? 0);
        }
      }

      const parentNode = currentParent ? byId[currentParent] : null;
      tr.title = parentNode ? `Depende de: ${parentNode.titulo || parentNode.id}` : "";
    });

    const chart = qs("#sgiOrgChart");
    if (chart) {
      renderChartFromNodes(nodes, chart, editorRedrawConnectors);
    }
  }

  function buildRow(node, idx) {
    const tr = document.createElement("tr");
    const userIds = Array.isArray(node.user_ids)
      ? node.user_ids.map(String)
      : node.user_id
        ? [String(node.user_id)]
        : [];
    const nodeId = node.id || slugId(node.titulo, `nuevo_${idx}`);
    const nodeKind = nodeKindFromData(node);
    tr.dataset.subtitulo = node.subtitulo || "";
    tr.dataset.orden = String(node.orden ?? idx);
    const nivelVal =
      node.nivel !== null && node.nivel !== undefined && Number.isFinite(node.nivel)
        ? Math.max(0, node.nivel)
        : 0;
    tr.innerHTML = `
      <td>
        <input type="hidden" class="org-id" value="${escHtml(nodeId)}">
        <input type="text" class="form-control form-control-sm org-titulo" value="${escHtml(node.titulo || "")}" placeholder="Ej. Gerente General">
      </td>
      <td>
        <select class="form-select form-select-sm org-kind" aria-label="Tipo de puesto">
          <option value="internal"${nodeKind === "internal" ? " selected" : ""}>Interno</option>
          <option value="external"${nodeKind === "external" ? " selected" : ""}>Servicio externo</option>
        </select>
      </td>
      <td>
        <select class="form-select form-select-sm org-parent">
          <option value="">— Sin superior —</option>
        </select>
      </td>
      <td>
        <select class="form-select form-select-sm org-children" multiple size="3" aria-label="Puestos por debajo">
        </select>
        <div class="form-text">Ctrl + clic para varios</div>
      </td>
      <td>
        <input type="number" class="form-control form-control-sm org-nivel text-center" min="0" step="1" value="${nivelVal}" aria-label="Nivel visual">
        <div class="form-text">0 = arriba</div>
      </td>
      <td>
        <select class="form-select form-select-sm org-users" multiple size="3" aria-label="Usuarios del puesto">
        </select>
        <div class="form-text">Ctrl + clic para varios</div>
      </td>
      <td><button type="button" class="btn btn-sm btn-link text-danger org-del">Quitar</button></td>
    `;

    const parentSel = qs(".org-parent", tr);
    if (node.parent_id) {
      const opt = document.createElement("option");
      opt.value = node.parent_id;
      opt.textContent = node.parent_id;
      opt.selected = true;
      parentSel.appendChild(opt);
    }

    const usersSel = qs(".org-users", tr);
    (editorCfg.usuarios || []).forEach((u) => {
      const opt = document.createElement("option");
      opt.value = String(u.id);
      opt.textContent = `${u.label} (${u.rol})`;
      if (userIds.includes(String(u.id))) opt.selected = true;
      usersSel.appendChild(opt);
    });

    tr.querySelector(".org-titulo")?.addEventListener("input", refreshEditorTable);
    tr.querySelector(".org-kind")?.addEventListener("change", refreshEditorTable);
    tr.querySelector(".org-parent")?.addEventListener("change", () => {
      const parentId = tr.querySelector(".org-parent")?.value?.trim() || "";
      const nivelInput = tr.querySelector(".org-nivel");
      if (nivelInput) {
        const nodes = collectNodesFromTable();
        const levels = nodeLevels(nodes);
        const parentNivel = parentId ? levels[parentId] ?? 0 : -1;
        nivelInput.value = String(parentId ? parentNivel + 1 : 0);
      }
      refreshEditorTable();
    });
    tr.querySelector(".org-children")?.addEventListener("change", () => {
      const currentId = tr.querySelector(".org-id")?.value?.trim() || nodeId;
      syncChildrenFromSelect(tr, currentId);
      refreshEditorTable();
    });
    tr.querySelector(".org-nivel")?.addEventListener("input", refreshEditorTable);
    tr.querySelector(".org-users")?.addEventListener("change", refreshEditorTable);
    tr.querySelector(".org-del")?.addEventListener("click", () => {
      tr.remove();
      refreshEditorTable();
    });
    return tr;
  }

  function collectNodes() {
    return collectNodesFromTable();
  }

  let editorRedrawConnectors = null;

  function initEditor() {
    const tbody = qs("#sgiOrgEditorTable tbody");
    if (!tbody || !editorCfg) return;
    editorRedrawConnectors = initConnectors();
    initZoom(editorRedrawConnectors);
    (editorCfg.nodes || []).forEach((n, i) => tbody.appendChild(buildRow(n, i)));
    refreshEditorTable();
    qs("#btnOrgAddRow")?.addEventListener("click", () => {
      const i = qsa("#sgiOrgEditorTable tbody tr").length;
      tbody.appendChild(buildRow({ id: `nuevo_${i}`, orden: i }, i));
      refreshEditorTable();
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
