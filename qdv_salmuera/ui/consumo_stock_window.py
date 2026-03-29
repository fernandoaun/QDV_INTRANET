from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import messagebox, simpledialog, ttk
from typing import Dict, List, Optional

from qdv_salmuera.auth.session import UserSession
from qdv_salmuera.data.db import DB
from qdv_salmuera.ui.equipos_admin_window import EquiposYTiposAdminWindow


VALID_CATEGORIES = ("materia_prima", "laboratorio")


def _refocus_toplevel(widget: tk.Misc) -> None:
    """Tras un diálogo modal, vuelve a poner la ventana de trabajo al frente (evita sensación de 'cierre' en Windows)."""
    w = widget.winfo_toplevel()

    def _do() -> None:
        try:
            w.lift()
            w.focus_set()
        except tk.TclError:
            pass

    w.after_idle(_do)


def _msg_info(parent: tk.Misc, title: str, message: str) -> None:
    messagebox.showinfo(title, message, parent=parent)
    _refocus_toplevel(parent)


def _msg_error(parent: tk.Misc, title: str, message: str) -> None:
    messagebox.showerror(title, message, parent=parent)
    _refocus_toplevel(parent)


def _msg_yesno(parent: tk.Misc, title: str, message: str) -> bool:
    r = messagebox.askyesno(title, message, parent=parent)
    _refocus_toplevel(parent)
    return bool(r)


def _categoria_label(cat: str) -> str:
    return "Materia prima" if cat == "materia_prima" else "Laboratorio"


