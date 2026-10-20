"""Audit log for important administrative actions.

``record`` only adds the row to the current session; the caller commits so the
action and its audit entry are saved together (or not at all).
"""
from app.extensions import db
from app.models import AuditLog


def record(actor, action: str, target=None, reason: str | None = None) -> AuditLog:
    entry = AuditLog(
        actor_id=actor.id if actor is not None else None,
        target_id=target.id if target is not None else None,
        action=action,
        reason=(reason or "").strip()[:1000] or None,
    )
    db.session.add(entry)
    return entry


def history_for(target, limit: int = 50):
    return (AuditLog.query.filter_by(target_id=target.id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).all())
