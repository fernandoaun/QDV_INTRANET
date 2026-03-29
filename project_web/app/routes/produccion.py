from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func, select

from app.auth_utils import current_user, login_required, permission_required, user_can
from app.constants import MODULE_LABELS, SECURITY_DELETE_CODE
from app.extensions import db
from app.models import (
    AguaRegistro,
    BolsonRegistro,
    ColumnaIntercambio,
    Operador,
    ReactorRegistro,
    SalmueraRegistro,
)
from app.services import stock_service

bp = Blueprint("produccion", __name__, url_prefix="/produccion")


def _operadores() -> list[Operador]:
    return list(db.session.scalars(select(Operador).order_by(Operador.nombre)).all())


def _next_salmuera_lote(fecha_iso: str) -> str:
    n = db.session.scalar(
        select(func.count()).select_from(SalmueraRegistro).where(SalmueraRegistro.fecha_iso == fecha_iso)
    )
    correlative = int(n or 0) + 1
    dt = datetime.strptime(fecha_iso, "%Y-%m-%d")
    return f"{dt.strftime('%y%m%d')}{correlative:02d}"


def _parse_voltajes(text: str, n: int) -> list[float]:
    parts = [p.strip() for p in (text or "").replace(";", ",").split(",") if p.strip()]
    if len(parts) != n:
        raise ValueError(f"Tenés que ingresar exactamente {n} voltajes (separados por coma).")
    return [float(p.replace(",", ".")) for p in parts]


@bp.get("/")
@login_required
@permission_required("produccion")
def hub():
    return render_template("produccion/hub.html", module_labels=MODULE_LABELS)


@bp.post("/operadores/agregar")
@login_required
@permission_required("produccion")
def operador_agregar():
    nombre = (request.form.get("nombre") or "").strip()
    if nombre:
        try:
            db.session.add(
                Operador(nombre=nombre, created_at_iso=datetime.now().isoformat(timespec="seconds"))
            )
            db.session.commit()
            flash(f"Operador {nombre!r} agregado.", "success")
        except Exception as e:
            db.session.rollback()
            flash(str(e), "danger")
    return redirect(request.referrer or url_for("produccion.hub"))


# ----- Salmuera -----
@bp.route("/salmuera", methods=["GET", "POST"])
@login_required
@permission_required("salmuera")
def salmuera():
    fecha = (request.values.get("fecha") or datetime.now().strftime("%Y-%m-%d")).strip()
    if request.method == "POST" and request.form.get("action") == "guardar":
        try:
            n = int((request.form.get("cantidad_celdas") or "0").strip())
            if n < 1:
                raise ValueError("Cantidad de celdas inválida.")
            volts = _parse_voltajes(request.form.get("voltajes") or "", n)
            now = datetime.now()
            data = SalmueraRegistro(
                fecha_iso=fecha,
                hora_hm=now.strftime("%H:%M"),
                electrolizador=int(request.form.get("electrolizador") or 0),
                cantidad_celdas=n,
                turno=(request.form.get("turno") or "").strip(),
                voltajes_json=json.dumps(volts, ensure_ascii=False),
                voltaje_total=float(sum(volts)),
                amperaje=float((request.form.get("amperaje") or "0").replace(",", ".")),
                caudal_agua_l_h=float((request.form.get("caudal_agua_l_h") or "0").replace(",", ".")),
                caudal_salmuera_l_h=float((request.form.get("caudal_salmuera_l_h") or "0").replace(",", ".")),
                hipo_conc=float((request.form.get("hipo_conc") or "0").replace(",", ".")),
                hipo_exceso_soda=float((request.form.get("hipo_exceso_soda") or "0").replace(",", ".")),
                sal_temp=float((request.form.get("sal_temp") or "0").replace(",", ".")),
                sal_conc=float((request.form.get("sal_conc") or "0").replace(",", ".")),
                sal_ph=float((request.form.get("sal_ph") or "0").replace(",", ".")),
                soda_conc=float((request.form.get("soda_conc") or "0").replace(",", ".")),
                declor_ph=float((request.form.get("declor_ph") or "0").replace(",", ".")),
                operador=(request.form.get("operador") or "").strip(),
                lote=(request.form.get("lote") or "").strip(),
                observaciones=(request.form.get("observaciones") or "").strip(),
                atraso_motivo=(request.form.get("atraso_motivo") or "").strip(),
                created_at_iso=now.isoformat(timespec="seconds"),
            )
            db.session.add(data)
            db.session.commit()
            flash("Registro de salmuera guardado.", "success")
            return redirect(url_for("produccion.salmuera", fecha=fecha))
        except Exception as e:
            db.session.rollback()
            flash(str(e), "danger")

    if request.method == "POST" and request.form.get("action") == "borrar":
        fecha_del = (request.form.get("fecha") or fecha).strip()
        rid = int(request.form.get("reg_id") or 0)
        codigo = (request.form.get("codigo_seguridad") or "").strip()
        if codigo != SECURITY_DELETE_CODE:
            flash("Código de seguridad incorrecto.", "danger")
        else:
            row = db.session.get(SalmueraRegistro, rid)
            if row:
                db.session.delete(row)
                db.session.commit()
                flash("Registro eliminado.", "info")
        return redirect(url_for("produccion.salmuera", fecha=fecha_del))

    rows = db.session.scalars(
        select(SalmueraRegistro)
        .where(SalmueraRegistro.fecha_iso == fecha)
        .order_by(SalmueraRegistro.id)
    ).all()
    registros: list[dict[str, Any]] = []
    for r in rows:
        try:
            vj = json.loads(r.voltajes_json) if r.voltajes_json else []
        except json.JSONDecodeError:
            vj = []
        registros.append(
            {
                "id": r.id,
                "hora_hm": r.hora_hm,
                "electrolizador": r.electrolizador,
                "cantidad_celdas": r.cantidad_celdas,
                "turno": r.turno,
                "voltajes_celdas": vj,
                "voltaje_total": r.voltaje_total,
                "amperaje": r.amperaje,
                "operador": r.operador,
                "lote": r.lote or "",
                "observaciones": r.observaciones or "",
                "created_at_iso": r.created_at_iso,
            }
        )

    return render_template(
        "produccion/salmuera.html",
        fecha=fecha,
        registros=registros,
        operadores=_operadores(),
        lote_sugerido=_next_salmuera_lote(fecha),
        module_title=MODULE_LABELS["salmuera"],
        username=current_user().username if current_user() else "",
    )


