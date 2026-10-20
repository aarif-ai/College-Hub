"""Volunteer opportunities and applications."""
from sqlalchemy.exc import IntegrityError

from app import constants as C
from app.extensions import db
from app.models import Event, VolunteerApplication, VolunteerOpportunity
from app.services import achievements
from app.services.errors import ServiceError
from app.services.notifications import notify
from app.utils import now


def create_opportunity(event: Event, creator, title: str, description: str, slots) -> VolunteerOpportunity:
    if creator.role != C.ORGANIZER or event.organizer_id != creator.id:
        raise ServiceError("You can only create opportunities for your own events.", "forbidden")
    title = (title or "").strip()
    description = (description or "").strip()
    try:
        slots = int(slots)
        if not 1 <= slots <= 200:
            raise ValueError
    except (TypeError, ValueError):
        raise ServiceError("Slots must be a number between 1 and 200.", "validation")
    if not 3 <= len(title) <= 160:
        raise ServiceError("Title must be 3 to 160 characters.", "validation")
    if len(description) < 10:
        raise ServiceError("Please describe the role in at least 10 characters.", "validation")
    opportunity = VolunteerOpportunity(
        event_id=event.id, title=title, description=description,
        slots=slots, created_by_id=creator.id,
    )
    db.session.add(opportunity)
    db.session.commit()
    return opportunity


def apply_for_opportunity(student, opportunity: VolunteerOpportunity, message: str) -> VolunteerApplication:
    if student.role != C.STUDENT:
        raise ServiceError("Only students can apply to volunteer.", "forbidden")
    if not student.is_verified:
        raise ServiceError("Only verified CollegeHub members can volunteer. "
                           "Complete your profile and wait for verification.",
                           "verification_required")
    if not opportunity.is_open:
        raise ServiceError("This opportunity is closed.", "closed")
    if opportunity.event and opportunity.event.status != C.PUBLISHED:
        raise ServiceError("This opportunity is not open yet.", "closed")
    if VolunteerApplication.query.filter_by(
        opportunity_id=opportunity.id, student_id=student.id
    ).first():
        raise ServiceError("You have already applied for this opportunity.", "duplicate")

    application = VolunteerApplication(
        opportunity_id=opportunity.id, student_id=student.id,
        message=(message or "").strip()[:400] or None,
    )
    db.session.add(application)
    notify(opportunity.created_by,
           f"{student.name} applied to volunteer: {opportunity.title}",
           f"/organizer/events/{opportunity.event_id}?tab=volunteers"
           if opportunity.event_id else None)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ServiceError("You have already applied for this opportunity.", "duplicate")
    return application


def _clean_assignment(text, opportunity) -> str:
    text = (text or "").strip()[:120]
    return text or opportunity.title


def decide_application(application: VolunteerApplication, decider, decision: str,
                       assignment: str | None = None) -> VolunteerApplication:
    opportunity = application.opportunity
    if decider.role != C.ORGANIZER or opportunity.created_by_id != decider.id:
        raise ServiceError("Only the organizer who created this opportunity can decide.", "forbidden")
    if decision not in ("approve", "reject"):
        raise ServiceError("Unknown decision.", "validation")
    if application.status != C.APP_PENDING:
        raise ServiceError("This application has already been decided.", "invalid_state")
    if decision == "approve" and opportunity.slots_left <= 0:
        raise ServiceError("No volunteer slots are left.", "full")

    application.status = C.APP_APPROVED if decision == "approve" else C.APP_REJECTED
    if decision == "approve":
        application.assignment = _clean_assignment(assignment, opportunity)
    application.decided_at = now()
    application.decided_by_id = decider.id
    notify(application.student,
           f"Your volunteer application for '{opportunity.title}' was {application.status}.",
           "/student/volunteering")
    db.session.flush()
    achievements.evaluate_student(application.student)
    db.session.commit()
    return application


def assign_volunteer(application: VolunteerApplication, actor, assignment: str) -> VolunteerApplication:
    """Set or change the event responsibility of an approved volunteer.

    This is about *event duties* (for example "Registration desk"). It has
    nothing to do with managing the Logistics account.
    """
    if actor.role != C.ORGANIZER or application.opportunity.created_by_id != actor.id:
        raise ServiceError("Only the Organizer can assign volunteers.", "forbidden")
    if application.status != C.APP_APPROVED:
        raise ServiceError("Approve the application before assigning a responsibility.",
                           "invalid_state")
    assignment = (assignment or "").strip()
    if not 3 <= len(assignment) <= 120:
        raise ServiceError("Responsibility must be 3 to 120 characters.", "validation")
    application.assignment = assignment
    notify(application.student,
           f"Your volunteer responsibility for '{application.opportunity.title}': {assignment}",
           "/student/volunteering")
    db.session.commit()
    return application
