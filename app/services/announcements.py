"""Announcements and who gets to see them."""
from sqlalchemy import or_

from app import constants as C
from app.extensions import db
from app.models import Announcement, Event, Registration
from app.services.errors import ServiceError
from app.services.notifications import notify


def create_announcement(author, title: str, message: str, event: Event | None,
                        audience: str) -> Announcement:
    """Faculty may announce anything; organizers only for their own events."""
    if author.role == C.ORGANIZER:
        if event is None or event.organizer_id != author.id:
            raise ServiceError("Organizers can only announce for their own events.", "forbidden")
    elif author.role != C.FACULTY:
        raise ServiceError("You are not allowed to publish announcements.", "forbidden")

    title, message = (title or "").strip(), (message or "").strip()
    if not 3 <= len(title) <= 160:
        raise ServiceError("Title must be 3 to 160 characters.", "validation")
    if not 5 <= len(message) <= 3000:
        raise ServiceError("Message must be 5 to 3000 characters.", "validation")
    if audience not in C.AUDIENCES:
        raise ServiceError("Choose a valid audience.", "validation")

    announcement = Announcement(
        title=title, message=message, event_id=event.id if event else None,
        audience=audience, author_id=author.id,
    )
    db.session.add(announcement)
    db.session.flush()

    if event is not None and audience in ("all", "students"):
        for reg in Registration.query.filter_by(event_id=event.id, status=C.REG_CONFIRMED):
            notify(reg.student, f"Announcement: {title}", "/student/announcements")
    db.session.commit()
    return announcement


def announcements_for(user, limit: int | None = None):
    """Announcements relevant to ``user``, newest first."""
    query = Announcement.query
    if user.role == C.STUDENT:
        registered = [
            r.event_id for r in Registration.query.filter_by(
                student_id=user.id, status=C.REG_CONFIRMED)
        ]
        query = query.filter(Announcement.audience.in_(["all", "students"])).filter(
            or_(Announcement.event_id.is_(None), Announcement.event_id.in_(registered or [0]))
        )
    elif user.role == C.ORGANIZER:
        query = query.filter(Announcement.audience.in_(["all", "organizers"]))
    elif user.role == C.LOGISTICS:
        query = query.filter(Announcement.audience.in_(["all", "logistics"]))
    query = query.order_by(Announcement.created_at.desc())
    return query.limit(limit).all() if limit else query.all()
