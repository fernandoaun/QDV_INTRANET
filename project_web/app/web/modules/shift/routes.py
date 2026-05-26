from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar, cast

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth_utils import current_user, login_required, user_can_access_production_hub
from app.extensions import db
from app.models import ShiftHandover, ShiftSession, User
from app.security_http import request_path_for_login_next
from app.services import shift_handover_service as sh

bp = Blueprint("shift", __name__, url_prefix="/operacion/turno")

F = TypeVar("F", bound=Callable[..., Any])


def _shift_eligible_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        u = current_user()
        if u is None:
            return redirect(url_for("auth.login", next=request_path_for_login_next()))
        if not sh.user_participates_operational_shift(u):
            flash("Esta sección es solo para el perfil de operaciones.", "warning")
            return redirect(url_for("main.dashboard"))
        return view(*args, **kwargs)

    return cast(F, wrapped)


def _shift_notifications_view_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        u = current_user()
        if u is None:
            return redirect(url_for("auth.login", next=request_path_for_login_next()))
        if not sh.user_can_view_shift_handover_notifications(u):
            return "", 403
        return view(*args, **kwargs)

    return cast(F, wrapped)


def _redirect_next_or_dashboard() -> Any:
    n = (request.args.get("next") or request.form.get("next") or "").strip()
    if n.startswith("/"):
        return redirect(n)
    return redirect(url_for("main.dashboard"))


@bp.get("/post-login")
@login_required
def post_login():
    u = current_user()
    if u is None:
        return redirect(url_for("auth.login"))
    if not sh.user_participates_operational_shift(u):
        return _redirect_next_or_dashboard()
    open_s = sh.get_open_shift_session()
    pending = sh.get_pending_handover()
    if open_s is not None and int(open_s.user_id) == int(u.id):
        return _redirect_next_or_dashboard()
    if open_s is not None and int(open_s.user_id) != int(u.id):
        flash(
            f"Hay un turno operativo abierto a cargo de {sh.format_shift_operator_display(open_s)}. "
            "Coordiná la entrega antes de tomar turno.",
            "info",
        )
        return _redirect_next_or_dashboard()
    if pending is not None:
        flash(
            "Hay una entrega de turno pendiente de recepción. Entrá a Producción → Cambio de turno y seguí el flujo de recepción, o usá el enlace del aviso superior.",
            "warning",
        )
        return _redirect_next_or_dashboard()
    if session.get(sh.SESSION_KEY_SHIFT_DECLINED):
        return _redirect_next_or_dashboard()
    n = (request.args.get("next") or "").strip()
    q = f"?next={n}" if n.startswith("/") else ""
    return redirect(url_for("shift.offer_take") + q)


@bp.route("/oferta-inicial", methods=["GET", "POST"])
@login_required
@_shift_eligible_required
def offer_take():
    u = current_user()
    assert u is not None
    if sh.get_pending_handover() is not None:
        return redirect(url_for("shift.take_shift"))
    open_s = sh.get_open_shift_session()
    if open_s is not None:
        if int(open_s.user_id) == int(u.id):
            flash("Ya tenés el turno operativo activo.", "info")
            return _redirect_next_or_dashboard()
        flash(
            f"El turno lo tiene {sh.format_shift_operator_display(open_s)}. No podés abrir otro.",
            "warning",
        )
        return _redirect_next_or_dashboard()
    if request.method == "POST":
        choice = (request.form.get("choice") or "").strip().lower()
        nxt = (request.form.get("next") or "").strip()
        if choice == "no":
            session[sh.SESSION_KEY_SHIFT_DECLINED] = True
            flash(
                "Entraste en modo solo lectura: podés consultar todo lo que tu perfil permite, pero no guardar ni confirmar acciones hasta activar el turno de planta (te lo pedirá el sistema al iniciar sesión o desde el aviso en pantalla).",
                "warning",
            )
            if nxt.startswith("/"):
                return redirect(nxt)
            return redirect(url_for("main.dashboard"))
        if choice == "si":
            q = f"?next={nxt}" if nxt.startswith("/") else ""
            return redirect(url_for("shift.confirm_take_shift") + q)
        flash("Elegí una opción válida.", "danger")
    return render_template("shift/offer_take.html", next_q=(request.args.get("next") or "").strip())


