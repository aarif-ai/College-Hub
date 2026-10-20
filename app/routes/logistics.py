"""Logistics team area: checklist, readiness and QR scanning."""
from flask import (
    Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for,
)
from flask_login import current_user

from app import constants as C
from app.decorators import role_required
from app.extensions import db
from app.models import (
    Attendance, Event, LogisticsTask, VolunteerApplication, VolunteerOpportunity,
)
from app.services import attendance as attendance_service
from app.services import logistics as logistics_service
from app.services.errors import ServiceError
from app.utils import is_safe_redirect

bp = Blueprint("logistics", __name__, url_prefix="/logistics")

_STATUS_CODES = {
    attendance_service.SUCCESS: 200,
    attendance_service.DUPLICATE: 409,
    attendance_service.WRONG_EVENT: 422,
    attendance_service.CANCELLED: 422,
    attendance_service.NOT_OPEN: 422,
    attendance_service.INVALID: 400,
}


def _workable_event(event_id: int) -> Event:
    event = db.get_or_404(Event, event_id)
    if event.status not in (C.APPROVED, C.PUBLISHED):
        abort(404)
    return event


@bp.route("/")
@role_required(C.LOGISTICS)
def dashboard():
    events = logistics_service.logistics_events()
    rows = [(e, logistics_service.readiness_summary(e)) for e in events]
    upcoming = [r for r in rows if not r[0].is_past]
    past = [r for r in rows if r[0].is_past]
    open_tasks = sum(r[1]["pending"] + r[1]["in_progress"] for r in upcoming)
    return render_template("logistics/dashboard.html", upcoming=upcoming,
                           past=past, open_tasks=open_tasks)


@bp.route("/events/<int:event_id>")
@role_required(C.LOGISTICS)
def event(event_id):
    event = _workable_event(event_id)
    volunteers = (
        VolunteerApplication.query.join(VolunteerOpportunity)
        .filter(VolunteerOpportunity.event_id == event.id,
                VolunteerApplication.status == C.APP_APPROVED).all()
    )
    return render_template(
        "logistics/event.html", event=event,
        readiness=logistics_service.readiness_summary(event),
        volunteers=volunteers,
        areas=sorted({t.area for t in event.tasks} | {"General"}),
    )


@bp.route("/events/<int:event_id>/tasks", methods=["POST"])
@role_required(C.LOGISTICS)
def task_create(event_id):
    event = _workable_event(event_id)
    try:
        logistics_service.add_task(event, current_user, request.form.get("title"),
                                   request.form.get("area"), request.form.get("assigned_to"))
        flash("Task added.", "success")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return redirect(url_for("logistics.event", event_id=event.id))


@bp.route("/tasks/<int:task_id>", methods=["POST"])
@role_required(C.LOGISTICS)
def task_update(task_id):
    task = db.get_or_404(LogisticsTask, task_id)
    event = _workable_event(task.event_id)
    try:
        logistics_service.update_task(
            task, current_user, request.form.get("status"),
            request.form.get("notes"), request.form.get("assigned_to"))
        flash("Task updated.", "success")
    except ServiceError as exc:
        flash(exc.message, "danger")
    target = request.form.get("next", "")
    if target and is_safe_redirect(target):
        return redirect(target)
    return redirect(url_for("logistics.event", event_id=event.id))


@bp.route("/events/<int:event_id>/scan")
@role_required(C.LOGISTICS)
def scanner(event_id):
    event = _workable_event(event_id)
    recent = Attendance.query.filter_by(event_id=event.id) \
        .order_by(Attendance.scanned_at.desc()).limit(8).all()
    return render_template("logistics/scanner.html", event=event, recent=recent)


@bp.route("/scan", methods=["POST"])
@role_required(C.LOGISTICS)
def scan():
    """Validate one scanned QR value. The server makes every decision."""
    payload = request.get_json(silent=True) or {}
    try:
        event_id = int(payload.get("event_id"))
    except (TypeError, ValueError):
        return jsonify(status="invalid", ok=False, message="No event selected."), 400
    result = attendance_service.record_attendance(
        str(payload.get("value", "")), event_id, current_user)
    event = db.session.get(Event, event_id)
    if event is not None:
        result["attended"] = event.attended_count
        result["registered"] = event.registered_count
    return jsonify(result), _STATUS_CODES.get(result["status"], 400)
