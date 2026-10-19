# Database guide

SQLAlchemy models live in `app/models.py`. SQLite is used locally; the same models run on PostgreSQL (tested on PostgreSQL 16).

## Entity relationships

```
User ─┬─< Event (organizer_id)              Event ─┬─< EventDocument
      ├─< Event (reviewed_by_id)                   ├─< Registration ──1 Attendance
      ├─1 StudentProfile                           ├─< LogisticsTask
      ├─< Notification                             ├─< VolunteerOpportunity ─< VolunteerApplication >─ User
      └─< UserAchievement >─ Achievement           ├─< Announcement
Club ─< Event                                      └─< Certificate >─ User (student)
```

## Tables

| Table | Purpose | Key constraints |
|-------|---------|-----------------|
| `users` | All four roles in one table (`role` column) | `username` and `email` unique; `role`, `account_status` and `verification_status` validated by CHECK constraints; a student must have a verification status, staff must not; **partial unique indexes allow only one Organizer and one Logistics row** |
| `student_profiles` | Student details: photo, phone, department, branch, semester, section, optional student ID, skills, interests, bio, links | one per user (`user_id` unique); `enrollment_no` optional, unique when present |
| `audit_logs` | Who did what to whom, when and why | actor, target, action, reason, timestamp; written for verification decisions and staff account changes |
| `clubs` | Communities that host events | `name` unique |
| `events` | The event and its lifecycle `status` | index on (`status`, `event_date`); status validated |
| `event_documents` | Uploaded official PDFs | `stored_filename` unique; `extracted_text` holds the PDF text with `[[Page N]]` markers |
| `registrations` | A student's registration | **unique (`student_id`, `event_id`)**; `reg_code` unique |
| `attendances` | A recorded check-in | **`registration_id` unique**, so a second check-in is impossible at database level |
| `logistics_tasks` | Event-day checklist | status: pending / in_progress / completed |
| `volunteer_opportunities` / `volunteer_applications` | Volunteer roles and applications | unique (`opportunity_id`, `student_id`) |
| `certificates` | Issued certificates | unique (`student_id`, `event_id`); `cert_code` unique |
| `announcements` | Messages with an audience | audience: all / students / organizers / logistics |
| `notifications` | In-app notifications | per user, `is_read` |
| `achievements` / `user_achievements` | Achievement definitions and awards | unique (`user_id`, `achievement_id`) |

## Users: two separate statuses

| Column | Values | Meaning |
|--------|--------|---------|
| `account_status` | `ACTIVE`, `INACTIVE`, `SUSPENDED` | May this account sign in? Inactive/suspended users are signed out immediately |
| `verification_status` | `PENDING`, `VERIFIED`, `REJECTED`, `SUSPENDED` (students only) | Is this student a Verified CollegeHub Member? |

Other user columns: `password_hash` (scrypt, never shown or logged), `must_change_password`, `verification_reason`, `verification_correction`, `verified_at`, `verified_by_id`, `is_demo`.

The "exactly one Organizer / Logistics" rule is enforced by the database, not only by code:

```
CREATE UNIQUE INDEX uq_users_single_organizer ON users (role) WHERE role = 'organizer';
CREATE UNIQUE INDEX uq_users_single_logistics ON users (role) WHERE role = 'logistics';
```

(Partial unique indexes work on SQLite and PostgreSQL.) A second insert fails even if two requests race.

Event `status` values: `DRAFT`, `SUBMITTED`, `APPROVED`, `REJECTED`, `PUBLISHED`, `COMPLETED`. Events also store department, faculty coordinator, eligibility, schedule, rules and contact details.

## Cascades

Deleting an **event** deletes its documents, registrations, attendance, tasks, opportunities, certificates and announcements (`cascade="all, delete-orphan"`). Deleting a **user** deletes their profile, notifications and achievements. In practice organizers can only delete *draft* events, which have none of these children.

## Timestamps

All timestamps are naive datetimes in college time (`APP_TIMEZONE`, default `Asia/Kolkata`) produced by `app.utils.now()`. Using one convention avoids mixing timezone-aware and naive values in comparisons such as "is the deadline past?".

## Migrating to PostgreSQL

1. Create an empty database and set `DATABASE_URL=postgresql://user:password@host/dbname` (the legacy `postgres://` prefix is rewritten automatically).
2. Start the app once. Tables are created on startup (`db.create_all()`), or run `flask --app wsgi init-db`.
3. Optionally load demo data with `flask --app wsgi seed`.

`create_all()` does not change existing tables, so this version needs a fresh database (`flask --app wsgi seed --reset` or delete `instance/collegehub.db`). If you later alter a model on a database that holds real data, add Flask-Migrate (Alembic). It was left out to keep the project understandable for a first database course.
