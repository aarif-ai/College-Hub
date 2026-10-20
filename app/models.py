"""Database models.

Entity overview (arrows are foreign keys):

    User ──< Event >── Club
    User ──1 StudentProfile
    User ──< AuditLog (actor / target)
    Event ──< EventDocument, LogisticsTask, VolunteerOpportunity,
              Announcement, Certificate, Registration
    Registration ──1 Attendance
    VolunteerOpportunity ──< VolunteerApplication >── User
    User ──< Notification, UserAchievement >── Achievement

Timestamps are naive college-local times (see ``app.utils.now``).
"""
from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, Index, UniqueConstraint, text
from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

from app import constants as C
from app.extensions import db
from app.utils import now


def _in_list(column, values):
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class User(UserMixin, db.Model):
    """Every account. ``role`` decides what the person may do.

    Two separate state fields (never mix them):

    * ``account_status``      - may this account sign in? (ACTIVE / INACTIVE / SUSPENDED)
    * ``verification_status`` - is this *student* a verified member?
      (PENDING / VERIFIED / REJECTED / SUSPENDED; ``NULL`` for staff roles)
    """
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(_in_list("role", C.ROLES), name="ck_users_role"),
        CheckConstraint(_in_list("account_status", C.ACCOUNT_STATUSES),
                        name="ck_users_account_status"),
        CheckConstraint(
            "verification_status IS NULL OR "
            + _in_list("verification_status", C.VERIFICATION_STATUSES),
            name="ck_users_verification_status"),
        CheckConstraint("role <> 'student' OR verification_status IS NOT NULL",
                        name="ck_users_student_has_verification"),
        # Exactly one official Organizer and one official Logistics account.
        Index("uq_users_single_organizer", "role", unique=True,
              sqlite_where=text("role = 'organizer'"),
              postgresql_where=text("role = 'organizer'")),
        Index("uq_users_single_logistics", "role", unique=True,
              sqlite_where=text("role = 'logistics'"),
              postgresql_where=text("role = 'logistics'")),
    )

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), nullable=False, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True)
    department = db.Column(db.String(120))
    account_status = db.Column(db.String(12), nullable=False, default=C.ACCOUNT_ACTIVE)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    password_changed_at = db.Column(db.DateTime)

    verification_status = db.Column(db.String(12))
    verified_at = db.Column(db.DateTime)
    verified_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    verification_reason = db.Column(db.Text)      # rejection / correction / suspension note
    verification_updated_at = db.Column(db.DateTime)
    correction_requested = db.Column(db.Boolean, nullable=False, default=False)

    is_demo = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now)

    verified_by = db.relationship("User", remote_side=[id], foreign_keys=[verified_by_id])
    profile = db.relationship(
        "StudentProfile", back_populates="user", uselist=False,
        cascade="all, delete-orphan",
    )
    notifications = db.relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan",
        order_by="Notification.created_at.desc()",
    )
    achievements = db.relationship(
        "UserAchievement", back_populates="user", cascade="all, delete-orphan",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.account_status is None:
            self.account_status = C.ACCOUNT_ACTIVE
        # Students always start unverified; staff have no verification state.
        if self.verification_status is None and self.role == C.STUDENT:
            self.verification_status = C.VERIFY_PENDING

    @property
    def short_name(self):
        """First name for greetings, skipping titles such as Dr. or Prof."""
        titles = {"dr", "dr.", "prof", "prof.", "mr", "mr.", "ms", "ms.", "mrs", "mrs."}
        parts = [p for p in (self.name or "").split() if p.lower() not in titles]
        return parts[0] if parts else (self.name or "there")

    @validates("role")
    def _validate_role(self, _key, value):
        if value not in C.ROLES:
            raise ValueError(f"Invalid role: {value}")
        return value

    @validates("account_status")
    def _validate_account_status(self, _key, value):
        if value not in C.ACCOUNT_STATUSES:
            raise ValueError(f"Invalid account status: {value}")
        return value

    @validates("verification_status")
    def _validate_verification_status(self, _key, value):
        if value is not None and value not in C.VERIFICATION_STATUSES:
            raise ValueError(f"Invalid verification status: {value}")
        return value

    @validates("email")
    def _normalise_email(self, _key, value):
        return (value or "").strip().lower()

    @validates("username")
    def _normalise_username(self, _key, value):
        return (value or "").strip().lower()

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)
        self.password_changed_at = now()

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        """Session id = ``<id>.<password fingerprint>``.

        Changing or resetting the password changes the fingerprint, which
        signs out every other device that still holds the old session.
        """
        import hashlib
        fingerprint = hashlib.sha256((self.password_hash or "").encode()).hexdigest()[:12]
        return f"{self.id}.{fingerprint}"

    @property
    def is_active(self):  # Flask-Login hook: only ACTIVE accounts may sign in
        return self.account_status == C.ACCOUNT_ACTIVE

    @property
    def is_verified(self) -> bool:
        """True only for students the Organizer has approved (server-side truth)."""
        return self.role == C.STUDENT and self.verification_status == C.VERIFY_VERIFIED

    @property
    def verification_label(self) -> str:
        return C.VERIFICATION_LABELS.get(self.verification_status or "", "")

    @property
    def role_label(self) -> str:
        return C.ROLE_LABELS.get(self.role, self.role)

    @property
    def initials(self) -> str:
        parts = [p for p in self.name.split() if p]
        return "".join(p[0] for p in parts[:2]).upper() or "?"

    def has_role(self, *roles) -> bool:
        return self.role in roles

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class StudentProfile(db.Model):
    __tablename__ = "student_profiles"
    __table_args__ = (
        CheckConstraint("semester IS NULL OR (semester >= 1 AND semester <= 8)",
                        name="ck_profile_semester"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    photo = db.Column(db.String(255))            # stored avatar filename
    phone = db.Column(db.String(20))
    branch = db.Column(db.String(60))
    semester = db.Column(db.Integer)
    section = db.Column(db.String(10))
    enrollment_no = db.Column(db.String(40), unique=True)   # optional
    skills = db.Column(db.String(255))
    interests = db.Column(db.String(255))
    bio = db.Column(db.Text)
    github_url = db.Column(db.String(200))
    linkedin_url = db.Column(db.String(200))
    portfolio_url = db.Column(db.String(200))
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)

    user = db.relationship("User", back_populates="profile")

    @property
    def is_complete(self) -> bool:
        """Enough information for the Organizer to review the student."""
        return bool(self.user and self.user.department and self.branch
                    and self.semester and self.phone and self.bio)

    @property
    def skill_list(self):
        return [x.strip() for x in (self.skills or "").split(",") if x.strip()]

    @property
    def interest_list(self):
        return [x.strip() for x in (self.interests or "").split(",") if x.strip()]

    @property
    def links(self):
        return [(label, url) for label, url in (
            ("GitHub", self.github_url), ("LinkedIn", self.linkedin_url),
            ("Portfolio", self.portfolio_url)) if url]


class AuditLog(db.Model):
    """Record of important administrative actions (who did what to whom)."""
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    target_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    action = db.Column(db.String(60), nullable=False, index=True)
    reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=now, index=True)

    actor = db.relationship("User", foreign_keys=[actor_id])
    target = db.relationship("User", foreign_keys=[target_id])

    @property
    def label(self) -> str:
        return C.AUDIT_ACTIONS.get(self.action, self.action)


