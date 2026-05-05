from __future__ import annotations

import logging
import os
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
        # Diagrama de proceso (evitar GC de PhotoImage)
        self.img_diagrama_tk = None
        self.img_diagrama_original = None
        self.lbl_diagrama: tk.Label | None = None
        self._frm_diagrama_inner: tk.Frame | None = None
        self._diagrama_resize_after: str | None = None
        self._diagrama_last_size: tuple[int, int] | None = None
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

        tk.Label(
            root,
            text=(
                "Datos locales: esta versión guarda en una base SQLite propia (no es la misma que la intranet QDV Web). "
                "Para uso compartido en planta o en red, usá solo la aplicación web (carpeta project_web)."
            ),
            fg=QDV_COLORS["muted"],
            bg=QDV_COLORS["bg"],
            wraplength=920,
            justify="left",
            font=(QDV_COLORS["font_family"], 9),
        ).pack(fill="x", pady=(0, 8))

        # Body
        body = ttk.Frame(root, style="QDV.Card.TFrame")
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body, style="QDV.CardInner.TFrame", padding=(10, 8))
        left.pack(side="left", fill="y", padx=(0, 12))

        right = ttk.Frame(body, style="QDV.CardInner.TFrame", padding=(4, 4))
        right.pack(side="left", fill="both", expand=True)

        right_inner = ttk.Frame(right, style="QDV.CardInner.TFrame")
        right_inner.pack(fill="both", expand=True)

        ttk.Label(left, text="Módulos", style="QDV.SectionCard.TLabel").pack(anchor="w", pady=(0, 10))

        if self.session.can("produccion"):
            ttk.Button(left, text="Producción", command=self.open_produccion, width=24, style="QDV.NeuModule.TButton").pack(anchor="w", pady=5)
        if self.session.can("graficos"):
            ttk.Button(left, text="Gráficos", command=self.open_graficos, width=24, style="QDV.NeuModule.TButton").pack(anchor="w", pady=5)

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

        # Panel derecho: gráfico Proceso químico últimas 24 h + diagrama de planta
        card = ttk.LabelFrame(right_inner, text="Estado - Proceso químico (últimas 24 h)", padding=8)
        card.pack(fill="both", expand=True)

        self._chart_frame = ttk.Frame(card)
        self._chart_frame.pack(fill="both", expand=True)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(0, weight=1)

        self.crear_bloque_diagrama_proceso(right_inner)

        # Diferir matplotlib: la ventana principal aparece antes; el gráfico no bloquea el primer paint
        self.after_idle(self._embed_proceso_chart)

    def crear_bloque_diagrama_proceso(self, parent: ttk.Frame) -> None:
        """Bloque tipo SCADA: imagen del proceso, ancho adaptable y segura si falta el archivo."""
        outer = ttk.LabelFrame(parent, text="Diagrama de proceso – Planta de Hipoclorito", padding=8)
        outer.pack(fill="x", expand=False, pady=(10, 0))

        card_bg = QDV_COLORS["card_elevated"]
        inner = tk.Frame(outer, bg=card_bg, highlightbackground=QDV_COLORS["border"], highlightthickness=1)
        inner.pack(fill="x", expand=True, pady=(4, 0))

        self._frm_diagrama_inner = inner
        self.lbl_diagrama = tk.Label(
            inner,
            bg=card_bg,
            fg=QDV_COLORS["muted"],
            text="",
            justify="center",
            font=(QDV_COLORS["font_family"], 10),
        )
        self.lbl_diagrama.pack(expand=True, pady=10, padx=10)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        img_path = os.path.join(base_dir, "planta_hipoclorito.png")

        if not PIL_OK:
            self.lbl_diagrama.config(
                text="Instalá Pillow (PIL) para mostrar planta_hipoclorito.png",
                wraplength=520,
            )
            return

        if not os.path.isfile(img_path):
            self.lbl_diagrama.config(text="No se encontró la imagen planta_hipoclorito.png", wraplength=520)
            return

        try:
            loaded = Image.open(img_path)
            self.img_diagrama_original = loaded.copy()
        except Exception:
            self.lbl_diagrama.config(text="No se encontró la imagen planta_hipoclorito.png", wraplength=520)
            self.img_diagrama_original = None
            return

        inner.bind("<Configure>", self._on_diagrama_inner_configure)
        self.after_idle(self._diagrama_refresh_size)

    def _on_diagrama_inner_configure(self, event: tk.Event) -> None:
        if self._frm_diagrama_inner is None or event.widget != self._frm_diagrama_inner:
            return
        w = int(event.width)
        if w < 40:
            return
        if self._diagrama_resize_after is not None:
            try:
                self.after_cancel(self._diagrama_resize_after)
            except Exception:
                pass
        self._diagrama_resize_after = self.after(75, lambda width=w: self._diagrama_apply_width(width))

    def _diagrama_refresh_size(self) -> None:
        if self._frm_diagrama_inner is None:
            return
        w = self._frm_diagrama_inner.winfo_width()
        if w < 64:
            self.after(100, self._diagrama_refresh_size)
            return
        self._diagrama_apply_width(w)

    def _diagrama_apply_width(self, inner_w: int) -> None:
        self._diagrama_resize_after = None
        if self.lbl_diagrama is None or self.img_diagrama_original is None:
            return
        pad = 24
        usable = max(40, inner_w - pad)
        ow, oh = self.img_diagrama_original.size
        if ow <= 0 or oh <= 0:
            return
        nw = usable
        nh = max(1, int(round(usable * oh / ow)))
        if self._diagrama_last_size == (nw, nh):
            return
        self._diagrama_last_size = (nw, nh)
        try:
            try:
                resample = Image.Resampling.LANCZOS  # type: ignore[attr-defined]
            except AttributeError:
                resample = Image.LANCZOS
            resized = self.img_diagrama_original.resize((nw, nh), resample)
            self.img_diagrama_tk = ImageTk.PhotoImage(resized)
            self.lbl_diagrama.config(image=self.img_diagrama_tk, text="", wraplength=0)
        except Exception as exc:
            logging.debug("Redimensionar diagrama: %s", exc)
            self.lbl_diagrama.config(
                text="No se pudo mostrar la imagen planta_hipoclorito.png",
                wraplength=520,
                image="",
            )

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

