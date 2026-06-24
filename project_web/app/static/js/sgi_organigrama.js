(function () {
  "use strict";

  const editorCfg = window.SGI_ORG_EDITOR;
  const MIN_ZOOM = 0.45;
  const MAX_ZOOM = 1.6;
  const ZOOM_STEP = 0.1;

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

  const CONNECTOR_STROKE = "#1a5c22";
  const CONNECTOR_WIDTH = 2.5;

  function nodeBox(btn, container) {
    const c = container.getBoundingClientRect();
    const r = btn.getBoundingClientRect();
    return {
      top: r.top - c.top,
      bottom: r.bottom - c.top,
      cx: r.left - c.left + r.width / 2,
    };
  }

  function svgLine(svg, x1, y1, x2, y2) {
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", String(Math.round(x1 * 10) / 10));
    line.setAttribute("y1", String(Math.round(y1 * 10) / 10));
    line.setAttribute("x2", String(Math.round(x2 * 10) / 10));
    line.setAttribute("y2", String(Math.round(y2 * 10) / 10));
    line.setAttribute("stroke", CONNECTOR_STROKE);
    line.setAttribute("stroke-width", String(CONNECTOR_WIDTH));
    line.setAttribute("stroke-linecap", "round");
    svg.appendChild(line);
  }

  function drawConnectors() {
    const wrap = qs("#sgiOrgChart");
    if (!wrap) return;
    let svg = qs("#sgiOrgConnectors", wrap);
    if (!svg) {
      svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.id = "sgiOrgConnectors";
      svg.classList.add("sgi-org-connectors");
      svg.setAttribute("aria-hidden", "true");
      wrap.insertBefore(svg, wrap.firstChild);
    }

    const w = Math.max(wrap.scrollWidth, wrap.offsetWidth);
    const h = Math.max(wrap.scrollHeight, wrap.offsetHeight);
    svg.setAttribute("width", String(w));
    svg.setAttribute("height", String(h));
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svg.innerHTML = "";

    qsa(".sgi-org-tree-item", wrap).forEach((item) => {
      const parentBtn = qs(":scope > .sgi-org-tree-node-wrap > .sgi-org-node", item);
      const childUl = qs(":scope > .sgi-org-tree-children", item);
      if (!parentBtn || !childUl) return;

      const childBtns = qsa(
        ":scope > .sgi-org-tree-item > .sgi-org-tree-node-wrap > .sgi-org-node",
        childUl
      );
      if (!childBtns.length) return;

      const parent = nodeBox(parentBtn, wrap);
      const children = childBtns.map((btn) => nodeBox(btn, wrap));

      if (children.length === 1) {
        svgLine(svg, parent.cx, parent.bottom, children[0].cx, children[0].top);
        return;
      }

      const gap = children[0].top - parent.bottom;
      const junctionY = parent.bottom + Math.max(14, gap * 0.5);
      svgLine(svg, parent.cx, parent.bottom, parent.cx, junctionY);
      const xs = children.map((c) => c.cx);
      svgLine(svg, Math.min(...xs), junctionY, Math.max(...xs), junctionY);
      children.forEach((c) => svgLine(svg, c.cx, junctionY, c.cx, c.top));
    });
  }

  function initConnectors() {
    function scheduleRedraw() {
      requestAnimationFrame(drawConnectors);
    }
    window.addEventListener("resize", scheduleRedraw);
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(scheduleRedraw).catch(() => scheduleRedraw());
    }
    scheduleRedraw();
    setTimeout(scheduleRedraw, 150);
    setTimeout(scheduleRedraw, 500);
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
    const zoom = initZoom(redrawConnectors);

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
        const subtitulo = btn.querySelector(".sgi-org-node-sub")?.textContent?.trim() || "";
        renderDetail(usuario, btn.querySelector(".sgi-org-node-title")?.textContent || "", subtitulo);
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
