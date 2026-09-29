"""Programa de Objetivos (registro SGI QDV-RG-PG-02_01): seguimiento anual por objetivo y mes."""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from typing import Any, BinaryIO

from sqlalchemy import select

from app.extensions import db
from app.models import Objetivo, ObjetivoCambio, ObjetivoMes, ObjetivoPrograma
from app.utils.datetime_operacion import now_operacion_naive_local

CODIGO_REGISTRO = "QDV-RG-PG-02_01"
TITULO = "PROGRAMA DE OBJETIVOS"

# Leyenda del registro, en el mismo orden y con los mismos colores que la planilla original.
ESTADOS: tuple[str, ...] = ("realizado", "en_implementacion", "atrasado", "na")
ESTADO_LABELS: dict[str, str] = {
    "realizado": "Realizado",
    "en_implementacion": "En implementación",
    "atrasado": "Atrasado",
    "na": "N/A",
}
ESTADO_COLORES: dict[str, str] = {
    "realizado": "92D050",
    "en_implementacion": "FFFF99",
    "atrasado": "FF0000",
    "na": "FFFFFF",
}
COLOR_ENCABEZADO = "FABF8F"

MESES: tuple[str, ...] = ("ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC")
MES_ANUAL = 13
FRECUENCIAS: tuple[str, ...] = ("Mensual", "Bimestral", "Trimestral", "Semestral", "Anual")

# Campos que solo toca el administrador (definición del objetivo).
CAMPOS_ADMIN: tuple[str, ...] = ("proceso", "objetivo", "meta", "indicador")
# Campos de seguimiento que también edita SGI (tareas y estado).
CAMPOS_SEGUIMIENTO: tuple[str, ...] = ("recursos", "frecuencia", "estado_cumplimiento")
CAMPO_LABELS: dict[str, str] = {
    "proceso": "Proceso",
    "objetivo": "Objetivo",
    "meta": "Meta",
    "indicador": "Indicador",
    "recursos": "Recursos / actividades",
    "frecuencia": "Frecuencia",
    "estado_cumplimiento": "Estado de cumplimiento",
    "alta": "Alta de objetivo",
    "baja": "Baja de objetivo",
    "encabezado": "Encabezado",
    "importacion": "Importación de planilla",
}


def _today() -> date:
    return now_operacion_naive_local().date()


def fecha_local(dt: datetime | None) -> str:
    """Fecha y hora de un cambio (guardado en UTC) en hora de planta."""
    if dt is None:
        return ""
    from datetime import timezone

    from app.utils.datetime_operacion import operacion_zoneinfo

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(operacion_zoneinfo()).strftime("%d/%m/%Y %H:%M")


def mes_label(mes: int) -> str:
    return "ANUAL" if mes == MES_ANUAL else MESES[mes - 1]


def labels_context() -> dict[str, Any]:
    return {
        "obj_estados": ESTADOS,
        "obj_estado_labels": ESTADO_LABELS,
        "obj_estado_colores": ESTADO_COLORES,
        "obj_meses": MESES,
        "obj_mes_anual": MES_ANUAL,
        "obj_frecuencias": FRECUENCIAS,
        "obj_color_encabezado": COLOR_ENCABEZADO,
        "obj_campo_labels": CAMPO_LABELS,
        "obj_mes_label": mes_label,
        "fecha_local": fecha_local,
    }


# ---------------------------------------------------------------- consultas


def get_programa(anio: int) -> ObjetivoPrograma | None:
    return db.session.scalar(select(ObjetivoPrograma).where(ObjetivoPrograma.anio == int(anio)))


def anios_disponibles() -> list[int]:
    return list(db.session.scalars(select(ObjetivoPrograma.anio).order_by(ObjetivoPrograma.anio.desc())))


def anio_por_defecto() -> int:
    """Año en curso si existe su programa; si no, el más reciente cargado."""
    hoy = _today().year
    anios = anios_disponibles()
    if not anios or hoy in anios:
        return hoy
    return anios[0]


def objetivos_activos(prog: ObjetivoPrograma) -> list[Objetivo]:
    return [o for o in prog.objetivos if o.activo]


def get_objetivo(objetivo_id: int) -> Objetivo | None:
    return db.session.get(Objetivo, int(objetivo_id))


