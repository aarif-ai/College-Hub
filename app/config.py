"""Application configuration.

Values come from environment variables (loaded from ``.env`` by
python-dotenv in ``create_app``). Nothing secret is hard coded here.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEV_SECRET = "dev-only-secret-do-not-use-in-production"


def _database_uri() -> str:
    """Return the SQLAlchemy URI, defaulting to local SQLite."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return "sqlite:///collegehub.db"  # stored in instance/
    # Some hosts still hand out the legacy "postgres://" scheme.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def _upload_folder() -> str:
    folder = Path(os.environ.get("UPLOAD_FOLDER", "uploads"))
    if not folder.is_absolute():
        folder = BASE_DIR / folder
    return str(folder)


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", DEV_SECRET)
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    UPLOAD_FOLDER = _upload_folder()
    MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "8"))
    MAX_CONTENT_LENGTH = (MAX_UPLOAD_MB + 1) * 1024 * 1024
    ALLOWED_DOCUMENT_EXTENSIONS = {"pdf"}
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_HTTPONLY = True

    AI_PROVIDER = os.environ.get("AI_PROVIDER", "anthropic").lower()
    AI_API_KEY = os.environ.get("AI_API_KEY", "").strip()
    AI_MODEL = os.environ.get("AI_MODEL", "claude-haiku-5-5")
    AI_BASE_URL = os.environ.get("AI_BASE_URL", "").strip()
    AI_TIMEOUT_SECONDS = int(os.environ.get("AI_TIMEOUT_SECONDS", "20"))

    # Demo accounts (seed data only). Every value can be overridden in .env.
    DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "CollegeHub@2026")
    DEMO_FACULTY_USERNAME = os.environ.get("DEMO_FACULTY_USERNAME", "collegehub_faculty")
    DEMO_FACULTY_EMAIL = os.environ.get("DEMO_FACULTY_EMAIL", "faculty@demo.collegehub.test")
    DEMO_ORGANIZER_USERNAME = os.environ.get("DEMO_ORGANIZER_USERNAME", "collegehub_org")
    DEMO_ORGANIZER_EMAIL = os.environ.get("DEMO_ORGANIZER_EMAIL", "organizer@demo.collegehub.test")
    DEMO_LOGISTICS_USERNAME = os.environ.get("DEMO_LOGISTICS_USERNAME", "collegehub_logistics")
    DEMO_LOGISTICS_EMAIL = os.environ.get("DEMO_LOGISTICS_EMAIL", "logistics@demo.collegehub.test")

    # Password reset
    RESET_TOKEN_MAX_AGE = int(os.environ.get("RESET_TOKEN_MAX_AGE", "3600"))  # seconds
    # Show the reset link on screen instead of e-mailing it. Demo/dev only:
    # anyone who can see the page could take over the account.
    DEMO_SHOW_RESET_LINK = os.environ.get("DEMO_SHOW_RESET_LINK", "0") == "1"

    # Outgoing e-mail (optional). Without MAIL_SERVER, messages are only logged.
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "").strip()
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "1") == "1"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "").strip()
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_FROM = os.environ.get("MAIL_FROM", "CollegeHub <no-reply@collegehub.example>")

    # Profile photos
    MAX_AVATAR_MB = 2
    DEBUG = False
    TESTING = False


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    DEMO_SHOW_RESET_LINK = True


class TestingConfig(BaseConfig):
    TESTING = True
    SECRET_KEY = "testing-secret-key"
    # In-memory SQLite by default; set TEST_DATABASE_URL to run tests on PostgreSQL.
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL") or "sqlite://"
    WTF_CSRF_ENABLED = False
    AI_API_KEY = ""  # tests always run in offline demo mode
    MAIL_SERVER = ""
    DEMO_SHOW_RESET_LINK = False


class ProductionConfig(BaseConfig):
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
