# Architecture

## Layers

```
Browser ──► Routes (app/routes/*) ──► Services (app/services/*) ──► Models ──► SQLite / PostgreSQL
            thin: parse, authorise,    all business rules,           constraints are the last
            render                     raise ServiceError            line of defence
```

Blueprints: `main`, `auth`, `student`, `organizer`, `faculty`, `logistics`, `api`.

## Roles and hierarchy

```
Faculty Mentor ──manages──► the ONE Organizer ──manages──► the ONE Logistics
                                   │ verifies
                                   ▼
                              Students (self-registered)
```

| Capability | Student | Organizer | Logistics | Faculty |
|------------|:------:|:---------:|:---------:|:-------:|
| Register own account | yes | no | no | no |
| Verify / reject / suspend students | no | **yes** | no | no |
| Manage Organizer credentials and status | no | no | no | **yes** |
| Manage Logistics credentials and status | no | **yes** | no | no |
| Propose and manage own events | no | yes | no | no |
| Approve / reject proposals | no | no | no | yes |
| Mark event completed | no | owner | no | yes |
| Issue certificates | no | owner | no | yes |
| Assign volunteers | no | yes | no | no |
| Scan QR, manage checklist | no | no | yes | no |
| Register, volunteer, certificates | **verified only** | – | – | – |

Faculty accounts exist only through `flask create-faculty`. Authorization is checked in three places: `role_required` on routes, `verified_required` for student actions, and again inside the services.

## Authentication

- Passwords: Werkzeug scrypt hashes. Plaintext is never stored or logged; hashes are never rendered or returned.
- Session id = `<user id>.<fingerprint of the password hash>`. Changing a password signs out every other session; inactive or suspended accounts are signed out on their next request.
- Staff passwords set or reset by a manager set `must_change_password`; `before_request` then redirects to *Change password* until it is done.
- Forgot password (students): generic response whether or not the account exists; signed `itsdangerous` token that expires (`RESET_TOKEN_MAX_AGE`) and dies as soon as the password changes; throttled.
- Login throttling, CSRF, safe redirects, security headers.

## Two statuses

`account_status` (ACTIVE / INACTIVE / SUSPENDED) controls sign-in. `verification_status` (PENDING / VERIFIED / REJECTED / SUSPENDED) controls the student's standing. The blue badge is computed by `User.is_verified` on the server; no form field can set it.

```
PENDING ──approve──► VERIFIED
PENDING ──reject (reason, optional "needs correction")──► REJECTED ──resubmit──► PENDING
REJECTED ──approve──► VERIFIED
any ──suspend (reason)──► SUSPENDED ──reinstate──► VERIFIED (if it was) or PENDING
```

Every decision writes an `audit_logs` row (actor, target, action, reason, time).

## Event lifecycle

`DRAFT → SUBMITTED → APPROVED → PUBLISHED → COMPLETED`, or `SUBMITTED → REJECTED → (edit) → SUBMITTED`. Attendance scanning works only while PUBLISHED. Certificates require COMPLETED and a recorded attendance of a verified student.

## Data integrity

Unique username and email; CHECK constraints for roles and statuses; partial unique indexes for the single Organizer and Logistics; unique (student, event) registration; unique attendance per registration. Services catch `IntegrityError` and turn races into friendly messages.

## AI assistant

Retrieval over the official event listing and uploaded PDFs; answers cite file and page; replies "I couldn't find that" instead of guessing; offline extractive mode without an API key. See `docs/DEVELOPER_MANUAL.md`.
