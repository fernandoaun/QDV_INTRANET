"""Utilidades compartidas entre ventanas de Producción (Tkinter)."""
from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import messagebox
from typing import Callable, List, Optional

from qdv_salmuera.data.db import DB


def bind_excel_field_navigation(widgets: List[tk.Widget], on_save: Callable[[], None]) -> None:
    """
    ENTER → siguiente campo; en el último campo ENTER ejecuta on_save.
    SHIFT+ENTER → campo anterior.
    """
    if not widgets:
        return
    last_idx = len(widgets) - 1
    for i, w in enumerate(widgets):
        def _next(event, i=i):
            if i < last_idx:
                widgets[i + 1].focus_set()
            else:
                on_save()
            return "break"

        def _prev(event, i=i):
            if i > 0:
                widgets[i - 1].focus_set()
            return "break"

        w.bind("<Return>", _next)
        w.bind("<Shift-Return>", _prev)


def add_operador_via_dialog(parent: tk.Misc, db: DB) -> Optional[str]:
    """
    Abre el diálogo de alta de operador, persiste en DB y devuelve el nombre a seleccionar.
    Tras IntegrityError (ya existía) devuelve igual el nombre para refrescar el combo.
    Si el usuario cancela o hay error grave, devuelve None.
    """
    from qdv_salmuera.ui.dialogs import AddOperadorDialog

    dlg = AddOperadorDialog(parent)
    parent.wait_window(dlg)
    if not dlg.result:
        return None
    name = dlg.result
    try:
        db.add_operador(name)
    except sqlite3.IntegrityError:
        messagebox.showwarning("Atención", "Ese operador ya existe.", parent=parent)
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo agregar el operador.\n\nDetalle: {e}", parent=parent)
        return None
    return name
