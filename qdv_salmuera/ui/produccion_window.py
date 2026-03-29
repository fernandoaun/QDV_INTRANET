from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Any

from qdv_salmuera.auth.session import UserSession
from qdv_salmuera.data.db import DB
from qdv_salmuera.ui.theme import QDV_COLORS, apply_qdv_theme

from qdv_salmuera.ui.salmuera_window import CircuitoSalmueraWindow
from qdv_salmuera.ui.consumo_stock_window import RealizarConsumoWindow, StockWindow
from qdv_salmuera.ui.reactor_window import ReactorWindow
from qdv_salmuera.ui.control_agua_window import ControlAguaWindow
from qdv_salmuera.ui.module_labels import module_label
from qdv_salmuera.ui.consumo_calendar_panel import ConsumoCalendarPanel


class ProduccionWindow(tk.Toplevel):
    def __init__(self, master, db: DB, session: UserSession):
        super().__init__(master)
        self.session = session
        self.title("Producción - Química del Valle")
        self.geometry("1200x800")
        self.minsize(820, 520)

        self.db = db

        self._build_ui()
        self._refresh_resumen()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root, style="QDV.Card.TFrame", padding=(4, 4))
        header.pack(fill="x")

        ttk.Label(header, text="Producción", style="QDV.HeaderTitle.TLabel").pack(side="left", padx=6)
        ttk.Button(header, text="Actualizar", style="QDV.Secondary.TButton", command=self._refresh_resumen).pack(side="right")

        ttk.Separator(root).pack(fill="x", pady=10)

        body = ttk.Frame(root)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body, style="QDV.CardInner.TFrame", padding=(10, 8))
        left.pack(side="left", fill="y", padx=(0, 12))

        right = ttk.Frame(body, style="QDV.CardInner.TFrame", padding=(4, 4))
        right.pack(side="left", fill="both", expand=True)

        ttk.Label(left, text="Acciones", style="QDV.SectionCard.TLabel").pack(anchor="w", pady=(0, 10))

        if self.session.can("salmuera"):
            ttk.Button(
                left,
                text=module_label("salmuera"),
                width=28,
                style="QDV.NeuModule.TButton",
                command=lambda: CircuitoSalmueraWindow(self, self.db),
            ).pack(anchor="w", pady=5)

        if self.session.can("bolson_carga"):
            ttk.Button(
                left,
                text="REALIZAR CONSUMO",
                width=28,
                style="QDV.NeuModule.TButton",
                command=lambda: RealizarConsumoWindow(self, self.db, self.session),
            ).pack(anchor="w", pady=5)

        if self.session.can("bolson_registro"):
            ttk.Button(
                left,
                text="STOCK",
                width=28,
                style="QDV.NeuModule.TButton",
                command=lambda: StockWindow(self, self.db),
            ).pack(anchor="w", pady=5)

        if self.session.can("reactor"):
            ttk.Button(
                left,
                text=module_label("reactor"),
                width=28,
                style="QDV.NeuModule.TButton",
                command=lambda: ReactorWindow(self, self.db),
            ).pack(anchor="w", pady=5)

        if self.session.can("agua"):
            ttk.Button(
                left,
                text=module_label("agua"),
                width=28,
                style="QDV.NeuModule.TButton",
                command=lambda: ControlAguaWindow(self, self.db),
            ).pack(anchor="w", pady=5)

        ttk.Separator(left).pack(fill="x", pady=12)
        ttk.Button(left, text="Cerrar", width=28, style="QDV.Secondary.TButton", command=self.destroy).pack(anchor="w", pady=5)

        # Resumen
        self.summary = ttk.LabelFrame(right, text="Resumen", padding=12)
        self.summary.pack(fill="both", expand=True)

        self.lbl_stock_mp = ttk.Label(self.summary, text="Stock materia prima (productos): -", style="QDV.BodyCard.TLabel")
        self.lbl_stock_mp.pack(anchor="w", pady=6)
        self.lbl_stock_lab = ttk.Label(self.summary, text="Stock laboratorio (productos): -", style="QDV.BodyCard.TLabel")
        self.lbl_stock_lab.pack(anchor="w", pady=6)

        ttk.Label(
            self.summary,
            text="(Acá también va el resumen del último registro de salmuera)",
            style="QDV.MutedCard.TLabel",
        ).pack(anchor="w", pady=6)

        cal_lf = ttk.LabelFrame(
            self.summary,
            text="CALENDARIO DE CONSUMOS – ÚLTIMOS 30 DÍAS",
            padding=8,
        )
        cal_lf.pack(fill="both", expand=True, pady=(12, 0))
        self._consumo_calendar = ConsumoCalendarPanel(cal_lf, self.db)
        self._consumo_calendar.pack(fill="both", expand=True)

    def _not_implemented(self):
        messagebox.showinfo("Producción", "Esta pantalla se migra en el próximo paso (Circuito Salmuera / Historial / Edición).")

    def _refresh_resumen(self):
        stock_mp = self.db.get_stock_consolidado("materia_prima")
        stock_lab = self.db.get_stock_consolidado("laboratorio")
        self.lbl_stock_mp.configure(text=f"Stock materia prima (productos): {len(stock_mp)}")
        self.lbl_stock_lab.configure(text=f"Stock laboratorio (productos): {len(stock_lab)}")
        if hasattr(self, "_consumo_calendar"):
            self._consumo_calendar.refresh()
