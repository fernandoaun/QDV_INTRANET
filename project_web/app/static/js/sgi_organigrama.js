(function () {
  "use strict";

  const editorCfg = window.SGI_ORG_EDITOR;

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

  function renderDetail(usuario, titulo) {
    const box = qs("#sgiOrgDetail");
    if (!box) return;
    if (!usuario) {
      box.innerHTML = `<p class="mb-1"><strong>${titulo || "Puesto"}</strong></p><p class="text-muted mb-0">Sin usuario asignado en la intranet.</p>`;
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
      .map(([k, v]) => `<dt class="col-sm-4">${k}</dt><dd class="col-sm-8">${v}</dd>`)
      .join("");
    box.innerHTML = `<p class="fw-semibold mb-2">${titulo || ""}</p><dl class="row mb-0 small">${rows}</dl>`;
  }

  function initView() {
    const chart = qs("#sgiOrgChart");
    if (!chart) return;
    qsa(".sgi-org-node", chart).forEach((btn) => {
      btn.addEventListener("click", () => {
        qsa(".sgi-org-node", chart).forEach((b) => b.classList.remove("is-active"));
        btn.classList.add("is-active");
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
        renderDetail(usuario, btn.querySelector(".sgi-org-node-title")?.textContent || "");
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
