"""Student verification, owned by the single Organizer account.

Account status (can they sign in?) and verification status (are they a
verified member?) are separate fields. Transitions::

    PENDING ──approve──> VERIFIED
    PENDING ──reject / request correction──> REJECTED ──(student edits)──resubmit──> PENDING
    REJECTED ──approve──> VERIFIED
    any ──suspend──> SUSPENDED (account SUSPENDED too) ──reinstate──> VERIFIED or PENDING

Only the Organizer may decide. Students can only resubmit themselves.
"""
from sqlalchemy import or_

from app import constants as C
from app.extensions import db
from app.models import User
from app.services import audit
from app.services.errors import ServiceError
from app.services.notifications import notify
from app.utils import now

PAGE_SIZE = 10


def _check(actor, student):
    if actor is None or actor.role != C.ORGANIZER or not actor.is_active:
        raise ServiceError("Only the Organizer can verify students.", "forbidden")
    if student is None or student.role != C.STUDENT:
        raise ServiceError("That is not a student account.", "not_found")


def _reason(text, label="reason") -> str:
    text = (text or "").strip()
    if len(text) < 5:
        raise ServiceError(f"Please give a {label} of at least 5 characters.", "reason_required")
    return text[:1000]


def _stamp(student):
    student.verification_updated_at = now()


def approve(student, actor):
    _check(actor, student)
    if student.account_status == C.ACCOUNT_SUSPENDED:
        raise ServiceError("This account is suspended. Reinstate it first.", "invalid_state")
    if student.verification_status not in (C.VERIFY_PENDING, C.VERIFY_REJECTED):
        raise ServiceError("Only pending or rejected students can be approved.", "invalid_state")
    student.verification_status = C.VERIFY_VERIFIED
    student.verified_at = now()
    student.verified_by_id = actor.id
    student.verification_reason = None
    student.correction_requested = False
    _stamp(student)
    audit.record(actor, "student.verified", student)
    notify(student, "You are now a Verified CollegeHub Member. "
                    "Event registration and volunteering are unlocked.", "/student/profile")
    db.session.commit()
    return student


def reject(student, actor, reason, correction=False):
    """Reject the profile, or (``correction=True``) ask for changes."""
    _check(actor, student)
    reason = _reason(reason, "reason for the student")
    if student.verification_status != C.VERIFY_PENDING:
        raise ServiceError("Only pending students can be rejected.", "invalid_state")
    student.verification_status = C.VERIFY_REJECTED
    student.correction_requested = bool(correction)
    student.verification_reason = reason
    _stamp(student)
    audit.record(actor, "student.correction_requested" if correction else "student.rejected",
                 student, reason)
    notify(student, ("The Organizing Committee asked you to update your profile."
                     if correction else "Your verification was not approved.")
           + " Open your profile to see why and resubmit.", "/student/profile")
    db.session.commit()
    return student


def suspend(student, actor, reason):
    _check(actor, student)
    reason = _reason(reason, "reason for the suspension")
    if student.verification_status == C.VERIFY_SUSPENDED:
        raise ServiceError("This student is already suspended.", "invalid_state")
    student.account_status = C.ACCOUNT_SUSPENDED
    student.verification_status = C.VERIFY_SUSPENDED
    student.correction_requested = False
    student.verification_reason = reason
    _stamp(student)
    audit.record(actor, "student.suspended", student, reason)
    db.session.commit()
    return student


def reinstate(student, actor):
    """Lift a suspension. Previously verified students return to VERIFIED."""
    _check(actor, student)
    if student.verification_status != C.VERIFY_SUSPENDED:
        raise ServiceError("Only suspended students can be reinstated.", "invalid_state")
    student.account_status = C.ACCOUNT_ACTIVE
    student.verification_status = (C.VERIFY_VERIFIED if student.verified_at
                                   else C.VERIFY_PENDING)
    student.verification_reason = None
    _stamp(student)
    audit.record(actor, "student.reinstated", student)
    notify(student, "Your account has been reinstated.", "/student/profile")
    db.session.commit()
    return student


def resubmit(student):
    """A rejected student asks for another review after fixing their profile."""
    if student.role != C.STUDENT or student.verification_status != C.VERIFY_REJECTED:
        raise ServiceError("Only students whose profile was returned can resubmit.", "invalid_state")
    if student.account_status != C.ACCOUNT_ACTIVE:
        raise ServiceError("Your account is not active.", "forbidden")
    if not (student.profile and student.profile.is_complete):
        raise ServiceError("Complete your profile (department, branch, semester, phone and "
                           "bio) before resubmitting.", "incomplete_profile")
    student.verification_status = C.VERIFY_PENDING
    student.correction_requested = False
    student.verification_reason = None
    _stamp(student)
    audit.record(student, "student.resubmitted", student)
    organizer = User.query.filter_by(role=C.ORGANIZER, account_status=C.ACCOUNT_ACTIVE).first()
    if organizer:
        notify(organizer, f"{student.name} resubmitted their profile for verification.",
               f"/organizer/members/{student.id}")
    db.session.commit()
    return student


def member_counts() -> dict:
    counts = {s: 0 for s in C.VERIFICATION_STATUSES}
    rows = db.session.query(User.verification_status, db.func.count(User.id)) \
        .filter(User.role == C.STUDENT).group_by(User.verification_status).all()
    for status, number in rows:
        counts[status] = number
    return counts


def query_members(status=C.VERIFY_PENDING, q="", department="", page=1):
    """Paginated, filtered list of students for the Organizer."""
    query = User.query.filter(User.role == C.STUDENT)
    if status in C.VERIFICATION_STATUSES:
        query = query.filter(User.verification_status == status)
    q = (q or "").strip()
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(or_(db.func.lower(User.name).like(like),
                                 User.username.like(like), User.email.like(like)))
    if department in C.DEPARTMENTS:
        query = query.filter(User.department == department)
    order = User.verification_updated_at.desc() if status != C.VERIFY_PENDING else User.created_at
    return query.order_by(order, User.id).paginate(page=page, per_page=PAGE_SIZE, error_out=False)