def _parse_vencimiento(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    try:
        return datetime.strptime(text, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Vencimiento inválido. Use formato dd/mm/aaaa.") from exc


def can_user_create_products(session: UserSession) -> bool:
    return bool(session.is_admin)


class RealizarConsumoWindow(tk.Toplevel):
    def __init__(self, master, db: DB, session: UserSession):
        super().__init__(master)
        self.db = db
        self.session = session
        try:
            self.transient(master)
        except tk.TclError:
            pass
        self.title("Producción - REALIZAR CONSUMO")
        self.geometry("1050x730")
        self.minsize(920, 620)

        if self.session.is_admin:
            topbar = ttk.Frame(self, padding=(12, 8, 12, 0))
            topbar.pack(fill="x")
            ttk.Button(
                topbar,
                text="Equipos y tipos de producto",
                command=lambda: EquiposYTiposAdminWindow(self, self.db),
                style="QDV.Secondary.TButton",
            ).pack(side="left")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=12, pady=12)

        # Ingresos: solo administrador (operadores solo ven Consumos)
        self.frm_mp: Optional[ttk.Frame] = None
        self.frm_lab: Optional[ttk.Frame] = None
        if self.session.is_admin:
            self.frm_mp = ttk.Frame(self.nb, padding=12)
            self.frm_lab = ttk.Frame(self.nb, padding=12)
            self.nb.add(self.frm_mp, text="Ingreso de materia prima")
            self.nb.add(self.frm_lab, text="Ingreso de productos de laboratorio")

        self.frm_consumos = ttk.Frame(self.nb, padding=12)
        self.nb.add(self.frm_consumos, text="Consumos")

        self.build_realizar_consumo_view()

    def build_realizar_consumo_view(self) -> None:
        if self.session.is_admin and self.frm_mp is not None and self.frm_lab is not None:
            self.build_ingreso_materia_prima_view()
            self.build_ingreso_laboratorio_view()
        self.build_consumos_view()

    def build_ingreso_materia_prima_view(self) -> None:
        if self.frm_mp is None:
            return
        self._build_ingreso_view(self.frm_mp, "materia_prima")

    def build_ingreso_laboratorio_view(self) -> None:
        if self.frm_lab is None:
            return
        self._build_ingreso_view(self.frm_lab, "laboratorio")

    def build_consumos_view(self) -> None:
        self._build_consumos_view(self.frm_consumos)

    def _build_ingreso_view(self, parent: ttk.Frame, categoria: str) -> None:
        title = ttk.Label(parent, text=f"Ingreso de {_categoria_label(categoria)}", style="QDV.HeaderSub.TLabel")
        title.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))

        ttk.Label(parent, text="Producto").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Label(parent, text="Marca").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Label(parent, text="Vencimiento (dd/mm/aaaa)").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Label(parent, text="Lote").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Label(parent, text="Cantidad").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=4)

        var_producto = tk.StringVar()
        var_marca = tk.StringVar()
        var_venc = tk.StringVar()
        var_lote = tk.StringVar()
        var_cantidad = tk.StringVar()

        cb_producto = ttk.Combobox(parent, textvariable=var_producto, width=42, state="readonly")
        cb_producto.grid(row=1, column=1, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=var_marca, width=44).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=var_venc, width=44).grid(row=3, column=1, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=var_lote, width=44).grid(row=4, column=1, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=var_cantidad, width=44).grid(row=5, column=1, sticky="w", pady=4)

        def refresh_productos() -> None:
            productos = self.db.get_productos_por_categoria(categoria)
            cb_producto["values"] = productos
            if productos and var_producto.get() not in productos:
                var_producto.set(productos[0])

        def on_add_producto() -> None:
            if not can_user_create_products(self.session):
                _msg_error(self, "Permisos", "Solo el administrador puede crear productos.")
                return
            nuevo = simpledialog.askstring("Nuevo producto", "Nombre del nuevo producto:", parent=self)
            _refocus_toplevel(self)
            if not nuevo:
                return
            try:
                tipo = (
                    "Filtro"
                    if messagebox.askyesno(
                        "Tipo de producto",
                        "¿Es un producto tipo filtro?\n(Si es filtro, al consumir se exigirá indicar equipo.)",
                        parent=self,
                    )
                    else "Normal"
                )
                _refocus_toplevel(self)
                self.db.create_new_product(categoria, nuevo, tipo_producto=tipo)
                refresh_productos()
                var_producto.set(nuevo.strip())
                _msg_info(self, "Catálogo", "Producto agregado correctamente.")
            except Exception as exc:
                _msg_error(self, "Error", f"No se pudo crear el producto:\n{exc}")

        def on_guardar() -> None:
            try:
                producto = var_producto.get().strip()
                marca = var_marca.get().strip()
                lote = var_lote.get().strip()
                if not producto:
                    raise ValueError("Seleccione un producto.")
                if not marca:
                    raise ValueError("La marca es obligatoria.")
                if not lote:
                    raise ValueError("El lote es obligatorio.")
                cantidad = float(var_cantidad.get().strip())
                if cantidad <= 0:
                    raise ValueError("La cantidad debe ser mayor a cero.")
                vencimiento_iso = _parse_vencimiento(var_venc.get())
                if not vencimiento_iso:
                    raise ValueError("El vencimiento es obligatorio.")
                self.db.save_ingreso_stock(
                    categoria=categoria,
                    producto=producto,
                    marca=marca,
                    vencimiento=vencimiento_iso,
                    lote=lote,
                    cantidad=cantidad,
                    operador=self.session.username,
                )
            except ValueError as exc:
                _msg_error(self, "Validación", str(exc))
                return
            except Exception as exc:
                _msg_error(self, "Error", f"No se pudo guardar el ingreso:\n{exc}")
                return

            var_marca.set("")
            var_venc.set("")
            var_lote.set("")
            var_cantidad.set("")
            _msg_info(self, "Éxito", "Ingreso registrado correctamente.")

        btns = ttk.Frame(parent)
        btns.grid(row=6, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Button(btns, text="Actualizar productos", command=refresh_productos, style="QDV.Secondary.TButton").pack(side="left")
        ttk.Button(btns, text="Agregar producto", command=on_add_producto, style="QDV.Secondary.TButton").pack(side="left", padx=8)
        ttk.Button(btns, text="Guardar ingreso", command=on_guardar, style="QDV.NeuModule.TButton").pack(side="left")

        if not can_user_create_products(self.session):
            ttk.Label(parent, text="Solo administrador puede crear nuevos productos.", style="QDV.MutedCard.TLabel").grid(
                row=7, column=0, columnspan=4, sticky="w", pady=(10, 0)
            )

        refresh_productos()

    def _build_consumos_view(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Registro de consumos", style="QDV.HeaderSub.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 10)
        )
        ttk.Label(parent, text="Categoría").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Label(parent, text="Producto").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Label(parent, text="Marca").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)
        frm_equipo = ttk.Frame(parent)
        ttk.Label(frm_equipo, text="Equipo").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        var_categoria = tk.StringVar(value="Materia prima")
        var_producto = tk.StringVar()
        var_marca = tk.StringVar()
        var_equipo_nom = tk.StringVar()
        var_cantidad = tk.StringVar()
        var_stock = tk.StringVar(value="Stock disponible: -")
        var_preview = tk.StringVar(value="Stock actual: - | Consumirá: - | Stock restante: -")

        cb_categoria = ttk.Combobox(parent, width=40, state="readonly", textvariable=var_categoria, values=("Materia prima", "Laboratorio"))
        cb_producto = ttk.Combobox(parent, width=40, state="readonly", textvariable=var_producto)
        cb_marca = ttk.Combobox(parent, width=40, state="readonly", textvariable=var_marca)
        cb_equipo = ttk.Combobox(frm_equipo, width=40, state="readonly", textvariable=var_equipo_nom)
        cb_equipo.grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(parent, text="Cantidad a consumir").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=4)
        en_cantidad = ttk.Entry(parent, width=42, textvariable=var_cantidad)

        cb_categoria.grid(row=1, column=1, sticky="w", pady=4)
        cb_producto.grid(row=2, column=1, sticky="w", pady=4)
        cb_marca.grid(row=3, column=1, sticky="w", pady=4)
        en_cantidad.grid(row=5, column=1, sticky="w", pady=4)

        equipo_name_to_id: Dict[str, int] = {}

        def get_categoria_key() -> str:
            return "materia_prima" if var_categoria.get() == "Materia prima" else "laboratorio"

        def refresh_equipos_combo() -> None:
            nonlocal equipo_name_to_id
            eqs = self.db.get_equipos_activos()
            equipo_name_to_id = {e["nombre_equipo"]: e["id"] for e in eqs}
            names = sorted(equipo_name_to_id.keys())
            cb_equipo["values"] = names
            cur = var_equipo_nom.get().strip()
            if cur and cur in equipo_name_to_id:
                return
            if names:
                var_equipo_nom.set(names[0])
            else:
                var_equipo_nom.set("")

        def sync_equipo_row() -> None:
            categoria = get_categoria_key()
            producto = var_producto.get().strip()
            if self.db.is_filter_product_by_categoria_nombre(categoria, producto):
                frm_equipo.grid(row=4, column=0, columnspan=2, sticky="w", pady=2)
                refresh_equipos_combo()
            else:
                frm_equipo.grid_remove()
                var_equipo_nom.set("")

        def refresh_productos() -> None:
            categoria = get_categoria_key()
            productos = self.db.get_productos_por_categoria(categoria)
            cb_producto["values"] = productos
            var_producto.set(productos[0] if productos else "")
            refresh_marcas()

        def refresh_marcas() -> None:
            categoria = get_categoria_key()
            producto = var_producto.get().strip()
            marcas: List[str] = self.db.get_marcas_por_producto(categoria, producto) if producto else []
            cb_marca["values"] = marcas
            var_marca.set(marcas[0] if marcas else "")
            sync_equipo_row()
            refresh_stock_preview()

        def refresh_stock_preview() -> None:
            categoria = get_categoria_key()
            producto = var_producto.get().strip()
            marca = var_marca.get().strip()
            if not (producto and marca):
                var_stock.set("Stock disponible: -")
                var_preview.set("Stock actual: - | Consumirá: - | Stock restante: -")
                return
            actual = self.db.get_stock_actual(categoria, producto, marca)
            var_stock.set(f"Stock disponible: {actual:.2f}")
            try:
                consumir = float(var_cantidad.get().strip() or "0")
            except ValueError:
                consumir = 0.0
            restante = actual - consumir
            var_preview.set(f"Stock actual: {actual:.2f} | Consumirá: {consumir:.2f} | Stock restante: {restante:.2f}")

        def on_consumir() -> None:
            categoria = get_categoria_key()
            producto = var_producto.get().strip()
            marca = var_marca.get().strip()
            if not producto:
                _msg_error(self, "Validación", "Seleccione un producto.")
                return
            if not marca:
                _msg_error(self, "Validación", "Seleccione una marca.")
                return
            try:
                cantidad = float(var_cantidad.get().strip())
            except ValueError:
                _msg_error(self, "Validación", "La cantidad debe ser numérica.")
                return
            if cantidad <= 0:
                _msg_error(self, "Validación", "La cantidad debe ser mayor a cero.")
                return

            es_filtro = self.db.is_filter_product_by_categoria_nombre(categoria, producto)
            equipo_id: Optional[int] = None
            if es_filtro:
                if not equipo_name_to_id:
                    _msg_error(
                        self,
                        "Equipos",
                        "No hay equipos activos. Solicite a un administrador que dé de alta el equipo.",
                    )
                    return
                nom_eq = var_equipo_nom.get().strip()
                equipo_id = equipo_name_to_id.get(nom_eq)
                if equipo_id is None:
                    _msg_error(
                        self,
                        "Validación",
                        "Debe seleccionar el equipo donde se instalará el filtro.",
                    )
                    return

            actual = self.db.get_stock_actual(categoria, producto, marca)
            if actual <= 0:
                _msg_error(self, "Stock", "No hay stock disponible para consumir.")
                return
            if cantidad > actual:
                _msg_error(self, "Stock", f"No puede consumir más de lo disponible ({actual:.2f}).")
                return
            restante = actual - cantidad

            linea_equipo = ""
            if es_filtro:
                linea_equipo = f"- Equipo: {var_equipo_nom.get().strip()}\n"

            ok = _msg_yesno(
                self,
                "Confirmar consumo",
                "Está por consumir:\n"
                f"- Categoría: {_categoria_label(categoria)}\n"
                f"- Producto: {producto}\n"
                f"- Marca: {marca}\n"
                f"- Cantidad: {cantidad:.2f}\n"
                f"{linea_equipo}\n"
                f"Stock actual: {actual:.2f}\n"
                f"Consumirá: {cantidad:.2f}\n"
                f"Stock restante: {restante:.2f}\n\n"
                "¿Desea confirmar la operación?",
            )
            if not ok:
                return
            try:
                self.db.save_consumo_stock(
                    categoria=categoria,
                    producto=producto,
                    marca=marca,
                    cantidad=cantidad,
                    operador=self.session.username,
                    observaciones="",
                    equipo_id=equipo_id,
                )
            except Exception as exc:
                _msg_error(self, "Error", f"No se pudo registrar el consumo:\n{exc}")
                return

            var_cantidad.set("")
            refresh_marcas()
            _msg_info(self, "Éxito", "Consumo registrado correctamente.")

        ttk.Label(parent, textvariable=var_stock, style="QDV.BodyCard.TLabel").grid(row=6, column=0, columnspan=4, sticky="w", pady=(10, 2))
        ttk.Label(parent, textvariable=var_preview, style="QDV.MutedCard.TLabel").grid(row=7, column=0, columnspan=4, sticky="w", pady=(2, 10))

        cb_categoria.bind("<<ComboboxSelected>>", lambda _e: refresh_productos())
        cb_producto.bind("<<ComboboxSelected>>", lambda _e: refresh_marcas())
        cb_marca.bind("<<ComboboxSelected>>", lambda _e: refresh_stock_preview())
        var_cantidad.trace_add("write", lambda *_: refresh_stock_preview())

        btns = ttk.Frame(parent)
        btns.grid(row=8, column=0, columnspan=4, sticky="w", pady=(4, 0))
        ttk.Button(btns, text="Refrescar", command=refresh_productos, style="QDV.Secondary.TButton").pack(side="left")
        ttk.Button(btns, text="Consumir", command=on_consumir, style="QDV.NeuModule.TButton").pack(side="left", padx=8)

        refresh_productos()