class Club(db.Model):
    __tablename__ = "clubs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    description = db.Column(db.String(300))
    category = db.Column(db.String(40))
    icon = db.Column(db.String(40), default="bi-people")
    created_at = db.Column(db.DateTime, nullable=False, default=now)

    events = db.relationship("Event", back_populates="club")


class Event(db.Model):
    __tablename__ = "events"
    __table_args__ = (
        db.Index("ix_events_status_date", "status", "event_date"),
        CheckConstraint(_in_list("status", C.EVENT_STATUSES), name="ck_events_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(40), nullable=False)
    venue = db.Column(db.String(160), nullable=False)
    event_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    registration_deadline = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=C.DRAFT, index=True)
    image = db.Column(db.String(255))  # stored cover image filename
    faculty_remarks = db.Column(db.Text)

    # Extra event information (all optional)
    department = db.Column(db.String(120))
    faculty_coordinator = db.Column(db.String(120))
    eligibility = db.Column(db.String(300))
    schedule = db.Column(db.Text)
    rules = db.Column(db.Text)
    contact_info = db.Column(db.String(200))
    completed_at = db.Column(db.DateTime)

    organizer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    club_id = db.Column(db.Integer, db.ForeignKey("clubs.id"))
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    reviewed_at = db.Column(db.DateTime)
    submitted_at = db.Column(db.DateTime)
    published_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    updated_at = db.Column(db.DateTime, nullable=False, default=now, onupdate=now)

    organizer = db.relationship("User", foreign_keys=[organizer_id], backref="organized_events")
    reviewer = db.relationship("User", foreign_keys=[reviewed_by_id])
    club = db.relationship("Club", back_populates="events")
    registrations = db.relationship(
        "Registration", back_populates="event", cascade="all, delete-orphan",
    )
    documents = db.relationship(
        "EventDocument", back_populates="event", cascade="all, delete-orphan",
        order_by="EventDocument.uploaded_at.desc()",
    )
    tasks = db.relationship(
        "LogisticsTask", back_populates="event", cascade="all, delete-orphan",
        order_by="LogisticsTask.id",
    )
    opportunities = db.relationship(
        "VolunteerOpportunity", back_populates="event", cascade="all, delete-orphan",
    )
    certificates = db.relationship(
        "Certificate", back_populates="event", cascade="all, delete-orphan",
    )
    attendances = db.relationship(
        "Attendance", back_populates="event", cascade="all, delete-orphan",
    )
    announcements = db.relationship(
        "Announcement", back_populates="event", cascade="all, delete-orphan",
    )

    @validates("status")
    def _validate_status(self, _key, value):
        if value not in C.EVENT_STATUSES:
            raise ValueError(f"Invalid event status: {value}")
        return value

    # ---- derived values -------------------------------------------------
    @property
    def status_label(self) -> str:
        return C.STATUS_LABELS[self.status]

    @property
    def icon(self) -> str:
        return C.CATEGORY_ICONS.get(self.category, "bi-calendar-event")

    @property
    def start_datetime(self) -> datetime:
        return datetime.combine(self.event_date, self.start_time)

    @property
    def end_datetime(self) -> datetime:
        return datetime.combine(self.event_date, self.end_time)

    @property
    def is_public(self) -> bool:
        return self.status in C.PUBLIC_STATUSES

    @property
    def is_past(self) -> bool:
        return now() > self.end_datetime

    @property
    def registered_count(self) -> int:
        return Registration.query.filter_by(
            event_id=self.id, status=C.REG_CONFIRMED
        ).count()

    @property
    def attended_count(self) -> int:
        return Attendance.query.filter_by(event_id=self.id).count()

    @property
    def seats_left(self) -> int:
        return max(self.capacity - self.registered_count, 0)

    @property
    def is_full(self) -> bool:
        return self.registered_count >= self.capacity

    @property
    def readiness_percent(self) -> int:
        total = len(self.tasks)
        if total == 0:
            return 0
        done = sum(1 for t in self.tasks if t.status == C.TASK_COMPLETED)
        return round(done * 100 / total)

    def registration_block_reason(self):
        """Why students cannot register right now, or ``None`` if they can."""
        if self.status != C.PUBLISHED:
            return "This event is not open for registration."
        if now() > self.end_datetime:
            return "This event has already taken place."
        if now() > self.registration_deadline:
            return "The registration deadline has passed."
        if self.is_full:
            return "This event is full."
        return None

    @property
    def registration_open(self) -> bool:
        return self.registration_block_reason() is None

    def __repr__(self):
        return f"<Event {self.id} {self.title!r} {self.status}>"


class EventDocument(db.Model):
    __tablename__ = "event_documents"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(
        db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    uploader_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False, unique=True)
    file_path = db.Column(db.String(500), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False, default=0)
    page_count = db.Column(db.Integer, default=0)
    # Text pulled from the PDF, with "[[Page N]]" markers. Used by the AI
    # assistant so the PDF does not need to be re-read for every question.
    extracted_text = db.Column(db.Text)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=now)

    event = db.relationship("Event", back_populates="documents")
    uploader = db.relationship("User")

    @property
    def has_text(self) -> bool:
        return bool(self.extracted_text and self.extracted_text.strip())


