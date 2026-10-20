"""Shared constants: roles, statuses, categories, default checklists."""

# --- Roles -------------------------------------------------------------
STUDENT = "student"
ORGANIZER = "organizer"
LOGISTICS = "logistics"
FACULTY = "faculty"

ROLES = (STUDENT, ORGANIZER, LOGISTICS, FACULTY)
ROLE_LABELS = {
    STUDENT: "Student",
    ORGANIZER: "Organizer",
    LOGISTICS: "Logistics",
    FACULTY: "Faculty",
}

# Roles that exist exactly once in the whole system (enforced by partial
# unique indexes in the database and again in services/accounts.py).
SINGLETON_ROLES = (ORGANIZER, LOGISTICS)

# --- Account status (can the person sign in?) ---------------------------
ACCOUNT_ACTIVE = "ACTIVE"
ACCOUNT_INACTIVE = "INACTIVE"
ACCOUNT_SUSPENDED = "SUSPENDED"
ACCOUNT_STATUSES = (ACCOUNT_ACTIVE, ACCOUNT_INACTIVE, ACCOUNT_SUSPENDED)

# --- Verification status (is the student a verified member?) ------------
# Kept completely separate from the account status above.
VERIFY_PENDING = "PENDING"
VERIFY_VERIFIED = "VERIFIED"
VERIFY_REJECTED = "REJECTED"
VERIFY_SUSPENDED = "SUSPENDED"
VERIFICATION_STATUSES = (VERIFY_PENDING, VERIFY_VERIFIED, VERIFY_REJECTED, VERIFY_SUSPENDED)
VERIFICATION_LABELS = {
    VERIFY_PENDING: "Verification pending",
    VERIFY_VERIFIED: "Verified member",
    VERIFY_REJECTED: "Not verified",
    VERIFY_SUSPENDED: "Suspended",
}

# --- Audit log actions ----------------------------------------------------
AUDIT_ACTIONS = {
    "student.verified": "Student verified",
    "student.rejected": "Student rejected",
    "student.correction_requested": "Profile correction requested",
    "student.suspended": "Student suspended",
    "student.reinstated": "Student reinstated",
    "student.resubmitted": "Student resubmitted profile",
    "organizer.password_set": "Organizer password changed",
    "organizer.password_reset": "Organizer password reset",
    "organizer.activated": "Organizer activated",
    "organizer.deactivated": "Organizer deactivated",
    "organizer.updated": "Organizer username/email updated",
    "logistics.password_set": "Logistics password changed",
    "logistics.password_reset": "Logistics password reset",
    "logistics.activated": "Logistics activated",
    "logistics.deactivated": "Logistics deactivated",
    "logistics.updated": "Logistics username/email updated",
}

# --- Event lifecycle ---------------------------------------------------
DRAFT = "draft"
SUBMITTED = "submitted"
APPROVED = "approved"
PUBLISHED = "published"
REJECTED = "rejected"
COMPLETED = "completed"

EVENT_STATUSES = (DRAFT, SUBMITTED, APPROVED, REJECTED, PUBLISHED, COMPLETED)
# Statuses students and the public may see.
PUBLIC_STATUSES = (PUBLISHED, COMPLETED)
STATUS_LABELS = {
    DRAFT: "Draft",
    SUBMITTED: "Pending approval",
    APPROVED: "Approved",
    PUBLISHED: "Published",
    REJECTED: "Rejected",
    COMPLETED: "Completed",
}

# --- Events ------------------------------------------------------------
CATEGORIES = (
    "Workshop",
    "Seminar",
    "Hackathon",
    "Cultural",
    "Sports",
    "Competition",
    "Career",
    "Community",
)
CATEGORY_ICONS = {
    "Workshop": "bi-tools",
    "Seminar": "bi-mic",
    "Hackathon": "bi-code-slash",
    "Cultural": "bi-music-note-beamed",
    "Sports": "bi-trophy",
    "Competition": "bi-award",
    "Career": "bi-briefcase",
    "Community": "bi-people",
}

# --- Registration / attendance ----------------------------------------
REG_CONFIRMED = "confirmed"
REG_CANCELLED = "cancelled"