def meses_map(obj: Objetivo) -> dict[int, ObjetivoMes]:
    return {int(m.mes): m for m in obj.meses}


def cambios_recientes(prog: ObjetivoPrograma, limit: int = 200) -> list[ObjetivoCambio]:
    stmt = (
        select(ObjetivoCambio)
        .where(ObjetivoCambio.programa_id == prog.id)
        .order_by(ObjetivoCambio.created_at.desc(), ObjetivoCambio.id.desc())
        .limit(limit)
    )
    return list(db.session.scalars(stmt).unique())


# ---------------------------------------------------------------- escritura


def _log(prog: ObjetivoPrograma, obj: Objetivo | None, user_id: int | None, campo: str, antes: Any, despues: Any) -> None:
    db.session.add(
        ObjetivoCambio(
            programa_id=prog.id,
            objetivo_id=obj.id if obj is not None else None,
            user_id=user_id,
            campo=campo,
            antes=None if antes is None else str(antes),
            despues=None if despues is None else str(despues),
        )
    )
    prog.fecha_actualizacion = _today()


def crear_programa(anio: int, user_id: int | None, copiar_de: ObjetivoPrograma | None = None) -> ObjetivoPrograma:
    """Crea el programa del año. Si `copiar_de`, copia los objetivos activos no realizados (sin seguimiento)."""
    prog = ObjetivoPrograma(anio=int(anio), codigo=CODIGO_REGISTRO, revision="00", fecha_actualizacion=_today())
    if copiar_de is not None:
        prog.codigo = copiar_de.codigo
        prog.revision = copiar_de.revision
        prog.fecha_vigencia = copiar_de.fecha_vigencia
        orden = 0
        for o in objetivos_activos(copiar_de):
            if o.estado_cumplimiento == "realizado":
                continue
            orden += 1
            prog.objetivos.append(
                Objetivo(
                    orden=orden,
                    proceso=o.proceso,
                    objetivo=o.objetivo,
                    meta=o.meta,
                    indicador=o.indicador,
                    recursos=o.recursos,
                    frecuencia=o.frecuencia,
                )
            )
    db.session.add(prog)
    db.session.flush()
    _log(prog, None, user_id, "alta", None, f"Programa {anio}" + (f" (copiado de {copiar_de.anio})" if copiar_de else ""))
    return prog


def _clean(campo: str, raw: Any) -> tuple[Any, str | None]:
    v = (raw or "").strip() if isinstance(raw, str) or raw is None else raw
    if campo == "estado_cumplimiento":
        if not v:
            return None, None
        if v not in ESTADOS:
            return None, "Estado de cumplimiento inválido."
        return v, None
    if campo == "proceso":
        if not v:
            return None, "El proceso es obligatorio."
        return v[:128], None
    if campo == "objetivo":
        if not v:
            return None, "El objetivo es obligatorio."
        return v, None
    if campo in ("meta", "indicador"):
        return v[:256], None
    if campo == "frecuencia":
        return (v or "Mensual")[:64], None
    return v, None


def actualizar_campos(obj: Objetivo, data: dict[str, Any], campos: tuple[str, ...], user_id: int | None) -> list[str]:
    """Aplica solo los `campos` permitidos presentes en `data`. Devuelve errores (sin aplicar nada si hay)."""
    nuevos: dict[str, Any] = {}
    errores: list[str] = []
    for campo in campos:
        if campo not in data:
            continue
        v, err = _clean(campo, data.get(campo))
        if err:
            errores.append(err)
        else:
            nuevos[campo] = v
    if errores:
        return errores
    prog = obj.programa
    for campo, v in nuevos.items():
        antes = getattr(obj, campo)
        if (antes or None) == (v or None):
            continue
        setattr(obj, campo, v)
        _log(prog, obj, user_id, campo, antes, v)
    return []


def alta_objetivo(prog: ObjetivoPrograma, data: dict[str, Any], user_id: int | None) -> tuple[Objetivo | None, list[str]]:
    obj = Objetivo(orden=max([o.orden for o in prog.objetivos] or [0]) + 1)
    errores: list[str] = []
    for campo in CAMPOS_ADMIN + CAMPOS_SEGUIMIENTO:
        v, err = _clean(campo, data.get(campo))
        if err:
            errores.append(err)
        else:
            setattr(obj, campo, v if v is not None or campo == "estado_cumplimiento" else "")
    if errores:
        return None, errores
    prog.objetivos.append(obj)
    db.session.flush()
    _log(prog, obj, user_id, "alta", None, obj.objetivo[:200])
    return obj, []