@bp.route("/confirmar-toma", methods=["GET", "POST"])
@login_required
@_shift_eligible_required
def confirm_take_shift():
    """Tras confirmar que toma turno: laboratorista acompañante opcional."""
    u = current_user()
    assert u is not None
    if sh.get_pending_handover() is not None:
        return redirect(url_for("shift.take_shift"))
    open_s = sh.get_open_shift_session()
    if open_s is not None:
        if int(open_s.user_id) == int(u.id):
            flash("Ya tenés el turno operativo activo.", "info")
            return _redirect_next_or_dashboard()
        flash(
            f"El turno lo tiene {sh.format_shift_operator_display(open_s)}. No podés abrir otro.",
            "warning",
        )
        return _redirect_next_or_dashboard()
    nxt = (request.args.get("next") or request.form.get("next") or "").strip()
    if request.method == "POST":
        lab_id, err = sh.resolve_laboratorist_from_form(
            request.form.get("with_laboratorist"),
            request.form.get("laboratorist_user_id"),
        )
        if err:
            flash(err, "danger")
            return render_template(
                "shift/confirm_take.html",
                next_q=nxt,
                laboratoristas=sh.list_active_laboratorista_users(),
            )
        return _create_open_shift_and_redirect(u, nxt, lab_id)
    return render_template(
        "shift/confirm_take.html",
        next_q=nxt,
        laboratoristas=sh.list_active_laboratorista_users(),
    )


@bp.route("/laboratorista-turno", methods=["GET", "POST"])
@login_required
@_shift_eligible_required
def edit_shift_laboratorist():
    """Actualizar laboratorista del turno abierto (solo titular)."""
    u = current_user()
    assert u is not None
    sess = sh.get_shift_session_for_user(u)
    if sess is None:
        flash("Solo podés informar laboratorista si tenés el turno operativo activo a tu nombre.", "warning")
        return redirect(url_for("produccion.hub"))
    if sh.get_pending_handover() is not None:
        flash("Hay una entrega de turno pendiente de recepción.", "danger")
        return redirect(url_for("shift.take_shift"))
    if request.method == "POST":
        lab_id, err = sh.resolve_laboratorist_from_form(
            request.form.get("with_laboratorist"),
            request.form.get("laboratorist_user_id"),
        )
        if err:
            flash(err, "danger")
        else:
            sess.laboratorist_user_id = lab_id
            sess.updated_at_iso = sh.now_local_iso()
            db.session.commit()
            flash("Laboratorista del turno actualizado.", "success")
            return redirect(url_for("produccion.hub"))
    return render_template(
        "shift/edit_shift_laboratorist.html",
        shift_session=sess,
        laboratoristas=sh.list_active_laboratorista_users(),
    )


def _create_open_shift_and_redirect(u: User, nxt: str, laboratorist_user_id: int | None = None) -> Any:
    try:
        sh.persist_new_open_shift_session(u, laboratorist_user_id)
    except ValueError as e:
        msg = str(e)
        flash(msg, "danger")
        if msg.startswith("Antes debés"):
            return redirect(url_for("shift.take_shift"))
        if msg == "Ya hay un turno activo.":
            return redirect(url_for("main.dashboard"))
        return redirect(url_for("shift.confirm_take_shift", next=nxt))
    flash("Turno operativo tomado.", "success")
    if nxt.startswith("/"):
        return redirect(nxt)
    return redirect(url_for("main.dashboard"))


@bp.get("/tomar")
@login_required
@_shift_eligible_required
def take_shift():
    """Desde hub: recepción pendiente o apertura de turno."""
    u = current_user()
    assert u is not None
    pending = sh.get_pending_handover()
    if pending is not None:
        if int(pending.outgoing_user_id) == int(u.id):
            flash("No podés recepcionar tu propia entrega de turno.", "danger")
            return redirect(url_for("produccion.hub"))
        return redirect(url_for("shift.receive_handover", handover_id=pending.id))
    open_s = sh.get_open_shift_session()
    if open_s is not None and int(open_s.user_id) == int(u.id):
        flash("Ya tenés el turno operativo activo.", "info")
        return redirect(url_for("produccion.hub"))
    if open_s is not None:
        flash(
            f"El turno lo tiene {sh.format_shift_operator_display(open_s)}. Esperá la entrega.",
            "warning",
        )
        return redirect(url_for("produccion.hub"))
    session.pop(sh.SESSION_KEY_SHIFT_DECLINED, None)
    return redirect(url_for("shift.confirm_take_shift"))


@bp.route("/entregar", methods=["GET", "POST"])
@login_required
@_shift_eligible_required
def handover_form():
    u = current_user()
    assert u is not None
    sess = sh.get_shift_session_for_user(u)
    if sess is None:
        flash("No tenés un turno operativo abierto para entregar.", "warning")
        return redirect(url_for("produccion.hub"))
    if sh.get_pending_handover() is not None:
        flash("Hay una entrega pendiente de recepción; no se puede iniciar otra.", "danger")
        return redirect(url_for("produccion.hub"))
    now_iso = sh.now_local_iso()
    warn_items = sh.collect_warning_items_for_user(u, sess.started_at_iso, now_iso)
    consumos = sh.consumos_en_intervalo(sess.started_at_iso, now_iso)
    from_logout = (request.args.get("from_logout") or request.form.get("from_logout") or "").strip() == "1"

    if request.method == "POST":
        try:
            sh.persist_handover_submission(request.form, u, sess, warn_items, now_iso)
        except ValueError as e:
            db.session.rollback()
            flash(str(e), "danger")
        else:
            flash("Entrega de turno registrada. El próximo operador debe recepcionarla.", "success")
            do_logout = (request.form.get("after_logout") or "").strip() == "1"
            if do_logout:
                session.clear()
                return redirect(url_for("main.index"))
            return redirect(url_for("produccion.hub"))

    return render_template(
        "shift/handover.html",
        shift_session=sess,
        consumos=consumos,
        warn_items=warn_items,
        from_logout=from_logout,
    )


