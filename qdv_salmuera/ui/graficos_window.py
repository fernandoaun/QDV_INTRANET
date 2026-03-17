import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# PEGAR AQUÍ: class DashboardGraficosWindow (V4 582–872)

# Nota: si en tu V4 llamaba a métodos DB con otros nombres,
# ajustamos en DB para que coincidan o adaptamos aquí.
class DashboardGraficosWindow(tk.Toplevel):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.title("Química del Valle - Gráficos")
        self.geometry("1200x800")
        self.db = db

        self.var_desde = tk.StringVar(value=date.today().isoformat())
        self.var_hasta = tk.StringVar(value=date.today().isoformat())
        self.var_elect = tk.StringVar(value="Todos")

        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Desde (YYYY-MM-DD):").pack(side="left")
        ttk.Entry(top, textvariable=self.var_desde, width=12).pack(side="left", padx=(6, 14))

        ttk.Label(top, text="Hasta (YYYY-MM-DD):").pack(side="left")
        ttk.Entry(top, textvariable=self.var_hasta, width=12).pack(side="left", padx=(6, 14))

        ttk.Label(top, text="Electrolizador:").pack(side="left")
        self.cmb_elect = ttk.Combobox(top, textvariable=self.var_elect, width=10, state="readonly",
                                     values=["Todos", "1", "2", "3", "4", "5"])
        self.cmb_elect.pack(side="left", padx=(6, 14))

        ttk.Button(top, text="Generar gráficos", command=self.render).pack(side="left")

        # Contenedor gráfico con scroll
        self.canvas_frame = ttk.Frame(self, padding=10)
        self.canvas_frame.pack(fill="both", expand=True)

        self._canvas = None
        self._fig = None

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_elec = ttk.Frame(self.nb)
        self.tab_caud = ttk.Frame(self.nb)
        self.tab_proc = ttk.Frame(self.nb)
        self.tab_cal = ttk.Frame(self.nb)

        self.nb.add(self.tab_elec, text="Eléctrico")
        self.nb.add(self.tab_caud, text="Caudales")
        self.nb.add(self.tab_proc, text="Proceso")
        self.nb.add(self.tab_cal, text="Calidad")

        self.after(200, self.render)


    def _plot_big(self, parent, x, series: dict, title: str, ylabel: str):
        fig = Figure(figsize=(11, 5), dpi=100)
        ax = fig.add_subplot(111)

        for label, y in series.items():
            ax.plot(x, y, label=label)

        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(True)
        ax.legend(loc="best")

        fig.autofmt_xdate()

        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)


    def render(self):
        import traceback

        def _parse_date_input(s: str) -> str:
            s = (s or "").strip()
            # acepta YYYY-MM-DD
            if len(s) == 10 and s[4] == "-" and s[7] == "-":
                return s
            # acepta DD/MM/YYYY
            if len(s) == 10 and s[2] == "/" and s[5] == "/":
                dd, mm, yyyy = s.split("/")
                return f"{yyyy}-{mm}-{dd}"
            return s  # deja como está; si es inválido, fallará más abajo

        def _parse_dt(r):
            # 1) created_at_iso si existe
            cat = (r.get("created_at_iso") or "").strip()
            if cat:
                try:
                    return datetime.fromisoformat(cat)
                except Exception:
                    pass

            # 2) fallback fecha_iso + hora_hm
            f = (r.get("fecha_iso") or "").strip()
            h = (r.get("hora_hm") or "").strip()

            # normalizar hora: HH:MM o HH:MM:SS
            if len(h) == 5:       # HH:MM
                hhmmss = h + ":00"
            elif len(h) == 8:     # HH:MM:SS
                hhmmss = h
            else:
                hhmmss = h

            try:
                return datetime.fromisoformat(f"{f}T{hhmmss}")
            except Exception:
                return None

        try:
            # limpiar canvas previo
            for w in self.canvas_frame.winfo_children():
                w.destroy()

            desde = _parse_date_input(self.var_desde.get())
            hasta = _parse_date_input(self.var_hasta.get())

            # validar formato básico
            if not (len(desde) == 10 and desde[4] == "-" and desde[7] == "-"):
                messagebox.showerror("Fechas", "Fecha DESDE inválida. Usá YYYY-MM-DD o DD/MM/YYYY.")
                return
            if not (len(hasta) == 10 and hasta[4] == "-" and hasta[7] == "-"):
                messagebox.showerror("Fechas", "Fecha HASTA inválida. Usá YYYY-MM-DD o DD/MM/YYYY.")
                return

            registros = self.db.fetch_salmuera_range(desde, hasta)
            if not registros:
                messagebox.showinfo("Sin datos", "No hay registros para el rango seleccionado.")
                return

            # filtro electrolizador
            elect_txt = (self.var_elect.get() or "").strip()
            if elect_txt != "Todos":
                try:
                    e = int(elect_txt)
                    registros = [r for r in registros if int(r.get("electrolizador", 0)) == e]
                except Exception:
                    pass

            if not registros:
                messagebox.showinfo("Sin datos", "No hay registros para el electrolizador seleccionado.")
                return

            # series
            xs = []
            series = {
                "Voltaje total": [],
                "Amperaje": [],
                "Caudal Agua (L/h)": [],
                "Caudal Salmuera (L/h)": [],
                "Hipoclorito - Concentración": [],
                "Hipoclorito - Exceso Soda": [],
                "Salmuera - Temperatura": [],
                "Salmuera - Concentración": [],
                "Salmuera - pH": [],
                "Soda - Concentración": [],
                "Declorinación - pH": [],
                "Voltaje celda (mín)": [],
                "Voltaje celda (máx)": [],
                "Voltaje celda (prom)": [],
            }

            def _to_float(x):
                try:
                    if x is None:
                        return None
                    return float(x)
                except Exception:
                    return None

            # cargar puntos
            for r in registros:
                dt = _parse_dt(r)
                if dt is None:
                    continue

                xs.append(dt)

                series["Voltaje total"].append(_to_float(r.get("voltaje_total")))
                series["Amperaje"].append(_to_float(r.get("amperaje")))
                series["Caudal Agua (L/h)"].append(_to_float(r.get("caudal_agua_l_h")))
                series["Caudal Salmuera (L/h)"].append(_to_float(r.get("caudal_salmuera_l_h")))
                series["Hipoclorito - Concentración"].append(_to_float(r.get("hipo_conc")))
                series["Hipoclorito - Exceso Soda"].append(_to_float(r.get("hipo_exceso_soda")))
                series["Salmuera - Temperatura"].append(_to_float(r.get("sal_temp")))
                series["Salmuera - Concentración"].append(_to_float(r.get("sal_conc")))
                series["Salmuera - pH"].append(_to_float(r.get("sal_ph")))
                series["Soda - Concentración"].append(_to_float(r.get("soda_conc")))
                series["Declorinación - pH"].append(_to_float(r.get("declor_ph")))

                volts = r.get("voltajes_celdas") or []
                try:
                    volts = [float(v) for v in volts]
                except Exception:
                    volts = []

                if not volts:
                    series["Voltaje celda (mín)"].append(None)
                    series["Voltaje celda (máx)"].append(None)
                    series["Voltaje celda (prom)"].append(None)
                else:
                    series["Voltaje celda (mín)"].append(min(volts))
                    series["Voltaje celda (máx)"].append(max(volts))
                    series["Voltaje celda (prom)"].append(sum(volts) / len(volts))

            if not xs:
                messagebox.showerror(
                    "Sin puntos válidos",
                    "Hay registros, pero no se pudo interpretar fecha/hora para graficar.\n"
                    "Revisar formato de created_at_iso / fecha_iso / hora_hm."
                )
                return

            # graficar (si hay None, matplotlib los maneja como cortes de línea)
            keys = list(series.keys())
            nplots = len(keys)
            height = max(8, nplots * 2.2)

            fig = Figure(figsize=(11, height), dpi=100)
            # limpiar tabs
            for tab in (self.tab_elec, self.tab_caud, self.tab_proc, self.tab_cal):
                for w in tab.winfo_children():
                    w.destroy()

            # ELÉCTRICO
            self._plot_big(
                self.tab_elec,
                xs,
                {
                    "Voltaje total": series["Voltaje total"],
                    "Voltaje celda (prom)": series["Voltaje celda (prom)"],
                    "Amperaje": series["Amperaje"],
                },
                "Variables eléctricas",
                "V / A"
            )

            # CAUDALES
            self._plot_big(
                self.tab_caud,
                xs,
                {
                    "Caudal agua": series["Caudal Agua (L/h)"],
                    "Caudal salmuera": series["Caudal Salmuera (L/h)"],
                },
                "Caudales",
                "L/h"
            )

            # PROCESO
            self._plot_big(
                self.tab_proc,
                xs,
                {
                    "Hipoclorito": series["Hipoclorito - Concentración"],
                    "Exceso soda": series["Hipoclorito - Exceso Soda"],
                    "Soda": series["Soda - Concentración"],
                },
                "Proceso químico",
                "g/L"
            )

            # CALIDAD
            self._plot_big(
                self.tab_cal,
                xs,
                {
                    "pH salmuera": series["Salmuera - pH"],
                    "pH declorinación": series["Declorinación - pH"],
                    "Temperatura": series["Salmuera - Temperatura"],
                },
                "Calidad",
                "pH / °C"
            )


            messagebox.showinfo("OK", f"Gráficos generados: {len(xs)} puntos.")

        except Exception as e:
            messagebox.showerror("Error en gráficos", f"{e}\n\n{traceback.format_exc()}")



    def _to_float(x):
        try:
            if x is None:
                return None
            return float(x)
        except Exception:
            return None
GraficosWindow = DashboardGraficosWindow
