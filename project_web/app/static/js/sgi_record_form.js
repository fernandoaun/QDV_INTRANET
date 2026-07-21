/**
 * Formulario de carga: conserva layout documental del Word/Excel.
 */
(function () {
  "use strict";
  const cfg = window.SGI_RECORD_ENTRY || {};
  const root = document.getElementById("recordDynamicForm");
  if (!root) return;

  const schema = cfg.schema || {};
  const fields = Array.isArray(schema.fields) ? schema.fields.slice() : [];
  fields.sort((a, b) => (a.order || 0) - (b.order || 0));
  const fieldByName = {};
  fields.forEach((f) => {
    fieldByName[f.name] = f;
  });
  let data = cfg.data && typeof cfg.data === "object" ? { ...cfg.data } : {};
  const soloLectura = !!cfg.soloLectura;
  const layoutHtml = schema.layoutHtml || "";
  const useLayout = !!(layoutHtml && (schema.layoutMode || "document") === "document");

  function flash(kind, msg) {
    const box = document.getElementById("recordFormAlert");
    if (!box) return;
    box.className = `alert alert-${kind}`;
    box.textContent = msg;
    box.classList.remove("d-none");
  }

  function bindControl(el) {
    const name = el.getAttribute("data-sgi-field");
    if (!name) return;
    if (soloLectura) {
      el.disabled = true;
      el.readOnly = true;
    }
    const val = data[name];
    if (el.tagName === "SELECT" || el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
      if (el.type === "checkbox") el.checked = !!val;
      else if (val != null) el.value = String(val);
    }
    const handler = () => {
      if (el.type === "checkbox") data[name] = el.checked;
      else data[name] = el.value;
    };
    el.addEventListener("input", handler);
    el.addEventListener("change", handler);
  }

  function renderTableBody(name) {
    const field = fieldByName[name];
    const cols = (field && field.columns) || [];
    let rows = Array.isArray(data[name]) ? data[name] : [];
    if (!rows.length) rows = [{}];
    data[name] = rows;
    const tbody = root.querySelector(`[data-sgi-table-body="${name.replace(/"/g, "")}"]`);
    if (!tbody) return;
    tbody.innerHTML = "";
    rows.forEach((row, ri) => {
      const tr = document.createElement("tr");
      cols.forEach((c) => {
        const td = document.createElement("td");
        const inp = document.createElement("input");
        inp.type = "text";
        inp.className = "sgi-rec-inline";
        inp.value = row[c.key] != null ? String(row[c.key]) : "";
        inp.disabled = soloLectura;
        inp.addEventListener("input", () => {
          rows[ri][c.key] = inp.value;
          data[name] = rows;
        });
        td.appendChild(inp);
        tr.appendChild(td);
      });
      if (!soloLectura) {
        const td = document.createElement("td");
        td.className = "sgi-proc-no-print";
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn btn-sm btn-link text-danger";
        btn.textContent = "×";
        btn.addEventListener("click", () => {
          rows.splice(ri, 1);
          if (!rows.length) rows.push({});
          data[name] = rows;
          renderTableBody(name);
        });
        td.appendChild(btn);
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    });
  }

  function wireTables() {
    root.querySelectorAll("[data-sgi-table-body]").forEach((tb) => {
      renderTableBody(tb.getAttribute("data-sgi-table-body"));
    });
    root.querySelectorAll("[data-sgi-table-add]").forEach((btn) => {
      if (soloLectura) {
        btn.remove();
        return;
      }
      btn.addEventListener("click", () => {
        const name = btn.getAttribute("data-sgi-table-add");
        if (!Array.isArray(data[name])) data[name] = [];
        data[name].push({});
        renderTableBody(name);
      });
    });
  }

  function renderFallbackFields() {
    const bySection = {};
    fields.forEach((f) => {
      const sec = f.section || "Datos generales";
      if (!bySection[sec]) bySection[sec] = [];
      bySection[sec].push(f);
    });
    let html = "";
    Object.keys(bySection).forEach((sec) => {
      html += `<h2 class="sgi-rec-sheet-title">${sec}</h2>`;
      html += `<table class="sgi-rec-doc-table"><tbody>`;
      bySection[sec].forEach((f) => {
        if (f.type === "editable_table") {
          const cols = f.columns || [];
          const heads = cols.map((c) => `<th>${c.label || c.key}</th>`).join("");
          html += `</tbody></table>
            <div class="sgi-rec-table-block" data-sgi-table="${f.name}">
              <p><strong>${f.label || f.name}</strong></p>
              <table class="sgi-rec-doc-table"><thead><tr>${heads}</tr></thead>
              <tbody data-sgi-table-body="${f.name}"></tbody></table>
              ${soloLectura ? "" : `<button type="button" class="sgi-rec-add-row" data-sgi-table-add="${f.name}">+ Fila</button>`}
            </div><table class="sgi-rec-doc-table"><tbody>`;
          return;
        }
        html += `<tr><td class="sgi-rec-label">${f.label || f.name}${f.required ? " *" : ""}</td><td>`;
        if (f.type === "textarea" || f.type === "observations") {
          html += `<textarea class="sgi-rec-inline" data-sgi-field="${f.name}" rows="3"></textarea>`;
        } else if (f.type === "yes_no") {
          html += `<select class="sgi-rec-inline" data-sgi-field="${f.name}"><option value="">—</option><option>Sí</option><option>No</option></select>`;
        } else {
          const t = f.type === "date" ? "date" : "text";
          html += `<input type="${t}" class="sgi-rec-inline" data-sgi-field="${f.name}" />`;
        }
        html += `</td></tr>`;
      });
      html += `</tbody></table>`;
    });
    root.innerHTML = html || "<p>Sin campos configurados.</p>";
  }

  function render() {
    if (useLayout) {
      root.innerHTML = layoutHtml;
    } else {
      renderFallbackFields();
    }
    root.querySelectorAll("[data-sgi-field]").forEach(bindControl);
    wireTables();
  }

  function save(opts) {
    return fetch(cfg.saveUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": cfg.csrf || "",
      },
      credentials: "same-origin",
      body: JSON.stringify({ data, submit: !!opts.submit, close: !!opts.close }),
    }).then((r) => r.json());
  }

  document.getElementById("btnSave")?.addEventListener("click", () => {
    save({}).then((res) => flash(res.ok ? "success" : "danger", res.message || (res.ok ? "Guardado" : "Error")));
  });

  render();
})();
