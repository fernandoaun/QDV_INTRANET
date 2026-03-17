from __future__ import annotations

import re
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Tuple

from qdv_salmuera.data.db import DB

from qdv_salmuera.config.settings import (
    VOLTAGE_MIN,
    VOLTAGE_MAX,
)

from qdv_salmuera.ui.widgets import ScrollableFrame
from qdv_salmuera.ui.dialogs import AddOperadorDialog

from qdv_salmuera.utils.validators import (
    validate_float,
    validate_int,
    is_int_ok,
    is_float_ok,
)

from qdv_salmuera.utils.dates import (
    iso_to_ddmmyyyy,
    parse_date_ddmmyyyy,
    date_to_iso,
)


# PEGAR AQUÍ: class EditRegistroDialog (V4 1098–1593)
# =========================
# EDIT DIALOG (Salmuera) - doble clic
# =========================
class EditRegistroDialog(tk.Toplevel):
    def __init__(self, master, db: DB, registro_id: int):
        super().__init__(master)
        self.db = db
        self.registro_id = registro_id
        self.title(f"Editar registro (Salmuera) ID {registro_id}")
        self.geometry("980x760")
        self.minsize(860, 640)

        self.vcmd_float = (self.register(validate_float), "%P")
        self.vcmd_int = (self.register(validate_int), "%P")

        r = self.db.fetch_salmuera_by_id(registro_id)
        if not r:
            messagebox.showerror("Error", "No se encontró el registro para editar.")
            self.destroy()
            return
        self.original = r

        self.var_fecha = tk.StringVar(value=iso_to_ddmmyyyy(r["fecha_iso"]))
        self.var_hora = tk.StringVar(value=r["hora_hm"])

        self.var_electrolizador = tk.StringVar(value=str(r["electrolizador"]))
        self.var_celdas = tk.StringVar(value=str(r["cantidad_celdas"]))
        self.var_turno = tk.StringVar(value=str(r["turno"]))

        self.var_amperaje = tk.StringVar(value=str(r["amperaje"]))
        self.var_caudal_agua = tk.StringVar(value=str(r["caudal_agua_l_h"]))
        self.var_caudal_salmuera = tk.StringVar(value=str(r["caudal_salmuera_l_h"]))

        self.var_hipo_conc = tk.StringVar(value=str(r["hipo_conc"]))
        self.var_hipo_exceso_soda = tk.StringVar(value=str(r["hipo_exceso_soda"]))

        self.var_sal_temp = tk.StringVar(value=str(r["sal_temp"]))
        self.var_sal_conc = tk.StringVar(value=str(r["sal_conc"]))
        self.var_sal_ph = tk.StringVar(value=str(r["sal_ph"]))

        self.var_soda_conc = tk.StringVar(value=str(r["soda_conc"]))
        self.var_declor_ph = tk.StringVar(value=str(r["declor_ph"]))

        self.var_operador = tk.StringVar(value=str(r["operador"]))
        self.operadores = self.db.fetch_operadores()
        self.var_motivo_atraso = tk.StringVar(value=str(r.get("atraso_motivo", "")))

        self.voltage_vars: List[tk.StringVar] = []
        self.voltage_container = None

        self.txt_obs = None
        self.btn_save = None
        self.lbl_status = None
        self.cbo_operador = None

        # Advertencias rojas grandes
        self.warn_caudad = None
        self.warn_voltajes = None

        self._build_ui()
        self._wire_validation()
        self._rebuild_voltage_fields(prefill=r["voltajes_celdas"])
        self._refresh_save_state()

        self.grab_set()

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

    def _build_ui(self):
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text=f"Editar registro (Salmuera) ID {self.registro_id}",
                  font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 8))

        sc = ScrollableFrame(outer)
        sc.pack(fill="both", expand=True)
        body = sc.inner

        reg = ttk.LabelFrame(body, text="Registro", padding=10)
        reg.pack(fill="x", pady=(0, 10))
        row = ttk.Frame(reg)
        row.pack(fill="x")

        ttk.Label(row, text="Fecha (dd/mm/aaaa):").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(row, textvariable=self.var_fecha, width=14).grid(row=0, column=1, sticky="w", padx=(0, 18), pady=4)

        ttk.Label(row, text="Hora (HH:MM):").grid(row=0, column=2, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(row, textvariable=self.var_hora, width=10).grid(row=0, column=3, sticky="w", pady=4)

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
        self.txt_obs.insert("1.0", self.original.get("observaciones", ""))

        act = ttk.Frame(body)
        act.pack(fill="x", pady=(6, 0))

        self.lbl_status = ttk.Label(act, text="", font=("Segoe UI", 10))
        self.lbl_status.pack(side="left", fill="x", expand=True)

        self.btn_save = ttk.Button(act, text="Guardar cambios", command=self.on_save)
        self.btn_save.pack(side="right", padx=(8, 0))
        ttk.Button(act, text="Cancelar", command=self.destroy).pack(side="right")

    def _clear_voltage_fields(self):
        for w in self.voltage_container.winfo_children():
            w.destroy()
        self.voltage_vars = []

    def _rebuild_voltage_fields(self, prefill=None):
        # Limpia campos anteriores
        for w in self.voltage_container.winfo_children():
            w.destroy()

        self.voltage_vars = []

        try:
            n = int(self.var_celdas.get().strip())
        except Exception:
            return

        if n <= 0:
            return

        per_row = 4  # cantidad de campos por fila

        for i in range(n):
            var = tk.StringVar()
            var.trace_add("write", lambda *_: self._refresh_save_state())
            self.voltage_vars.append(var)

            r = i // per_row
            c = (i % per_row) * 2

            if n == 1:
                label_txt = "Voltaje total:"
            else:
                label_txt = f"V{i+1}:"

            ttk.Label(
                self.voltage_container,
                text=label_txt
            ).grid(row=r, column=c, sticky="e", padx=(0, 6), pady=3)

            ttk.Entry(
                self.voltage_container,
                textvariable=var,
                width=14 if n == 1 else 10,
                validate="key",
                validatecommand=self.vcmd_float
            ).grid(row=r, column=c + 1, sticky="w", padx=(0, 14), pady=3)

        if n == 1:
            ttk.Label(
                self.voltage_container,
                text="(Carga directa del voltaje total)",
                font=("Segoe UI", 9, "italic")
            ).grid(row=r + 1, column=0, columnspan=per_row * 2, sticky="w", pady=(6, 0))

        if prefill:
            for i, valor in enumerate(prefill):
                if i < len(self.voltage_vars):
                    self.voltage_vars[i].set(str(valor))

        self._refresh_save_state()

    def _wire_validation(self):
        vars_to_trace = [
            self.var_fecha, self.var_hora,
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

    def _validate_all(self) -> Tuple[bool, str]:
        d = parse_date_ddmmyyyy(self.var_fecha.get())
        if not d:
            return False, "Fecha inválida (use dd/mm/aaaa)."

        hora = self.var_hora.get().strip()
        if not re.fullmatch(r"\d{2}:\d{2}", hora):
            return False, "Hora inválida (use HH:MM)."
        hh, mm = hora.split(":")
        try:
            ih, im = int(hh), int(mm)
            if not (0 <= ih <= 23 and 0 <= im <= 59):
                return False, "Hora inválida (rango 00:00 a 23:59)."
        except Exception:
            return False, "Hora inválida (use HH:MM)."

        if not is_int_ok(self.var_electrolizador.get()):
            return False, "Electrolizador debe ser numérico entero."
        if not is_int_ok(self.var_celdas.get()):
            return False, "Cantidad de celdas debe ser numérica entera."

        n = int(self.var_celdas.get().strip())
        if n <= 0:
            return False, "Cantidad de celdas debe ser mayor que 0."
        if len(self.voltage_vars) != n:
            return False, "Complete los voltajes según la cantidad de celdas."
        
        if n == 1:
            elect = int(self.var_electrolizador.get().strip())
            rows = self.db.fetch_last_salmuera_by_electrolizador(elect, limit=15)

            # excluyo el propio registro en edición para no contarlo doble
            rows = [r for r in rows if int(r.get("id", -1)) != int(self.registro_id)]

            consec = 0
            for r in rows:
                if int(r.get("cantidad_celdas", 0)) == 1:
                    consec += 1
                else:
                    break

            if consec >= 2:
                return False, "ADVERTENCIA: Para este electrolizador ya hubo 2 registros seguidos con 1 celda. En la tercera carga, la cantidad de celdas debe ser distinta de 1."

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

        return True, "OK"
    
    def _count_consecutive_single_cell(self, electrolizador: int) -> int:
        # Cuenta cuántos registros consecutivos más recientes tienen cantidad_celdas = 1
        rows = self.db.fetch_last_salmuera_by_electrolizador(electrolizador, limit=10)
        count = 0
        for r in rows:
            if int(r.get("cantidad_celdas", 0)) == 1:
                count += 1
            else:
                break
        return count


    def _refresh_save_state(self):
        ok, msg = self._validate_all()
        self.btn_save.config(state=("normal" if ok else "disabled"))

        is_alert = "ADVERTENCIA" in msg

        if ok:
            self.lbl_status.config(
                text="Listo para guardar cambios.",
                foreground="green",
                font=("Segoe UI", 10, "bold")
            )
        else:
            self.lbl_status.config(
                text=msg,
                foreground=("red" if is_alert else "black"),
                font=("Segoe UI", 12, "bold" if is_alert else "normal")
            )

    def on_save(self):
        
        ok, msg = self._validate_all()
        if not ok:
            messagebox.showerror("ERROR - No se puede guardar", msg)
            return

        d = parse_date_ddmmyyyy(self.var_fecha.get())
        fecha_iso = date_to_iso(d)
        hora_hm = self.var_hora.get().strip()

        voltajes = [float(v.get().strip()) for v in self.voltage_vars]
        voltaje_total = sum(voltajes)

        data = {
            "fecha_iso": fecha_iso,
            "hora_hm": hora_hm,
            "electrolizador": int(self.var_electrolizador.get().strip()),
            "cantidad_celdas": int(self.var_celdas.get().strip()),
            "turno": self.var_turno.get().strip(),
            "voltajes_celdas": voltajes,
            "voltaje_total": float(voltaje_total),
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
        }

        try:
            self.db.update_salmuera_by_id(self.registro_id, data)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron guardar los cambios.\n\nDetalle: {e}")
            return

        self.destroy()