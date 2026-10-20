"""Faculty (institutional oversight) area."""
from flask import (
    Blueprint, abort, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user

from app import constants as C
from app.decorators import role_required
from app.extensions import db
from app.models import Event, Registration
from app.services import accounts, analytics, audit
from app.services import events as event_service
from app.services import logistics as logistics_service
from app.services.announcements import announcements_for, create_announcement
from app.services.errors import ServiceError
from app.utils import now

bp = Blueprint("faculty", __name__, url_prefix="/faculty")


@bp.route("/")
@role_required(C.FACULTY)
def dashboard():
    overview = analytics.faculty_overview()
    pending = Event.query.filter_by(status=C.SUBMITTED) \
        .order_by(Event.submitted_at.asc()).limit(5).all()
    upcoming_ready = [
        (e, logistics_service.readiness_summary(e))
        for e in Event.query.filter(Event.status.in_([C.APPROVED, C.PUBLISHED]))
        .order_by(Event.event_date).all() if not e.is_past
    ][:5]
    return render_template("faculty/dashboard.html", overview=overview,
                           organizer_account=accounts.managed_account(C.ORGANIZER),
                           pending=pending, upcoming_ready=upcoming_ready,
                           announcements=announcements_for(current_user, limit=3))


@bp.route("/proposals")
@role_required(C.FACULTY)
def proposals():
    pending = Event.query.filter_by(status=C.SUBMITTED) \
        .order_by(Event.submitted_at.asc()).all()
    recent = Event.query.filter(Event.status.in_([C.APPROVED, C.REJECTED])) \
        .order_by(Event.reviewed_at.desc()).limit(8).all()
    return render_template("faculty/proposals.html", pending=pending, recent=recent)


@bp.route("/events/<int:event_id>/review")
@role_required(C.FACULTY)
def review(event_id):
    event = db.get_or_404(Event, event_id)
    organizer = event.organizer
    past = [e for e in organizer.organized_events
            if e.id != event.id and e.status in C.PUBLIC_STATUSES]
    return render_template(
        "faculty/review.html", event=event, organizer=organizer,
        past_events=past, past_stats={e.id: analytics.event_stats(e) for e in past},
    )


@bp.route("/events/<int:event_id>/decide", methods=["POST"])
@role_required(C.FACULTY)
def decide(event_id):
    event = db.get_or_404(Event, event_id)
    decision = request.form.get("decision")
    remarks = request.form.get("remarks", "")
    target = {"approve": C.APPROVED, "reject": C.REJECTED}.get(decision)
    if target is None:
        flash("Choose approve or reject.", "danger")
        return redirect(url_for("faculty.review", event_id=event.id))
    try:
        event_service.change_status(event, target, current_user, remarks)
        flash("Event approved. Logistics checklist created." if target == C.APPROVED
              else "Event rejected. The organizer has been notified.",
              "success" if target == C.APPROVED else "info")
    except ServiceError as exc:
        flash(exc.message, "danger")
        return redirect(url_for("faculty.review", event_id=event.id))
    return redirect(url_for("faculty.proposals"))


@bp.route("/events/<int:event_id>/publish", methods=["POST"])
@role_required(C.FACULTY)
def publish(event_id):
    event = db.get_or_404(Event, event_id)
    try:
        event_service.change_status(event, C.PUBLISHED, current_user)
        flash("Event published.", "success")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return redirect(url_for("faculty.report", event_id=event.id))


@bp.route("/events/<int:event_id>/complete", methods=["POST"])
@role_required(C.FACULTY)
def complete(event_id):
    event = db.get_or_404(Event, event_id)
    try:
        event_service.change_status(event, C.COMPLETED, current_user)
        flash("Event marked as completed.", "success")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return redirect(url_for("faculty.report", event_id=event.id))


@bp.route("/events")
@role_required(C.FACULTY)
def monitor():
    status = request.args.get("status", "")
    query = Event.query
    if status in C.EVENT_STATUSES:
        query = query.filter_by(status=status)
    rows = [(e, analytics.event_stats(e)) for e in
            query.order_by(Event.event_date.desc()).all()]
    return render_template("faculty/monitor.html", rows=rows, status=status)


@bp.route("/events/<int:event_id>/report")
@role_required(C.FACULTY)
def report(event_id):
    event = db.get_or_404(Event, event_id)
    registrations = Registration.query.filter_by(event_id=event.id) \
        .order_by(Registration.created_at).all()
    return render_template(
        "faculty/report.html", event=event, stats=analytics.event_stats(event),
        readiness=logistics_service.readiness_summary(event),
        registrations=registrations, now_local=now(),
    )


@bp.route("/announcements", methods=["GET", "POST"])
@role_required(C.FACULTY)
def announcements():
    if request.method == "POST":
        event_id = request.form.get("event_id", type=int)
        event = db.session.get(Event, event_id) if event_id else None
        try:
            create_announcement(current_user, request.form.get("title"),
                                request.form.get("message"), event,
                                request.form.get("audience", "all"))
            flash("Announcement published.", "success")
            return redirect(url_for("faculty.announcements"))
        except ServiceError as exc:
            flash(exc.message, "danger")
    events = Event.query.filter(Event.status == C.PUBLISHED) \
        .order_by(Event.event_date.desc()).all()
    from app.models import Announcement
    items = Announcement.query.order_by(Announcement.created_at.desc()).limit(30).all()
    event_options = [(e.id, e.title) for e in events]
    return render_template("faculty/announcements.html", event_options=event_options, items=items)


@bp.route("/clubs")
@role_required(C.FACULTY)
def clubs():
    return render_template("faculty/clubs.html", rows=analytics.club_overview())


# ---------------------------------------------------------------------------
# Organizer account (Faculty manage the ONE Organizer account)
# ---------------------------------------------------------------------------
@bp.route("/organizer-account", methods=["GET", "POST"])
@role_required(C.FACULTY)
def organizer_account():
    account = accounts.managed_account(C.ORGANIZER)
    errors = {}
    revealed = None
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "create":
                accounts.create_staff_account(
                    current_user, C.ORGANIZER, request.form.get("username"),
                    request.form.get("email"), request.form.get("password"),
                    request.form.get("name"))
                flash("Organizer account created.", "success")
            elif action == "details":
                accounts.update_staff_details(current_user, C.ORGANIZER,
                                              request.form.get("username"), request.form.get("email"))
                flash("Organizer username and email updated.", "success")
            elif action == "password":
                accounts.set_staff_password(current_user, C.ORGANIZER,
                                            request.form.get("new_password"),
                                            request.form.get("confirm_password"))
                flash("Organizer password changed. They will be asked to choose their own at the next sign-in.",
                      "success")
            elif action == "reset":
                _acc, revealed = accounts.reset_staff_password(current_user, C.ORGANIZER)
            elif action in ("activate", "deactivate"):
                accounts.set_staff_active(current_user, C.ORGANIZER, action == "activate")
                flash("Organizer access activated." if action == "activate"
                      else "Organizer access deactivated.", "success")
            else:
                abort(400)
            if revealed is None:
                return redirect(url_for("faculty.organizer_account"))
        except ServiceError as exc:
            flash(exc.message, "danger")
            errors["form"] = exc.message
        account = accounts.managed_account(C.ORGANIZER)
    return render_template(
        "faculty/organizer_account.html", account=account, revealed=revealed,
        history=audit.history_for(account) if account else [], errors=errors,
        logistics_account=accounts.managed_account(C.LOGISTICS),
        form=request.form if request.method == "POST" else {},
    ), (400 if errors else 200)
