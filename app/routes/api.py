"""JSON endpoints used by the page JavaScript."""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app import constants as C
from app.extensions import db
from app.models import Event
from app.services import achievements
from app.services.ai.assistant import answer_question
from app.services.errors import ServiceError

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/events/<int:event_id>/ask", methods=["POST"])
@login_required
def ask(event_id):
    """AI Event Assistant. Answers only from official event information."""
    event = db.get_or_404(Event, event_id)
    is_owner = current_user.role == C.ORGANIZER and event.organizer_id == current_user.id
    if not event.is_public and not (is_owner or current_user.role == C.FACULTY):
        return jsonify(error="This event is not available."), 404

    payload = request.get_json(silent=True) or {}
    try:
        result = answer_question(event, payload.get("question", ""))
    except ServiceError as exc:
        return jsonify(error=exc.message), 400

    if current_user.role == C.STUDENT:
        if achievements.award(current_user, "curious_mind"):
            db.session.commit()
    return jsonify(
        answer=result.answer, found=result.found, sources=result.sources,
        mode=result.mode, note=result.note,
    )
