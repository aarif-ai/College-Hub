"""Organizer / core team area."""
import csv
import io

from flask import (
    Blueprint, Response, abort, current_app, flash, redirect, render_template,
    request, url_for,
)
from flask_login import current_user

from app import constants as C
from app.decorators import role_required
from app.extensions import db
from app.models import (
    Club, Event, EventDocument, LogisticsTask, Registration, User, VolunteerApplication,
)
from app.services import accounts, analytics, audit, verification, volunteering
from app.services import certificates as cert_service
from app.services import documents as doc_service
from app.services import events as event_service
from app.services import logistics as logistics_service
from app.services.announcements import create_announcement
from app.services.errors import ServiceError
from app.services.registration import cancel_registration
from app.utils import is_safe_redirect, now

bp = Blueprint("organizer", __name__, url_prefix="/organizer")

TABS = ("overview", "registrations", "documents", "logistics",
        "volunteers", "certificates", "announcements")


def _own_event(event_id: int) -> Event:
    event = db.get_or_404(Event, event_id)
    if event.organizer_id != current_user.id:
        abort(403)
    return event


def _back_to(event: Event, tab: str):
    return redirect(url_for("organizer.event_manage", event_id=event.id, tab=tab))


def _form_values(event: Event | None) -> dict:
    if event is None:
        return {}
    return {
        "title": event.title, "description": event.description,
        "category": event.category, "venue": event.venue,
        "event_date": event.event_date.strftime("%Y-%m-%d"),
        "start_time": event.start_time.strftime("%H:%M"),
        "end_time": event.end_time.strftime("%H:%M"),
        "capacity": event.capacity,
        "registration_deadline": event.registration_deadline.strftime("%Y-%m-%dT%H:%M"),
        "club_id": event.club_id or "",
        "department": event.department or "",
        "faculty_coordinator": event.faculty_coordinator or "",
        "eligibility": event.eligibility or "",
        "schedule": event.schedule or "",
        "rules": event.rules or "",
        "contact_info": event.contact_info or "",
    }


# ---------------------------------------------------------------------------
# Dashboard and event list
# ---------------------------------------------------------------------------
@bp.route("/")
@role_required(C.ORGANIZER)
def dashboard():
    stats = analytics.organizer_stats(current_user)
    events = Event.query.filter_by(organizer_id=current_user.id) \
        .order_by(Event.updated_at.desc()).limit(6).all()
    needs_action = [e for e in events if e.status in (C.APPROVED, C.REJECTED)]
    return render_template("organizer/dashboard.html", stats=stats,
                           events=events, needs_action=needs_action,
                           members=verification.member_counts(),
                           logistics_account=accounts.managed_account(C.LOGISTICS))


@bp.route("/events")
@role_required(C.ORGANIZER)
def events():
    status = request.args.get("status", "")
    query = Event.query.filter_by(organizer_id=current_user.id)
    if status in C.EVENT_STATUSES:
        query = query.filter_by(status=status)
    items = query.order_by(Event.event_date.desc()).all()
    return render_template("organizer/events.html", items=items, status=status)


# ---------------------------------------------------------------------------
# Create / edit
# ---------------------------------------------------------------------------
def _event_form(event: Event | None):
    clubs = Club.query.order_by(Club.name).all()
    club_options = [(c.id, c.name) for c in clubs]
    if request.method == "POST":
        data, errors = event_service.parse_event_form(request.form)
        cover_name = None
        file = request.files.get("cover")
        if not errors and file and file.filename:
            try:
                cover_name = doc_service.save_cover_image(file)
            except ServiceError as exc:
                errors["cover"] = exc.message

        if not errors:
            try:
                if event is None:
                    event = event_service.create_event(current_user, data)
                else:
                    event_service.update_event(event, current_user, data)
            except ServiceError as exc:
                flash(exc.message, "danger")
                return redirect(url_for("organizer.events"))
            if cover_name:
                event.image = cover_name
                db.session.commit()

            action = request.form.get("action")
            try:
                if action == "submit":
                    event_service.change_status(event, C.SUBMITTED, current_user)
                    flash("Event submitted for faculty approval.", "success")
                else:
                    if event.status == C.REJECTED:
                        event_service.change_status(event, C.DRAFT, current_user)
                    flash("Draft saved.", "success")
            except ServiceError as exc:
                flash(exc.message, "danger")
            return redirect(url_for("organizer.event_manage", event_id=event.id))

        flash("Please fix the highlighted fields.", "danger")
        return render_template("organizer/event_form.html", event=event, form=request.form,
                               errors=errors, club_options=club_options), 400

    return render_template("organizer/event_form.html", event=event,
                           form=_form_values(event), errors={}, club_options=club_options)


