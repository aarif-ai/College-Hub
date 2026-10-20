"""Basic analytics for each role's dashboard."""
from sqlalchemy import func

from app import constants as C
from app.extensions import db
from app.models import (
    Attendance, Certificate, Club, Event, Registration, VolunteerApplication,
    VolunteerOpportunity,
)


def _pct(part: int, whole: int) -> int:
    return round(part * 100 / whole) if whole else 0


def event_stats(event: Event) -> dict:
    registered = event.registered_count
    attended = event.attended_count
    volunteers = (
        db.session.query(func.count(VolunteerApplication.id))
        .join(VolunteerOpportunity)
        .filter(VolunteerOpportunity.event_id == event.id,
                VolunteerApplication.status == C.APP_APPROVED)
        .scalar()
    )
    return {
        "registered": registered,
        "attended": attended,
        "attendance_rate": _pct(attended, registered),
        "fill_rate": _pct(registered, event.capacity),
        "readiness": event.readiness_percent,
        "volunteers": volunteers,
        "certificates": Certificate.query.filter_by(event_id=event.id).count(),
    }


def student_stats(student) -> dict:
    registered = Registration.query.filter_by(
        student_id=student.id, status=C.REG_CONFIRMED
    ).count()
    attended = Attendance.query.filter_by(student_id=student.id).count()
    return {
        "registered": registered,
        "attended": attended,
        "attendance_rate": _pct(attended, registered),
        "certificates": Certificate.query.filter_by(student_id=student.id).count(),
        "volunteering": VolunteerApplication.query.filter_by(
            student_id=student.id, status=C.APP_APPROVED
        ).count(),
        "achievements": len(student.achievements),
    }


def organizer_stats(organizer) -> dict:
    events = Event.query.filter_by(organizer_id=organizer.id).all()
    by_status = {s: 0 for s in C.EVENT_STATUSES}
    for event in events:
        by_status[event.status] += 1
    performance = []
    total_reg = total_att = total_vol = 0
    for event in sorted(events, key=lambda e: e.event_date, reverse=True):
        stats = event_stats(event)
        total_reg += stats["registered"]
        total_att += stats["attended"]
        total_vol += stats["volunteers"]
        if event.status in C.PUBLIC_STATUSES:
            performance.append((event, stats))
    return {
        "total": len(events),
        "by_status": by_status,
        "registrations": total_reg,
        "attendance": total_att,
        "volunteers": total_vol,
        "performance": performance,
    }


def faculty_overview() -> dict:
    published = Event.query.filter(Event.status.in_(C.PUBLIC_STATUSES)).order_by(Event.event_date.desc()).all()
    rows = [(event, event_stats(event)) for event in published]
    total_reg = sum(s["registered"] for _e, s in rows)
    total_att = sum(s["attended"] for _e, s in rows)
    return {
        "pending": Event.query.filter_by(status=C.SUBMITTED).count(),
        "approved": Event.query.filter_by(status=C.APPROVED).count(),
        "published": len(published),
        "registrations": total_reg,
        "attendance": total_att,
        "attendance_rate": _pct(total_att, total_reg),
        "rows": rows,
        "students": db.session.query(func.count(Registration.student_id.distinct())).scalar(),
    }


def club_overview() -> list[dict]:
    result = []
    for club in Club.query.order_by(Club.name).all():
        events = [e for e in club.events if e.status in C.PUBLIC_STATUSES]
        registered = sum(e.registered_count for e in events)
        attended = sum(e.attended_count for e in events)
        result.append({
            "club": club,
            "events": len(events),
            "registered": registered,
            "attended": attended,
            "attendance_rate": _pct(attended, registered),
        })
    return result