def baja_objetivo(obj: Objetivo, user_id: int | None) -> None:
    if not obj.activo:
        return
    obj.activo = False
    _log(obj.programa, obj, user_id, "baja", obj.objetivo[:200], None)


def _mes_texto(estado: str | None, valor: str) -> str:
    partes = [ESTADO_LABELS.get(estado or "", "")] if estado else []
    if valor:
        partes.append(valor)
    return " · ".join(partes) or "(vacío)"


def set_mes(obj: Objetivo, mes: int, estado: str | None, valor: str | None, user_id: int | None) -> tuple[ObjetivoMes | None, str | None]:
    if not 1 <= int(mes) <= MES_ANUAL:
        return None, "Mes inválido."
    estado = (estado or "").strip() or None
    if estado is not None and estado not in ESTADOS:
        return None, "Estado inválido."
    valor = (valor or "").strip()[:64]
    m = meses_map(obj).get(int(mes))
    antes = _mes_texto(m.estado, m.valor) if m is not None else "(vacío)"
    if m is None:
        m = ObjetivoMes(mes=int(mes), estado=estado, valor=valor)
        obj.meses.append(m)
    elif m.estado == estado and (m.valor or "") == valor:
        return m, None
    else:
        m.estado = estado
        m.valor = valor
    _log(obj.programa, obj, user_id, f"mes:{mes_label(int(mes))}", antes, _mes_texto(estado, valor))
    return m, None


def actualizar_encabezado(prog: ObjetivoPrograma, data: dict[str, Any], user_id: int | None) -> list[str]:
    codigo = (data.get("codigo") or "").strip()[:64]
    revision = (data.get("revision") or "").strip()[:16]
    raw_vig = (data.get("fecha_vigencia") or "").strip()
    if not codigo or not revision:
        return ["Código y revisión son obligatorios."]
    vig: date | None = None
    if raw_vig:
        try:
            vig = date.fromisoformat(raw_vig)
        except ValueError:
            return ["Fecha de vigencia inválida."]
    antes = f"{prog.codigo} · Rev. {prog.revision} · {prog.fecha_vigencia or '—'}"
    prog.codigo, prog.revision, prog.fecha_vigencia = codigo, revision, vig
    despues = f"{prog.codigo} · Rev. {prog.revision} · {prog.fecha_vigencia or '—'}"
    if antes != despues:
        _log(prog, None, user_id, "encabezado", antes, despues)
    return []


# ---------------------------------------------------------------- importación desde la planilla


def _color_a_estado(rgb: str | None) -> str | None:
    if not rgb or len(rgb) < 6:
        return None
    c = rgb[-6:].upper()
    for estado, hexa in ESTADO_COLORES.items():
        if estado != "na" and c == hexa:
            return estado
    # Variantes de amarillo que Excel ofrece en la paleta estándar.
    if c in ("FFFF00", "FFFF66", "FFFFCC", "FFE699", "FFD966"):
        return "en_implementacion"
    if c in ("00B050", "00FF00", "A9D08E", "C6EFCE"):
        return "realizado"
    if c in ("C00000", "FF5050", "FFC7CE"):
        return "atrasado"
    return None


def _texto_a_estado(v: Any) -> str | None:
    t = str(v or "").strip().lower()
    if not t:
        return None
    for estado, label in ESTADO_LABELS.items():
        if t == label.lower():
            return estado
    return None