# ----- Bolson -----
@bp.route("/bolson", methods=["GET", "POST"])
@login_required
@permission_required("bolson_registro")
def bolson():
    if request.method == "POST":
        now = datetime.now()
        db.session.add(
            BolsonRegistro(
                fecha_iso=now.strftime("%Y-%m-%d"),
                hora_hm=now.strftime("%H:%M"),
                created_at_iso=now.isoformat(timespec="seconds"),
            )
        )
        db.session.commit()
        flash("Registro de bolson guardado.", "success")
        return redirect(url_for("produccion.bolson"))

    rows = list(
        db.session.scalars(select(BolsonRegistro).order_by(BolsonRegistro.id.desc()).limit(200)).all()
    )
    return render_template("produccion/bolson.html", registros=rows)


# ----- Reactor -----
@bp.route("/reactor", methods=["GET", "POST"])
@login_required
@permission_required("reactor")
def reactor():
    fecha = (request.values.get("fecha") or datetime.now().strftime("%Y-%m-%d")).strip()
    if request.method == "POST":
        try:
            now = datetime.now()
            n = db.session.scalar(
                select(func.count()).select_from(ReactorRegistro).where(ReactorRegistro.fecha_iso == fecha)
            )
            correlative = int(n or 0) + 1
            dt = datetime.strptime(fecha, "%Y-%m-%d")
            lote = f"{dt.strftime('%y%m%d')}{correlative:02d}"
            db.session.add(
                ReactorRegistro(
                    fecha_iso=fecha,
                    hora_hm=now.strftime("%H:%M"),
                    operador=(request.form.get("operador") or "").strip(),
                    lote=lote,
                    ph=float((request.form.get("ph") or "0").replace(",", ".")),
                    temperatura=float((request.form.get("temperatura") or "0").replace(",", ".")),
                    densidad=float((request.form.get("densidad") or "0").replace(",", ".")),
                    concentracion_tabla=float((request.form.get("concentracion_tabla") or "0").replace(",", ".")),
                    exceso_naoh=float((request.form.get("exceso_naoh") or "0").replace(",", ".")),
                    exceso_na2co3=float((request.form.get("exceso_na2co3") or "0").replace(",", ".")),
                    observaciones=(request.form.get("observaciones") or "").strip(),
                    created_at_iso=now.isoformat(timespec="seconds"),
                )
            )
            db.session.commit()
            flash("Registro reactor guardado.", "success")
            return redirect(url_for("produccion.reactor", fecha=fecha))
        except Exception as e:
            db.session.rollback()
            flash(str(e), "danger")

    rows = db.session.scalars(
        select(ReactorRegistro).where(ReactorRegistro.fecha_iso == fecha).order_by(ReactorRegistro.id)
    ).all()
    return render_template(
        "produccion/reactor.html",
        fecha=fecha,
        registros=list(rows),
        operadores=_operadores(),
        module_title=MODULE_LABELS["reactor"],
    )


