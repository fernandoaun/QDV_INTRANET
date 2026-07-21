/**
 * Formulario dinámico de carga de registro SGC.
 */
(function () {
  "use strict";
  const cfg = window.SGI_RECORD_ENTRY || {};
  const root = document.getElementById("recordDynamicForm");
  if (!root) return;

  const schema = cfg.schema || {};
  const fields = Array.isArray(schema.fields) ? schema.fields.slice() : [];
  fields.sort((a, b) => (a.order || 0) - (b.order || 0));
  let data = cfg.data && typeof cfg.data === "object" ? { ...cfg.data } : {};
  const soloLectura = !!cfg.soloLectura;

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      Object.entries(attrs).forEach(([k, v]) => {
        if (v == null || v === false) return;
        if (k === "className") node.className = v;
        else if (k === "text") node.textContent = v;
        else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2).toLowerCase(), v);
        else node.setAttribute(k, v === true ? "" : String(v));
      });
    }
    (children || []).forEach((c) => {
      if (c == null) return;
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
  }

  function inputFor(field) {
    const name = field.name;
    const val = data[name];
    const common = {
      className: "form-control",
      id: `fld_${name}`,
      name,
      disabled: soloLectura || field.mode === "readonly" || field.type === "calculated",
    };
    const type = field.type || "text";

    if (type === "textarea" || type === "observations") {
      const ta = el("textarea", { ...common, rows: "3" });
      ta.value = val != null ? String(val) : "";
      ta.addEventListener("input", () => {
        data[name] = ta.value;
      });
      return ta;
    }
    if (type === "yes_no") {
      const sel = el("select", { ...common, className: "form-select" });
      ["", "Sí", "No"].forEach((opt) => {
        const o = el("option", { value: opt, text: opt || "—" });
        if (String(val || "") === opt) o.selected = true;
        sel.appendChild(o);
      });
      sel.addEventListener("change", () => {
        data[name] = sel.value;
      });
      return sel;
    }
    if (type === "checkbox") {
      const wrap = el("div", { className: "form-check" });
      const cb = el("input", {
        type: "checkbox",
        className: "form-check-input",
        id: common.id,
        disabled: common.disabled,
      });
      cb.checked = !!val;
      cb.addEventListener("change", () => {
        data[name] = cb.checked;
      });
      wrap.appendChild(cb);
      wrap.appendChild(el("label", { className: "form-check-label", for: common.id, text: field.label || name }));
      return wrap;
    }
    if (type === "select" || type === "dropdown") {
      const sel = el("select", { ...common, className: "form-select" });
      sel.appendChild(el("option", { value: "", text: "—" }));
      (field.options || []).forEach((opt) => {
        const o = el("option", { value: String(opt), text: String(opt) });
        if (String(val || "") === String(opt)) o.selected = true;
        sel.appendChild(o);
      });
      sel.addEventListener("change", () => {
        data[name] = sel.value;
      });
      return sel;
    }
    if (type === "editable_table") {
      return renderTable(field);
    }

    let inputType = "text";
    if (type === "date") inputType = "date";
    else if (type === "datetime") inputType = "datetime-local";
    else if (type === "time") inputType = "time";
    else if (type === "email") inputType = "email";
    else if (type === "integer" || type === "decimal" || type === "percent" || type === "currency") inputType = "number";

    const inp = el("input", { ...common, type: inputType, placeholder: field.placeholder || "" });
    if (val != null) inp.value = String(val);
    inp.addEventListener("input", () => {
      data[name] = inp.value;
    });
    return inp;
  }

  function renderTable(field) {
    const cols = field.columns || [];
    let rows = Array.isArray(data[field.name]) ? data[field.name] : [];
    if (!rows.length) rows = [{}];
    data[field.name] = rows;

    const wrap = el("div", { className: "table-responsive" });
    const table = el("table", { className: "table table-sm align-middle" });
    const thead = el("thead");
    const hr = el("tr");
    cols.forEach((c) => hr.appendChild(el("th", { text: c.label || c.key })));
    if (!soloLectura) hr.appendChild(el("th", { text: "" }));
    thead.appendChild(hr);
    table.appendChild(thead);
    const tbody = el("tbody");

    function sync() {
      data[field.name] = rows;
    }

    function draw() {
      tbody.innerHTML = "";
      rows.forEach((row, ri) => {
        const tr = el("tr");
        cols.forEach((c) => {
          const td = el("td");
          const inp = el("input", {
            type: "text",
            className: "form-control form-control-sm",
            disabled: soloLectura,
            value: row[c.key] != null ? String(row[c.key]) : "",
          });
          inp.addEventListener("input", () => {
            rows[ri][c.key] = inp.value;
            sync();
          });
          td.appendChild(inp);
          tr.appendChild(td);
        });
        if (!soloLectura) {
          const td = el("td");
          const btn = el("button", {
            type: "button",
            className: "btn btn-sm btn-link text-danger",
            text: "×",
            onclick: () => {
              rows.splice(ri, 1);
              if (!rows.length) rows.push({});
              sync();
              draw();
            },
          });
          td.appendChild(btn);
          tr.appendChild(td);
        }
        tbody.appendChild(tr);
      });
    }
    draw();
    table.appendChild(tbody);
    wrap.appendChild(table);
    if (!soloLectura) {
      wrap.appendChild(
        el("button", {
          type: "button",
          className: "btn btn-sm btn-outline-secondary",
          text: "Agregar fila",
          onclick: () => {
            rows.push({});
            sync();
            draw();
          },
        })
      );
    }
    return wrap;
  }

  function render() {
    root.innerHTML = "";
    const bySection = {};
    fields.forEach((f) => {
      const sec = f.section || "Datos generales";
      if (!bySection[sec]) bySection[sec] = [];
      bySection[sec].push(f);
    });
    Object.keys(bySection).forEach((sec) => {
      root.appendChild(el("h2", { className: "h6 mt-3 mb-2", text: sec }));
      bySection[sec].forEach((f) => {
        if (f.type === "checkbox") {
          root.appendChild(el("div", { className: "mb-3" }, [inputFor(f)]));
          return;
        }
        const group = el("div", { className: "mb-3" });
        group.appendChild(
          el("label", {
            className: "form-label",
            for: `fld_${f.name}`,
            text: (f.label || f.name) + (f.required ? " *" : ""),
          })
        );
        group.appendChild(inputFor(f));
        root.appendChild(group);
      });
    });
  }

  function flash(kind, msg) {
    const box = document.getElementById("recordFormAlert");
    if (!box) return;
    box.className = `alert alert-${kind}`;
    box.textContent = msg;
    box.classList.remove("d-none");
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

  document.getElementById("btnSaveDraft")?.addEventListener("click", () => {
    save({}).then((res) => flash(res.ok ? "success" : "danger", res.message || (res.ok ? "Guardado" : "Error")));
  });
  document.getElementById("btnSubmit")?.addEventListener("click", () => {
    save({ submit: true }).then((res) => {
      flash(res.ok ? "success" : "danger", res.message || "");
      if (res.ok) setTimeout(() => location.reload(), 600);
    });
  });
  document.getElementById("btnClose")?.addEventListener("click", () => {
    if (!confirm("¿Cerrar esta carga? No podrá editarse después.")) return;
    save({ close: true }).then((res) => {
      flash(res.ok ? "success" : "danger", res.message || "");
      if (res.ok) setTimeout(() => location.reload(), 600);
    });
  });

  render();
})();
