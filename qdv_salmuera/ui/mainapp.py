from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from qdv_salmuera.auth.session import UserSession
from qdv_salmuera.config.settings import APP_TITLE, logo_path
from qdv_salmuera.data.db import DB
from qdv_salmuera.ui.theme import QDV_COLORS, apply_qdv_theme
from qdv_salmuera.utils.app_paths import get_database_path, migrate_legacy_database_if_needed, setup_persistent_logging

from qdv_salmuera.ui.produccion_window import ProduccionWindow
from qdv_salmuera.ui.graficos_window import DashboardGraficosWindow, build_fig_proceso_quimico_ultimas_24h
from qdv_salmuera.ui.users_admin_window import UsersAdminWindow

# Pillow para logo (opcional)
try:
    from PIL import Image, ImageTk
    PIL_OK = True
except Exception:
    PIL_OK = False

class QDVApp(tk.Tk):
    def __init__(self, session: UserSession, db: Optional[DB] = None):
        super().__init__()
        self.session = session
        self._logout_requested = False

        self.title(APP_TITLE)
        self.configure(bg=QDV_COLORS["bg"])
        self.geometry("980x620")
        self.minsize(860, 560)

        if db is not None:
            self.db = db
        else:
            from qdv_salmuera.config.settings import project_root

            setup_persistent_logging(prefer_roaming=True)
            mig_msg = migrate_legacy_database_if_needed(project_root=project_root(), prefer_roaming=True)
            if mig_msg:
                logging.info(mig_msg)
            ruta = get_database_path(prefer_roaming=True)
            logging.info("Usando base de datos en: %s", ruta)
            self.db = DB(ruta)

        # UI base
        self.style = ttk.Style(self)
        apply_qdv_theme(self.style)

        self.logo_img = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)

        # Header
        header = ttk.Frame(root, style="QDV.Card.TFrame")
        header.pack(fill="x")

        self._try_load_logo(header)

        ttk.Label(header, text="Química del Valle", style="QDV.HeaderTitle.TLabel").pack(side="left", padx=10)

        ttk.Label(header, text="Panel Principal", style="QDV.HeaderSub.TLabel").pack(side="left", padx=6)

        self.lbl_user = ttk.Label(
            header,
            text=f"Usuario: {self.session.username}",
            style="QDV.HeaderUser.TLabel",
        )
        self.lbl_user.pack(side="right", padx=(12, 0))

        ttk.Separator(root).pack(fill="x", pady=10)

        # Body
        body = ttk.Frame(root, style="QDV.Card.TFrame")
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body, style="QDV.CardInner.TFrame", padding=(10, 8))
        left.pack(side="left", fill="y", padx=(0, 12))

        right = ttk.Frame(body, style="QDV.CardInner.TFrame", padding=(4, 4))
        right.pack(side="left", fill="both", expand=True)

        ttk.Label(left, text="Módulos", style="QDV.SectionCard.TLabel").pack(anchor="w", pady=(0, 10))

        if self.session.can("produccion"):
            ttk.Button(left, text="Producción", command=self.open_produccion, width=24, style="QDV.NeuModule.TButton").pack(anchor="w", pady=5)
        if self.session.can("graficos"):
            ttk.Button(left, text="Gráficos", command=self.open_graficos, width=24, style="QDV.NeuModule.TButton").pack(anchor="w", pady=5)

        if self.session.can("recepcion"):
            ttk.Button(left, text="Recepción (próx.)", command=self._not_implemented, width=24, style="QDV.NeuModule.TButton").pack(anchor="w", pady=5)
        if self.session.can("despacho"):
            ttk.Button(left, text="Despacho (próx.)", command=self._not_implemented, width=24, style="QDV.NeuModule.TButton").pack(anchor="w", pady=5)

        if self.session.is_admin:
            ttk.Button(
                left,
                text="Usuarios y permisos",
                command=self.open_users_admin,
                width=24,
                style="QDV.NeuModule.TButton",
            ).pack(anchor="w", pady=5)

        ttk.Separator(left).pack(fill="x", pady=12)

        ttk.Button(left, text="Cerrar sesión", command=self.logout, width=24, style="QDV.Secondary.TButton").pack(anchor="w", pady=5)
        ttk.Button(left, text="Salir", command=self.destroy, width=24, style="QDV.Secondary.TButton").pack(anchor="w", pady=5)

        # Panel derecho: gráfico Proceso químico últimas 24 h
        card = ttk.LabelFrame(right, text="Estado - Proceso químico (últimas 24 h)", padding=8)
        card.pack(fill="both", expand=True)

        self._chart_frame = ttk.Frame(card)
        self._chart_frame.pack(fill="both", expand=True)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(0, weight=1)

        self._embed_proceso_chart()

    def _embed_proceso_chart(self) -> None:
        """Dibuja el gráfico de Proceso químico (últimas 24 h) en el panel Estado."""
        for w in self._chart_frame.winfo_children():
            w.destroy()
        try:
            fig = build_fig_proceso_quimico_ultimas_24h(self.db)
            canvas = FigureCanvasTkAgg(fig, master=self._chart_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)
        except Exception:
            ttk.Label(self._chart_frame, text="No se pudo cargar el gráfico.", foreground="gray").pack(expand=True)

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

    def logout(self) -> None:
        self._logout_requested = True
        self.destroy()

    def open_users_admin(self) -> None:
        if not self.session.is_admin:
            messagebox.showerror("Permisos", "Solo un administrador puede gestionar usuarios.")
            return
        UsersAdminWindow(self, self.db, self.session)

    def open_produccion(self):
        if not self.session.can("produccion"):
            messagebox.showerror("Permisos", "No tiene acceso al módulo Producción.")
            return
        ProduccionWindow(self, self.db, self.session)

    def open_graficos(self):
        if not self.session.can("graficos"):
            messagebox.showerror("Permisos", "No tiene acceso a Gráficos.")
            return
        DashboardGraficosWindow(self, self.db)

