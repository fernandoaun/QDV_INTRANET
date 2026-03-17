from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    OPENPYXL_OK = True
except ImportError:
    OPENPYXL_OK = False

from qdv_salmuera.data.db import DB

from .dialogs import MotivoAtrasoDialog

from qdv_salmuera.config.settings import (
    DEFAULT_OPERATORS,
    SECURITY_DELETE_CODE,
    VOLTAGE_MIN,
    VOLTAGE_MAX,
    ANALYSIS_INTERVAL_SECONDS,
)

from qdv_salmuera.utils.validators import (
    validate_float,
    validate_int,
    is_int_ok,
    is_float_ok,
    fmt_num,
)

from qdv_salmuera.utils.dates import (
    iso_to_ddmmyyyy,
    parse_date_ddmmyyyy,
    date_to_iso,
)

from qdv_salmuera.ui.widgets import ScrollableFrame
from qdv_salmuera.ui.dialogs import HistorialDialog, CodigoSeguridadDialog, AddOperadorDialog
from qdv_salmuera.ui.salmuera_edit import EditRegistroDialog

# PEGAR AQUÍ: class CircuitoSalmueraWindow (V4 1594–2575)
# =========================
# VENTANA: Circuito de Salmuera
# =========================
class CircuitoSalmueraWindow(tk.Toplevel):
    def __init__(self, master, db: DB):
        super().__init__(master)
        self.next_due_dt = None

        self.db = db

        self.title("Química del Valle - Producción - Circuito de Salmuera")
        self.geometry("1280x860")
        self.minsize(980, 680)

        now = datetime.now()
        self.fixed_date_ddmmyyyy = now.strftime("%d/%m/%Y")
        self.fixed_date_iso = now.strftime("%Y-%m-%d")

        self.var_fecha = tk.StringVar(value=self.fixed_date_ddmmyyyy)
        self.var_hora = tk.StringVar(value=now.strftime("%H:%M"))

        self.var_electrolizador = tk.StringVar()
        self.var_celdas = tk.StringVar()
        self.var_turno = tk.StringVar()

        self.var_amperaje = tk.StringVar()
        self.var_caudal_agua = tk.StringVar()
        self.var_caudal_salmuera = tk.StringVar()

        self.var_hipo_conc = tk.StringVar()
        self.var_hipo_exceso_soda = tk.StringVar()

        self.var_sal_temp = tk.StringVar()
        self.var_sal_conc = tk.StringVar()
        self.var_sal_ph = tk.StringVar()

        self.var_soda_conc = tk.StringVar()
        self.var_declor_ph = tk.StringVar()

        self.operadores = self.db.fetch_operadores()
        self.var_operador = tk.StringVar()
        self.cbo_operador = None

        self.txt_obs = None

        self.voltage_vars: List[tk.StringVar] = []
        self.voltage_container = None

        self.vcmd_float = (self.register(validate_float), "%P")
        self.vcmd_int = (self.register(validate_int), "%P")

        self.tree = None
        self.tree_cols = []
        self._selected_row_id: Optional[int] = None

        self.btn_guardar = None
        self.btn_historial = None
        self.btn_borrar = None
        self.lbl_status = None

        # Cronómetro análisis
        self.timer_seconds_left = ANALYSIS_INTERVAL_SECONDS
        self.timer_overdue = False
        self.lbl_timer = None
        self.var_timer = tk.StringVar(value="02:00:00")
        self.var_motivo_atraso = tk.StringVar()
        self.ent_motivo_atraso = None
        self._timer_job = None
        self._overdue_prompt_shown = False


        # Advertencias rojas grandes
        self.warn_caudad = None
        self.warn_voltajes = None

        self._build_ui()
        self._compute_timer_from_last_record_today()
        self._start_timer()
        self._wire_validation()
        self._refresh_save_state()
        self._load_day_table()


        if self.timer_overdue and (not self._overdue_prompt_shown):
            self._overdue_prompt_shown = True
            self.after(50, self._prompt_motivo_atraso)
        
        
    
    def _format_hhmmss(self, seconds: int) -> str:
        seconds = max(0, int(seconds))
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _set_timer_overdue_ui(self, overdue: bool):
        self.timer_overdue = overdue
        if getattr(self, "lbl_timer", None) is not None:
            self.lbl_timer.config(foreground=("red" if overdue else "black"))

        if getattr(self, "ent_motivo_atraso", None) is not None:
            if overdue:
                self.ent_motivo_atraso.configure(state="normal")
            else:
                self.var_motivo_atraso.set("")
                self.ent_motivo_atraso.configure(state="disabled")

    def _compute_timer_from_last_record_today(self):
        """
        Define el 'deadline' del próximo análisis (último registro + 2 horas)
        y calcula cuántos segundos faltan. Funciona aunque cierres el programa,
        porque depende de created_at_iso guardado en la DB.
        """
        now = datetime.now()

        # default: ahora + 2h
        self.next_due_dt = now + timedelta(seconds=ANALYSIS_INTERVAL_SECONDS)

        # estado previo (para detectar transición a vencido)
        prev_overdue = getattr(self, "timer_overdue", False)

        # Buscar último registro
        last = None
        try:
            last = self.db.fetch_last_salmuera()
        except Exception:
            last = None

        # Si hay último registro y tiene created_at_iso válido, usamos eso
        if last and last.get("created_at_iso"):
            try:
                created = datetime.fromisoformat(last["created_at_iso"])
                if created.tzinfo is not None:
                    created = created.astimezone().replace(tzinfo=None)

                self.next_due_dt = created + timedelta(seconds=ANALYSIS_INTERVAL_SECONDS)
            except Exception:
                # si falla parseo, queda default
                self.next_due_dt = now + timedelta(seconds=ANALYSIS_INTERVAL_SECONDS)

        # calcular restante
        remaining = int((self.next_due_dt - now).total_seconds())
        self.timer_seconds_left = max(0, remaining)

        # actualizar overdue
        self._set_timer_overdue_ui(self.timer_seconds_left <= 0)

        # si recién se venció, pedir motivo una sola vez
        if (not prev_overdue) and self.timer_overdue and (not getattr(self, "_overdue_prompt_shown", False)):
            self._overdue_prompt_shown = True
            self.after(10, self._prompt_motivo_atraso)


    def _start_timer(self):
        # Cancela el timer anterior si existe
        if getattr(self, "_timer_job", None) is not None:
            try:
                self.after_cancel(self._timer_job)
            except Exception:
                pass
            self._timer_job = None

        # Arranca el loop
        self._tick_timer()


    def _stop_timer(self):
        job = getattr(self, "_timer_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._timer_job = None

    def _tick_timer(self):
        # Si la ventana ya no existe, cortamos
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return

        try:
            now = datetime.now()

            # Si no tenemos deadline, recalculamos
            if self.next_due_dt is None:
                self._compute_timer_from_last_record_today()

            # Normalizar next_due_dt por si vino con tzinfo (evita TypeError)
            if self.next_due_dt is not None and getattr(self.next_due_dt, "tzinfo", None) is not None:
                self.next_due_dt = self.next_due_dt.astimezone().replace(tzinfo=None)

            # Calcular segundos restantes
            remaining = int((self.next_due_dt - now).total_seconds())
            self.timer_seconds_left = max(0, remaining)

            # Mostrar en pantalla
            # Mostrar en pantalla
            if self.lbl_timer is not None:
                self.var_timer.set(self._format_hhmmss(self.timer_seconds_left))

            # Estado vencido / no vencido
            self._set_timer_overdue_ui(self.timer_seconds_left <= 0)

            # Refrescar validación de Guardar
            try:
                self._refresh_save_state()
            except Exception:
                pass

        except Exception as e:
            # Si algo falla, lo ves en el reloj (así no queda "02:00:00" engañoso)
            try:
                if self.lbl_timer is not None:
                    self.var_timer.set(f"ERR: {type(e).__name__}")
            except Exception:
                pass

        finally:
            # Pase lo que pase, reprogramar cada 1 segundo
            self._timer_job = self.after(1000, self._tick_timer)


    def destroy(self):
        # importante: frenar after para que no quede corriendo
        try:
            self._stop_timer()
        except Exception:
            pass
        super().destroy()


    def _add_operador(self):
        dlg = AddOperadorDialog(self)
        self.wait_window(dlg)
        if not dlg.result:
            return
        try:
            self.db.add_operador(dlg.result)
        except sqlite3.IntegrityError:
            messagebox.showwarning("Atención", "Ese operador ya existe.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo agregar el operador.\n\nDetalle: {e}")
            return

        self.operadores = self.db.fetch_operadores()
        self.cbo_operador["values"] = self.operadores
        self.var_operador.set(dlg.result)
        self._refresh_save_state()

    def _build_ui(self):
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="Circuito de Salmuera", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Label(header, text=f"Día: {self.fixed_date_ddmmyyyy}", font=("Segoe UI", 11)).pack(side="right")

        pw = ttk.Panedwindow(outer, orient="vertical")
        pw.pack(fill="both", expand=True)

        top_frame = ttk.Frame(pw)
        bottom_frame = ttk.Frame(pw)
        pw.add(top_frame, weight=1)
        pw.add(bottom_frame, weight=1)

        form_box = ttk.LabelFrame(top_frame, text="Registro", padding=10)
        form_box.pack(fill="both", expand=True)

        sc = ScrollableFrame(form_box)
        sc.pack(fill="both", expand=True)
        body = sc.inner

        reg = ttk.Frame(body)
        reg.pack(fill="x", pady=(0, 10))
        ttk.Label(reg, text="Fecha:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(reg, textvariable=self.var_fecha, width=14, state="readonly").grid(row=0, column=1, sticky="w", padx=(0, 18), pady=4)
        ttk.Label(reg, text="Hora:").grid(row=0, column=2, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(reg, textvariable=self.var_hora, width=10, state="readonly").grid(row=0, column=3, sticky="w", pady=4)

        # =========================
        # CRONÓMETRO DE ANÁLISIS (2 HORAS)
        # =========================
        timer_box = ttk.LabelFrame(body, text="Cronómetro de análisis (cada 2 horas)", padding=10)
        timer_box.pack(fill="x", pady=(0, 10))

        trow = ttk.Frame(timer_box)
        trow.pack(fill="x")

        ttk.Label(trow, text="Tiempo restante:").pack(side="left")
        self.lbl_timer = ttk.Label(
            trow,
            textvariable=self.var_timer,
            font=("Segoe UI", 16, "bold")
        )

        self.lbl_timer.pack(side="left", padx=(10, 0))

        ttk.Label(
            timer_box,
            text="Si el tiempo venció, debe indicar el motivo del atraso para poder guardar.",
            font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(6, 0))

        mot = ttk.Frame(timer_box)
        mot.pack(fill="x", pady=(6, 0))

        ttk.Label(mot, text="Motivo atraso (obligatorio si venció):").pack(side="left")

        self.ent_motivo_atraso = ttk.Entry(
            mot,
            textvariable=self.var_motivo_atraso,
            width=80
        )
        self.ent_motivo_atraso.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self.ent_motivo_atraso.configure(state="disabled")


        gen = ttk.LabelFrame(body, text="Información general", padding=10)
        gen.pack(fill="x", pady=(0, 10))
        gg = ttk.Frame(gen)
        gg.pack(fill="x")
        gg.columnconfigure(1, weight=1)
        gg.columnconfigure(3, weight=1)

        ttk.Label(gg, text="Electrolizador (N°):").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(gg, textvariable=self.var_electrolizador, validate="key", validatecommand=self.vcmd_int, width=20)\
            .grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(gg, text="Cantidad de celdas:").grid(row=0, column=2, sticky="w", padx=(18, 8), pady=4)
        ttk.Entry(gg, textvariable=self.var_celdas, validate="key", validatecommand=self.vcmd_int, width=20)\
            .grid(row=0, column=3, sticky="w", pady=4)

        ttk.Label(gg, text="Turno:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(gg, textvariable=self.var_turno, values=["M", "T", "N"], width=18, state="readonly")\
            .grid(row=1, column=1, sticky="w", pady=4)

        volt = ttk.LabelFrame(body, text="Voltaje de celdas", padding=10)
        volt.pack(fill="x", pady=(0, 10))

        self.warn_voltajes = ttk.Label(
            volt,
            text=f"ADVERTENCIA: Cada voltaje de celda debe estar entre {VOLTAGE_MIN} y {VOLTAGE_MAX}.",
            font=("Segoe UI", 12, "bold"),
            foreground="red"
        )
        self.warn_voltajes.pack(anchor="w", pady=(0, 8))

        self.voltage_container = ttk.Frame(volt)
        self.voltage_container.pack(fill="x")

        proc = ttk.LabelFrame(body, text="Proceso", padding=10)
        proc.pack(fill="x", pady=(0, 10))
        pg = ttk.Frame(proc)
        pg.pack(fill="x")
        pg.columnconfigure(1, weight=1)
        pg.columnconfigure(3, weight=1)

        ttk.Label(pg, text="Amperaje:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(pg, textvariable=self.var_amperaje, validate="key", validatecommand=self.vcmd_float, width=20)\
            .grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(pg, text="Caudal agua (L/h):").grid(row=0, column=2, sticky="w", padx=(18, 8), pady=4)
        ttk.Entry(pg, textvariable=self.var_caudal_agua, validate="key", validatecommand=self.vcmd_float, width=20)\
            .grid(row=0, column=3, sticky="w", pady=4)

        ttk.Label(pg, text="Caudal salmuera (L/h):").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(pg, textvariable=self.var_caudal_salmuera, validate="key", validatecommand=self.vcmd_float, width=20)\
            .grid(row=1, column=1, sticky="w", pady=4)

        self.warn_caudad = ttk.Label(
            proc,
            text="ADVERTENCIA: Caudal de salmuera DEBE ser mayor al caudal de agua.",
            font=("Segoe UI", 12, "bold"),
            foreground="red"
        )
        self.warn_caudad.pack(anchor="w", pady=(8, 0))

        hipo = ttk.LabelFrame(body, text="Hipoclorito", padding=10)
        hipo.pack(fill="x", pady=(0, 10))
        hg = ttk.Frame(hipo)
        hg.pack(fill="x")
        hg.columnconfigure(1, weight=1)
        hg.columnconfigure(3, weight=1)

        ttk.Label(hg, text="Concentración:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(hg, textvariable=self.var_hipo_conc, validate="key", validatecommand=self.vcmd_float, width=20)\
            .grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(hg, text="Exceso de soda:").grid(row=0, column=2, sticky="w", padx=(18, 8), pady=4)
        ttk.Entry(hg, textvariable=self.var_hipo_exceso_soda, validate="key", validatecommand=self.vcmd_float, width=20)\
            .grid(row=0, column=3, sticky="w", pady=4)

        sal = ttk.LabelFrame(body, text="Salmuera a la salida de la celda", padding=10)
        sal.pack(fill="x", pady=(0, 10))
        sg = ttk.Frame(sal)
        sg.pack(fill="x")
        sg.columnconfigure(1, weight=1)
        sg.columnconfigure(3, weight=1)

        ttk.Label(sg, text="Temperatura:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(sg, textvariable=self.var_sal_temp, validate="key", validatecommand=self.vcmd_float, width=20)\
            .grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(sg, text="Concentración:").grid(row=0, column=2, sticky="w", padx=(18, 8), pady=4)
        ttk.Entry(sg, textvariable=self.var_sal_conc, validate="key", validatecommand=self.vcmd_float, width=20)\
            .grid(row=0, column=3, sticky="w", pady=4)

        ttk.Label(sg, text="pH:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(sg, textvariable=self.var_sal_ph, validate="key", validatecommand=self.vcmd_float, width=20)\
            .grid(row=1, column=1, sticky="w", pady=4)

        soda = ttk.LabelFrame(body, text="Soda a la salida de la celda", padding=10)
        soda.pack(fill="x", pady=(0, 10))
        sodag = ttk.Frame(soda)
        sodag.pack(fill="x")
        ttk.Label(sodag, text="Concentración:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(sodag, textvariable=self.var_soda_conc, validate="key", validatecommand=self.vcmd_float, width=20)\
            .grid(row=0, column=1, sticky="w", pady=4)

        decl = ttk.LabelFrame(body, text="Declorinación", padding=10)
        decl.pack(fill="x", pady=(0, 10))
        dg = ttk.Frame(decl)
        dg.pack(fill="x")
        ttk.Label(dg, text="pH:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(dg, textvariable=self.var_declor_ph, validate="key", validatecommand=self.vcmd_float, width=20)\
            .grid(row=0, column=1, sticky="w", pady=4)

        end = ttk.LabelFrame(body, text="Cierre", padding=10)
        end.pack(fill="x", pady=(0, 10))
        eg = ttk.Frame(end)
        eg.pack(fill="x")
        eg.columnconfigure(1, weight=1)

        ttk.Label(eg, text="Operador:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)

        op_frame = ttk.Frame(eg)
        op_frame.grid(row=0, column=1, sticky="w", pady=4)

        self.cbo_operador = ttk.Combobox(op_frame, textvariable=self.var_operador, values=self.operadores,
                                         width=35, state="readonly")
        self.cbo_operador.pack(side="left")
        ttk.Button(op_frame, text="+", width=3, command=self._add_operador).pack(side="left", padx=(8, 0))

        ttk.Label(end, text="Observaciones (opcional):").pack(anchor="w", pady=(8, 4))
        self.txt_obs = tk.Text(end, height=4, wrap="word")
        self.txt_obs.pack(fill="x")

        act = ttk.Frame(body)
        act.pack(fill="x", pady=(4, 0))

        self.lbl_status = ttk.Label(act, text="", font=("Segoe UI", 10))
        self.lbl_status.pack(side="left", fill="x", expand=True)

        self.btn_historial = ttk.Button(act, text="Historial (Excel)", command=self.on_historial)
        self.btn_historial.pack(side="right")

        self.btn_guardar = ttk.Button(act, text="Guardar", command=self.on_save)
        self.btn_guardar.pack(side="right", padx=(8, 8))

        ttk.Button(act, text="Cerrar", command=self.destroy).pack(side="right")

        bottom_box = ttk.LabelFrame(bottom_frame, text="Registros del día (solo hoy) - Doble clic para editar", padding=10)
        bottom_box.pack(fill="both", expand=True)

        toolbar = ttk.Frame(bottom_box)
        toolbar.pack(fill="x", pady=(0, 8))

        ttk.Label(toolbar, text="Tip: doble clic sobre una fila para editar cualquier parámetro.", font=("Segoe UI", 9))\
            .pack(side="left")
        self.btn_borrar = ttk.Button(toolbar, text="Borrar seleccionado", command=self.on_delete_selected)
        self.btn_borrar.pack(side="right")

        tv_wrap = ttk.Frame(bottom_box)
        tv_wrap.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(tv_wrap, columns=(), show="headings")
        vsb = ttk.Scrollbar(tv_wrap, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(bottom_box, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._on_tree_double_click)

    def _on_tree_select(self, _event):
        sel = self.tree.selection()
        if not sel:
            self._selected_row_id = None
            return
        vals = self.tree.item(sel[0], "values")
        if not vals:
            self._selected_row_id = None
            return
        try:
            self._selected_row_id = int(vals[0])
        except Exception:
            self._selected_row_id = None

    def _on_tree_double_click(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        if not vals:
            return
        try:
            rid = int(vals[0])
        except Exception:
            return

        dlg = EditRegistroDialog(self, self.db, rid)
        self.wait_window(dlg)
        self.operadores = self.db.fetch_operadores()
        self.cbo_operador["values"] = self.operadores
        self._load_day_table()

    def _clear_voltage_fields(self):
        for w in self.voltage_container.winfo_children():
            w.destroy()
        self.voltage_vars = []

    def _validate_voltages_rule(self, n: int) -> Tuple[bool, str]:
        voltajes = []
        for i, var in enumerate(self.voltage_vars):
            s = var.get().strip()
            if not s:
                return False, "Complete los voltajes."
            try:
                v = float(s)
            except Exception:
                return False, "Voltajes: solo números y punto (.)"
            voltajes.append(v)

        # Si hay más de 1 celda, aplicar rango por celda
        if n > 1:
            for i, v in enumerate(voltajes):
                if v < VOLTAGE_MIN or v > VOLTAGE_MAX:
                    return False, f"ADVERTENCIA: Voltaje de celda {i+1} fuera de rango ({VOLTAGE_MIN} a {VOLTAGE_MAX})."

        return True, "OK"


    def _rebuild_voltage_fields(self):
        raw = self.var_celdas.get().strip()
        if raw == "" or (not raw.isdigit()):
            self._clear_voltage_fields()
            self._refresh_save_state()
            return

        n = int(raw)
        if n <= 0 or n > 200:
            self._clear_voltage_fields()
            self._refresh_save_state()
            return

        if len(self.voltage_vars) == n:
            self._refresh_save_state()
            return

        self._clear_voltage_fields()
        per_row = 8

        for i in range(n):
            var = tk.StringVar()
            var.trace_add("write", lambda *_: self._refresh_save_state())
            self.voltage_vars.append(var)

            r = i // per_row
            c = (i % per_row) * 2
            label_txt = "Voltaje total:" if n == 1 else f"V{i+1}:"
            ttk.Label(self.voltage_container, text=label_txt).grid(row=r, column=c, sticky="e", padx=(0, 6), pady=3)

            ttk.Entry(self.voltage_container, textvariable=var, width=9, validate="key", validatecommand=self.vcmd_float)\
                .grid(row=r, column=c + 1, sticky="w", padx=(0, 14), pady=3)

        self._refresh_save_state()

    def _wire_validation(self):
        vars_to_trace = [
            self.var_electrolizador, self.var_celdas, self.var_turno,
            self.var_amperaje, self.var_caudal_agua, self.var_caudal_salmuera,
            self.var_hipo_conc, self.var_hipo_exceso_soda,
            self.var_sal_temp, self.var_sal_conc, self.var_sal_ph,
            self.var_soda_conc, self.var_declor_ph,
            self.var_operador
        ]
        for v in vars_to_trace:
            v.trace_add("write", lambda *_: self._refresh_save_state())

        self.var_celdas.trace_add("write", lambda *_: self._rebuild_voltage_fields())
        self.txt_obs.bind("<KeyRelease>", lambda _e: self._refresh_save_state())

    def _validate_all(self):
        n = 0
        try: n = int(self.var_celdas.get().strip())
        except: return False, "Cantidad de celdas inválida."

        if not is_int_ok(self.var_electrolizador.get()):
            return False, "Electrolizador debe ser numérico entero."
        if not is_int_ok(self.var_celdas.get()):
            return False, "Cantidad de celdas debe ser numérica entera."

        # Regla especial:
        # Si cantidad_celdas == 1, se permite solo 2 veces seguidas por electrolizador.
        if n == 1:
            elect = int(self.var_electrolizador.get().strip())
            consec = self._count_consecutive_single_cell(elect)
            if consec >= 2:
                return False, "ADVERTENCIA: Para este electrolizador ya hubo 2 registros seguidos con 1 celda. En la tercera carga, la cantidad de celdas debe ser distinta de 1."

        n = int(self.var_celdas.get().strip())
        if n <= 0:
            return False, "Cantidad de celdas debe ser mayor que 0."
        if len(self.voltage_vars) != n:
            return False, "Complete los voltajes según la cantidad de celdas."

        if self.var_turno.get().strip() not in ("M", "T", "N"):
            return False, "Turno es obligatorio (M, T o N)."

        # Validación de voltajes
        voltajes = []
        for i, var in enumerate(self.voltage_vars):
            s = var.get().strip()
            if not s:
                return False, "Complete los voltajes."
            try:
                v = float(s)
            except Exception:
                return False, "Voltajes: solo números y punto (.)"
            voltajes.append(v)

        # Regla: rango por celda SOLO si hay más de 1 celda
        # Si n == 1, es Voltaje total (manual) y puede ser > 4.5
        if n > 1:
            for i, v in enumerate(voltajes):
                if v < VOLTAGE_MIN or v > VOLTAGE_MAX:
                    return False, f"ADVERTENCIA: Voltaje de celda {i+1} fuera de rango ({VOLTAGE_MIN} a {VOLTAGE_MAX})."


        checks = [
            ("Amperaje", self.var_amperaje.get()),
            ("Caudal agua (L/h)", self.var_caudal_agua.get()),
            ("Caudal salmuera (L/h)", self.var_caudal_salmuera.get()),
            ("Hipoclorito - Concentración", self.var_hipo_conc.get()),
            ("Hipoclorito - Exceso de soda", self.var_hipo_exceso_soda.get()),
            ("Salmuera salida - Temperatura", self.var_sal_temp.get()),
            ("Salmuera salida - Concentración", self.var_sal_conc.get()),
            ("Salmuera salida - pH", self.var_sal_ph.get()),
            ("Soda salida - Concentración", self.var_soda_conc.get()),
            ("Declorinación - pH", self.var_declor_ph.get()),
        ]
        for label, val in checks:
            if not is_float_ok(val):
                return False, f"{label} es obligatorio y debe ser numérico (usar punto)."

        q_agua = float(self.var_caudal_agua.get().strip())
        q_sal = float(self.var_caudal_salmuera.get().strip())

        # Regla: Salmuera SIEMPRE mayor que Agua
        if q_sal <= q_agua:
            return False, "ADVERTENCIA: Caudal de salmuera DEBE ser mayor al caudal de agua."


        op = self.var_operador.get().strip()
        if not op:
            return False, "Operador es obligatorio."
        if op not in self.operadores:
            return False, "Operador inválido. Seleccione uno del desplegable o agregue uno nuevo con +."

        # Si el cronómetro venció, motivo es obligatorio
        if self.timer_overdue:
            if not self.var_motivo_atraso.get().strip():
                return False, "ADVERTENCIA: Análisis vencido. Debe indicar el motivo del atraso para poder guardar."

        return True, "OK"
    
    def _prompt_motivo_atraso(self):
            dlg = MotivoAtrasoDialog(self)
            self.wait_window(dlg)
            if dlg.result:
                self.var_motivo_atraso.set(dlg.result)
                # Si tenés entry en pantalla, le podés dar foco a Guardar
                try:
                    self._refresh_save_state()
                except Exception:
                    pass

    
    def _count_consecutive_single_cell(self, electrolizador: int) -> int:
        """
        Cuenta cuántos registros consecutivos más recientes tienen cantidad_celdas = 1
        para el electrolizador indicado.
        """
        try:
            rows = self.db.fetch_last_salmuera_by_electrolizador(electrolizador, limit=10)
        except Exception:
            return 0

        count = 0
        for r in rows:
            try:
                if int(r.get("cantidad_celdas", 0)) == 1:
                    count += 1
                else:
                    break
            except Exception:
                break
        return count


    def _refresh_save_state(self):
        ok, msg = self._validate_all()

        # Mostrar mensaje rojo grande si no está OK (si usás un label de estado)
        if hasattr(self, "lbl_status") and self.lbl_status is not None:
            if ok:
                self.lbl_status.config(text="")
            else:
                self.lbl_status.config(text=msg, foreground="red", font=("Segoe UI", 12, "bold"))

        # Habilitar / deshabilitar Guardar
        if hasattr(self, "btn_guardar") and self.btn_guardar is not None:
            self.btn_guardar.configure(state=("normal" if ok else "disabled"))


    def _build_tree_columns_for_day(self, registros: List[Dict[str, Any]]):
        max_celdas = 0
        for r in registros:
            try:
                max_celdas = max(max_celdas, int(r["cantidad_celdas"]))
            except Exception:
                pass

        cols = [
            ("id", "ID", 60),
            ("fecha", "Fecha", 90),
            ("hora", "Hora", 70),
            ("elect", "Elect.", 70),
            ("celdas", "Celdas", 70),
            ("turno", "Turno", 70),
        ]
        for i in range(1, max_celdas + 1):
            cols.append((f"v{i}", f"V{i}", 75))
        cols += [
            ("vtotal", "V Total", 80),
            ("amper", "Amperaje", 85),
            ("qagua", "Q Agua (L/h)", 100),
            ("qsal", "Q Salmuera (L/h)", 115),
            ("hipoc", "Hipo Conc", 85),
            ("hipexs", "Hipo Exceso Soda", 130),
            ("stemp", "Sal T°", 75),
            ("sconc", "Sal Conc", 85),
            ("sph", "Sal pH", 75),
            ("sodac", "Soda Conc", 95),
            ("dph", "Declor pH", 85),
            ("oper", "Operador", 140),
            ("obs", "Observaciones", 260),
            ("creado", "Creado", 160),
        ]

        self.tree_cols = [c[0] for c in cols]
        self.tree.configure(columns=self.tree_cols)

        for col_key, col_title, col_w in cols:
            self.tree.heading(col_key, text=col_title)
            anchor = "w" if col_key in ("oper", "obs", "creado") else "center"
            self.tree.column(col_key, width=col_w, anchor=anchor, stretch=False)

    def _load_day_table(self):
        registros = self.db.fetch_salmuera_by_date(self.fixed_date_iso)
        self._build_tree_columns_for_day(registros)

        for item in self.tree.get_children():
            self.tree.delete(item)

        for r in registros:
            volts = r["voltajes_celdas"] or []
            row = [
                r["id"],
                iso_to_ddmmyyyy(r["fecha_iso"]),
                r["hora_hm"],
                r["electrolizador"],
                r["cantidad_celdas"],
                r["turno"],
            ]

            v_cols = [c for c in self.tree_cols if c.startswith("v") and c[1:].isdigit()]
            vmax = len(v_cols)
            for i in range(vmax):
                row.append(fmt_num(volts[i]) if i < len(volts) else "")

            row += [
                fmt_num(r["voltaje_total"]),
                fmt_num(r["amperaje"]),
                fmt_num(r["caudal_agua_l_h"]),
                fmt_num(r["caudal_salmuera_l_h"]),
                fmt_num(r["hipo_conc"]),
                fmt_num(r["hipo_exceso_soda"]),
                fmt_num(r["sal_temp"]),
                fmt_num(r["sal_conc"]),
                fmt_num(r["sal_ph"]),
                fmt_num(r["soda_conc"]),
                fmt_num(r["declor_ph"]),
                r["operador"],
                (r.get("observaciones", "") or ""),
                r["created_at_iso"],
            ]
            self.tree.insert("", "end", values=row)

        self._selected_row_id = None

    def on_save(self):
        import traceback
        try:
            # 1) Validar
            ok, msg = self._validate_all()
            if not ok:
                messagebox.showerror("No se puede guardar", msg)
                return

            # 2) Armar datos mínimos y guardar
            now = datetime.now()
            n = int(self.var_celdas.get().strip())

            voltajes = []
            for var in self.voltage_vars:
                voltajes.append(float(var.get().strip()))

            data = {
                "fecha_iso": self.fixed_date_iso,
                "hora_hm": now.strftime("%H:%M"),
                "electrolizador": int(self.var_electrolizador.get().strip()),
                "cantidad_celdas": n,
                "turno": self.var_turno.get().strip(),

                "voltajes_celdas": voltajes,
                "voltaje_total": float(sum(voltajes)),

                "amperaje": float(self.var_amperaje.get().strip()),
                "caudal_agua_l_h": float(self.var_caudal_agua.get().strip()),
                "caudal_salmuera_l_h": float(self.var_caudal_salmuera.get().strip()),

                "hipo_conc": float(self.var_hipo_conc.get().strip()),
                "hipo_exceso_soda": float(self.var_hipo_exceso_soda.get().strip()),

                "sal_temp": float(self.var_sal_temp.get().strip()),
                "sal_conc": float(self.var_sal_conc.get().strip()),
                "sal_ph": float(self.var_sal_ph.get().strip()),

                "soda_conc": float(self.var_soda_conc.get().strip()),
                "declor_ph": float(self.var_declor_ph.get().strip()),

                "operador": self.var_operador.get().strip(),
                "observaciones": self.txt_obs.get("1.0", "end").strip(),
                "atraso_motivo": self.var_motivo_atraso.get().strip(),

                "created_at_iso": now.isoformat(timespec="seconds"),
            }

            # Insertar una sola vez
            self.db.insert_salmuera(data)

            # Refrescar tabla
            self._load_day_table()

            # Confirmar
            messagebox.showinfo("OK", "Registro guardado correctamente.")

            # Recalcular deadline desde momento real de guardado
            created = datetime.fromisoformat(data["created_at_iso"])
            if created.tzinfo is not None:
                created = created.astimezone().replace(tzinfo=None)

            self.next_due_dt = created + timedelta(seconds=ANALYSIS_INTERVAL_SECONDS)

            # Reiniciar timer correctamente
            self._start_timer()

        except Exception as e:
            messagebox.showerror("Error al guardar", f"{e}\n\n{traceback.format_exc()}")


    def _clear_form(self):
        self.var_electrolizador.set("")
        self.var_celdas.set("")
        self.var_turno.set("")
        self._clear_voltage_fields()

        self.var_amperaje.set("")
        self.var_caudal_agua.set("")
        self.var_caudal_salmuera.set("")

        self.var_hipo_conc.set("")
        self.var_hipo_exceso_soda.set("")

        self.var_sal_temp.set("")
        self.var_sal_conc.set("")
        self.var_sal_ph.set("")

        self.var_soda_conc.set("")
        self.var_declor_ph.set("")

        self.var_operador.set("")
        self.txt_obs.delete("1.0", "end")

        self._refresh_save_state()

    def on_delete_selected(self):
        if self._selected_row_id is None:
            messagebox.showwarning("Atención", "Seleccione un registro en la tabla para borrarlo.")
            return

        dlg = CodigoSeguridadDialog(self, title="Borrar registro - Código de seguridad")
        self.wait_window(dlg)
        if dlg.result is None:
            return

        if dlg.result != SECURITY_DELETE_CODE:
            messagebox.showerror("Código incorrecto", "Código de seguridad inválido. No se borró el registro.")
            return

        if not messagebox.askyesno("Confirmar", f"¿Confirma borrar el registro ID {self._selected_row_id}?"):
            return

        try:
            self.db.delete_salmuera_by_id(self._selected_row_id)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo borrar el registro.\n\nDetalle: {e}")
            return

        self._load_day_table()
        messagebox.showinfo("OK", f"Registro ID {self._selected_row_id} eliminado.")

    def on_historial(self):
        if not OPENPYXL_OK:
            messagebox.showerror("Falta dependencia", "Para exportar a Excel instalá:\n\npip install openpyxl")
            return

        hoy_ddmmyyyy = datetime.now().strftime("%d/%m/%Y")
        dlg = HistorialDialog(self, default_desde=hoy_ddmmyyyy, default_hasta=hoy_ddmmyyyy)
        self.wait_window(dlg)
        if not dlg.result:
            return

        desde_s, hasta_s = dlg.result
        d1 = parse_date_ddmmyyyy(desde_s)
        d2 = parse_date_ddmmyyyy(hasta_s)
        if not d1 or not d2:
            messagebox.showerror("Error", "Rango de fechas inválido.")
            return

        desde_iso = date_to_iso(d1)
        hasta_iso = date_to_iso(d2)

        try:
            registros = self.db.fetch_salmuera_range(desde_iso, hasta_iso)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el historial.\n\nDetalle: {e}")
            return

        if not registros:
            messagebox.showinfo("Sin datos", "No hay registros en el rango seleccionado.")
            return

        default_name = f"historial_salmuera_{desde_iso}_a_{hasta_iso}.xlsx"
        save_path = filedialog.asksaveasfilename(
            title="Guardar reporte Excel",
            defaultextension=".xlsx",
            initialfile=default_name,
            filetypes=[("Excel", "*.xlsx")]
        )
        if not save_path:
            return

        try:
            self._export_excel(registros, save_path)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo generar el Excel.\n\nDetalle: {e}")
            return

        messagebox.showinfo("OK", f"Reporte generado:\n{save_path}")

    def _export_excel(self, registros: List[Dict[str, Any]], path: str):
        max_celdas = 0
        for r in registros:
            try:
                max_celdas = max(max_celdas, int(r["cantidad_celdas"]))
            except Exception:
                pass

        wb = Workbook()
        ws = wb.active
        ws.title = "Historial Salmuera"

        headers = ["ID", "Fecha", "Hora", "Electrolizador", "Cantidad Celdas", "Turno"]
        for i in range(1, max_celdas + 1):
            headers.append(f"V{i}")
        headers.append("Voltaje Total")
        headers += [
            "Amperaje", "Caudal Agua (L/h)", "Caudal Salmuera (L/h)",
            "Hipoclorito - Concentración", "Hipoclorito - Exceso Soda",
            "Salmuera Salida - Temperatura", "Salmuera Salida - Concentración", "Salmuera Salida - pH",
            "Soda Salida - Concentración", "Declorinación - pH",
            "Operador", "Observaciones", "Creado (ISO)"
        ]
        ws.append(headers)

        for r in registros:
            row = [
                r["id"],
                iso_to_ddmmyyyy(r["fecha_iso"]),
                r["hora_hm"],
                r["electrolizador"],
                r["cantidad_celdas"],
                r["turno"],
            ]
            volts = r["voltajes_celdas"] or []
            for i in range(max_celdas):
                row.append(volts[i] if i < len(volts) else "")
            row.append(r["voltaje_total"])

            row += [
                r["amperaje"],
                r["caudal_agua_l_h"],
                r["caudal_salmuera_l_h"],
                r["hipo_conc"],
                r["hipo_exceso_soda"],
                r["sal_temp"],
                r["sal_conc"],
                r["sal_ph"],
                r["soda_conc"],
                r["declor_ph"],
                r["operador"],
                r.get("observaciones", ""),
                r["created_at_iso"]
            ]
            ws.append(row)

        for col_idx in range(1, len(headers) + 1):
            col_letter = get_column_letter(col_idx)
            max_len = 0
            for cell in ws[col_letter]:
                v = "" if cell.value is None else str(cell.value)
                max_len = max(max_len, len(v))
            ws.column_dimensions[col_letter].width = min(max(10, max_len + 2), 40)

        wb.save(path)