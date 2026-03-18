import tkinter as tk
from tkinter import ttk

from qdv_salmuera.data.db import DB
from qdv_salmuera.utils.dates import iso_to_ddmmyyyy

#Demostracion de funcionamiento GIT
# PEGAR AQUÍ: class BolsonRegistroWindow (V4 1037–1097)
# =========================
# Ventana: Registro Bolsón (histórico)
# =========================
class BolsonRegistroWindow(tk.Toplevel):
    def __init__(self, master, db: DB):
        super().__init__(master)
        self.db = db
        self.title("Química del Valle - Producción - Registro de Carga de Bolsón")
        # Obtener ancho y alto de la pantalla
        self.geometry("1200x800")
        self.minsize(820, 520)

        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="Registro (Histórico) - Carga de Bolsón", font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Button(header, text="Actualizar", command=self.load).pack(side="right")

        box = ttk.LabelFrame(outer, text="Bolsónes cargados", padding=10)
        box.pack(fill="both", expand=True)

        wrap = ttk.Frame(box)
        wrap.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(wrap, columns=("id", "fecha", "hora", "creado"), show="headings")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.heading("id", text="ID")
        self.tree.heading("fecha", text="Fecha")
        self.tree.heading("hora", text="Hora")
        self.tree.heading("creado", text="Creado (ISO)")

        self.tree.column("id", width=80, anchor="center", stretch=False)
        self.tree.column("fecha", width=110, anchor="center", stretch=False)
        self.tree.column("hora", width=90, anchor="center", stretch=False)
        self.tree.column("creado", width=220, anchor="w", stretch=True)

        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(10, 0))
        ttk.Button(footer, text="Cerrar", command=self.destroy).pack(side="right")

        self.load()

    def load(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        rows = self.db.fetch_bolson_all()
        for r in rows:
            self.tree.insert(
                "",
                "end",
                values=(r["id"], iso_to_ddmmyyyy(r["fecha_iso"]), r["hora_hm"], r["created_at_iso"])
            )