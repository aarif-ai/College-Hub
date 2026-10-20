"""Student registration for events."""
import secrets

from sqlalchemy.exc import IntegrityError

from app import constants as C
from app.extensions import db
from app.models import Event, Registration
from app.services import achievements
from app.services.errors import ServiceError
from app.services.notifications import notify
from app.utils import now

# No 0/O/1/I so codes are easy to read aloud at the registration desk.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_reg_code(event_id: int) -> str:
    """Unique registration ID such as ``CH-2026-004-7K2QX``."""
    while True:
        suffix = "".join(secrets.choice(_ALPHABET) for _ in range(5))
        code = f"CH-{now().year}-{event_id:03d}-{suffix}"
        if not Registration.query.filter_by(reg_code=code).first():
            return code


def register_student(student, event: Event) -> Registration:
    """Register ``student`` or raise ``ServiceError`` explaining why not."""
    if student.role != C.STUDENT:
        raise ServiceError("Only students can register for events.", "forbidden")
    if not student.is_verified:
        raise ServiceError("Only verified CollegeHub members can register for events. "
                           "Complete your profile and wait for verification.",
                           "verification_required")

    existing = Registration.query.filter_by(student_id=student.id, event_id=event.id).first()
    if existing and existing.is_confirmed:
        raise ServiceError("You are already registered for this event.", "duplicate")

    reason = event.registration_block_reason()
    if reason:
        raise ServiceError(reason, "closed")

    if existing:  # previously cancelled: reactivate the same record and ID
        existing.status = C.REG_CONFIRMED
        existing.cancelled_at = None
        existing.created_at = now()
        registration = existing
    else:
        registration = Registration(
            reg_code=generate_reg_code(event.id),
            student_id=student.id,
            event_id=event.id,
        )
        db.session.add(registration)

    try:
        db.session.flush()  # assigns registration.id (or raises on a duplicate)
        notify(student, f"You are registered for '{event.title}'. Your QR code is ready.",
               f"/student/registrations/{registration.id}")
        achievements.evaluate_student(student)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ServiceError("You are already registered for this event.", "duplicate")
    return registration


def cancel_registration(registration: Registration, actor) -> Registration:
    is_owner = actor.id == registration.student_id
    is_event_organizer = (
        actor.role == C.ORGANIZER and registration.event.organizer_id == actor.id
    )
    if not (is_owner or is_event_organizer):
        raise ServiceError("You cannot cancel this registration.", "forbidden")
    if not registration.is_confirmed:
        raise ServiceError("This registration is already cancelled.", "invalid_state")
    if registration.attendance is not None:
        raise ServiceError("Attendance is already recorded, so it cannot be cancelled.",
                           "invalid_state")
    registration.status = C.REG_CANCELLED
    registration.cancelled_at = now()
    if not is_owner:
        notify(registration.student,
               f"Your registration for '{registration.event.title}' was cancelled by the organizer.")
    db.session.commit()
    return registration
