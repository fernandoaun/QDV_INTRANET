from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable

from qdv_salmuera.auth.service import login
from qdv_salmuera.auth.session import UserSession
from qdv_salmuera.data.db import DB
from qdv_salmuera.ui.theme import QDV_COLORS, apply_qdv_theme


class LoginWindow:
    """Pantalla inicial de inicio de sesión."""

    def __init__(self, master: tk.Tk, db: DB, on_success: Callable[[UserSession], None]) -> None:
        self.master = master
        self.db = db
        self.on_success = on_success
        self._pw_visible = False

        master.title("Inicio de sesión")
        master.configure(bg=QDV_COLORS["bg"])
        master.geometry("440x360")
        master.minsize(400, 320)
        master.resizable(False, False)

        style = ttk.Style(master)
        apply_qdv_theme(style)

        outer = ttk.Frame(master, padding=20)
        outer.pack(fill="both", expand=True)

        panel = ttk.Frame(outer, style="QDV.NeuPanel.TFrame", padding=22)
        panel.pack(fill="both", expand=True)

        ttk.Label(panel, text="Inicio de sesión", style="QDV.TitleCard.TLabel").pack(anchor="w", pady=(0, 18))

        ttk.Label(panel, text="Usuario", style="QDV.OnCard.TLabel").pack(anchor="w")
        self.var_user = tk.StringVar()
        self.ent_user = ttk.Entry(panel, textvariable=self.var_user, width=36)
        self.ent_user.pack(fill="x", pady=(4, 12))

        ttk.Label(panel, text="Contraseña", style="QDV.OnCard.TLabel").pack(anchor="w")
        pw_row = ttk.Frame(panel, style="QDV.OnCard.TFrame")
        pw_row.pack(fill="x", pady=(4, 8))
        self.var_pw = tk.StringVar()
        self.ent_pw = ttk.Entry(pw_row, textvariable=self.var_pw, show="*", width=30)
        self.ent_pw.pack(side="left", fill="x", expand=True)
        self.btn_toggle = ttk.Button(pw_row, text="Mostrar", width=10, command=self._toggle_pw)
        self.btn_toggle.pack(side="right", padx=(8, 0))

        ttk.Button(panel, text="Ingresar", style="QDV.Primary.TButton", command=self._try_login).pack(fill="x", pady=(18, 8))

        ttk.Button(panel, text="Salir", style="QDV.Secondary.TButton", command=master.quit).pack(fill="x")

        self.ent_user.bind("<Return>", lambda e: self.ent_pw.focus_set())
        self.ent_pw.bind("<Return>", lambda e: self._try_login())

        master.protocol("WM_DELETE_WINDOW", master.quit)
        self.ent_user.focus_set()

    def _toggle_pw(self) -> None:
        self._pw_visible = not self._pw_visible
        self.ent_pw.configure(show="" if self._pw_visible else "*")
        self.btn_toggle.configure(text="Ocultar" if self._pw_visible else "Mostrar")

    def _try_login(self) -> None:
        u = (self.var_user.get() or "").strip()
        p = self.var_pw.get() or ""
        if not u or not p:
            messagebox.showerror("Inicio de sesión", "Ingrese usuario y contraseña.")
            return
        sess = login(self.db, u, p)
        if sess is None:
            messagebox.showerror("Inicio de sesión", "Usuario o contraseña incorrectos, o usuario inactivo.")
            return
        self.on_success(sess)
        self.master.quit()