def _fecha_en_texto(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(v or ""))
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def importar_planilla(fh: BinaryIO, anio: int, user_id: int | None) -> tuple[ObjetivoPrograma | None, list[str]]:
    """Carga un programa desde la planilla Excel del registro. Solo si el año todavía no tiene objetivos."""
    import openpyxl

    try:
        wb = openpyxl.load_workbook(fh, data_only=True)
    except Exception:
        return None, ["No se pudo leer el archivo. Tiene que ser la planilla .xlsx del Programa de Objetivos."]
    ws = wb.active

    fila_enc = None
    for r in range(1, min(ws.max_row, 40) + 1):
        if str(ws.cell(r, 1).value or "").strip().upper() == "PROCESO":
            fila_enc = r
            break
    if fila_enc is None:
        return None, ["No encontré la fila de encabezados (PROCESO / OBJETIVO / META…)."]

    # Columnas de meses: buscar ENE…DIC y ANUAL en la fila siguiente al encabezado.
    col_mes: dict[int, int] = {}
    for c in range(1, ws.max_column + 1):
        t = str(ws.cell(fila_enc + 1, c).value or "").strip().upper()
        if t in MESES:
            col_mes[MESES.index(t) + 1] = c
        elif t == "ANUAL":
            col_mes[MES_ANUAL] = c
    if len(col_mes) < 12:
        return None, ["No encontré las columnas de meses (ENE a DIC)."]

    prog = get_programa(anio)
    if prog is not None and objetivos_activos(prog):
        return None, [f"El programa {anio} ya tiene objetivos cargados; no se importa encima."]

    filas: list[dict[str, Any]] = []
    r = fila_enc + 2
    while r <= ws.max_row:
        proceso = str(ws.cell(r, 1).value or "").strip()
        objetivo = str(ws.cell(r, 2).value or "").strip()
        if not proceso and not objetivo:
            break
        meses: dict[int, tuple[str | None, str]] = {}
        for mes, c in col_mes.items():
            cell = ws.cell(r, c)
            fg = cell.fill.fgColor if cell.fill is not None and cell.fill.fill_type == "solid" else None
            estado = _color_a_estado(fg.rgb if fg is not None and fg.type == "rgb" else None)
            valor = str(cell.value).strip() if cell.value is not None else ""
            if estado or valor:
                meses[mes] = (estado, valor[:64])
        filas.append(
            {
                "proceso": proceso[:128] or "—",
                "objetivo": objetivo or "—",
                "meta": str(ws.cell(r, 3).value or "").strip()[:256],
                "indicador": str(ws.cell(r, 4).value or "").strip()[:256],
                "estado_cumplimiento": _texto_a_estado(ws.cell(r, 5).value),
                "recursos": str(ws.cell(r, 6).value or "").strip(),
                "frecuencia": (str(ws.cell(r, 7).value or "").strip() or "Mensual")[:64],
                "meses": meses,
            }
        )
        r += 1
    if not filas:
        return None, ["La planilla no tiene objetivos debajo de los encabezados."]

    if prog is None:
        prog = crear_programa(anio, user_id)
    # Encabezado del registro (celdas de la derecha y fecha de actualización).
    for rr in range(1, fila_enc):
        for cc in range(1, ws.max_column + 1):
            t = str(ws.cell(rr, cc).value or "").strip()
            if not t:
                continue
            if t.upper().startswith("QDV-RG"):
                prog.codigo = t.split()[0][:64]
            elif t.lower().startswith("fecha de vigencia"):
                prog.fecha_vigencia = _fecha_en_texto(t) or prog.fecha_vigencia
            elif re.match(r"(?i)^rev\.?\s*\d+", t):
                prog.revision = re.sub(r"(?i)^rev\.?\s*", "", t)[:16]
    for i, f in enumerate(filas, start=1):
        obj = Objetivo(
            orden=i,
            proceso=f["proceso"],
            objetivo=f["objetivo"],
            meta=f["meta"],
            indicador=f["indicador"],
            estado_cumplimiento=f["estado_cumplimiento"],
            recursos=f["recursos"],
            frecuencia=f["frecuencia"],
        )
        for mes, (estado, valor) in sorted(f["meses"].items()):
            obj.meses.append(ObjetivoMes(mes=mes, estado=estado, valor=valor))
        prog.objetivos.append(obj)
    db.session.flush()
    _log(prog, None, user_id, "importacion", None, f"{len(filas)} objetivo(s)")
    return prog, []


# ---------------------------------------------------------------- exportación con el formato del registro


