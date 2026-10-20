"""Logistics checklist and readiness."""
from app import constants as C
from app.extensions import db
from app.models import Event, LogisticsTask
from app.services.errors import ServiceError


def create_default_tasks(event: Event) -> int:
    """Add the standard checklist once (does nothing if tasks already exist)."""
    if event.tasks:
        return 0
    for title, area, team in C.DEFAULT_TASKS:
        event.tasks.append(LogisticsTask(title=title, area=area, assigned_to=team))
    return len(C.DEFAULT_TASKS)


def logistics_events():
    """Events the logistics team works on: approved or published."""
    return (
        Event.query.filter(Event.status.in_([C.APPROVED, C.PUBLISHED]))
        .order_by(Event.event_date.asc(), Event.start_time.asc())
        .all()
    )


def add_task(event: Event, actor, title: str, area: str, assigned_to: str) -> LogisticsTask:
    title = (title or "").strip()
    if not 3 <= len(title) <= 160:
        raise ServiceError("Task title must be 3 to 160 characters.", "validation")
    task = LogisticsTask(
        event_id=event.id,
        title=title,
        area=(area or "General").strip()[:60] or "General",
        assigned_to=(assigned_to or "").strip()[:120] or None,
        updated_by_id=actor.id,
    )
    db.session.add(task)
    db.session.commit()
    return task


def update_task(task: LogisticsTask, actor, status: str | None,
                notes: str | None, assigned_to: str | None) -> LogisticsTask:
    if status is not None:
        if status not in C.TASK_STATUSES:
            raise ServiceError("Unknown task status.", "validation")
        task.status = status
    if notes is not None:
        task.notes = notes.strip()[:1000] or None
    if assigned_to is not None:
        task.assigned_to = assigned_to.strip()[:120] or None
    task.updated_by_id = actor.id
    db.session.commit()
    return task


def readiness_summary(event: Event) -> dict:
    total = len(event.tasks)
    counts = {s: 0 for s in C.TASK_STATUSES}
    for task in event.tasks:
        counts[task.status] += 1
    return {
        "total": total,
        "pending": counts[C.TASK_PENDING],
        "in_progress": counts[C.TASK_IN_PROGRESS],
        "completed": counts[C.TASK_COMPLETED],
        "percent": event.readiness_percent,
    }
