"""QR attendance validation.

``record_attendance`` is the single place where a scan becomes attendance.
The browser only sends the raw scanned text and the event being scanned; every
decision is made here.
"""
from sqlalchemy.exc import IntegrityError

from app import constants as C
from app.extensions import db
from app.models import Attendance, Event, Registration
from app.services import achievements, qr
from app.services.notifications import notify
from app.utils import fmt_datetime, now

SUCCESS = "success"
DUPLICATE = "duplicate"
INVALID = "invalid"
WRONG_EVENT = "wrong_event"
CANCELLED = "cancelled"
NOT_OPEN = "not_open"


def _result(status, message, registration=None, attendance=None):
    student = registration.student if registration else None
    return {
        "status": status,
        "ok": status == SUCCESS,
        "message": message,
        "student_name": student.name if student else None,
        "reg_code": registration.reg_code if registration else None,
        "scanned_at": fmt_datetime(attendance.scanned_at) if attendance else None,
    }


def record_attendance(raw_value: str, event_id, scanner) -> dict:
    """Validate a scanned value and record attendance.

    Checks, in order: the event exists and is open, the value is a genuine
    token (or a typed registration ID), the registration exists, it belongs to
    this event, it is confirmed, the student exists, and no attendance has
    been recorded yet.
    """
    raw_value = (raw_value or "").strip()
    if not raw_value or len(raw_value) > 500:
        return _result(INVALID, "Invalid QR code. Nothing was scanned.")

    event = db.session.get(Event, event_id) if isinstance(event_id, int) else None
    if event is None:
        return _result(INVALID, "This event could not be found.")
    if event.status != C.PUBLISHED:
        return _result(NOT_OPEN, "Attendance can only be recorded for published events.")

    # Scanned QR codes carry a signed token. Typed manual entries use the
    # printed registration ID; both are resolved to a registration code.
    if raw_value.startswith(qr.TOKEN_PREFIX):
        reg_code = qr.read_token(raw_value)
    else:
        reg_code = raw_value.upper()
    if not reg_code:
        return _result(INVALID, "Invalid QR code. It was not issued by CollegeHub.")

    registration = Registration.query.filter_by(reg_code=reg_code).first()
    if registration is None:
        return _result(INVALID, "Invalid QR code. No matching registration was found.")

    if registration.event_id != event.id:
        other = registration.event.title if registration.event else "another event"
        return _result(
            WRONG_EVENT,
            f"Wrong event. This registration is for '{other}', not '{event.title}'.",
            registration,
        )

    if registration.student is None:
        return _result(INVALID, "Invalid registration: the student record is missing.")

    if not registration.is_confirmed:
        return _result(CANCELLED, "This registration was cancelled and is not valid.",
                       registration)

    existing = registration.attendance
    if existing is not None:
        return _result(
            DUPLICATE,
            f"Duplicate scan. {registration.student.name} was already checked in at "
            f"{fmt_datetime(existing.scanned_at)}.",
            registration, existing,
        )

    attendance = Attendance(
        registration_id=registration.id,
        event_id=event.id,
        student_id=registration.student_id,
        scanned_by_id=scanner.id if scanner else None,
        method="qr" if raw_value.startswith(qr.TOKEN_PREFIX) else "manual",
        scanned_at=now(),
    )
    db.session.add(attendance)
    try:
        db.session.flush()
        notify(registration.student, f"Attendance recorded for '{event.title}'. Thank you for coming!",
               f"/student/registrations/{registration.id}")
        achievements.evaluate_student(registration.student)
        db.session.commit()
    except IntegrityError:
        # Two scans raced: the unique constraint let only one through.
        db.session.rollback()
        registration = Registration.query.filter_by(reg_code=reg_code).first()
        return _result(
            DUPLICATE,
            f"Duplicate scan. {registration.student.name} was already checked in.",
            registration, registration.attendance,
        )

    return _result(
        SUCCESS,
        f"Checked in: {registration.student.name}.",
        registration, attendance,
    )
