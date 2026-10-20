"""CollegeHub application factory."""
import logging
import os

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFError

# Load .env BEFORE importing config, which reads environment variables.
load_dotenv()

from app import constants as C  # noqa: E402
from app.config import CONFIGS, DEV_SECRET  # noqa: E402
from app.extensions import csrf, db, login_manager  # noqa: E402
from app.utils import fmt_date, fmt_datetime, fmt_short_date, fmt_time  # noqa: E402

ROLE_HOME = {
    C.STUDENT: "student.dashboard",
    C.ORGANIZER: "organizer.dashboard",
    C.LOGISTICS: "logistics.dashboard",
    C.FACULTY: "faculty.dashboard",
}


def home_endpoint(user) -> str:
    """Dashboard endpoint for ``user`` (or the landing page when signed out)."""
    if user is not None and user.is_authenticated:
        return ROLE_HOME.get(user.role, "main.landing")
    return "main.landing"


def create_app(config_name: str | None = None) -> Flask:
    config_name = config_name or os.environ.get("APP_ENV", "development")
    if config_name not in CONFIGS:
        raise RuntimeError(f"Unknown APP_ENV '{config_name}'")
    config = CONFIGS[config_name]

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config)

    if config_name == "production" and app.config["SECRET_KEY"] == DEV_SECRET:
        raise RuntimeError("SECRET_KEY must be set to a strong random value in production.")

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(session_id):
        import hashlib
        try:
            user_id, fingerprint = str(session_id).split(".", 1)
            user = db.session.get(User, int(user_id))
        except ValueError:
            return None
        if user is None or not user.is_active:
            return None          # deactivated or suspended: signed out immediately
        if hashlib.sha256(user.password_hash.encode()).hexdigest()[:12] != fingerprint:
            return None          # password changed since this session started
        return user

    @app.before_request
    def force_password_change():
        """Accounts whose password was set or reset by someone else must choose
        their own before using anything else."""
        from flask_login import current_user
        if (current_user.is_authenticated and current_user.must_change_password
                and request.endpoint not in ("auth.change_password", "auth.logout", "static")):
            return redirect(url_for("auth.change_password"))

    _register_blueprints(app)
    _register_template_helpers(app)
    _register_error_handlers(app)
    _register_security_headers(app)

    from app.cli import register_account_cli, register_cli
    register_cli(app)
    register_account_cli(app)

    # Create tables if they do not exist yet (safe to repeat).
    with app.app_context():
        db.create_all()

    if not app.debug and not app.testing:
        logging.basicConfig(level=logging.INFO)
    return app


def _register_blueprints(app: Flask) -> None:
    from app.routes.api import bp as api_bp
    from app.routes.auth import bp as auth_bp
    from app.routes.faculty import bp as faculty_bp
    from app.routes.logistics import bp as logistics_bp
    from app.routes.main import bp as main_bp
    from app.routes.organizer import bp as organizer_bp
    from app.routes.student import bp as student_bp

    for blueprint in (main_bp, auth_bp, student_bp, organizer_bp,
                      faculty_bp, logistics_bp, api_bp):
        app.register_blueprint(blueprint)


def _register_template_helpers(app: Flask) -> None:
    app.jinja_env.filters.update(
        fmt_date=fmt_date, fmt_time=fmt_time,
        fmt_datetime=fmt_datetime, fmt_short_date=fmt_short_date,
    )
    app.jinja_env.globals.update(home_endpoint=home_endpoint)

    @app.context_processor
    def inject_globals():
        from app.models import Event
        from app.services.notifications import unread_count
        from app.utils import now
        unread = unread_count(current_user) if current_user.is_authenticated else 0
        pending = pending_members = 0
        if current_user.is_authenticated and current_user.role == C.FACULTY:
            pending = Event.query.filter_by(status=C.SUBMITTED).count()
        if current_user.is_authenticated and current_user.role == C.ORGANIZER:
            from app.models import User
            pending_members = User.query.filter_by(
                role=C.STUDENT, verification_status=C.VERIFY_PENDING).count()
        return {
            "C": C,
            "unread_notifications": unread,
            "pending_proposals": pending,
            "pending_members": pending_members,
            "now_year": now().year,
            "ai_demo_mode": not app.config.get("AI_API_KEY"),
        }


def _register_error_handlers(app: Flask) -> None:
    def render_error(code, title, message):
        return render_template(
            f"errors/{code}.html", code=code, title=title, message=message
        ), code

    @app.errorhandler(400)
    def bad_request(_e):
        return render_error(400, "Bad request", "We could not understand that request.")

    @app.errorhandler(CSRFError)
    def csrf_error(_e):
        return render_error(
            400, "Session expired",
            "Your form session expired. Go back, refresh the page and try again.",
        )

    @app.errorhandler(403)
    def forbidden(_e):
        return render_error(
            403, "Access denied",
            "Your account does not have permission to open this page.",
        )

    @app.errorhandler(404)
    def not_found(_e):
        return render_error(404, "Page not found",
                            "The page you are looking for does not exist or has moved.")

    @app.errorhandler(413)
    def too_large(_e):
        return render_error(
            400, "File too large",
            f"Uploads can be at most {app.config['MAX_UPLOAD_MB']} MB.",
        )

    @app.errorhandler(500)
    def server_error(_e):
        db.session.rollback()
        return render_error(
            500, "Something went wrong",
            "An unexpected error occurred. Please try again in a moment.",
        )


def _register_security_headers(app: Flask) -> None:
    @app.after_request
    def add_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        if request.endpoint and request.endpoint.startswith(("student.qr", "api.")):
            response.headers["Cache-Control"] = "no-store"
        return response
