"""Accounts: student sign-up, passwords, and the staff hierarchy.

Hierarchy (who may manage whose credentials)::

    Faculty ──manages──> the ONE Organizer account
    Organizer ──manages──> the ONE Logistics account
    Students register themselves

Everything here is enforced on the server. The database backs the "exactly
one" rules with partial unique indexes (see ``User.__table_args__``); the
checks below give friendly messages and handle race conditions.
"""
import hashlib
import re
import secrets

from flask import current_app
from itsdangerous import BadData, URLSafeTimedSerializer
from sqlalchemy.exc import IntegrityError

from app import constants as C
from app.extensions import db
from app.models import StudentProfile, User
from app.services import audit
from app.services.errors import ServiceError
from app.services.notifications import notify

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(C.USERNAME_PATTERN)
STAFF_USERNAME_RE = re.compile(C.STAFF_USERNAME_PATTERN)

# Which role may manage which staff role.
MANAGER_OF = {C.ORGANIZER: C.FACULTY, C.LOGISTICS: C.ORGANIZER}
_ROLE_NAMES = {C.ORGANIZER: "Organizer", C.LOGISTICS: "Logistics"}
_DEFAULT_NAMES = {
    C.ORGANIZER: "CollegeHub Organizing Committee",
    C.LOGISTICS: "CollegeHub Logistics Team",
}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def password_problem(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if len(password) > 128:
        return "Password is too long (maximum 128 characters)."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must contain at least one letter and one number."
    return None


def normalise_email(value: str) -> str:
    return (value or "").strip().lower()


def email_problem(email: str, ignore_user_id: int | None = None) -> str | None:
    if not EMAIL_RE.match(email) or len(email) > 120:
        return "Enter a valid email address."
    clash = User.query.filter_by(email=email).first()
    if clash and clash.id != ignore_user_id:
        return "An account with this email already exists."
    return None


def username_taken(username: str) -> bool:
    return User.query.filter_by(username=username).first() is not None


def suggest_username(username: str) -> str | None:
    """Next free username for ``firstname.lastname`` (adds 01, 02, ...)."""
    base = re.sub(r"\d+$", "", username)
    if not re.match(r"^[a-z]{2,24}\.[a-z]{2,24}$", base):
        return None
    for n in range(1, 100):
        candidate = f"{base}{n:02d}"
        if not username_taken(candidate):
            return candidate
    return None


def student_username_problem(username: str) -> str | None:
    """Validate a student username against the CollegeHub pattern."""
    if not username:
        return "Choose a username."
    if not USERNAME_RE.match(username):
        return (f"Use the format {C.USERNAME_EXAMPLE}: lowercase letters only, one dot "
                "between first and last name (for example rahul.sharma).")
    if username_taken(username):
        hint = suggest_username(username)
        return ("That username is already taken."
                + (f" Try {hint}." if hint else ""))
    return None


def name_from_username(username: str) -> str:
    """``aarif.mushtaq01`` -> ``Aarif Mushtaq`` (editable later in the profile)."""
    parts = re.sub(r"\d+$", "", username).split(".")
    return " ".join(p.capitalize() for p in parts if p)


# ---------------------------------------------------------------------------
# Student registration
# ---------------------------------------------------------------------------
def register_student(username: str, email: str, password: str, confirm: str):
    """Create a student account. Returns ``(user, errors)``; ``user`` is None on error.

    The account starts ACTIVE with verification PENDING. The role is fixed by
    this function: nothing the client sends can choose a different role or
    verification status.
    """
    username = (username or "").strip().lower()
    email = normalise_email(email)
    errors: dict[str, str] = {}

    problem = student_username_problem(username)
    if problem:
        errors["username"] = problem
    problem = email_problem(email)
    if problem:
        errors["email"] = problem
    problem = password_problem(password or "")
    if problem:
        errors["password"] = problem
    elif password != confirm:
        errors["confirm_password"] = "Passwords do not match."
    if errors:
        return None, errors

    user = User(username=username, email=email, name=name_from_username(username),
                role=C.STUDENT, account_status=C.ACCOUNT_ACTIVE,
                verification_status=C.VERIFY_PENDING)
    user.set_password(password)
    user.profile = StudentProfile()
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        # Two people raced for the same username/email: the database decides.
        db.session.rollback()
        if username_taken(username):
            errors["username"] = student_username_problem(username) or "That username is taken."
        else:
            errors["email"] = "An account with this email already exists."
        return None, errors
    return user, {}


# ---------------------------------------------------------------------------
# Sign in
# ---------------------------------------------------------------------------
def find_by_login(identifier: str) -> User | None:
    """Look an account up by username or email (case-insensitive)."""
    identifier = (identifier or "").strip().lower()
    if not identifier:
        return None
    field = User.email if "@" in identifier else User.username
    return User.query.filter(field == identifier).first()


# ---------------------------------------------------------------------------
# Password change / reset
# ---------------------------------------------------------------------------
def change_own_password(user: User, current: str, new: str, confirm: str) -> dict:
    errors: dict[str, str] = {}
    if not user.check_password(current or ""):
        errors["current_password"] = "Your current password is not correct."
    problem = password_problem(new or "")
    if problem:
        errors["new_password"] = problem
    elif new != confirm:
        errors["confirm_password"] = "Passwords do not match."
    elif (current or "") == new:
        errors["new_password"] = "Choose a password different from the current one."
    if errors:
        return errors
    user.set_password(new)
    user.must_change_password = False
    db.session.commit()
    return {}


def _fingerprint(user: User) -> str:
    return hashlib.sha256(user.password_hash.encode()).hexdigest()[:20]


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="collegehub-password-reset")