@bp.route("/recibir/<int:handover_id>", methods=["GET", "POST"])
@login_required
@_shift_eligible_required
def receive_handover(handover_id: int):
    u = current_user()
    assert u is not None
    ho = db.session.get(ShiftHandover, handover_id)
    if ho is None or ho.status != sh.HANDOVER_PENDING:
        flash("Entrega de turno no encontrada o ya recepcionada.", "danger")
        return redirect(url_for("shift.historial"))
    if int(ho.outgoing_user_id) == int(u.id):
        flash("No podés recepcionar tu propia entrega.", "danger")
        return redirect(url_for("produccion.hub"))
    pending = sh.get_pending_handover()
    if pending is None or int(pending.id) != int(ho.id):
        flash("Esta entrega no es la pendiente actual.", "danger")
        return redirect(url_for("shift.historial"))
    detail = sh.handover_to_detail_dict(ho)
    if request.method == "POST":
        try:
            sh.persist_handover_reception(
                request.form,
                u,
                ho,
                lambda: session.pop(sh.SESSION_KEY_SHIFT_DECLINED, None),
            )
        except ValueError as e:
            db.session.rollback()
            flash(str(e), "danger")
        else:
            flash("Turno recepcionado. Tenés el turno operativo activo.", "success")
            return redirect(url_for("produccion.hub"))
    return render_template(
        "shift/receive.html",
        ho=ho,
        detail=detail,
        laboratoristas=sh.list_active_laboratorista_users(),
    )


@bp.route("/salir-pregunta", methods=["GET", "POST"])
@login_required
@_shift_eligible_required
def logout_ask_leave_shift():
    """Tras intentar cerrar sesión con turno propio: preguntar si entrega turno."""
    u = current_user()
    assert u is not None
    if not sh.user_has_open_shift(u):
        flash("No tenés turno abierto. Podés cerrar sesión desde el menú de usuario.", "info")
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        choice = (request.form.get("choice") or "").strip().lower()
        if choice == "si":
            return redirect(url_for("shift.handover_form", from_logout=1))
        if choice == "mantener":
            session.clear()
            flash(
                "Sesión cerrada. El turno operativo queda abierto a tu nombre para que otro perfil use esta computadora.",
                "info",
            )
            return redirect(url_for("auth.login"))
        if choice == "no":
            flash(
                "Seguís conectado con el turno a tu nombre. Cuando quieras cambiar de usuario en esta computadora, usá "
                "«Cerrar sesión y mantener turno abierto».",
                "warning",
            )
            return redirect(url_for("main.dashboard"))
        flash("Elegí una opción válida.", "danger")
    return render_template("shift/logout_ask_leave.html")


@bp.post("/notificaciones/visto")
@login_required
@_shift_notifications_view_required
def notifications_mark_seen():
    raw = (request.form.get("up_to_id") or "").strip()
    up_to: int | None = None
    if raw:
        try:
            up_to = int(raw)
        except ValueError:
            up_to = None
    sh.mark_shift_observation_notifications_seen(session, up_to_id=up_to)
    return "", 204


@bp.route("/historial")
@login_required
def historial():
    summaries = sh.summarize_handovers_for_history_view()
    return render_template("shift/historial.html", rows=summaries)


@bp.get("/historial/<int:hid>")
@login_required
def historial_detalle(hid: int):
    u = current_user()
    assert u is not None
    ho = db.session.scalar(
        select(ShiftHandover)
        .where(ShiftHandover.id == hid)
        .options(
            selectinload(ShiftHandover.shift_session).selectinload(ShiftSession.user),
            selectinload(ShiftHandover.shift_session).selectinload(ShiftSession.laboratorist_user),
        )
    )
    if ho is None:
        flash("Registro no encontrado.", "danger")
        return redirect(url_for("shift.historial"))
    detail = sh.handover_to_detail_dict(ho)
    if sh.user_can_view_shift_handover_notifications(u):
        sh.mark_shift_observation_notifications_seen(session, up_to_id=int(ho.id))
    return render_template("shift/historial_detalle.html", ho=ho, detail=detail)