@bp.route("/events/new", methods=["GET", "POST"])
@role_required(C.ORGANIZER)
def event_new():
    return _event_form(None)


@bp.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
@role_required(C.ORGANIZER)
def event_edit(event_id):
    event = _own_event(event_id)
    if not event_service.can_edit(event, current_user):
        flash("Only draft or rejected events can be edited.", "warning")
        return redirect(url_for("organizer.event_manage", event_id=event.id))
    return _event_form(event)


@bp.route("/events/<int:event_id>/delete", methods=["POST"])
@role_required(C.ORGANIZER)
def event_delete(event_id):
    event = _own_event(event_id)
    try:
        event_service.delete_event(event, current_user)
        flash("Draft deleted.", "info")
    except ServiceError as exc:
        flash(exc.message, "danger")
        return redirect(url_for("organizer.event_manage", event_id=event.id))
    return redirect(url_for("organizer.events"))


# ---------------------------------------------------------------------------
# Event hub
# ---------------------------------------------------------------------------
@bp.route("/events/<int:event_id>")
@role_required(C.ORGANIZER)
def event_manage(event_id):
    event = _own_event(event_id)
    tab = request.args.get("tab", "overview")
    if tab not in TABS:
        tab = "overview"
    registrations = Registration.query.filter_by(event_id=event.id) \
        .order_by(Registration.created_at.desc()).all()
    return render_template(
        "organizer/event_manage.html", event=event, tab=tab, tabs=TABS,
        stats=analytics.event_stats(event), registrations=registrations,
        readiness=logistics_service.readiness_summary(event),
        can_edit=event_service.can_edit(event, current_user),
        departments=C.DEPARTMENT_OPTIONS, now_local=now(),
        max_upload_mb=current_app.config["MAX_UPLOAD_MB"],
    )


@bp.route("/events/<int:event_id>/submit", methods=["POST"])
@role_required(C.ORGANIZER)
def event_submit(event_id):
    event = _own_event(event_id)
    try:
        event_service.change_status(event, C.SUBMITTED, current_user)
        flash("Event submitted for faculty approval.", "success")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return _back_to(event, "overview")


@bp.route("/events/<int:event_id>/withdraw", methods=["POST"])
@role_required(C.ORGANIZER)
def event_withdraw(event_id):
    event = _own_event(event_id)
    try:
        event_service.change_status(event, C.DRAFT, current_user)
        flash("Proposal withdrawn. It is a draft again.", "info")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return _back_to(event, "overview")


@bp.route("/events/<int:event_id>/publish", methods=["POST"])
@role_required(C.ORGANIZER)
def event_publish(event_id):
    event = _own_event(event_id)
    try:
        event_service.change_status(event, C.PUBLISHED, current_user)
        flash("Event published. Students can now find and register for it.", "success")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return _back_to(event, "overview")


@bp.route("/events/<int:event_id>/complete", methods=["POST"])
@role_required(C.ORGANIZER)
def event_complete(event_id):
    event = _own_event(event_id)
    try:
        event_service.change_status(event, C.COMPLETED, current_user)
        flash("Event marked as completed. You can now issue certificates.", "success")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return _back_to(event, "certificates")


# ---------------------------------------------------------------------------
# Documents (official PDFs used by the AI assistant)
# ---------------------------------------------------------------------------
@bp.route("/events/<int:event_id>/documents", methods=["POST"])
@role_required(C.ORGANIZER)
def document_upload(event_id):
    event = _own_event(event_id)
    try:
        document = doc_service.save_document(request.files.get("document"), event, current_user)
        if document.has_text:
            flash(f"'{document.original_filename}' uploaded. The AI assistant can now "
                  "answer questions from it.", "success")
        else:
            flash("Uploaded, but no readable text was found (it may be a scanned image). "
                  "The AI assistant cannot use this file.", "warning")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return _back_to(event, "documents")


@bp.route("/documents/<int:document_id>/delete", methods=["POST"])
@role_required(C.ORGANIZER)
def document_delete(document_id):
    document = db.get_or_404(EventDocument, document_id)
    event = _own_event(document.event_id)
    doc_service.delete_document(document)
    flash("Document removed.", "info")
    return _back_to(event, "documents")


# ---------------------------------------------------------------------------
# Registrations
# ---------------------------------------------------------------------------
@bp.route("/registrations/<int:reg_id>/cancel", methods=["POST"])
@role_required(C.ORGANIZER)
def registration_cancel(reg_id):
    registration = db.get_or_404(Registration, reg_id)
    event = _own_event(registration.event_id)
    try:
        cancel_registration(registration, current_user)
        flash("Registration cancelled.", "info")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return _back_to(event, "registrations")


