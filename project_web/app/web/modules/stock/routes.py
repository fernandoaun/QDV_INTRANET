"""Rutas de stock operativo registradas sobre el blueprint `produccion` (URLs /produccion/stock/*)."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.auth_utils import (
    current_user,
    login_required,
    user_can_access_stock_hub,
    user_can_edit_stock_catalogo_alta,
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
                    fecha_hora_fallback=now_local(),
                    cargado_por_user_id=int(u_post.id) if u_post else None,
                )
                flash("Ingreso guardado.", "success")
                return redirect(url_for("produccion.stock_ingreso", categoria=categoria_post))
            except Exception as e:
                flash(str(e), "danger")
        dt_local = now_local()
        try:
            productos_sugeridos = stock_service.productos_catalogo(categoria_req)
        except Exception:
            productos_sugeridos = []
        return render_template(
            "produccion/stock_ingreso.html",
            categoria_sel=categoria_req,
            categorias_habilitadas=categorias_habilitadas,
            username=current_user().username,
            default_fecha_ingreso=dt_local.strftime("%Y-%m-%d"),
            default_hora_ingreso=dt_local.strftime("%H:%M"),
            operador_sugerido=default_operador_for_salmuera(),
            operador_display_line=operador_display_line(),
            productos_sugeridos=productos_sugeridos,
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
        marca = (request.values.get("marca") or "").strip()
        if request.method == "POST":
            if not user_can_edit_stock_consumos(u):
                flash("Tenés acceso de solo lectura en consumos.", "warning")
                return redirect(url_for("produccion.stock_consumo", categoria=cat, producto=producto, marca=marca))
            try:
                stock_service.save_consumo_from_web_form(
                    request.form,
                    default_operador=default_operador_for_salmuera(),
                )
                flash("Consumo guardado.", "success")
                return redirect(url_for("produccion.stock_consumo", categoria=cat))
            except Exception as e:
                flash(str(e), "danger")

        data = stock_service.load_stock_consumo_view_data(cat, producto, marca)
        return render_template(
            "produccion/stock_consumo.html",
            categoria=cat,
            productos=data["productos"],
            producto_sel=producto,
            marca_sel=data.get("marca_sel") or "",
            marcas=data["marcas"],
            lotes=data.get("lotes") or [],
            equipos=data["equipos"],
            consumos_recientes=data["consumos_recientes"],
            operador_sugerido=default_operador_for_salmuera(),
            operador_display_line=operador_display_line(),
            username=current_user().username if current_user() else "",
            producto_requiere_equipo=data["producto_requiere_equipo"],
            producto_es_stockeable=data["producto_es_stockeable"],
        )

    @bp.route("/stock/ajustes", methods=["GET", "POST"])
    @login_required
    def stock_ajustes():
        u = current_user()
        if u is None or not bool(getattr(u, "is_admin", False)):
            flash("Solo administradores pueden registrar ajustes de stock.", "warning")
            return redirect(url_for("produccion.stock_hub"))
        cat = (request.values.get("categoria") or "materia_prima").strip()
        producto = (request.values.get("producto") or "").strip()
        marca = (request.values.get("marca") or "").strip()
        if request.method == "POST":
            cat = (request.form.get("categoria") or cat).strip()
            producto = (request.form.get("producto") or producto).strip()
            marca = (request.form.get("marca") or marca).strip()
            try:
                stock_service.save_ajuste_from_web_form(
                    request.form,
                    operador=operador_display_line() or default_operador_for_salmuera() or u.username,
                    admin_user_id=int(u.id),
                )
                flash("Ajuste de stock guardado.", "success")
                return redirect(url_for("produccion.stock_ajustes", categoria=cat, producto=producto, marca=marca))
            except Exception as e:
                flash(str(e), "danger")
        data = stock_service.load_stock_ajuste_view_data(cat, producto, marca)
        return render_template(
            "produccion/stock_ajustes.html",
            categoria=cat,
            productos=data["productos"],
            producto_sel=data["producto_sel"],
            producto_es_stockeable=data["producto_es_stockeable"],
            marca_sel=data["marca_sel"],
            marcas=data["marcas"],
            lotes=data["lotes"],
            ajustes_recientes=data["ajustes_recientes"],
            operador_display_line=operador_display_line(),
            operador_sugerido=default_operador_for_salmuera(),
            username=u.username,
        )

    @bp.get("/stock/ver")
    @login_required
    def stock_ver():
        u = current_user()
        if not user_can_view_stock_existencias(u):
            flash("No tenés permiso para ver existencias.", "warning")
            return redirect(url_for("produccion.stock_hub"))
        dias_ing = 30
        try:
            dias_ing = int((request.args.get("dias_ingresos") or "30").strip())
        except ValueError:
            dias_ing = 30
        try:
            ctx = stock_service.build_stock_ver_template_context(
                request.args.get("categoria") or "todas",
                fecha_consulta=request.args.get("fecha_consulta"),
                hora_consulta=request.args.get("hora_consulta"),
                dias_ingresos=dias_ing,
            )
        except ValueError as e:
            flash(str(e), "warning")
            ctx = stock_service.build_stock_ver_template_context(
                request.args.get("categoria") or "todas",
                dias_ingresos=dias_ing,
            )
        return render_template("produccion/stock_ver.html", **ctx)

    @bp.route("/stock/catalogo", methods=["GET"])
    @login_required
    def stock_catalogo_lista():
        u = current_user()
        if not user_can_access_stock_hub(u):
            flash("No tenés permiso.", "warning")
            return redirect(url_for("produccion.hub"))
        filtro = (request.args.get("categoria") or "").strip()
        try:
            rows = stock_service.list_productos_catalogo_rows(filtro or None)
        except Exception:
            rows = []
        return render_template(
            "produccion/stock_catalogo_lista.html",
            rows=rows,
            filtro_cat=filtro,
        )

    @bp.route("/stock/catalogo/alta", methods=["GET", "POST"])
    @login_required
    def stock_catalogo_alta():
        u = current_user()
        if not user_can_edit_stock_catalogo_alta(u):
            flash("No tenés permiso para dar de alta productos en catálogo.", "warning")
            return redirect(url_for("produccion.stock_hub"))
        categorias_alta: list[str] = []
        if u.is_admin or user_can_edit_stock_ingreso_categoria(u, "materia_prima"):
            categorias_alta.extend(["materia_prima", "producto_terminado"])
        if u.is_admin or user_can_edit_stock_ingreso_categoria(u, "laboratorio"):
            if "laboratorio" not in categorias_alta:
                categorias_alta.append("laboratorio")
        if not categorias_alta:
            flash("No tenés permiso de ingreso para ninguna categoría.", "warning")
            return redirect(url_for("produccion.stock_hub"))
        if request.method == "POST":
            cat = (request.form.get("categoria") or "").strip()
            if not user_can_edit_stock_ingreso_categoria(u, cat):
                flash("No tenés permiso de edición para esa categoría.", "warning")
                return redirect(url_for("produccion.stock_catalogo_alta"))
            try:
                smin_raw = (request.form.get("stock_minimo_alerta") or "").strip().replace(",", ".")
                smin = float(smin_raw) if smin_raw else 0.0
                is_stock = (request.form.get("is_stockable") or "1").strip() != "0"
                stock_service.create_catalog_product(
                    cat,
                    request.form.get("nombre_producto") or "",
                    stock_minimo_alerta=smin,
                    tipo_producto=(request.form.get("tipo_producto") or "Normal").strip() or "Normal",
                    requiere_equipo=(request.form.get("requiere_equipo") == "1"),
                    is_stockable=is_stock,
                )
                flash("Producto creado en el catálogo.", "success")
                return redirect(url_for("produccion.stock_catalogo_lista"))
            except Exception as e:
                flash(str(e), "danger")
        return render_template("produccion/stock_catalogo_alta.html", categorias_alta=categorias_alta)

    @bp.route("/stock/catalogo/<int:pid>/editar", methods=["GET", "POST"])
    @login_required
    def stock_catalogo_editar(pid: int):
        u = current_user()
        if u is None or not u.is_admin:
            flash("Solo administradores pueden editar el catálogo de productos.", "warning")
            return redirect(url_for("produccion.stock_catalogo_lista"))
        match = stock_service.get_catalog_product(pid)
        if match is None:
            flash("Producto no encontrado.", "danger")
            return redirect(url_for("produccion.stock_catalogo_lista"))
        if request.method == "POST":
            try:
                nueva_cat = (request.form.get("nueva_categoria") or "").strip()
                if nueva_cat and nueva_cat != str(match.categoria or "").strip():
                    stock_service.reassign_catalog_product_categoria(pid, nueva_cat)
                    match = stock_service.get_catalog_product(pid)
                    if match is None:
                        flash("Producto no encontrado tras el cambio de categoría.", "danger")
                        return redirect(url_for("produccion.stock_catalogo_lista"))
                smin_raw = (request.form.get("stock_minimo_alerta") or "").strip().replace(",", ".")
                smin_opt = float(smin_raw) if smin_raw else None
                is_mp = str(match.categoria) == "materia_prima"
                stock_service.update_catalog_product_admin(
                    pid,
                    stock_minimo_alerta=smin_opt,
                    requiere_equipo=(request.form.get("requiere_equipo") == "1"),
                    is_stockable=(request.form.get("is_stockable") == "1") if is_mp else None,
                    tipo_producto=(request.form.get("tipo_producto") or "").strip() or None,
                )
                flash("Producto actualizado.", "success")
                return redirect(url_for("produccion.stock_catalogo_lista"))
            except Exception as e:
                flash(str(e), "danger")
        return render_template("produccion/stock_catalogo_editar.html", p=match)