class Registration(db.Model):
    __tablename__ = "registrations"
    __table_args__ = (
        UniqueConstraint("student_id", "event_id", name="uq_registration_student_event"),
    )

    id = db.Column(db.Integer, primary_key=True)
    reg_code = db.Column(db.String(40), nullable=False, unique=True, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    event_id = db.Column(
        db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    status = db.Column(db.String(20), nullable=False, default=C.REG_CONFIRMED)
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    cancelled_at = db.Column(db.DateTime)

    student = db.relationship("User", backref="registrations")
    event = db.relationship("Event", back_populates="registrations")
    attendance = db.relationship(
        "Attendance", back_populates="registration", uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def is_confirmed(self) -> bool:
        return self.status == C.REG_CONFIRMED


class Attendance(db.Model):
    __tablename__ = "attendances"

    id = db.Column(db.Integer, primary_key=True)
    # unique=True is the database-level guard against duplicate attendance
    registration_id = db.Column(
        db.Integer, db.ForeignKey("registrations.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    event_id = db.Column(
        db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    scanned_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    method = db.Column(db.String(20), nullable=False, default="qr")
    scanned_at = db.Column(db.DateTime, nullable=False, default=now)

    registration = db.relationship("Registration", back_populates="attendance")
    event = db.relationship("Event", back_populates="attendances")
    student = db.relationship("User", foreign_keys=[student_id])
    scanned_by = db.relationship("User", foreign_keys=[scanned_by_id])


class LogisticsTask(db.Model):
    __tablename__ = "logistics_tasks"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(
        db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    title = db.Column(db.String(160), nullable=False)
    area = db.Column(db.String(60), nullable=False, default="General")
    assigned_to = db.Column(db.String(120))
    status = db.Column(db.String(20), nullable=False, default=C.TASK_PENDING)
    notes = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, nullable=False, default=now, onupdate=now)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    event = db.relationship("Event", back_populates="tasks")
    updated_by = db.relationship("User")

    @validates("status")
    def _validate_status(self, _key, value):
        if value not in C.TASK_STATUSES:
            raise ValueError(f"Invalid task status: {value}")
        return value

    @property
    def status_label(self) -> str:
        return C.TASK_LABELS[self.status]


class VolunteerOpportunity(db.Model):
    __tablename__ = "volunteer_opportunities"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(
        db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"), index=True,
    )
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False)
    slots = db.Column(db.Integer, nullable=False, default=5)
    is_open = db.Column(db.Boolean, nullable=False, default=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now)

    event = db.relationship("Event", back_populates="opportunities")
    created_by = db.relationship("User")
    applications = db.relationship(
        "VolunteerApplication", back_populates="opportunity",
        cascade="all, delete-orphan", order_by="VolunteerApplication.created_at",
    )

    @property
    def approved_count(self) -> int:
        return sum(1 for a in self.applications if a.status == C.APP_APPROVED)

    @property
    def slots_left(self) -> int:
        return max(self.slots - self.approved_count, 0)


class VolunteerApplication(db.Model):
    __tablename__ = "volunteer_applications"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "student_id", name="uq_application_once"),
    )

    id = db.Column(db.Integer, primary_key=True)
    opportunity_id = db.Column(
        db.Integer, db.ForeignKey("volunteer_opportunities.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    message = db.Column(db.String(400))
    assignment = db.Column(db.String(120))   # event responsibility once approved
    status = db.Column(db.String(20), nullable=False, default=C.APP_PENDING)
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    decided_at = db.Column(db.DateTime)
    decided_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    opportunity = db.relationship("VolunteerOpportunity", back_populates="applications")
    student = db.relationship("User", foreign_keys=[student_id], backref="volunteer_applications")
    decided_by = db.relationship("User", foreign_keys=[decided_by_id])


class Certificate(db.Model):
    __tablename__ = "certificates"
    __table_args__ = (
        UniqueConstraint("student_id", "event_id", name="uq_certificate_student_event"),
    )

    id = db.Column(db.Integer, primary_key=True)
    cert_code = db.Column(db.String(40), nullable=False, unique=True, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    event_id = db.Column(
        db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    issued_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    issued_at = db.Column(db.DateTime, nullable=False, default=now)

    student = db.relationship("User", foreign_keys=[student_id], backref="certificates")
    event = db.relationship("Event", back_populates="certificates")
    issued_by = db.relationship("User", foreign_keys=[issued_by_id])


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)
    event_id = db.Column(
        db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"), index=True,
    )
    audience = db.Column(db.String(20), nullable=False, default="all")
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now, index=True)

    event = db.relationship("Event", back_populates="announcements")
    author = db.relationship("User")


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    message = db.Column(db.String(300), nullable=False)
    link = db.Column(db.String(300))
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now)

    user = db.relationship("User", back_populates="notifications")


class Achievement(db.Model):
    __tablename__ = "achievements"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), nullable=False, unique=True)
    title = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    icon = db.Column(db.String(40), nullable=False, default="bi-award")


class UserAchievement(db.Model):
    __tablename__ = "user_achievements"
    __table_args__ = (
        UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    achievement_id = db.Column(
        db.Integer, db.ForeignKey("achievements.id", ondelete="CASCADE"), nullable=False,
    )
    awarded_at = db.Column(db.DateTime, nullable=False, default=now)

    user = db.relationship("User", back_populates="achievements")
    achievement = db.relationship("Achievement")