def make_reset_token(user: User) -> str:
    """Signed, expiring token. It embeds a fingerprint of the current password
    hash, so it stops working as soon as the password changes (single use)."""
    return _serializer().dumps({"uid": user.id, "fp": _fingerprint(user)})


def user_from_reset_token(token: str) -> User | None:
    try:
        data = _serializer().loads(token, max_age=current_app.config["RESET_TOKEN_MAX_AGE"])
    except BadData:
        return None
    user = db.session.get(User, data.get("uid")) if isinstance(data, dict) else None
    if (user is None or user.role != C.STUDENT or not user.is_active
            or data.get("fp") != _fingerprint(user)):
        return None
    return user


def reset_password_with_token(token: str, new: str, confirm: str):
    """Returns ``(user, errors)``. ``user`` is None when the token is bad."""
    user = user_from_reset_token(token)
    if user is None:
        return None, {"token": "This reset link is invalid or has expired."}
    problem = password_problem(new or "")
    if problem:
        return user, {"password": problem}
    if new != confirm:
        return user, {"confirm_password": "Passwords do not match."}
    user.set_password(new)
    user.must_change_password = False
    db.session.commit()
    return user, {}


# ---------------------------------------------------------------------------
# Staff hierarchy: Faculty -> Organizer, Organizer -> Logistics
# ---------------------------------------------------------------------------
def managed_account(role: str) -> User | None:
    """The single official account for ``role`` (or None if not created yet)."""
    return User.query.filter_by(role=role).first()


def _require_manager(actor: User, role: str) -> None:
    if role not in MANAGER_OF:
        raise ServiceError("This account cannot be managed here.", "forbidden")
    if actor is None or actor.role != MANAGER_OF[role] or not actor.is_active:
        raise ServiceError(
            f"Only {C.ROLE_LABELS[MANAGER_OF[role]]} can manage the "
            f"{_ROLE_NAMES[role]} account.", "forbidden")


def _staff_target(actor: User, role: str) -> User:
    _require_manager(actor, role)
    account = managed_account(role)
    if account is None:
        raise ServiceError(f"The {_ROLE_NAMES[role]} account has not been created yet.",
                           "not_found")
    return account


def _staff_username_problem(username: str, ignore_user_id=None) -> str | None:
    if not STAFF_USERNAME_RE.match(username):
        return ("Username must be 3-30 characters: lowercase letters, numbers and "
                "underscores, starting with a letter.")
    clash = User.query.filter_by(username=username).first()
    if clash and clash.id != ignore_user_id:
        return "That username is already in use."
    return None


def create_staff_account(actor: User, role: str, username: str, email: str,
                         password: str, name: str | None = None) -> User:
    """Create the one official Organizer (by Faculty) or Logistics (by Organizer) account."""
    _require_manager(actor, role)
    return provision_staff_account(role, username, email, password, name, actor=actor)


def provision_staff_account(role: str, username: str, email: str, password: str,
                            name: str | None = None, actor: User | None = None,
                            is_demo: bool = False) -> User:
    """Create a singleton staff account. Also used by seed data and the CLI.

    Raises ``ServiceError`` if the role already has an account: there is never
    more than one Organizer or Logistics account.
    """
    if role not in C.SINGLETON_ROLES:
        raise ServiceError("Only the Organizer and Logistics accounts are provisioned here.",
                           "forbidden")
    if managed_account(role) is not None:
        raise ServiceError(f"The {_ROLE_NAMES[role]} account already exists. "
                           "There can only be one.", "duplicate")
    username = (username or "").strip().lower()
    email = normalise_email(email)
    problem = _staff_username_problem(username) or email_problem(email) or password_problem(password or "")
    if problem:
        raise ServiceError(problem, "validation")
    user = User(username=username, email=email, role=role,
                name=(name or "").strip() or _DEFAULT_NAMES[role],
                account_status=C.ACCOUNT_ACTIVE, is_demo=is_demo)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ServiceError("That username, email or role is already in use.", "duplicate")
    return user


def update_staff_details(actor: User, role: str, username: str, email: str) -> User:
    account = _staff_target(actor, role)
    username = (username or "").strip().lower()
    email = normalise_email(email)
    problem = (_staff_username_problem(username, account.id)
               or email_problem(email, account.id))
    if problem:
        raise ServiceError(problem, "validation")
    account.username = username
    account.email = email
    audit.record(actor, f"{role}.updated", account, f"username={username}, email={email}")
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ServiceError("That username or email is already in use.", "duplicate")
    return account


def set_staff_password(actor: User, role: str, new: str, confirm: str) -> User:
    account = _staff_target(actor, role)
    problem = password_problem(new or "")
    if problem:
        raise ServiceError(problem, "validation")
    if new != confirm:
        raise ServiceError("Passwords do not match.", "validation")
    account.set_password(new)
    account.must_change_password = True      # the account holder picks their own next
    audit.record(actor, f"{role}.password_set", account)
    notify(account, f"Your password was changed by {actor.name}. Please sign in with the new one.")
    db.session.commit()
    return account


def reset_staff_password(actor: User, role: str) -> tuple[User, str]:
    """Generate a one-time temporary password (shown once to the manager)."""
    account = _staff_target(actor, role)
    temporary = "Ch-" + secrets.token_urlsafe(9) + "7"
    account.set_password(temporary)
    account.must_change_password = True
    audit.record(actor, f"{role}.password_reset", account)
    db.session.commit()
    return account, temporary


def set_staff_active(actor: User, role: str, active: bool) -> User:
    account = _staff_target(actor, role)
    account.account_status = C.ACCOUNT_ACTIVE if active else C.ACCOUNT_INACTIVE
    audit.record(actor, f"{role}.{'activated' if active else 'deactivated'}", account)
    db.session.commit()
    return account

