from __future__ import annotations

import tkinter as tk
from collections import defaultdict
from datetime import date, timedelta
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

from qdv_salmuera.data.db import DB
from qdv_salmuera.ui.theme import QDV_COLORS


class _CellToolTip:
    """Tooltip simple al pasar el mouse sobre una celda del calendario."""

    def __init__(self, widget: tk.Misc, text_supplier: Callable[[], str]) -> None:
        self.widget = widget
        self.text_supplier = text_supplier
        self._tip: Optional[tk.Toplevel] = None
        self._after_id: Optional[str] = None
        widget.bind("<Enter>", self._schedule, add=True)
        widget.bind("<Leave>", self._hide, add=True)
        widget.bind("<ButtonPress>", self._hide, add=True)

    def _schedule(self, _event=None) -> None:
        self._cancel_sched()
        self._after_id = self.widget.after(400, self._show)

    def _cancel_sched(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _hide(self, _event=None) -> None:
        self._cancel_sched()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None

    def _show(self) -> None:
        self._after_id = None
        text = (self.text_supplier() or "").strip()
        if not text:
            return
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        try:
            tw.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        fg = QDV_COLORS["fg"]
        bg = QDV_COLORS["card_elevated"]
        lbl = tk.Label(
            tw,
            text=text,
            justify="left",
            background=bg,
            foreground=fg,
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
            padx=8,
            pady=6,
            font=(QDV_COLORS["font_family"], 9),
        )
        lbl.pack()
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        tw.wm_geometry(f"+{x}+{y}")


class _ConsumosDiaDetalleDialog(tk.Toplevel):
    """Detalle de cada consumo del día: hora, producto, cantidad."""

    def __init__(self, master: tk.Misc, day: date, items: List[Dict[str, Any]]) -> None:
        super().__init__(master)
        self.title(f"Consumos — {day.strftime('%d/%m/%Y')}")
        self.geometry("720x400")
        self.minsize(640, 300)
        try:
            self.transient(master)
        except tk.TclError:
            pass

        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        cols = ("hora", "producto", "cantidad", "equipo")
        tree = ttk.Treeview(frm, columns=cols, show="headings", height=14)
        tree.heading("hora", text="Hora")
        tree.heading("producto", text="Producto")
        tree.heading("cantidad", text="Cantidad")
        tree.heading("equipo", text="Equipo")
        tree.column("hora", width=72, anchor="center", stretch=False)
        tree.column("producto", width=240, anchor="w", stretch=True)
        tree.column("cantidad", width=80, anchor="e", stretch=False)
        tree.column("equipo", width=140, anchor="w", stretch=False)
        for it in items:
            eq = (it.get("equipo_nombre") or "").strip() or "—"
            tree.insert("", "end", values=(it["hora"], it["producto"], f'{it["cantidad"]:.2f}', eq))

        vsb = ttk.Scrollbar(frm, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        bar = ttk.Frame(self, padding=(10, 0, 10, 10))
        bar.pack(fill="x")
        ttk.Button(bar, text="Cerrar", command=self.destroy, style="QDV.Secondary.TButton").pack(side="right")

        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.focus_set()


class ConsumoCalendarPanel(ttk.Frame):
    """
    Calendario tipo almanaque (lun–dom) de los últimos 30 días con puntos por producto consumido.
    Colores persistidos vía DB.get_or_create_product_color.
    """

    WEEKDAYS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")

    def __init__(self, master: tk.Misc, db: DB) -> None:
        super().__init__(master, style="QDV.OnCard.TFrame")
        self.db = db
        self._body = ttk.Frame(self, style="QDV.OnCard.TFrame")
        self._body.pack(fill="both", expand=True)
        self.refresh()

    def refresh(self) -> None:
        for w in self._body.winfo_children():
            w.destroy()

        rows = self.db.get_consumos_ultimos_30_dias()
        by_date: Dict[str, Dict[str, float]] = defaultdict(dict)
        for r in rows:
            by_date[r["fecha_iso"]][r["producto"]] = float(r["cantidad_total"])

        products_in_range = sorted(
            {r["producto"] for r in rows},
            key=lambda s: s.lower(),
        )
        for pname in products_in_range:
            self.db.get_or_create_product_color(pname)

        today = date.today()
        range_start = today - timedelta(days=29)
        range_end = today
        cal_start = range_start - timedelta(days=range_start.weekday())
        cal_end = range_end + timedelta(days=(6 - range_end.weekday()))

        grid = ttk.Frame(self._body, style="QDV.OnCard.TFrame")
        grid.pack(fill="x", pady=(0, 10))

        c = QDV_COLORS
        for col, wd in enumerate(self.WEEKDAYS):
            ttk.Label(grid, text=wd, style="QDV.MutedCard.TLabel", width=6, anchor="center").grid(
                row=0, column=col, padx=2, pady=(0, 4)
            )

        d = cal_start
        row = 1
        while d <= cal_end:
            for col in range(7):
                if d > cal_end:
                    break
                self._make_day_cell(grid, row, col, d, range_start, range_end, by_date)
                d += timedelta(days=1)
            row += 1

        legend = ttk.LabelFrame(self._body, text="Leyenda (producto → color)", padding=8)
        legend.pack(fill="x", pady=(4, 0))

        if not products_in_range:
            ttk.Label(legend, text="Sin consumos registrados en este período.", style="QDV.MutedCard.TLabel").pack(
                anchor="w"
            )
            return

        leg_grid = ttk.Frame(legend, style="QDV.OnCard.TFrame")
        leg_grid.pack(fill="x")
        max_cols = 3
        for i, prod in enumerate(products_in_range):
            r, col = divmod(i, max_cols)
            cell = ttk.Frame(leg_grid, style="QDV.OnCard.TFrame")
            cell.grid(row=r, column=col, sticky="w", padx=8, pady=4)
            hex_c = self.db.get_or_create_product_color(prod)
            tk.Label(
                cell,
                text="●",
                fg=hex_c,
                bg=c["card_elevated"],
                font=(c["font_family"], 11),
            ).pack(side="left")
            ttk.Label(cell, text=prod, style="QDV.BodyCard.TLabel").pack(side="left", padx=(4, 0))

    def _refocus_app(self) -> None:
        w = self.winfo_toplevel()

        def _lift() -> None:
            try:
                w.lift()
                w.focus_set()
            except tk.TclError:
                pass

        w.after_idle(_lift)

    def _on_day_click(self, d: date, in_30: bool) -> None:
        if not in_30:
            return
        parent = self.winfo_toplevel()
        items = self.db.get_consumos_detalle_por_fecha(d.isoformat())
        if not items:
            messagebox.showinfo(
                "Consumos del día",
                f"{d.strftime('%d/%m/%Y')}\nSin consumos registrados.",
                parent=parent,
            )
            self._refocus_app()
            return
        _ConsumosDiaDetalleDialog(parent, d, items)

    def _make_day_cell(
        self,
        parent: ttk.Frame,
        row: int,
        col: int,
        d: date,
        range_start: date,
        range_end: date,
        by_date: Dict[str, Dict[str, float]],
    ) -> None:
        c = QDV_COLORS
        in_30 = range_start <= d <= range_end
        bg = c["card_elevated"] if in_30 else c["input_inset"]
        fg = c["fg"] if in_30 else c["muted"]

        outer = tk.Frame(
            parent,
            bg=bg,
            highlightthickness=1,
            highlightbackground=c["border"],
            width=88,
            height=72,
            cursor="hand2" if in_30 else "",
        )
        outer.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")
        outer.grid_propagate(False)

        if in_30:
            outer.bind("<Button-1>", lambda e, dd=d: self._on_day_click(dd, True))

        day_lbl = tk.Label(
            outer,
            text=str(d.day),
            bg=bg,
            fg=fg,
            font=(c["font_family"], 10, "bold" if in_30 else "normal"),
        )
        day_lbl.pack(anchor="nw", padx=4, pady=(2, 0))
        if in_30:
            day_lbl.bind("<Button-1>", lambda e, dd=d: self._on_day_click(dd, True))

        dots_f = tk.Frame(outer, bg=bg)
        dots_f.pack(side="bottom", fill="x", padx=2, pady=(0, 4))
        if in_30:
            dots_f.bind("<Button-1>", lambda e, dd=d: self._on_day_click(dd, True))

        iso = d.isoformat()
        prods_day = by_date.get(iso, {})

        def tooltip_text() -> str:
            if not in_30:
                return ""
            if not prods_day:
                return f"{d.strftime('%d/%m/%Y')}\n(sin consumos)\n(Clic para detalle)"
            lines = [d.strftime("%d/%m/%Y"), "(Clic para ver hora y cantidad por ítem)"]
            for pname in sorted(prods_day.keys(), key=lambda x: x.lower()):
                lines.append(f"{pname} — {prods_day[pname]:.2f}")
            return "\n".join(lines)

        _CellToolTip(outer, tooltip_text)

        if prods_day and in_30:
            wrap = tk.Frame(dots_f, bg=bg)
            wrap.pack(anchor="s")
            wrap.bind("<Button-1>", lambda e, dd=d: self._on_day_click(dd, True))
            for pname in sorted(prods_day.keys(), key=lambda x: x.lower()):
                hx = self.db.get_or_create_product_color(pname)
                lb = tk.Label(
                    wrap,
                    text="●",
                    fg=hx,
                    bg=bg,
                    font=(c["font_family"], 9),
                    cursor="hand2",
                )
                lb.pack(side="left", padx=1)
                lb.bind("<Button-1>", lambda e, dd=d: self._on_day_click(dd, True))
