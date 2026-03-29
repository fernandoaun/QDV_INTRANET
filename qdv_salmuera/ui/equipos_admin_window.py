from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import List, Optional

from qdv_salmuera.data.db import DB, normalize_tipo_producto


def _categoria_ui(cat: str) -> str:
    return "Materia prima" if cat == "materia_prima" else "Laboratorio"


class EquiposYTiposAdminWindow(tk.Toplevel):
    """Administración de equipos y tipo de producto (Normal / Filtro). Solo administrador."""

    def __init__(self, master: tk.Misc, db: DB) -> None:
        super().__init__(master)
        self.db = db
        try:
            self.transient(master)
        except tk.TclError:
            pass
        self.title("Equipos y tipos de producto")
        self.geometry("820x560")
        self.minsize(720, 480)

        nb = ttk.Notebook(self, padding=8)
        nb.pack(fill="both", expand=True)

        self.tab_equipos = ttk.Frame(nb, padding=8)
        self.tab_tipos = ttk.Frame(nb, padding=8)
        nb.add(self.tab_equipos, text="Equipos")
        nb.add(self.tab_tipos, text="Tipos de producto (filtro)")

        self._build_tab_equipos()
        self._build_tab_tipos()

        ttk.Button(self, text="Cerrar", command=self.destroy, style="QDV.Secondary.TButton").pack(pady=8)

    def _build_tab_equipos(self) -> None:
        f = self.tab_equipos
        ttk.Label(f, text="Gestión de equipos (instalación de filtros).", style="QDV.MutedCard.TLabel").pack(
            anchor="w", pady=(0, 8)
        )

        twrap = ttk.Frame(f)
        twrap.pack(fill="both", expand=True)
        cols = ("id", "nombre", "desc", "activo")
        tree = ttk.Treeview(twrap, columns=cols, show="headings", height=12, selectmode="browse")
        tree.heading("id", text="ID")
        tree.heading("nombre", text="Nombre")
        tree.heading("desc", text="Descripción")
        tree.heading("activo", text="Activo")
        tree.column("id", width=44, anchor="center", stretch=False)
        tree.column("nombre", width=200, anchor="w")
        tree.column("desc", width=360, anchor="w")
        tree.column("activo", width=70, anchor="center", stretch=False)
        vsb = ttk.Scrollbar(twrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        form = ttk.LabelFrame(f, text="Editar / nuevo equipo", padding=8)
        form.pack(fill="x", pady=(10, 0))

        ttk.Label(form, text="Nombre:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        var_nombre = tk.StringVar()
        ttk.Entry(form, textvariable=var_nombre, width=40).grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(form, text="Descripción:").grid(row=1, column=0, sticky="nw", padx=(0, 8), pady=4)
        var_desc = tk.StringVar()
        ttk.Entry(form, textvariable=var_desc, width=40).grid(row=1, column=1, sticky="w", pady=4)

        var_activo = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="Equipo activo", variable=var_activo).grid(row=2, column=1, sticky="w", pady=4)

        var_sel_id: List[Optional[int]] = [None]

        def load_equipos() -> None:
            for iid in tree.get_children():
                tree.delete(iid)
            for r in self.db.get_equipos_todos():
                tree.insert(
                    "",
                    "end",
                    iid=str(r["id"]),
                    values=(r["id"], r["nombre_equipo"], r["descripcion"], "Sí" if r["activo"] else "No"),
                )

        def on_select(_e=None) -> None:
            sel = tree.selection()
            if not sel:
                var_sel_id[0] = None
                return
            var_sel_id[0] = int(sel[0])
            r = next((x for x in self.db.get_equipos_todos() if x["id"] == var_sel_id[0]), None)
            if r:
                var_nombre.set(r["nombre_equipo"])
                var_desc.set(r["descripcion"])
                var_activo.set(bool(r["activo"]))

        def clear_form() -> None:
            var_sel_id[0] = None
            tree.selection_remove(tree.selection())
            var_nombre.set("")
            var_desc.set("")
            var_activo.set(True)

        def save_equipo() -> None:
            nombre = var_nombre.get().strip()
            if not nombre:
                messagebox.showerror("Validación", "Ingrese el nombre del equipo.", parent=self)
                return
            desc = var_desc.get().strip()
            try:
                if var_sel_id[0] is None:
                    self.db.create_equipo(nombre, desc)
                    messagebox.showinfo("Equipos", "Equipo creado.", parent=self)
                else:
                    self.db.update_equipo(var_sel_id[0], nombre, desc, 1 if var_activo.get() else 0)
                    messagebox.showinfo("Equipos", "Equipo actualizado.", parent=self)
            except Exception as exc:
                messagebox.showerror("Error", str(exc), parent=self)
                return
            load_equipos()
            clear_form()

        tree.bind("<<TreeviewSelect>>", on_select)

        bf = ttk.Frame(form)
        bf.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(bf, text="Guardar", command=save_equipo, style="QDV.NeuModule.TButton").pack(side="left")
        ttk.Button(bf, text="Nuevo (limpiar)", command=clear_form, style="QDV.Secondary.TButton").pack(
            side="left", padx=8
        )
        ttk.Button(bf, text="Actualizar lista", command=load_equipos, style="QDV.Secondary.TButton").pack(side="left")

        load_equipos()

    def _build_tab_tipos(self) -> None:
        f = self.tab_tipos
        ttk.Label(
            f,
            text="Marque qué productos son filtros (el consumo exigirá indicar equipo).",
            style="QDV.MutedCard.TLabel",
        ).pack(anchor="w", pady=(0, 8))

        twrap = ttk.Frame(f)
        twrap.pack(fill="both", expand=True)
        cols = ("id", "cat", "nombre", "tipo")
        tree = ttk.Treeview(twrap, columns=cols, show="headings", height=14, selectmode="browse")
        tree.heading("id", text="ID")
        tree.heading("cat", text="Categoría")
        tree.heading("nombre", text="Producto")
        tree.heading("tipo", text="Tipo")
        tree.column("id", width=44, anchor="center", stretch=False)
        tree.column("cat", width=120, anchor="w")
        tree.column("nombre", width=280, anchor="w")
        tree.column("tipo", width=100, anchor="center", stretch=False)
        vsb = ttk.Scrollbar(twrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(10, 0))

        ttk.Label(bar, text="Tipo:").pack(side="left")
        var_tipo = tk.StringVar(value="Normal")
        cb = ttk.Combobox(bar, textvariable=var_tipo, width=14, state="readonly", values=("Normal", "Filtro"))
        cb.pack(side="left", padx=8)

        def load_cat() -> None:
            for iid in tree.get_children():
                tree.delete(iid)
            for r in self.db.fetch_catalogo_productos_admin():
                if not r["activo"]:
                    continue
                tree.insert(
                    "",
                    "end",
                    iid=str(r["id"]),
                    values=(r["id"], _categoria_ui(r["categoria"]), r["nombre_producto"], r["tipo_producto"]),
                )

        def on_sel(_e=None) -> None:
            sel = tree.selection()
            if not sel:
                return
            r = next((x for x in self.db.fetch_catalogo_productos_admin() if x["id"] == int(sel[0])), None)
            if r:
                var_tipo.set(normalize_tipo_producto(r.get("tipo_producto")))

        def apply_tipo() -> None:
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Catálogo", "Seleccione un producto.", parent=self)
                return
            pid = int(sel[0])
            try:
                self.db.update_producto_tipo_catalogo(pid, var_tipo.get())
                messagebox.showinfo("Catálogo", "Tipo actualizado.", parent=self)
            except Exception as exc:
                messagebox.showerror("Error", str(exc), parent=self)
                return
            load_cat()

        tree.bind("<<TreeviewSelect>>", on_sel)
        ttk.Button(bar, text="Aplicar tipo al seleccionado", command=apply_tipo, style="QDV.NeuModule.TButton").pack(
            side="left", padx=12
        )
        ttk.Button(bar, text="Actualizar lista", command=load_cat, style="QDV.Secondary.TButton").pack(side="left")

        load_cat()
