from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, List, Optional

from qdv_salmuera.auth.passwords import hash_password
from qdv_salmuera.auth.permissions import PERMISSION_KEYS, PERMISSION_LABELS
from qdv_salmuera.auth.session import UserSession
from qdv_salmuera.data.db import DB
from qdv_salmuera.ui.theme import QDV_COLORS, apply_qdv_theme


class UsersAdminWindow(tk.Toplevel):
    """Administración de usuarios, contraseñas y permisos (solo administradores)."""

    def __init__(self, master, db: DB, editor: UserSession) -> None:
        super().__init__(master)
        self.db = db
        self.editor = editor
        self.title("Usuarios y permisos")
        self.geometry("900x620")
        self.minsize(820, 520)

        self.configure(bg=QDV_COLORS["bg"])
        style = ttk.Style(self)
        apply_qdv_theme(style)

        self._editing_id: Optional[int] = None
        self._perm_vars: Dict[str, tk.BooleanVar] = {}
        self._perm_checks: List[ttk.Checkbutton] = []

        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="Administración de usuarios", style="QDV.Title.TLabel").pack(anchor="w", pady=(0, 12))

        pan = ttk.Frame(root)
        pan.pack(fill="both", expand=True)

        left = ttk.LabelFrame(pan, text="Usuarios", padding=8)
        left.pack(side="left", fill="y", padx=(0, 12))

        cols = ("id", "usuario", "admin", "activo")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=18, selectmode="browse")
        self.tree.heading("id", text="ID")
        self.tree.heading("usuario", text="Usuario")
        self.tree.heading("admin", text="Admin")
        self.tree.heading("activo", text="Activo")
        self.tree.column("id", width=50, anchor="center", stretch=False)
        self.tree.column("usuario", width=160, anchor="w")
        self.tree.column("admin", width=60, anchor="center")
        self.tree.column("activo", width=60, anchor="center")
        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        ttk.Button(left, text="Nuevo usuario", command=self._new_user).pack(fill="x", pady=(8, 4))
        ttk.Button(left, text="Eliminar", style="QDV.Secondary.TButton", command=self._delete_user).pack(fill="x", pady=4)

        right = ttk.LabelFrame(pan, text="Datos y permisos", padding=12)
        right.pack(side="left", fill="both", expand=True)

        ttk.Label(right, text="Usuario (login)").grid(row=0, column=0, sticky="w")
        self.var_username = tk.StringVar()
        ttk.Entry(right, textvariable=self.var_username, width=32).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=4)

        ttk.Label(right, text="Nueva contraseña").grid(row=1, column=0, sticky="w")
        self.var_password = tk.StringVar()
        ttk.Entry(right, textvariable=self.var_password, show="*", width=32).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=4)
        ttk.Label(right, text="(dejar vacío para no cambiar al editar)", foreground=QDV_COLORS["muted"]).grid(
            row=2, column=1, sticky="w", padx=(8, 0)
        )

        self.var_is_admin = tk.BooleanVar(value=False)
        self.chk_admin = ttk.Checkbutton(
            right,
            text="Administrador (acceso total)",
            variable=self.var_is_admin,
            command=self._sync_perm_widgets_state,
        )
        self.chk_admin.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 4))

        self.var_activo = tk.BooleanVar(value=True)
        ttk.Checkbutton(right, text="Usuario activo", variable=self.var_activo).grid(row=4, column=0, columnspan=2, sticky="w", pady=4)

        ttk.Separator(right).grid(row=5, column=0, columnspan=2, sticky="ew", pady=12)

        ttk.Label(right, text="Permisos por módulo", font=("Segoe UI", 10, "bold")).grid(row=6, column=0, columnspan=2, sticky="w", pady=(0, 6))

        perms_f = ttk.Frame(right)
        perms_f.grid(row=7, column=0, columnspan=2, sticky="nsew")
        for i, key in enumerate(PERMISSION_KEYS):
            self._perm_vars[key] = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(perms_f, text=PERMISSION_LABELS.get(key, key), variable=self._perm_vars[key])
            cb.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 16), pady=2)
            self._perm_checks.append(cb)

        right.columnconfigure(1, weight=1)
        right.rowconfigure(7, weight=1)

        bar = ttk.Frame(root)
        bar.pack(fill="x", pady=(12, 0))
        ttk.Button(bar, text="Guardar cambios", style="QDV.Primary.TButton", command=self._save).pack(side="right", padx=(8, 0))
        ttk.Button(bar, text="Cerrar", style="QDV.Secondary.TButton", command=self.destroy).pack(side="right")

        self._reload_list()
        self._new_user()

    def _sync_perm_widgets_state(self) -> None:
        """Si es admin, los permisos no aplican (acceso total) — deshabilitar casillas."""
        st = "disabled" if self.var_is_admin.get() else "normal"
        for cb in self._perm_checks:
            try:
                cb.configure(state=st)
            except Exception:
                pass

    def _reload_list(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for u in self.db.fetch_usuarios_list():
            self.tree.insert(
                "",
                "end",
                iid=str(u["id"]),
                values=(u["id"], u["username"], "Sí" if u["is_admin"] else "No", "Sí" if u["activo"] else "No"),
            )

    def _on_select(self, _evt=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        try:
            uid = int(sel[0])
        except Exception:
            return
        self._load_user(uid)

    def _load_user(self, uid: int) -> None:
        u = self.db.fetch_usuario_by_id(uid)
        if not u:
            return
        self._editing_id = uid
        self.var_username.set(u["username"])
        self.var_password.set("")
        self.var_is_admin.set(bool(u["is_admin"]))
        self.var_activo.set(bool(u["activo"]))
        pmap = self.db.fetch_permisos_map(uid)
        for k in PERMISSION_KEYS:
            self._perm_vars[k].set(pmap.get(k, False))
        self._sync_perm_widgets_state()

    def _new_user(self) -> None:
        self.tree.selection_remove(self.tree.selection())
        self._editing_id = None
        self.var_username.set("")
        self.var_password.set("")
        self.var_is_admin.set(False)
        self.var_activo.set(True)
        for k in PERMISSION_KEYS:
            self._perm_vars[k].set(False)
        self._sync_perm_widgets_state()

    def _delete_user(self) -> None:
        if self._editing_id is None:
            messagebox.showwarning("Usuarios", "Seleccione un usuario o use Nuevo usuario.")
            return
        if self._editing_id == self.editor.user_id:
            messagebox.showerror("Usuarios", "No puede eliminar su propio usuario.")
            return
        u = self.db.fetch_usuario_by_id(self._editing_id)
        if not u:
            return
        if u.get("is_admin") and self.db.count_admins_activos() <= 1 and u.get("activo"):
            messagebox.showerror("Usuarios", "No puede eliminar el último administrador activo.")
            return
        if not messagebox.askyesno("Confirmar", f"¿Eliminar al usuario «{u['username']}»?"):
            return
        try:
            self.db.delete_usuario(self._editing_id)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
        self._reload_list()
        self._new_user()
        messagebox.showinfo("Usuarios", "Usuario eliminado.")

    def _save(self) -> None:
        name = (self.var_username.get() or "").strip()
        pw = self.var_password.get() or ""
        is_ad = self.var_is_admin.get()
        act = self.var_activo.get()

        if not name:
            messagebox.showerror("Usuarios", "El nombre de usuario es obligatorio.")
            return

        perms = {k: self._perm_vars[k].get() for k in PERMISSION_KEYS}

        try:
            if self._editing_id is None:
                if not pw:
                    messagebox.showerror("Usuarios", "Defina una contraseña para el usuario nuevo.")
                    return
                ph = hash_password(pw)
                uid = self.db.create_usuario(name, ph, int(is_ad), int(act))
                if not is_ad:
                    self.db.set_permisos_usuario(uid, perms)
                self._reload_list()
                self.tree.selection_set(str(uid))
                self._load_user(uid)
                messagebox.showinfo("Usuarios", "Usuario creado.")
                return

            u = self.db.fetch_usuario_by_id(self._editing_id)
            if not u:
                return
            if u.get("is_admin") and not is_ad and self.db.count_admins_activos() <= 1 and u.get("activo"):
                messagebox.showerror("Usuarios", "No puede quitar el rol administrador al último admin activo.")
                return

            self.db.update_usuario_core(self._editing_id, name, int(is_ad), int(act))
            if pw:
                self.db.update_usuario_password(self._editing_id, hash_password(pw))
            if not is_ad:
                self.db.set_permisos_usuario(self._editing_id, perms)
            else:
                self.db.set_permisos_usuario(self._editing_id, {})
            self._reload_list()
            self.tree.selection_set(str(self._editing_id))
            messagebox.showinfo("Usuarios", "Cambios guardados.")
        except sqlite3.IntegrityError:
            messagebox.showerror("Usuarios", "Ese nombre de usuario ya existe.")
        except Exception as e:
            messagebox.showerror("Error", str(e))