def exportar_xlsx(prog: ObjetivoPrograma) -> bytes:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = (prog.codigo or CODIGO_REGISTRO).replace("QDV-RG-", "QDV-")[:31]
    medium = Side(style="medium", color="000000")
    thin = Side(style="thin", color="000000")
    caja = Border(left=medium, right=medium, top=medium, bottom=medium)
    celda = Border(left=thin, right=thin, top=thin, bottom=thin)
    naranja = PatternFill("solid", fgColor=COLOR_ENCABEZADO)
    centro = Alignment(horizontal="center", vertical="center", wrap_text=True)
    izq = Alignment(horizontal="left", vertical="center", wrap_text=True)
    negrita = Font(bold=True, size=12)
    normal = Font(size=12)

    anchos = {"A": 32.5, "B": 37.3, "C": 26.5, "D": 36.8, "E": 27.7, "F": 41.2, "G": 41.3, "T": 12.2}
    for col in range(8, 20):
        anchos[get_column_letter(col)] = 8.5
    for k, v in anchos.items():
        ws.column_dimensions[k].width = v

    # Encabezado del registro.
    ws["A1"] = "QUÍMICA DEL VALLE S.R.L."
    ws["A1"].font = Font(bold=True, size=14, color="E46C0A")
    ws["A1"].alignment = centro
    ws.merge_cells("A1:A4")
    ws["B1"] = TITULO
    ws["B1"].font = Font(bold=True, size=20)
    ws["B1"].alignment = centro
    ws.merge_cells("B1:O4")
    vig = prog.fecha_vigencia.strftime("%d/%m/%Y") if prog.fecha_vigencia else "—"
    for i, txt in enumerate(
        [prog.codigo, f"Fecha de Vigencia: {vig}", f"Rev. {prog.revision}", "Página 1 de 1"], start=1
    ):
        ws.cell(i, 16, txt).font = negrita
        ws.cell(i, 16).alignment = centro
        ws.merge_cells(start_row=i, start_column=16, end_row=i, end_column=20)
    for r in range(1, 5):
        for c in range(1, 21):
            ws.cell(r, c).border = caja
    act = prog.fecha_actualizacion.strftime("%d/%m/%Y") if prog.fecha_actualizacion else "—"
    ws["A6"] = f"Fecha de actualización: {act}"
    ws["A6"].font = negrita
    ws["A6"].fill = naranja
    ws.merge_cells("A6:T6")

    for col, txt in zip("ABCDE", ("PROCESO", "OBJETIVO", "META", "INDICADOR", "ESTADO DE CUMPLIMIENTO")):
        ws[f"{col}7"] = txt
        ws.merge_cells(f"{col}7:{col}8")
    ws["F7"] = "SEGUIMIENTO DE PLANIFICACION DEL OBJETIVO/VALOR DEL INDICADOR"
    ws.merge_cells("F7:T7")
    ws["F8"] = "RECURSOS/ACTIVIDADES A DESARROLLAR"
    ws["G8"] = "FRECUENCIA"
    for i, m in enumerate(MESES):
        ws.cell(8, 8 + i, m)
    ws["T8"] = "ANUAL"
    for r in (7, 8):
        for c in range(1, 21):
            cell = ws.cell(r, c)
            cell.fill = naranja
            cell.font = negrita
            cell.alignment = centro
            cell.border = caja
    ws.row_dimensions[8].height = 35.5

    r = 9
    for o in objetivos_activos(prog):
        mm = meses_map(o)
        valores = [
            o.proceso,
            o.objetivo,
            o.meta,
            o.indicador,
            ESTADO_LABELS.get(o.estado_cumplimiento or "", ""),
            o.recursos,
            o.frecuencia,
        ]
        for c, v in enumerate(valores, start=1):
            cell = ws.cell(r, c, v)
            cell.font = negrita if c in (1, 7) else normal
            cell.alignment = izq if c in (2, 6) else centro
            cell.border = celda
        if o.estado_cumplimiento:
            ws.cell(r, 5).fill = PatternFill("solid", fgColor=ESTADO_COLORES[o.estado_cumplimiento])
        for mes in range(1, MES_ANUAL + 1):
            cell = ws.cell(r, 7 + mes)
            cell.border = celda
            cell.alignment = centro
            m = mm.get(mes)
            if m is None:
                continue
            if m.valor:
                cell.value = m.valor
            if m.estado:
                cell.fill = PatternFill("solid", fgColor=ESTADO_COLORES[m.estado])
        ws.row_dimensions[r].height = 96
        r += 1

    r += 2
    for estado in ESTADOS:
        ws.cell(r, 1).fill = PatternFill("solid", fgColor=ESTADO_COLORES[estado])
        ws.cell(r, 1).border = celda
        ws.cell(r, 2, ESTADO_LABELS[estado]).alignment = Alignment(vertical="center")
        r += 1

    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
