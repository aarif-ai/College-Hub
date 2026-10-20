"""Public pages: landing, event discovery, certificate verification, files."""
from pathlib import Path

from flask import (
    Blueprint, abort, jsonify, redirect, render_template, request,
    send_from_directory, url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_

from app import constants as C
from app.extensions import db
from app.models import (
    Announcement, Certificate, Club, Event, EventDocument, Notification,
    Registration, VolunteerOpportunity,
)
from app.services import documents as doc_service
from app.utils import now

bp = Blueprint("main", __name__)


@bp.route("/")
def landing():
    today = now().date()
    upcoming = (
        Event.query.filter(Event.status == C.PUBLISHED, Event.event_date >= today)
        .order_by(Event.event_date, Event.start_time).limit(3).all()
    )
    clubs = Club.query.order_by(Club.name).limit(6).all()
    opportunities = (
        VolunteerOpportunity.query.join(Event, isouter=True)
        .filter(VolunteerOpportunity.is_open.is_(True),
                or_(Event.status == C.PUBLISHED, VolunteerOpportunity.event_id.is_(None)))
        .order_by(VolunteerOpportunity.created_at.desc()).limit(3).all()
    )
    return render_template("public/landing.html", upcoming=upcoming,
                           clubs=clubs, opportunities=opportunities)


@bp.route("/dashboard")
@login_required
def dashboard():
    from app import home_endpoint
    return redirect(url_for(home_endpoint(current_user)))


@bp.route("/events")
def events():
    """Public discovery: published events only."""
    q = (request.args.get("q") or "").strip()[:80]
    category = request.args.get("category", "")
    club_id = request.args.get("club", type=int)
    when = request.args.get("when", "upcoming")
    page = request.args.get("page", 1, type=int)

    query = Event.query.filter(Event.status.in_(C.PUBLIC_STATUSES))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Event.title.ilike(like), Event.description.ilike(like),
                                 Event.venue.ilike(like)))
    if category in C.CATEGORIES:
        query = query.filter(Event.category == category)
    if club_id:
        query = query.filter(Event.club_id == club_id)
    today = now().date()
    if when == "past":
        query = query.filter(Event.event_date < today).order_by(Event.event_date.desc())
    elif when == "all":
        query = query.order_by(Event.event_date.desc())
    else:
        when = "upcoming"
        query = query.filter(Event.event_date >= today).order_by(Event.event_date, Event.start_time)

    pagination = query.paginate(page=page, per_page=9, error_out=False)
    return render_template(
        "public/events.html", pagination=pagination, events=pagination.items,
        q=q, category=category, club_id=club_id, when=when,
        clubs=Club.query.order_by(Club.name).all(),
    )


def _can_preview(event: Event) -> bool:
    """Non-published events are visible only to people involved with them."""
    if not current_user.is_authenticated:
        return False
    if current_user.role == C.FACULTY:
        return True
    if current_user.role == C.ORGANIZER:
        return event.organizer_id == current_user.id
    if current_user.role == C.LOGISTICS:
        return event.status in (C.APPROVED, C.PUBLISHED)
    return False


@bp.route("/events/<int:event_id>")
def event_detail(event_id):
    event = db.get_or_404(Event, event_id)
    if not event.is_public and not _can_preview(event):
        abort(404)
    registration = None
    if current_user.is_authenticated and current_user.role == C.STUDENT:
        registration = Registration.query.filter_by(
            student_id=current_user.id, event_id=event.id).first()
    announcements = (
        Announcement.query.filter_by(event_id=event.id)
        .filter(Announcement.audience.in_(["all", "students"]))
        .order_by(Announcement.created_at.desc()).limit(3).all()
        if event.is_public else []
    )
    opportunities = [o for o in event.opportunities if o.is_open] \
        if event.status == C.PUBLISHED else []
    return render_template(
        "public/event_detail.html", event=event, registration=registration,
        announcements=announcements, opportunities=opportunities,
        block_reason=event.registration_block_reason(),
        can_ask=event.is_public or _can_preview(event),
    )


@bp.route("/verify/<code>")
def verify_certificate(code):
    certificate = Certificate.query.filter_by(cert_code=code.strip().upper()).first()
    return render_template("public/verify.html", certificate=certificate, code=code), (
        200 if certificate else 404
    )


@bp.route("/media/covers/<path:filename>")
def cover(filename):
    """Event cover images are public (they appear on the public event pages)."""
    return send_from_directory(doc_service.cover_directory(), filename, max_age=3600)


@bp.route("/media/avatars/<path:filename>")
@login_required
def avatar(filename):
    """Profile photos are only shown to signed-in users."""
    return send_from_directory(doc_service.avatar_directory(), filename, max_age=3600)


@bp.route("/documents/<int:document_id>")
@login_required
def document_download(document_id):
    """Official PDFs are private: only the owning organizer, faculty and logistics."""
    document = db.get_or_404(EventDocument, document_id)
    event = document.event
    allowed = (
        current_user.role in (C.FACULTY, C.LOGISTICS)
        or (current_user.role == C.ORGANIZER and event.organizer_id == current_user.id)
    )
    if not allowed:
        abort(403)
    path = doc_service.absolute_path(document.file_path)
    if not Path(path).exists():
        abort(404)
    return send_from_directory(
        path.parent, path.name, as_attachment=True,
        download_name=document.original_filename, mimetype="application/pdf",
    )


@bp.route("/notifications")
@login_required
def notifications():
    items = Notification.query.filter_by(user_id=current_user.id) \
        .order_by(Notification.created_at.desc()).limit(50).all()
    return render_template("shared/notifications.html", items=items)


@bp.route("/notifications/read", methods=["POST"])
@login_required
def notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False) \
        .update({"is_read": True})
    db.session.commit()
    return redirect(url_for("main.notifications"))


@bp.route("/healthz")
def health():
    """Used by hosting platforms to check the app is up."""
    db.session.execute(db.text("SELECT 1"))
    return jsonify(status="ok")
