import tkinter as tk
from tkinter import ttk, messagebox

from qdv_salmuera.utils.dates import parse_date_ddmmyyyy


class HistorialDialog(tk.Toplevel):
    def __init__(self, master, default_desde: str, default_hasta: str):
        super().__init__(master)
        self.title("Historial - Exportar a Excel")
        self.resizable(False, False)
        self.result = None

        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Ingrese rango de fechas para el reporte (dd/mm/aaaa):")\
            .grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(frm, text="Desde:").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=6)
        self.e_desde = ttk.Entry(frm, width=14)
        self.e_desde.grid(row=1, column=1, sticky="w", pady=6)
        self.e_desde.insert(0, default_desde)

        ttk.Label(frm, text="Hasta:").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=6)
        self.e_hasta = ttk.Entry(frm, width=14)
        self.e_hasta.grid(row=2, column=1, sticky="w", pady=6)
        self.e_hasta.insert(0, default_hasta)

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))

        ttk.Button(btns, text="Cancelar", command=self._cancel).pack(side="right", padx=(8, 0))
        ttk.Button(btns, text="Continuar", command=self._ok).pack(side="right")

        self.grab_set()
        self.e_desde.focus_set()

    def _ok(self):
        desde = self.e_desde.get().strip()
        hasta = self.e_hasta.get().strip()

        d1 = parse_date_ddmmyyyy(desde)
        d2 = parse_date_ddmmyyyy(hasta)

        if not d1:
            messagebox.showerror("Error", "Fecha 'Desde' inválida. Use dd/mm/aaaa.")
            return
        if not d2:
            messagebox.showerror("Error", "Fecha 'Hasta' inválida. Use dd/mm/aaaa.")
            return
        if d2 < d1:
            messagebox.showerror("Error", "La fecha 'Hasta' no puede ser anterior a 'Desde'.")
            return

        self.result = (desde, hasta)
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class CodigoSeguridadDialog(tk.Toplevel):
    def __init__(self, master, title="Código de seguridad"):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.result = None

        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Ingrese el código de seguridad para borrar:")\
            .grid(row=0, column=0, sticky="w", pady=(0, 10))

        self.var = tk.StringVar()
        self.entry = ttk.Entry(frm, textvariable=self.var, width=18, show="•")
        self.entry.grid(row=1, column=0, sticky="w", pady=(0, 10))

        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, sticky="e")

        ttk.Button(btns, text="Cancelar", command=self._cancel).pack(side="right", padx=(8, 0))
        ttk.Button(btns, text="Confirmar", command=self._ok).pack(side="right")

        self.grab_set()
        self.entry.focus_set()

    def _ok(self):
        self.result = self.var.get().strip()
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class AddOperadorDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Agregar operador")
        self.resizable(False, False)
        self.result = None

        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Nombre del operador:").grid(row=0, column=0, sticky="w")
        self.var = tk.StringVar()
        e = ttk.Entry(frm, textvariable=self.var, width=30)
        e.grid(row=1, column=0, sticky="w", pady=(6, 10))

        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, sticky="e")

        ttk.Button(btns, text="Cancelar", command=self._cancel).pack(side="right", padx=(8, 0))
        ttk.Button(btns, text="Agregar", command=self._ok).pack(side="right")

        self.grab_set()
        e.focus_set()

    def _ok(self):
        name = self.var.get().strip()
        if not name:
            messagebox.showerror("Error", "Ingrese un nombre de operador.")
            return
        self.result = name
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()
