from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


KIND_DIRECT = "direct"
KIND_GROUP = "group"
KIND_ROLE = "role"


class InternalChatThread(db.Model):
    __tablename__ = "internal_chat_threads"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    kind = db.Column(db.String(16), nullable=False, default=KIND_DIRECT, server_default=KIND_DIRECT)
    title = db.Column(db.String(256), nullable=False, default="", server_default="")
    target_role = db.Column(db.String(32), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)

    created_by = db.relationship("User", foreign_keys=[created_by_id])
    participants = db.relationship(
        "InternalChatParticipant",
        backref="thread",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    messages = db.relationship(
        "InternalChatMessage",
        backref="thread",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="InternalChatMessage.id",
    )


class InternalChatParticipant(db.Model):
    __tablename__ = "internal_chat_participants"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    thread_id = db.Column(
        db.Integer,
        db.ForeignKey("internal_chat_threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    last_read_message_id = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    joined_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)

    user = db.relationship("User", foreign_keys=[user_id])

    __table_args__ = (db.UniqueConstraint("thread_id", "user_id", name="uq_chat_participant_thread_user"),)


class InternalChatMessage(db.Model):
    __tablename__ = "internal_chat_messages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    thread_id = db.Column(
        db.Integer,
        db.ForeignKey("internal_chat_threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    body = db.Column(db.String(4000), nullable=False, default="", server_default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)

    sender = db.relationship("User", foreign_keys=[sender_id])
