"""In-app notifications."""
from app.extensions import db
from app.models import Notification


def notify(user, message: str, link: str | None = None, commit: bool = False) -> None:
    """Queue a notification for ``user`` (committed with the caller's work)."""
    if user is None:
        return
    db.session.add(Notification(user_id=user.id, message=message[:300], link=link))
    if commit:
        db.session.commit()


def unread_count(user) -> int:
    return Notification.query.filter_by(user_id=user.id, is_read=False).count()
