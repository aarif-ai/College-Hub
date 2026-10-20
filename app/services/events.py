"""Event validation, creation, editing and the lifecycle state machine.

Lifecycle::

    draft ──submit──> submitted ──approve──> approved ──publish──> published ──complete──> completed
      ^                   │
      │                   └──reject──> rejected ──(edit / resubmit)──┐
      └───────────────────────────────────────────────────────────────┘

Only the Organizer submits, publishes and completes; only Faculty approve or
reject (Faculty may also publish or complete). Certificates are issued once
an event is completed.

Who may do what is enforced here (on the server), not only in templates.
"""
from datetime import datetime

from app import constants as C
from app.extensions import db
from app.models import Club, Event
from app.services.errors import ServiceError
from app.services.logistics import create_default_tasks
from app.services.notifications import notify
from app.utils import now

# target status -> statuses it may be reached from
ALLOWED_TRANSITIONS = {
    C.SUBMITTED: {C.DRAFT, C.REJECTED},
    C.DRAFT: {C.SUBMITTED, C.REJECTED},      # withdraw / revise
    C.APPROVED: {C.SUBMITTED},
    C.REJECTED: {C.SUBMITTED},
    C.PUBLISHED: {C.APPROVED},
    C.COMPLETED: {C.PUBLISHED},
}

EDITABLE_STATUSES = {C.DRAFT, C.REJECTED}


# ---------------------------------------------------------------------------
# Form parsing and validation
# ---------------------------------------------------------------------------
def _parse(value, fmt):
    try:
        return datetime.strptime((value or "").strip(), fmt)
    except ValueError:
        return None


def parse_event_form(form) -> tuple[dict, dict]:
    """Validate raw form data. Returns ``(clean_data, errors)``."""
    errors: dict[str, str] = {}
    data: dict = {}

    title = (form.get("title") or "").strip()
    if not 5 <= len(title) <= 160:
        errors["title"] = "Title must be between 5 and 160 characters."
    data["title"] = title

    description = (form.get("description") or "").strip()
    if len(description) < 20:
        errors["description"] = "Please describe the event in at least 20 characters."
    elif len(description) > 5000:
        errors["description"] = "Description is too long (maximum 5000 characters)."
    data["description"] = description

    category = (form.get("category") or "").strip()
    if category not in C.CATEGORIES:
        errors["category"] = "Choose a category from the list."
    data["category"] = category

    venue = (form.get("venue") or "").strip()
    if not 3 <= len(venue) <= 160:
        errors["venue"] = "Venue must be between 3 and 160 characters."
    data["venue"] = venue

    parsed_date = _parse(form.get("event_date"), "%Y-%m-%d")
    if parsed_date is None:
        errors["event_date"] = "Enter a valid event date."
    elif parsed_date.date() < now().date():
        errors["event_date"] = "The event date cannot be in the past."
    data["event_date"] = parsed_date.date() if parsed_date else None

    start = _parse(form.get("start_time"), "%H:%M")
    end = _parse(form.get("end_time"), "%H:%M")
    if start is None:
        errors["start_time"] = "Enter a valid start time."
    if end is None:
        errors["end_time"] = "Enter a valid end time."
    if start and end and end <= start:
        errors["end_time"] = "End time must be after the start time."
    data["start_time"] = start.time() if start else None
    data["end_time"] = end.time() if end else None

    try:
        capacity = int(form.get("capacity") or "")
        if not 1 <= capacity <= 5000:
            raise ValueError
    except ValueError:
        capacity = None
        errors["capacity"] = "Capacity must be a whole number between 1 and 5000."
    data["capacity"] = capacity

    deadline = _parse(form.get("registration_deadline"), "%Y-%m-%dT%H:%M")
    if deadline is None:
        errors["registration_deadline"] = "Enter a valid registration deadline."
    elif data["event_date"] and start:
        if deadline > datetime.combine(data["event_date"], start.time()):
            errors["registration_deadline"] = "The deadline must be before the event starts."
    data["registration_deadline"] = deadline

    club_id = (form.get("club_id") or "").strip()
    if club_id:
        club = db.session.get(Club, int(club_id)) if club_id.isdigit() else None
        if club is None:
            errors["club_id"] = "Choose a valid club."
        data["club_id"] = club.id if club else None
    else:
        data["club_id"] = None

    department = (form.get("department") or "").strip()
    if department and department not in C.DEPARTMENTS:
        errors["department"] = "Choose a department from the list."
    data["department"] = department or None

    for field, limit, label in (
        ("faculty_coordinator", 120, "Faculty coordinator"),
        ("eligibility", 300, "Eligibility"),
        ("contact_info", 200, "Contact information"),
        ("schedule", 3000, "Schedule"),
        ("rules", 3000, "Rules"),
    ):
        value = (form.get(field) or "").strip()
        if len(value) > limit:
            errors[field] = f"{label} is too long (maximum {limit} characters)."
        data[field] = value or None

    return data, errors


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def create_event(organizer, data: dict) -> Event:
    if organizer.role != C.ORGANIZER:
        raise ServiceError("Only organizers can create events.", "forbidden")
    event = Event(organizer_id=organizer.id, status=C.DRAFT, **data)
    db.session.add(event)
    db.session.commit()
    return event


