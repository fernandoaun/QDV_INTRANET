"""Rutas de stock operativo registradas sobre el blueprint `produccion` (URLs /produccion/stock/*)."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.auth_utils import (
    current_user,
    login_required,
    user_can_access_stock_hub,
    user_can_edit_stock_consumos,
    user_can_edit_stock_ingreso_categoria,
    user_can_view_stock_consumos,
    user_can_view_stock_existencias,
    user_can_view_stock_ingreso_categoria,
)
from app.services import stock_service
from app.web.modules.produccion.operativa_context import (
    default_operador_for_salmuera,
    now_local,
    operador_display_line,
)


def register_stock_routes(bp: Blueprint) -> None:
    @bp.get("/stock")
    @login_required
    def stock_hub():
        u = current_user()
        if not user_can_access_stock_hub(u):
            flash("No tenés permiso para stock/consumos.", "warning")
            return redirect(url_for("produccion.hub"))
        ctx = stock_service.build_stock_hub_template_context(u)
        return render_template("produccion/stock_hub.html", **ctx)

    @bp.route("/stock/ingreso", methods=["GET", "POST"])
    @login_required
    def stock_ingreso():
        u = current_user()
        categoria_req = (request.values.get("categoria") or "materia_prima").strip()
        categorias_habilitadas: list[str] = []
        if user_can_view_stock_ingreso_categoria(u, "materia_prima"):
            categorias_habilitadas.append("materia_prima")
            categorias_habilitadas.append("producto_terminado")
        if user_can_view_stock_ingreso_categoria(u, "laboratorio"):
            categorias_habilitadas.append("laboratorio")
        if not categorias_habilitadas:
            flash("No tenés permiso para ingresar stock.", "warning")
            return redirect(url_for("produccion.stock_hub"))
        if categoria_req not in categorias_habilitadas:
            categoria_req = categorias_habilitadas[0]

        if request.method == "POST":
            categoria_post = (request.form.get("categoria") or categoria_req).strip()
            if not user_can_view_stock_ingreso_categoria(u, categoria_post):
                flash("No tenés permiso para ver este ingreso.", "warning")
                return redirect(url_for("produccion.stock_hub"))
            if not user_can_edit_stock_ingreso_categoria(u, categoria_post):
                flash("Tenés acceso de solo lectura para este ingreso.", "warning")
                return redirect(url_for("produccion.stock_ingreso", categoria=categoria_post))
            try:
                u_post = current_user()
                stock_service.save_ingreso_from_web_form(
                    request.form,
                    categoria_post=categoria_post,
                    username_fallback=(u_post.username if u_post else None),
                    default_operador=default_operador_for_salmuera(),
                    actor_is_admin=bool(current_user().is_admin),
                    fecha_hora_fallback=now_local(),
                )
                flash("Ingreso guardado.", "success")
                return redirect(url_for("produccion.stock_ingreso", categoria=categoria_post))
            except Exception as e:
                flash(str(e), "danger")
        dt_local = now_local()
        return render_template(
            "produccion/stock_ingreso.html",
            categoria_sel=categoria_req,
            categorias_habilitadas=categorias_habilitadas,
            username=current_user().username,
            is_admin=bool(current_user().is_admin),
            default_fecha_ingreso=dt_local.strftime("%Y-%m-%d"),
            default_hora_ingreso=dt_local.strftime("%H:%M"),
            operador_sugerido=default_operador_for_salmuera(),
            operador_display_line=operador_display_line(),
        )

    @bp.route("/stock/consumo", methods=["GET", "POST"])
    @login_required
    def stock_consumo():
        u = current_user()
        if not user_can_view_stock_consumos(u):
            flash("No tenés permiso para ver consumos.", "warning")
            return redirect(url_for("produccion.stock_hub"))
        cat = (request.values.get("categoria") or "materia_prima").strip()
        producto = (request.values.get("producto") or "").strip()
        if request.method == "POST":
            if not user_can_edit_stock_consumos(u):
                flash("Tenés acceso de solo lectura en consumos.", "warning")
                return redirect(url_for("produccion.stock_consumo", categoria=cat, producto=producto))
            try:
                stock_service.save_consumo_from_web_form(
                    request.form,
                    default_operador=default_operador_for_salmuera(),
                )
                flash("Consumo guardado.", "success")
                return redirect(url_for("produccion.stock_consumo", categoria=cat))
            except Exception as e:
                flash(str(e), "danger")

        data = stock_service.load_stock_consumo_view_data(cat, producto)
        return render_template(
            "produccion/stock_consumo.html",
            categoria=cat,
            productos=data["productos"],
            producto_sel=producto,
            marcas=data["marcas"],
            equipos=data["equipos"],
            consumos_recientes=data["consumos_recientes"],
            operador_sugerido=default_operador_for_salmuera(),
            operador_display_line=operador_display_line(),
            username=current_user().username if current_user() else "",
            producto_requiere_equipo=data["producto_requiere_equipo"],
            producto_es_stockeable=data["producto_es_stockeable"],
        )

    @bp.get("/stock/ver")
    @login_required
    def stock_ver():
        u = current_user()
        if not user_can_view_stock_existencias(u):
            flash("No tenés permiso para ver existencias.", "warning")
            return redirect(url_for("produccion.stock_hub"))
        ctx = stock_service.build_stock_ver_template_context(request.args.get("categoria") or "todas")
        return render_template("produccion/stock_ver.html", **ctx)
