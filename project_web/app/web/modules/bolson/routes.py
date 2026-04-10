"""Registro de bolsones: rutas en blueprint `produccion`."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from app.auth_utils import login_required, permission_required
from app.extensions import db
from app.models import BolsonRegistro
from app.utils.datetime_operacion import now_operacion_naive_local


def register_bolson_routes(bp: Blueprint) -> None:
    @bp.route("/bolson", methods=["GET", "POST"])
    @login_required
    @permission_required("bolson_registro")
    def bolson():
        if request.method == "POST":
            now = now_operacion_naive_local()
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