class StockWindow(tk.Toplevel):
    def __init__(self, master, db: DB):
        super().__init__(master)
        self.db = db
        try:
            self.transient(master)
        except tk.TclError:
            pass
        self.title("Producción - STOCK")
        self.geometry("980x680")
        self.minsize(880, 580)

        main = ttk.Frame(self, padding=12)
        main.pack(fill="both", expand=True)

        controls = ttk.Frame(main)
        controls.pack(fill="x", pady=(0, 8))

        ttk.Label(controls, text="Categoría:").pack(side="left")
        self.var_categoria = tk.StringVar(value="Materia prima")
        self.cb_categoria = ttk.Combobox(
            controls,
            state="readonly",
            width=24,
            textvariable=self.var_categoria,
            values=("Materia prima", "Laboratorio"),
        )
        self.cb_categoria.pack(side="left", padx=(8, 16))

        ttk.Label(controls, text="Vista:").pack(side="left")
        self.var_vista = tk.StringVar(value="Consolidado por producto")
        self.cb_vista = ttk.Combobox(
            controls,
            state="readonly",
            width=30,
            textvariable=self.var_vista,
            values=("Consolidado por producto", "Separado por marcas"),
        )
        self.cb_vista.pack(side="left", padx=(8, 12))
        ttk.Button(controls, text="Actualizar", command=self.refresh).pack(side="left")

        self.tree = ttk.Treeview(main, columns=("producto", "marca", "stock"), show="headings")
        self.tree.pack(fill="both", expand=True)
        self.tree.heading("producto", text="Producto")
        self.tree.heading("marca", text="Marca")
        self.tree.heading("stock", text="STOCK")
        self.tree.column("producto", width=380, anchor="w")
        self.tree.column("marca", width=240, anchor="w")
        self.tree.column("stock", width=140, anchor="e")

        self.cb_categoria.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        self.cb_vista.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        self.build_stock_view()

    def build_stock_view(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        categoria = "materia_prima" if self.var_categoria.get() == "Materia prima" else "laboratorio"
        by_brand = self.var_vista.get() == "Separado por marcas"

        if by_brand:
            rows = self.db.get_stock_por_marca(categoria)
            for r in rows:
                self.tree.insert("", "end", values=(r["producto"], r["marca"], f'{float(r["stock"]):.2f}'))
            return

        rows = self.db.get_stock_consolidado(categoria)
        for r in rows:
            self.tree.insert("", "end", values=(r["producto"], "-", f'{float(r["stock"]):.2f}'))
