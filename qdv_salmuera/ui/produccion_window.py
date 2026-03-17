from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Any

from qdv_salmuera.data.db import DB

from qdv_salmuera.ui.salmuera_window import CircuitoSalmueraWindow
from qdv_salmuera.ui.bolson_window import BolsonRegistroWindow


class ProduccionWindow(tk.Toplevel):
    def __init__(self, master, db: DB):
        super().__init__(master)
        self.title("Producción - Química del Valle")
        self.geometry("1200x800")
        self.minsize(820, 520)

        self.db = db

        self._build_ui()
        self._refresh_resumen()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x")

        ttk.Label(header, text="Producción", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(header, text="Actualizar", command=self._refresh_resumen).pack(side="right")

        ttk.Separator(root).pack(fill="x", pady=10)

        body = ttk.Frame(root)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="y", padx=(0, 12))

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        ttk.Label(left, text="Acciones", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 8))

        ttk.Button(
            left,
            text="Circuito de Salmuera",
            width=28,
            command=lambda: CircuitoSalmueraWindow(self, self.db)
        ).pack(anchor="w", pady=4)

        ttk.Button(
            left,
            text="Carga de Bolsón (NOW)",
            width=28,
            command=self._cargar_bolson
        ).pack(anchor="w", pady=4)

        ttk.Button(
            left,
            text="Registro Bolsón",
            width=28,
            command=lambda: BolsonRegistroWindow(self, self.db)
        ).pack(anchor="w", pady=4)

        ttk.Separator(left).pack(fill="x", pady=10)
        ttk.Button(left, text="Cerrar", width=28, command=self.destroy).pack(anchor="w", pady=4)

        # Resumen
        self.summary = ttk.LabelFrame(right, text="Resumen", padding=12)
        self.summary.pack(fill="both", expand=True)

        self.lbl_bolson = ttk.Label(self.summary, text="Último bolsón: -", font=("Segoe UI", 11))
        self.lbl_bolson.pack(anchor="w", pady=6)

        ttk.Label(self.summary, text="(Acá también va el resumen del último registro de salmuera)", foreground="#444").pack(anchor="w", pady=6)

    def _not_implemented(self):
        messagebox.showinfo("Producción", "Esta pantalla se migra en el próximo paso (Circuito Salmuera / Historial / Edición).")

    def _cargar_bolson(self):
        try:
            self.db.insert_bolson_now()
            messagebox.showinfo("Bolsón", "Bolsón cargado correctamente (fecha/hora actual).")
            self._refresh_resumen()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar bolsón:\n{e}")

    def _refresh_resumen(self):
        last = self.db.fetch_last_bolson()
        if not last:
            self.lbl_bolson.configure(text="Último bolsón: (sin registros)")
            return

        txt = f"Último bolsón: {last.get('fecha_iso','-')} {last.get('hora_hm','-')}  | created_at: {last.get('created_at_iso','-')}"
        self.lbl_bolson.configure(text=txt)
