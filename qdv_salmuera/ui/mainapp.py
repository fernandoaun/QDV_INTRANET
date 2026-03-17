from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, messagebox

from qdv_salmuera.config.settings import APP_TITLE, db_path, logo_path
from qdv_salmuera.data.db import DB

from qdv_salmuera.ui.produccion_window import ProduccionWindow
from qdv_salmuera.ui.graficos_window import DashboardGraficosWindow

# Pillow para logo (opcional)
try:
    from PIL import Image, ImageTk
    PIL_OK = True
except Exception:
    PIL_OK = False

def db_path() -> str:
    # 1) Carpeta fija de Windows (AppData\Local)
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        # si por algún motivo no existe, usamos tu carpeta de usuario
        base = os.path.expanduser("~")

    # 2) Carpeta donde vamos a guardar TODO lo persistente (DB, backups, etc.)
    data_dir = os.path.join(base, "QuimicaDelValle", "qdv_salmuera", "data")
    os.makedirs(data_dir, exist_ok=True)  # crea la carpeta si no existe

    # 3) Archivo de base de datos SIEMPRE igual (no cambia aunque muevas el proyecto)
    return os.path.join(data_dir, "salmuera.db")

class QDVApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x620")
        self.minsize(860, 560)

        # DB
        ruta = db_path()
        print("USANDO DB:", ruta)
        self.db = DB(ruta)


        # UI base
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("vista")
        except Exception:
            try:
                self.style.theme_use("clam")
            except Exception:
                pass

        self.logo_img = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        # Header
        header = ttk.Frame(root)
        header.pack(fill="x")

        self._try_load_logo(header)

        title = ttk.Label(header, text="Química del Valle", font=("Segoe UI", 18, "bold"))
        title.pack(side="left", padx=10)

        subtitle = ttk.Label(header, text="Panel Principal", font=("Segoe UI", 11))
        subtitle.pack(side="left", padx=6)

        ttk.Separator(root).pack(fill="x", pady=10)

        # Body
        body = ttk.Frame(root)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="y", padx=(0, 12))

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        ttk.Label(left, text="Módulos", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 8))

        ttk.Button(left, text="Producción", command=self.open_produccion, width=24).pack(anchor="w", pady=4)
        ttk.Button(left, text="Gráficos", command=self.open_graficos, width=24).pack(anchor="w", pady=4)

        ttk.Button(left, text="Recepción (próx.)", command=self._not_implemented, width=24).pack(anchor="w", pady=4)
        ttk.Button(left, text="Despacho (próx.)", command=self._not_implemented, width=24).pack(anchor="w", pady=4)

        ttk.Separator(left).pack(fill="x", pady=10)

        ttk.Button(left, text="Salir", command=self.destroy, width=24).pack(anchor="w", pady=4)

        # Panel derecho (info)
        card = ttk.LabelFrame(right, text="Estado", padding=12)
        card.pack(fill="both", expand=True)

        ttk.Label(card, text="DB:", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(card, text=db_path()).grid(row=0, column=1, sticky="w")

        card.grid_columnconfigure(1, weight=1)

    def _try_load_logo(self, parent) -> None:
        if not PIL_OK:
            return
        try:
            p = logo_path()
            img = Image.open(p)
            img = img.resize((56, 56))
            self.logo_img = ImageTk.PhotoImage(img)
            ttk.Label(parent, image=self.logo_img).pack(side="left")
        except Exception:
            # logo opcional, no frenamos la app
            pass

    def _not_implemented(self):
        messagebox.showinfo("QDV", "Módulo aún no implementado.")

    def open_produccion(self):
        ProduccionWindow(self, self.db)

    def open_graficos(self):
        DashboardGraficosWindow(self, self.db)