def can_edit(event: Event, actor) -> bool:
    return (
        actor.role == C.ORGANIZER
        and event.organizer_id == actor.id
        and event.status in EDITABLE_STATUSES
    )


def update_event(event: Event, actor, data: dict) -> Event:
    if not can_edit(event, actor):
        raise ServiceError(
            "Only draft or rejected events can be edited by their organizer.", "forbidden"
        )
    for key, value in data.items():
        setattr(event, key, value)
    db.session.commit()
    return event


def delete_event(event: Event, actor) -> None:
    if actor.role != C.ORGANIZER or event.organizer_id != actor.id:
        raise ServiceError("You cannot delete this event.", "forbidden")
    if event.status != C.DRAFT:
        raise ServiceError("Only draft events can be deleted.", "invalid_state")
    db.session.delete(event)
    db.session.commit()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
def _actor_may(actor, event: Event, target: str) -> bool:
    is_owner = actor.role == C.ORGANIZER and event.organizer_id == actor.id
    if target in (C.SUBMITTED, C.DRAFT):
        return is_owner
    if target in (C.APPROVED, C.REJECTED):
        return actor.role == C.FACULTY
    if target in (C.PUBLISHED, C.COMPLETED):
        return actor.role == C.FACULTY or is_owner
    return False


def change_status(event: Event, target: str, actor, remarks: str | None = None) -> Event:
    """Move ``event`` to ``target`` if ``actor`` is allowed and the move is legal."""
    if target not in C.EVENT_STATUSES:
        raise ServiceError("Unknown event status.", "invalid_state")
    if not _actor_may(actor, event, target):
        raise ServiceError("You are not allowed to make this change.", "forbidden")
    if event.status not in ALLOWED_TRANSITIONS.get(target, set()):
        raise ServiceError(
            f"An event that is {event.status_label.lower()} cannot become "
            f"{C.STATUS_LABELS[target].lower()}.",
            "invalid_state",
        )

    remarks = (remarks or "").strip()
    if target == C.REJECTED and not remarks:
        raise ServiceError("Please add remarks explaining the rejection.", "remarks_required")

    if target == C.COMPLETED and now() < event.start_datetime:
        raise ServiceError("An event can only be marked completed once it has started.",
                           "invalid_state")

    if target == C.SUBMITTED:
        if event.event_date < now().date():
            raise ServiceError("This event's date has passed. Edit the date first.", "invalid_state")
        if not event.venue or not event.description:
            raise ServiceError("Complete all event details before submitting.", "invalid_state")
        event.submitted_at = now()

    event.status = target

    if target in (C.APPROVED, C.REJECTED):
        event.reviewed_by_id = actor.id
        event.reviewed_at = now()
        event.faculty_remarks = remarks or event.faculty_remarks
        if target == C.APPROVED:
            create_default_tasks(event)
            notify(event.organizer, f"'{event.title}' was approved. You can now publish it.",
                   f"/organizer/events/{event.id}")
        else:
            notify(event.organizer, f"'{event.title}' was rejected. See the faculty remarks.",
                   f"/organizer/events/{event.id}")
    elif target == C.PUBLISHED:
        event.published_at = now()
        notify(event.organizer, f"'{event.title}' is now published for students.",
               f"/organizer/events/{event.id}")
    elif target == C.COMPLETED:
        event.completed_at = now()
        notify(event.organizer, f"'{event.title}' is completed. You can now issue certificates.",
               f"/organizer/events/{event.id}?tab=certificates")
    elif target == C.SUBMITTED:
        from app.models import User  # local import avoids a cycle at import time
        for faculty in User.query.filter_by(role=C.FACULTY, account_status=C.ACCOUNT_ACTIVE).all():
            notify(faculty, f"New proposal awaiting review: '{event.title}'",
                   f"/faculty/events/{event.id}/review")

    db.session.commit()
    return event
