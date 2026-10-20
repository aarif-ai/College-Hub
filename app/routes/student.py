"""Student area."""
import re

from flask import (
    Blueprint, Response, abort, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from app import constants as C
from app.decorators import role_required, verified_required
from app.extensions import db
from app.models import (
    Achievement, Certificate, Event, Registration, StudentProfile,
    VolunteerOpportunity,
)
from app.services import achievements, analytics, qr, verification, volunteering
from app.services import documents as doc_service
from app.services import certificates as cert_service
from app.services.announcements import announcements_for
from app.services.errors import ServiceError
from app.services.registration import cancel_registration, register_student
from app.utils import now

bp = Blueprint("student", __name__, url_prefix="/student")


def _own_registration(reg_id: int) -> Registration:
    registration = db.get_or_404(Registration, reg_id)
    if registration.student_id != current_user.id:
        abort(403)
    return registration


@bp.route("/")
@role_required(C.STUDENT)
def dashboard():
    today = now().date()
    regs = Registration.query.filter_by(
        student_id=current_user.id, status=C.REG_CONFIRMED).all()
    upcoming_regs = sorted(
        (r for r in regs if r.event.event_date >= today),
        key=lambda r: (r.event.event_date, r.event.start_time))
    registered_ids = {r.event_id for r in regs}

    suggested = [
        e for e in Event.query.filter(
            Event.status == C.PUBLISHED, Event.event_date >= today
        ).order_by(Event.event_date).all()
        if e.id not in registered_ids and e.registration_open
    ][:3]

    opportunities = [
        o for o in VolunteerOpportunity.query.filter_by(is_open=True)
        .order_by(VolunteerOpportunity.created_at.desc()).all()
        if (o.event is None or o.event.status == C.PUBLISHED)
    ][:3]
    applied_ids = {a.opportunity_id for a in current_user.volunteer_applications}

    recent_achievements = sorted(
        current_user.achievements, key=lambda a: a.awarded_at, reverse=True)[:4]
    return render_template(
        "student/dashboard.html", stats=analytics.student_stats(current_user),
        upcoming_regs=upcoming_regs, suggested=suggested,
        announcements=announcements_for(current_user, limit=4),
        opportunities=opportunities, applied_ids=applied_ids,
        recent_achievements=recent_achievements,
    )


PHONE_RE = re.compile(r"^\+?[0-9][0-9 \-]{6,17}$")
SECTION_RE = re.compile(r"^[A-Za-z0-9]{1,10}$")


def _profile(user):
    profile = user.profile
    if profile is None:
        profile = StudentProfile(user_id=user.id)
        db.session.add(profile)
        db.session.flush()
    return profile


def _clean_url(value, label, errors, key):
    value = (value or "").strip()
    if not value:
        return None
    if len(value) > 200 or not re.match(r"^https?://[^\s/$.?#][^\s]*$", value, re.I):
        errors[key] = f"Enter a full {label} link starting with https://"
        return None
    return value


@bp.route("/profile")
@role_required(C.STUDENT)
def profile():
    """Profile page: photo, badge, verification status, details and achievements."""
    all_achievements = Achievement.query.order_by(Achievement.id).all()
    earned = {ua.achievement_id: ua for ua in current_user.achievements}
    return render_template(
        "student/profile.html", profile=_profile(current_user),
        stats=analytics.student_stats(current_user),
        all_achievements=all_achievements, earned=earned,
    )


@bp.route("/profile/edit", methods=["GET", "POST"])
@role_required(C.STUDENT)
def profile_edit():
    """Edit the permitted profile fields only.

    Role, username, verification status/timestamps and account status are never
    read from the form, so a crafted request cannot change them.
    """
    profile = _profile(current_user)
    errors = {}
    form = {}
    if request.method == "POST":
        f = request.form
        form = {k: (f.get(k) or "").strip() for k in (
            "name", "department", "branch", "semester", "section", "phone",
            "enrollment_no", "skills", "interests", "bio")}
        urls = {}
        for key, label in (("github_url", "GitHub"), ("linkedin_url", "LinkedIn"),
                           ("portfolio_url", "portfolio")):
            form[key] = (f.get(key) or "").strip()
            urls[key] = _clean_url(form[key], label, errors, key)

        if not 2 <= len(form["name"]) <= 120:
            errors["name"] = "Enter your full name (2-120 characters)."
        if form["department"] not in C.DEPARTMENTS:
            errors["department"] = "Choose your department."
        if form["branch"] and form["branch"] not in C.BRANCHES:
            errors["branch"] = "Choose a branch from the list."
        semester = None
        if form["semester"]:
            if form["semester"].isdigit() and 1 <= int(form["semester"]) <= 8:
                semester = int(form["semester"])
            else:
                errors["semester"] = "Semester must be between 1 and 8."
        if form["section"] and not SECTION_RE.match(form["section"]):
            errors["section"] = "Section can use letters and numbers only (up to 10)."
        if form["phone"] and not PHONE_RE.match(form["phone"]):
            errors["phone"] = "Enter a valid phone number (digits, spaces, dashes, optional +)."
        if len(form["skills"]) > 255 or len(form["interests"]) > 255:
            errors["skills"] = "Skills and interests can be at most 255 characters each."
        if len(form["bio"]) > 600:
            errors["bio"] = "Bio can be at most 600 characters."
        enrollment = form["enrollment_no"][:40] or None
        if enrollment:
            clash = StudentProfile.query.filter(
                StudentProfile.enrollment_no == enrollment,
                StudentProfile.user_id != current_user.id).first()
            if clash:
                errors["enrollment_no"] = "That student ID belongs to another account."

        new_photo = None
        photo = request.files.get("photo")
        if not errors and photo and photo.filename:
            try:
                new_photo = doc_service.save_avatar(photo)
            except ServiceError as exc:
                errors["photo"] = exc.message

        if not errors:
            current_user.name = form["name"]
            current_user.department = form["department"]
            profile.branch = form["branch"] or None
            profile.semester = semester
            profile.section = form["section"] or None
            profile.phone = form["phone"] or None
            profile.enrollment_no = enrollment
            profile.skills = form["skills"] or None
            profile.interests = form["interests"] or None
            profile.bio = form["bio"] or None
            profile.github_url = urls["github_url"]
            profile.linkedin_url = urls["linkedin_url"]
            profile.portfolio_url = urls["portfolio_url"]
            if new_photo:
                doc_service.delete_avatar(profile.photo)
                profile.photo = new_photo
            elif request.form.get("remove_photo") and profile.photo:
                doc_service.delete_avatar(profile.photo)
                profile.photo = None
            try:
                db.session.flush()
                achievements.evaluate_student(current_user)
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                errors["enrollment_no"] = "That student ID belongs to another account."
            else:
                flash("Profile updated.", "success")
                return redirect(url_for("student.profile"))
        flash("Please fix the highlighted fields.", "danger")
    else:
        form = {
            "name": current_user.name, "department": current_user.department or "",
            "branch": profile.branch or "", "semester": profile.semester or "",
            "section": profile.section or "", "phone": profile.phone or "",
            "enrollment_no": profile.enrollment_no or "", "skills": profile.skills or "",
            "interests": profile.interests or "", "bio": profile.bio or "",
            "github_url": profile.github_url or "", "linkedin_url": profile.linkedin_url or "",
            "portfolio_url": profile.portfolio_url or "",
        }
    return render_template("student/profile_edit.html", profile=profile, form=form,
                           errors=errors), (400 if errors else 200)


@bp.route("/verification/resubmit", methods=["POST"])
@role_required(C.STUDENT)
def verification_resubmit():
    try:
        verification.resubmit(current_user)
        flash("Thanks. Your profile was sent back to the Organizing Committee for review.",
              "success")
    except ServiceError as exc:
        flash(exc.message, "danger")
        if exc.code == "incomplete_profile":
            return redirect(url_for("student.profile_edit"))
    return redirect(url_for("student.profile"))


@bp.route("/events/<int:event_id>/register", methods=["POST"])
@role_required(C.STUDENT)
@verified_required
def register_event(event_id):
    event = db.get_or_404(Event, event_id)
    try:
        registration = register_student(current_user, event)
    except ServiceError as exc:
        flash(exc.message, "danger" if exc.code != "duplicate" else "warning")
        return redirect(url_for("main.event_detail", event_id=event.id))
    flash(f"You're registered! Your registration ID is {registration.reg_code}.", "success")
    return redirect(url_for("student.registration_detail", reg_id=registration.id))


@bp.route("/registrations")
@role_required(C.STUDENT)
def registrations():
    items = sorted(
        Registration.query.filter_by(student_id=current_user.id).all(),
        key=lambda r: r.event.start_datetime, reverse=True)
    return render_template("student/registrations.html", items=items, today=now().date())


@bp.route("/registrations/<int:reg_id>")
@role_required(C.STUDENT)
def registration_detail(reg_id):
    registration = _own_registration(reg_id)
    certificate = Certificate.query.filter_by(
        student_id=current_user.id, event_id=registration.event_id).first()
    return render_template("student/registration_detail.html",
                           registration=registration, certificate=certificate)


@bp.route("/registrations/<int:reg_id>/qr.png")
@role_required(C.STUDENT)
def qr_image(reg_id):
    registration = _own_registration(reg_id)
    if not registration.is_confirmed:
        abort(404)
    png = qr.qr_png(qr.make_token(registration.reg_code))
    return Response(png, mimetype="image/png",
                    headers={"Cache-Control": "private, no-store"})


@bp.route("/registrations/<int:reg_id>/cancel", methods=["POST"])
@role_required(C.STUDENT)
def cancel(reg_id):
    registration = _own_registration(reg_id)
    try:
        cancel_registration(registration, current_user)
        flash("Your registration was cancelled.", "info")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return redirect(url_for("student.registrations"))


@bp.route("/certificates")
@role_required(C.STUDENT)
@verified_required
def certificates():
    items = Certificate.query.filter_by(student_id=current_user.id) \
        .order_by(Certificate.issued_at.desc()).all()
    return render_template("student/certificates.html", items=items)


@bp.route("/certificates/<int:cert_id>/download")
@role_required(C.STUDENT)
@verified_required
def certificate_download(cert_id):
    certificate = db.get_or_404(Certificate, cert_id)
    if certificate.student_id != current_user.id:
        abort(403)
    verify_url = url_for("main.verify_certificate", code=certificate.cert_code, _external=True)
    pdf = cert_service.certificate_pdf(certificate, verify_url)
    return Response(
        pdf, mimetype="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="CollegeHub-{certificate.cert_code}.pdf"'})


@bp.route("/announcements")
@role_required(C.STUDENT)
def announcements():
    return render_template("student/announcements.html",
                           items=announcements_for(current_user))


@bp.route("/volunteering")
@role_required(C.STUDENT)
def volunteering_page():
    opportunities = [
        o for o in VolunteerOpportunity.query.filter_by(is_open=True)
        .order_by(VolunteerOpportunity.created_at.desc()).all()
        if o.event is None or o.event.status == C.PUBLISHED
    ]
    applications = {a.opportunity_id: a for a in current_user.volunteer_applications}
    history = sorted(
        (a for a in current_user.volunteer_applications),
        key=lambda a: a.created_at, reverse=True)
    return render_template("student/volunteering.html", opportunities=opportunities,
                           applications=applications, history=history)


@bp.route("/volunteering/<int:opp_id>/apply", methods=["POST"])
@role_required(C.STUDENT)
@verified_required
def volunteer_apply(opp_id):
    opportunity = db.get_or_404(VolunteerOpportunity, opp_id)
    try:
        volunteering.apply_for_opportunity(
            current_user, opportunity, request.form.get("message", ""))
        flash("Application sent. The organizer will review it.", "success")
    except ServiceError as exc:
        flash(exc.message, "warning" if exc.code == "duplicate" else "danger")
    return redirect(url_for("student.volunteering_page"))


@bp.route("/history")
@role_required(C.STUDENT)
def history():
    """Chronological participation history."""
    entries = []
    for reg in Registration.query.filter_by(student_id=current_user.id).all():
        entries.append((reg.created_at, "registered", f"Registered for {reg.event.title}",
                        url_for("student.registration_detail", reg_id=reg.id)))
        if reg.attendance:
            entries.append((reg.attendance.scanned_at, "attended",
                            f"Attended {reg.event.title}",
                            url_for("student.registration_detail", reg_id=reg.id)))
    for cert in current_user.certificates:
        entries.append((cert.issued_at, "certificate",
                        f"Certificate earned: {cert.event.title}",
                        url_for("student.certificates")))
    for app_ in current_user.volunteer_applications:
        if app_.status == C.APP_APPROVED:
            entries.append((app_.decided_at or app_.created_at, "volunteer",
                            f"Volunteer: {app_.opportunity.title}",
                            url_for("student.volunteering_page")))
    for ua in current_user.achievements:
        entries.append((ua.awarded_at, "achievement",
                        f"Achievement unlocked: {ua.achievement.title}",
                        url_for("student.profile")))
    entries.sort(key=lambda row: row[0], reverse=True)
    return render_template("student/history.html", entries=entries,
                           stats=analytics.student_stats(current_user))


@bp.route("/assistant")
@role_required(C.STUDENT)
def assistant():
    today = now().date()
    events = Event.query.filter(Event.status.in_(C.PUBLIC_STATUSES)) \
        .order_by(Event.event_date.desc()).all()
    registered_ids = {
        r.event_id for r in Registration.query.filter_by(
            student_id=current_user.id, status=C.REG_CONFIRMED)}
    selected = request.args.get("event", type=int)
    if selected not in {e.id for e in events}:
        selected = next((e.id for e in events if e.id in registered_ids),
                        events[0].id if events else None)
    return render_template("student/assistant.html", events=events,
                           selected=selected, registered_ids=registered_ids, today=today)
