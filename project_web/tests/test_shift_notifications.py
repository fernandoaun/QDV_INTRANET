from __future__ import annotations

from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import ShiftHandover, ShiftSession, User
from app.services import shift_handover_service as sh
from app.user_roles import ROLE_LOGISTICA, ROLE_OPERACIONES


def test_list_shift_observation_notifications_filters_and_orders(app):
    with app.app_context():
        op = User(
            username="pytest_notif_ops",
            password_hash=generate_password_hash("x"),
            is_admin=False,
            activo=True,
            rol=ROLE_OPERACIONES,
        )
        db.session.add(op)
        db.session.flush()
        sess = ShiftSession(
            user_id=int(op.id),
            effective_role=ROLE_OPERACIONES,
            started_at_iso="2026-05-01T08:00:00",
            ended_at_iso="2026-05-01T16:00:00",
            status="closed",
            created_at_iso="2026-05-01T08:00:00",
            updated_at_iso="2026-05-01T16:00:00",
        )
        db.session.add(sess)
        db.session.flush()
        ho_empty = ShiftHandover(
            shift_session_id=int(sess.id),
            outgoing_user_id=int(op.id),
            incoming_user_id=int(op.id),
            shift_started_at_iso="2026-05-01T08:00:00",
            handed_over_at_iso="2026-05-01T12:00:00",
            received_at_iso="2026-05-01T12:30:00",
            hypochlorite_stock_liters=100.0,
            closing_notes=None,
            reception_notes=None,
            reception_status="accepted",
            status="received",
            created_at_iso="2026-05-01T12:00:00",
            updated_at_iso="2026-05-01T12:30:00",
        )
        ho_with_notes = ShiftHandover(
            shift_session_id=int(sess.id),
            outgoing_user_id=int(op.id),
            incoming_user_id=int(op.id),
            shift_started_at_iso="2026-05-02T08:00:00",
            handed_over_at_iso="2026-05-02T16:00:00",
            received_at_iso="2026-05-02T16:30:00",
            hypochlorite_stock_liters=90.0,
            closing_notes="Bomba 2 con ruido",
            reception_notes="Tomado conocimiento",
            reception_status="accepted_with_observations",
            status="received",
            created_at_iso="2026-05-02T16:00:00",
            updated_at_iso="2026-05-02T16:30:00",
        )
        db.session.add_all([ho_empty, ho_with_notes])
        db.session.commit()
        notes_id = int(ho_with_notes.id)

        items = sh.list_shift_observation_notifications(10)
        assert len(items) == 1
        assert items[0]["id"] == notes_id
        assert items[0]["has_closing_notes"] is True
        assert items[0]["has_reception_notes"] is True
        assert "Bomba 2" in items[0]["closing_notes"]
        assert "Tomado" in items[0]["reception_notes"]


def test_user_can_view_shift_handover_notifications_all_profiles(app):
    with app.app_context():
        users = [
            User(
                username="pytest_notif_admin",
                password_hash=generate_password_hash("x"),
                is_admin=True,
                activo=True,
                rol="operaciones",
            ),
            User(
                username="pytest_notif_ops2",
                password_hash=generate_password_hash("x"),
                is_admin=False,
                activo=True,
                rol=ROLE_OPERACIONES,
            ),
            User(
                username="pytest_notif_log",
                password_hash=generate_password_hash("x"),
                is_admin=False,
                activo=True,
                rol=ROLE_LOGISTICA,
            ),
        ]
        db.session.add_all(users)
        db.session.commit()
        for u in users:
            assert sh.user_can_view_shift_handover_notifications(u) is True
        assert sh.user_can_view_shift_handover_notifications(None) is False


def test_index_renders_with_shift_notifications_bell(app, client):
  from werkzeug.security import generate_password_hash

  from app.extensions import db
  from app.models import User

  with app.app_context():
      u = User(
          username="pytest_bell_render",
          password_hash=generate_password_hash("x"),
          is_admin=True,
          activo=True,
          rol="administrador",
      )
      db.session.add(u)
      db.session.commit()
      uid = int(u.id)

  with client.session_transaction() as sess:
      sess["user_id"] = uid
      sess["perms"] = list(__import__("app.constants", fromlist=["PERMISSION_KEYS"]).PERMISSION_KEYS)
      sess["perms_edit"] = sess["perms"]

  r = client.get("/")
  assert r.status_code == 200
  body = r.get_data(as_text=True)
  assert "appNotificationsBtn" in body
  assert "Error interno" not in body


def test_mark_shift_observation_notifications_seen_updates_session(app):
    with app.app_context():
        from flask import session

        with app.test_request_context():
            session.clear()
            sh.mark_shift_observation_notifications_seen(session, up_to_id=42)
            assert session[sh.SESSION_KEY_SHIFT_NOTIF_LAST_SEEN_ID] == 42
            sh.mark_shift_observation_notifications_seen(session, up_to_id=30)
            assert session[sh.SESSION_KEY_SHIFT_NOTIF_LAST_SEEN_ID] == 42