# ----- Agua -----
@bp.route("/agua", methods=["GET", "POST"])
@login_required
@permission_required("agua")
def agua():
    fecha = (request.values.get("fecha") or datetime.now().strftime("%Y-%m-%d")).strip()
    if request.method == "POST":
        try:
            now = datetime.now()
            n = db.session.scalar(
                select(func.count()).select_from(AguaRegistro).where(AguaRegistro.fecha_iso == fecha)
            )
            correlative = int(n or 0) + 1
            dt = datetime.strptime(fecha, "%Y-%m-%d")
            lote = f"{dt.strftime('%y%m%d')}{correlative:02d}"
            db.session.add(
                AguaRegistro(
                    fecha_iso=fecha,
                    hora_hm=now.strftime("%H:%M"),
                    turno=(request.form.get("turno") or "").strip(),
                    operador=(request.form.get("operador") or "").strip(),
                    lote=lote,
                    numero_columna=int(request.form.get("numero_columna") or 1),
                    temperatura=float((request.form.get("temperatura") or "0").replace(",", ".")),
                    dureza=float((request.form.get("dureza") or "0").replace(",", ".")),
                    observaciones=(request.form.get("observaciones") or "").strip(),
                    created_at_iso=now.isoformat(timespec="seconds"),
                )
            )
            db.session.commit()
            flash("Registro de agua guardado.", "success")
            return redirect(url_for("produccion.agua", fecha=fecha))
        except Exception as e:
            db.session.rollback()
            flash(str(e), "danger")

    rows = db.session.scalars(
        select(AguaRegistro).where(AguaRegistro.fecha_iso == fecha).order_by(AguaRegistro.id)
    ).all()
    return render_template(
        "produccion/agua.html",
        fecha=fecha,
        registros=list(rows),
        operadores=_operadores(),
        module_title=MODULE_LABELS["agua"],
    )


# ----- Columnas -----
@bp.route("/columnas", methods=["GET", "POST"])
@login_required
@permission_required("agua")
def columnas():
    if request.method == "POST":
        now = datetime.now()
        now_iso = now.isoformat(timespec="seconds")
        col = int(request.form.get("columna_numero") or 1)
        estado = (request.form.get("estado") or "").strip()
        fr = (request.form.get("fecha_regeneracion") or "").strip() or None
        hr = (request.form.get("hora_regeneracion") or "").strip() or None
        if estado == "Regenerada":
            if not fr:
                fr = now.strftime("%d/%m/%Y")
            if not hr:
                hr = now.strftime("%H:%M")
        dsp = request.form.get("dureza_salida_ppm")
        dpp = request.form.get("dureza_post_regeneracion_ppm")
        db.session.add(
            ColumnaIntercambio(
                columna_numero=col,
                estado=estado,
                fecha_regeneracion=fr,
                hora_regeneracion=hr,
                dureza_salida_ppm=float(dsp.replace(",", ".")) if dsp else None,
                dureza_post_regeneracion_ppm=float(dpp.replace(",", ".")) if dpp else None,
                observaciones=(request.form.get("observaciones") or "").strip(),
                created_at_iso=now_iso,
                updated_at_iso=now_iso,
            )
        )
        db.session.commit()
        flash("Estado de columna guardado.", "success")
        return redirect(url_for("produccion.columnas"))

    latest: dict[int, dict[str, Any]] = {}
    for col in (1, 2, 3):
        r = db.session.scalars(
            select(ColumnaIntercambio)
            .where(ColumnaIntercambio.columna_numero == col)
            .order_by(ColumnaIntercambio.id.desc())
            .limit(1)
        ).first()
        if r:
            latest[col] = {
                "estado": r.estado,
                "fecha_regeneracion": r.fecha_regeneracion or "",
                "hora_regeneracion": r.hora_regeneracion or "",
                "dureza_salida_ppm": r.dureza_salida_ppm,
                "dureza_post_regeneracion_ppm": r.dureza_post_regeneracion_ppm,
                "observaciones": r.observaciones or "",
            }
        else:
            latest[col] = {
                "estado": "En operación",
                "fecha_regeneracion": "",
                "hora_regeneracion": "",
                "dureza_salida_ppm": None,
                "dureza_post_regeneracion_ppm": None,
                "observaciones": "",
            }
    return render_template("produccion/columnas.html", latest=latest)