def _csv_safe(value) -> str:
    """Stop spreadsheet apps from running a cell that starts like a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


@bp.route("/events/<int:event_id>/registrations.csv")
@role_required(C.ORGANIZER)
def registrations_export(event_id):
    event = _own_event(event_id)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Registration ID", "Name", "Email", "Department", "Status",
                     "Registered at", "Attended at"])
    for reg in Registration.query.filter_by(event_id=event.id).order_by(Registration.created_at):
        writer.writerow([
            reg.reg_code, _csv_safe(reg.student.name), _csv_safe(reg.student.email),
            _csv_safe(reg.student.department), reg.status,
            reg.created_at.strftime("%Y-%m-%d %H:%M"),
            reg.attendance.scanned_at.strftime("%Y-%m-%d %H:%M") if reg.attendance else "",
        ])
    return Response(out.getvalue(), mimetype="text/csv", headers={
        "Content-Disposition": f'attachment; filename="event-{event.id}-registrations.csv"'})


# ---------------------------------------------------------------------------
# Logistics tasks
# ---------------------------------------------------------------------------
def _task_redirect(event: Event):
    target = request.form.get("next", "")
    if target and is_safe_redirect(target):
        return redirect(target)
    return _back_to(event, "logistics")


@bp.route("/events/<int:event_id>/tasks", methods=["POST"])
@role_required(C.ORGANIZER)
def task_create(event_id):
    event = _own_event(event_id)
    if event.status not in (C.APPROVED, C.PUBLISHED):
        flash("The checklist opens once faculty approve the event.", "warning")
        return _back_to(event, "logistics")
    try:
        logistics_service.add_task(event, current_user, request.form.get("title"),
                                   request.form.get("area"), request.form.get("assigned_to"))
        flash("Task added.", "success")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return _task_redirect(event)


@bp.route("/tasks/<int:task_id>", methods=["POST"])
@role_required(C.ORGANIZER)
def task_update(task_id):
    task = db.get_or_404(LogisticsTask, task_id)
    event = _own_event(task.event_id)
    try:
        logistics_service.update_task(
            task, current_user, request.form.get("status"),
            request.form.get("notes"), request.form.get("assigned_to"))
        flash("Task updated.", "success")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return _task_redirect(event)


# ---------------------------------------------------------------------------
# Volunteers, certificates, announcements
# ---------------------------------------------------------------------------
@bp.route("/events/<int:event_id>/opportunities", methods=["POST"])
@role_required(C.ORGANIZER)
def opportunity_create(event_id):
    event = _own_event(event_id)
    try:
        volunteering.create_opportunity(
            event, current_user, request.form.get("title"),
            request.form.get("description"), request.form.get("slots"))
        flash("Volunteer opportunity created.", "success")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return _back_to(event, "volunteers")


@bp.route("/applications/<int:app_id>/<decision>", methods=["POST"])
@role_required(C.ORGANIZER)
def application_decide(app_id, decision):
    application = db.get_or_404(VolunteerApplication, app_id)
    event = _own_event(application.opportunity.event_id) \
        if application.opportunity.event_id else None
    if event is None:
        abort(403)
    try:
        volunteering.decide_application(application, current_user, decision,
                                        request.form.get("assignment"))
        flash(f"Application {application.status}.", "success")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return _back_to(event, "volunteers")


@bp.route("/applications/<int:app_id>/assign", methods=["POST"])
@role_required(C.ORGANIZER)
def application_assign(app_id):
    application = db.get_or_404(VolunteerApplication, app_id)
    if not application.opportunity.event_id:
        abort(403)
    event = _own_event(application.opportunity.event_id)
    try:
        volunteering.assign_volunteer(application, current_user, request.form.get("assignment"))
        flash("Responsibility assigned.", "success")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return _back_to(event, "volunteers")


@bp.route("/events/<int:event_id>/certificates", methods=["POST"])
@role_required(C.ORGANIZER)
def certificates_issue(event_id):
    event = _own_event(event_id)
    try:
        created = cert_service.issue_certificates(event, current_user)
        flash(f"{created} new certificate(s) issued." if created
              else "Every attendee already has a certificate.", "success" if created else "info")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return _back_to(event, "certificates")


@bp.route("/events/<int:event_id>/announcements", methods=["POST"])
@role_required(C.ORGANIZER)
def announcement_create(event_id):
    event = _own_event(event_id)
    try:
        create_announcement(current_user, request.form.get("title"),
                            request.form.get("message"), event,
                            request.form.get("audience", "students"))
        flash("Announcement published.", "success")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return _back_to(event, "announcements")


@bp.route("/analytics")
@role_required(C.ORGANIZER)
def analytics_page():
    return render_template("organizer/analytics.html",
                           stats=analytics.organizer_stats(current_user))


# ---------------------------------------------------------------------------
# Member verification (only the Organizer may verify students)
# ---------------------------------------------------------------------------
def _student_or_404(student_id: int) -> User:
    student = db.get_or_404(User, student_id)
    if student.role != C.STUDENT:
        abort(404)
    return student


@bp.route("/members")
@role_required(C.ORGANIZER)
def members():
    status = request.args.get("status", C.VERIFY_PENDING).upper()
    if status not in C.VERIFICATION_STATUSES:
        status = C.VERIFY_PENDING
    q = (request.args.get("q") or "").strip()[:80]
    department = request.args.get("department", "")
    page = request.args.get("page", 1, type=int)
    pagination = verification.query_members(status, q, department, page)
    return render_template(
        "organizer/members.html", pagination=pagination, status=status, q=q,
        department=department, counts=verification.member_counts(),
        departments=C.DEPARTMENT_OPTIONS,
    )


@bp.route("/members/<int:student_id>")
@role_required(C.ORGANIZER)
def member_detail(student_id):
    student = _student_or_404(student_id)
    return render_template("organizer/member_detail.html", student=student,
                           profile=student.profile, history=audit.history_for(student),
                           stats=analytics.student_stats(student))


@bp.route("/members/<int:student_id>/<action>", methods=["POST"])
@role_required(C.ORGANIZER)
def member_decide(student_id, action):
    student = _student_or_404(student_id)
    reason = request.form.get("reason", "")
    try:
        if action == "approve":
            verification.approve(student, current_user)
            flash(f"{student.name} is now a Verified CollegeHub Member.", "success")
        elif action == "reject":
            verification.reject(student, current_user, reason)
            flash(f"{student.name}'s verification was rejected. They can correct and resubmit.", "info")
        elif action == "correction":
            verification.reject(student, current_user, reason, correction=True)
            flash(f"Correction requested from {student.name}.", "info")
        elif action == "suspend":
            verification.suspend(student, current_user, reason)
            flash(f"{student.name} was suspended.", "warning")
        elif action == "reinstate":
            verification.reinstate(student, current_user)
            flash(f"{student.name} was reinstated.", "success")
        else:
            abort(404)
    except ServiceError as exc:
        flash(exc.message, "danger")
    target = request.form.get("next", "")
    if target and is_safe_redirect(target):
        return redirect(target)
    return redirect(url_for("organizer.member_detail", student_id=student.id))


# ---------------------------------------------------------------------------
# Logistics account (the Organizer manages the ONE Logistics account)
# ---------------------------------------------------------------------------
@bp.route("/logistics-account", methods=["GET", "POST"])
@role_required(C.ORGANIZER)
def logistics_account():
    account = accounts.managed_account(C.LOGISTICS)
    errors = {}
    revealed = None
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "create":
                accounts.create_staff_account(
                    current_user, C.LOGISTICS, request.form.get("username"),
                    request.form.get("email"), request.form.get("password"),
                    request.form.get("name"))
                flash("Logistics account created.", "success")
            elif action == "details":
                accounts.update_staff_details(current_user, C.LOGISTICS,
                                              request.form.get("username"), request.form.get("email"))
                flash("Logistics username and email updated.", "success")
            elif action == "password":
                accounts.set_staff_password(current_user, C.LOGISTICS,
                                            request.form.get("new_password"),
                                            request.form.get("confirm_password"))
                flash("Logistics password changed. They will be asked to choose their own at the next sign-in.",
                      "success")
            elif action == "reset":
                _acc, revealed = accounts.reset_staff_password(current_user, C.LOGISTICS)
            elif action in ("activate", "deactivate"):
                accounts.set_staff_active(current_user, C.LOGISTICS, action == "activate")
                flash("Logistics access activated." if action == "activate"
                      else "Logistics access deactivated.", "success")
            else:
                abort(400)
            if revealed is None:
                return redirect(url_for("organizer.logistics_account"))
        except ServiceError as exc:
            flash(exc.message, "danger")
            errors["form"] = exc.message
        account = accounts.managed_account(C.LOGISTICS)
    return render_template(
        "organizer/logistics_account.html", account=account, revealed=revealed,
        history=audit.history_for(account) if account else [], errors=errors,
        form=request.form if request.method == "POST" else {},
    ), (400 if errors else 200)
