import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime, timedelta
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

    def _plot_big_dual_y(self, parent, x, series_left: dict, series_right: dict,
                         title: str, ylabel_left: str, ylabel_right: str):
        """Gráfico con eje Y izquierdo (series_left) y eje Y derecho (series_right)."""
        fig = Figure(figsize=(11, 5), dpi=100)
        ax = fig.add_subplot(111)

        for label, y in series_left.items():
            ax.plot(x, y, label=label)

        ax.set_ylabel(ylabel_left, color="C0")
        ax.tick_params(axis="y", labelcolor="C0")
        ax.grid(True)

        ax2 = ax.twinx()
        for label, y in series_right.items():
            ax2.plot(x, y, label=label, color="C2")

        ax2.set_ylabel(ylabel_right, color="C2")
        ax2.tick_params(axis="y", labelcolor="C2")

        # leyenda unificada
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, loc="best")

        ax.set_title(title)
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

            # ELÉCTRICO (eje izquierdo: V; eje derecho: A)
            self._plot_big_dual_y(
                self.tab_elec,
                xs,
                {"Voltaje total": series["Voltaje total"]},
                {"Amperaje": series["Amperaje"]},
                "Variables eléctricas",
                "V",
                "A"
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

            # PROCESO (eje izquierdo: Hipoclorito y Soda; eje derecho: Exceso soda)
            self._plot_big_dual_y(
                self.tab_proc,
                xs,
                {
                    "Hipoclorito": series["Hipoclorito - Concentración"],
                    "Soda": series["Soda - Concentración"],
                },
                {"Exceso soda": series["Hipoclorito - Exceso Soda"]},
                "Proceso químico",
                "g/L",
                "g/L (exceso soda)"
            )

            # CALIDAD (eje izquierdo: ambos pH; eje derecho: temperatura)
            self._plot_big_dual_y(
                self.tab_cal,
                xs,
                {
                    "pH salmuera": series["Salmuera - pH"],
                    "pH declorinación": series["Declorinación - pH"],
                },
                {"Temperatura": series["Salmuera - Temperatura"]},
                "Calidad",
                "pH",
                "°C"
            )

        except Exception as e:
            messagebox.showerror("Error en gráficos", f"{e}\n\n{traceback.format_exc()}")



    def _to_float(x):
        try:
            if x is None:
                return None
            return float(x)
        except Exception:
            return None


def build_fig_proceso_quimico_ultimas_24h(db) -> Figure:
    """Construye la figura del gráfico Proceso químico para las últimas 24 h (electrolizadores 2 y 3)."""
    def _parse_dt(r):
        cat = (r.get("created_at_iso") or "").strip()
        if cat:
            try:
                return datetime.fromisoformat(cat)
            except Exception:
                pass
        f = (r.get("fecha_iso") or "").strip()
        h = (r.get("hora_hm") or "").strip()
        if len(h) == 5:
            hhmmss = h + ":00"
        elif len(h) == 8:
            hhmmss = h
        else:
            hhmmss = h
        try:
            return datetime.fromisoformat(f"{f}T{hhmmss}")
        except Exception:
            return None

    def _to_float(x):
        try:
            return float(x) if x is not None else None
        except Exception:
            return None

    ahora = datetime.now()
    hace_24 = ahora - timedelta(hours=24)
    desde = hace_24.strftime("%Y-%m-%d")
    hasta = ahora.strftime("%Y-%m-%d")

    try:
        registros = db.fetch_salmuera_range(desde, hasta)
    except Exception:
        registros = []

    # Solo electrolizador 2 y 3
    registros_e2 = [r for r in registros if int(r.get("electrolizador", 0)) == 2]
    registros_e3 = [r for r in registros if int(r.get("electrolizador", 0)) == 3]

    def _build_series(registros_list):
        xs, hipo, exceso_soda, soda = [], [], [], []
        for r in registros_list:
            dt = _parse_dt(r)
            if dt is None or dt < hace_24:
                continue
            xs.append(dt)
            hipo.append(_to_float(r.get("hipo_conc")))
            exceso_soda.append(_to_float(r.get("hipo_exceso_soda")))
            soda.append(_to_float(r.get("soda_conc")))
        return xs, hipo, exceso_soda, soda

    xs_e2, hipo_e2, exceso_e2, soda_e2 = _build_series(registros_e2)
    xs_e3, hipo_e3, exceso_e3, soda_e3 = _build_series(registros_e3)

    fig = Figure(figsize=(8, 3.8), dpi=100)
    ax = fig.add_subplot(111)

    if not xs_e2 and not xs_e3:
        ax.text(0.5, 0.5, "Sin datos (últimas 24 h) - Electrolizadores 2 y 3", ha="center", va="center", fontsize=12, transform=ax.transAxes)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        return fig

    # Colores: Electrolizador 2 = azul; Electrolizador 3 = naranja/verde
    color_e2 = "#1f77b4"
    color_e3 = "#ff7f0e"
    color_e2_exceso = "#4a90d9"
    color_e3_exceso = "#f4a261"

    ax2 = ax.twinx()

    # Electrolizador 2 (azul)
    if xs_e2:
        ax.plot(xs_e2, hipo_e2, label="E2 - Hipoclorito", color=color_e2, linestyle="-", linewidth=1.8)
        ax.plot(xs_e2, soda_e2, label="E2 - Soda", color=color_e2, linestyle="--", linewidth=1.5)
        ax2.plot(xs_e2, exceso_e2, label="E2 - Exceso soda", color=color_e2_exceso, linestyle=":", linewidth=1.5)

    # Electrolizador 3 (naranja)
    if xs_e3:
        ax.plot(xs_e3, hipo_e3, label="E3 - Hipoclorito", color=color_e3, linestyle="-", linewidth=1.8)
        ax.plot(xs_e3, soda_e3, label="E3 - Soda", color=color_e3, linestyle="--", linewidth=1.5)
        ax2.plot(xs_e3, exceso_e3, label="E3 - Exceso soda", color=color_e3_exceso, linestyle=":", linewidth=1.5)

    ax.set_ylabel("g/L (Hipoclorito / Soda)", color="#333")
    ax.tick_params(axis="y", labelcolor="#333")
    ax2.set_ylabel("g/L (exceso soda)", color="#666")
    ax2.tick_params(axis="y", labelcolor="#666")
    ax.grid(True, alpha=0.4)

    # Cuadro de referencias (leyenda unificada)
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8, framealpha=0.95)

    ax.set_title("Proceso químico - Últimas 24 h (Electrolizadores 2 y 3)", fontsize=10)
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


GraficosWindow = DashboardGraficosWindow