# ----- Stock -----
@bp.get("/stock")
@login_required
def stock_hub():
    u = current_user()
    if not u or not (user_can(u, "bolson_registro") or user_can(u, "bolson_carga")):
        flash("No tenés permiso para stock/consumos.", "warning")
        return redirect(url_for("produccion.hub"))
    return render_template("produccion/stock_hub.html")


@bp.route("/stock/ingreso", methods=["GET", "POST"])
@login_required
@permission_required("bolson_registro")
def stock_ingreso():
    if request.method == "POST":
        try:
            stock_service.save_ingreso(
                request.form.get("categoria") or "",
                request.form.get("producto") or "",
                request.form.get("marca") or "",
                request.form.get("vencimiento") or "",
                request.form.get("lote") or "",
                float((request.form.get("cantidad") or "0").replace(",", ".")),
                (request.form.get("operador") or current_user().username),
            )
            flash("Ingreso guardado.", "success")
            return redirect(url_for("produccion.stock_ingreso"))
        except Exception as e:
            flash(str(e), "danger")
    return render_template(
        "produccion/stock_ingreso.html",
        operadores=_operadores(),
        username=current_user().username,
    )


@bp.route("/stock/consumo", methods=["GET", "POST"])
@login_required
@permission_required("bolson_carga")
def stock_consumo():
    cat = (request.values.get("categoria") or "materia_prima").strip()
    producto = (request.values.get("producto") or "").strip()
    marcas: list[str] = []
    if producto:
        try:
            marcas = stock_service.marcas_con_stock(cat, producto)
        except Exception:
            marcas = []
    if request.method == "POST":
        try:
            eq = request.form.get("equipo_id")
            stock_service.save_consumo(
                request.form.get("categoria") or "",
                request.form.get("producto") or "",
                request.form.get("marca") or "",
                float((request.form.get("cantidad") or "0").replace(",", ".")),
                (request.form.get("operador") or current_user().username),
                request.form.get("observaciones") or "",
                int(eq) if eq else None,
            )
            flash("Consumo guardado.", "success")
            return redirect(url_for("produccion.stock_consumo", categoria=cat))
        except Exception as e:
            flash(str(e), "danger")

    productos = []
    try:
        productos = stock_service.productos_catalogo(cat)
    except Exception:
        productos = []

    return render_template(
        "produccion/stock_consumo.html",
        categoria=cat,
        productos=productos,
        producto_sel=producto,
        marcas=marcas,
        equipos=stock_service.equipos_activos(),
        operadores=_operadores(),
        username=current_user().username,
        is_filter=stock_service.is_filter_product(cat, producto) if producto else False,
    )


@bp.get("/stock/ver")
@login_required
@permission_required("bolson_registro")
def stock_ver():
    cat = (request.args.get("categoria") or "materia_prima").strip()
    try:
        items = stock_service.stock_consolidado(cat)
    except Exception:
        items = []
    return render_template("produccion/stock_ver.html", categoria=cat, items=items)


# ----- Gráficos (resumen simple) -----
@bp.get("/graficos")
@login_required
@permission_required("graficos")
def graficos():
    desde = (request.args.get("desde") or datetime.now().strftime("%Y-%m-%d")).strip()
    rows = db.session.execute(
        select(SalmueraRegistro.fecha_iso, func.count(SalmueraRegistro.id))
        .where(SalmueraRegistro.fecha_iso >= desde)
        .group_by(SalmueraRegistro.fecha_iso)
        .order_by(SalmueraRegistro.fecha_iso)
    ).all()
    return render_template("produccion/graficos.html", desde=desde, serie=[{"fecha": r[0], "n": r[1]} for r in rows])