# --- Logistics ---------------------------------------------------------
TASK_PENDING = "pending"
TASK_IN_PROGRESS = "in_progress"
TASK_COMPLETED = "completed"
TASK_STATUSES = (TASK_PENDING, TASK_IN_PROGRESS, TASK_COMPLETED)
TASK_LABELS = {
    TASK_PENDING: "Pending",
    TASK_IN_PROGRESS: "In progress",
    TASK_COMPLETED: "Completed",
}

# (title, area, default assignee team)
DEFAULT_TASKS = (
    ("Venue booked and prepared", "Venue", "Venue team"),
    ("Projector tested", "Equipment", "AV team"),
    ("Microphone tested", "Equipment", "AV team"),
    ("Speakers tested", "Equipment", "AV team"),
    ("Seating arranged", "Seating", "Venue team"),
    ("Refreshments confirmed", "Refreshments", "Catering team"),
    ("Registration desk set up", "Registration desk", "Desk team"),
    ("Internet connectivity checked", "Equipment", "IT team"),
    ("Power supply and extensions checked", "Equipment", "Electrical team"),
    ("Volunteers briefed", "Volunteers", "Volunteer lead"),
    ("Certificates prepared", "Certificates", "Organizer"),
)

# --- Volunteering ------------------------------------------------------
APP_PENDING = "pending"
APP_APPROVED = "approved"
APP_REJECTED = "rejected"

# --- Announcements -----------------------------------------------------
AUDIENCES = ("all", "students", "organizers", "logistics")
AUDIENCE_LABELS = {
    "all": "Everyone",
    "students": "Students",
    "organizers": "Organizers",
    "logistics": "Logistics Team",
}

# --- Achievements (code, title, description, icon) --------------------
ACHIEVEMENTS = (
    ("first_step", "First Step", "Registered for your first event.", "bi-flag"),
    ("showing_up", "Showing Up", "Checked in at an event with your QR code.", "bi-qr-code-scan"),
    ("regular", "Regular", "Attended three or more events.", "bi-calendar-check"),
    ("certified", "Certified", "Earned a certificate of participation.", "bi-patch-check"),
    ("volunteer", "Volunteer", "Approved as an event volunteer.", "bi-hand-thumbs-up"),
    ("curious_mind", "Curious Mind", "Asked the AI Event Assistant a question.", "bi-chat-square-text"),
    ("profile_ready", "Profile Ready", "Completed your student profile.", "bi-person-check"),
)

DEPARTMENTS = (
    "Computer Science & Engineering",
    "Artificial Intelligence & Data Science",
    "Electronics & Communication",
    "Mechanical Engineering",
    "Civil Engineering",
    "Management Studies",
    "Humanities",
)

# --- Student username pattern ---------------------------------------------
# firstname.lastname, lowercase letters only, optional two-digit suffix
# (01-99) added when the plain name is already taken.
USERNAME_PATTERN = r"^[a-z]{2,24}\.[a-z]{2,24}(0[1-9]|[1-9][0-9])?$"
USERNAME_EXAMPLE = "firstname.lastname"
# Staff accounts are provisioned by the hierarchy, not self-service.
STAFF_USERNAME_PATTERN = r"^[a-z][a-z0-9_]{2,29}$"

BRANCHES = (
    "B.Tech", "M.Tech", "BBA", "MBA", "B.A.", "M.A.", "B.Sc.", "M.Sc.", "Other",
)

# (value, label) pairs for <select> fields in templates
DEPARTMENT_OPTIONS = tuple((d, d) for d in DEPARTMENTS)
BRANCH_OPTIONS = tuple((b, b) for b in BRANCHES)
SEMESTER_OPTIONS = tuple((str(n), f"Semester {n}") for n in range(1, 9))
CATEGORY_OPTIONS = tuple((c, c) for c in CATEGORIES)
AUDIENCE_OPTIONS = tuple((k, AUDIENCE_LABELS[k]) for k in AUDIENCES)
TASK_STATUS_OPTIONS = tuple((k, TASK_LABELS[k]) for k in TASK_STATUSES)
