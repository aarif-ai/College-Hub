# Developer manual

## 1. Architecture in one page

```
request ─► route (app/routes/<area>.py) ─► service (app/services/*.py) ─► models (app/models.py) ─► DB
              │ check role, read form        │ validate, apply rules,        
              │ call service, flash/redirect │ raise ServiceError if refused  
              ▼
        template (Jinja)  ◄── context processor adds C (constants), unread count, AI mode
```

- **Routes are thin.** They parse input, check the role and call a service.
- **Services hold the rules** and raise `ServiceError(message, code)` for expected problems. Routes show `exc.message` to the user; tests assert on `exc.code`.
- **Templates** extend `layouts/public.html` or `layouts/app.html` and use macros from `components/macros.html`.

## 2. Application factory (`app/__init__.py`)

`create_app(config_name)`: loads `.env`, picks a config class, refuses to start in production without a real `SECRET_KEY`, initialises extensions, registers blueprints, template filters, error handlers (400/403/404/500, CSRF), security headers, CLI commands, then `db.create_all()`.

## 3. Database and models

See `docs/DATABASE.md`. Notable choices: one `users` table with a validated `role`; `Registration` unique on (student, event); `Attendance.registration_id` unique; status values validated with `@validates`; counts such as `Event.registered_count` are computed properties so they can never drift from the data.

## 4. Authentication

`app/routes/auth.py` and `app/services/accounts.py`. Passwords are hashed with Werkzeug (`generate_password_hash`, scrypt) in `User.set_password`; hashes are never rendered. Sessions use Flask-Login with an id of `<user id>.<password-hash fingerprint>`, so a password change signs out other sessions and a deactivated/suspended user is signed out at once. Self-registration **always** creates a student (`accounts.register_student`); posted `role`, `verification_status` or `account_status` fields are ignored (tested). Student usernames are validated server-side against `constants.USERNAME_PATTERN` (`^[a-z]{2,24}\.[a-z]{2,24}(0[1-9]|[1-9][0-9])?$`) after lower-casing. Login accepts username or email and has an in-memory throttle; `next` redirects pass `is_safe_redirect`. Forgot-password uses `URLSafeTimedSerializer` tokens that embed a password-hash fingerprint (single use) and expire after `RESET_TOKEN_MAX_AGE`; `services/mailer.py` sends by SMTP or logs. Staff passwords set by a manager set `must_change_password`, enforced by a `before_request` hook. CSRF tokens are required on every POST (`csrf_token()` in forms, `X-CSRFToken` header for `fetch`).

## 5. Authorization

`@role_required("faculty")` (in `app/decorators.py`) wraps `login_required` and returns 403 for the wrong role. `@verified_required` renders a 403 explanation page for students who are not VERIFIED; the services check it again. The hierarchy lives in `accounts.MANAGER_OF` (Organizer is managed by Faculty, Logistics by the Organizer). Verification rules are in `services/verification.py`; every decision calls `services/audit.record`. Ownership is checked in routes/services: `_own_event()` in the organizer blueprint, `_own_registration()` in the student blueprint. State changes are checked in `services/events.py::change_status`: *who* (`_actor_may`) and *from which state* (`ALLOWED_TRANSITIONS`). `tests/test_authorization.py` loops over every role × area.

## 6. Routes

| Blueprint | Prefix | Role |
|-----------|--------|------|
| `main` | `/` | public: landing, events, verify certificate, `/healthz`; login-only: documents, notifications |
| `auth` | `/` | login, register, logout |
| `student` | `/student` | student |
| `organizer` | `/organizer` | organizer (own events only) |
| `faculty` | `/faculty` | faculty |
| `logistics` | `/logistics` | logistics |
| `api` | `/api` | JSON for the AI chat |

List them all: `flask --app wsgi routes`.

## 7. Services (`app/services/`)

| Module | Responsibility |
|--------|----------------|
| `events.py` | form validation, create/update/delete, lifecycle state machine |
| `registration.py` | register, cancel, registration ID generation |
| `qr.py` | signed token create/verify, PNG rendering |
| `attendance.py` | `record_attendance`, the single place a scan becomes attendance |
| `logistics.py` | default checklist, task updates, readiness summary |
| `documents.py` | validate/store PDFs and cover images, path-traversal guard |
| `certificates.py` | issue certificates, render PDF |
| `volunteering.py`, `announcements.py`, `achievements.py`, `notifications.py`, `analytics.py` | as named |
| `ai/` | the assistant pipeline (section 9) |

## 8. QR workflow

1. Registration creates `reg_code` (`CH-<year>-<event>-<5 random chars>`).
2. `student.qr_image` renders a PNG of `qr.make_token(reg_code)`: `"CH1." + itsdangerous.sign(reg_code)` with the app `SECRET_KEY`. A forged or edited code fails the signature.
3. The scanner page (`static/js/scanner.js`) decodes the QR with `html5-qrcode` and `POST`s `{event_id, value}` to `/logistics/scan`.
4. `attendance.record_attendance` checks in order: event exists and is published → token genuine (or typed registration ID) → registration exists → belongs to this event → confirmed → student exists → no attendance yet. It returns a status (`success`, `duplicate`, `wrong_event`, `cancelled`, `not_open`, `invalid`) and the route maps it to an HTTP code (200/409/422/400).
5. `Attendance.registration_id` is `UNIQUE`; if two scans race, the database rejects the second and the service reports `duplicate`.

The browser never decides anything. Rotating `SECRET_KEY` invalidates all issued QR codes.

## 9. AI workflow (`app/services/ai/`)

| Step | Module | What happens |
|------|--------|--------------|
| 1 Extraction | `extraction.py` | at upload, `pypdf` reads text page by page into `[[Page N]]` blocks stored in `event_documents.extracted_text` |
| 2 Processing | `processing.py` | builds labelled chunks: the official listing facts (title, venue, date, time, deadline, capacity, organizer) plus PDF text split into sentences (abbreviation-aware) |
| 3 Context | `retrieval.py` | keyword + synonym-group matching selects chunks; the question is answerable only if ≥ 60 % of its meaningful words are covered |
| 4 Request | `provider.py` | only if `AI_API_KEY` is set: sends the top chunks with a strict system prompt to Anthropic or an OpenAI-compatible API (stdlib `urllib`, no SDK) |
| 5 Validation | `validation.py` | rejects an answer if it contains a number not in the sources or if < 70 % of its words are supported |
| 6 Orchestration | `assistant.py` | refusal text when nothing is found; offline extractive answer when no key or the provider fails |

Guarantees: nothing but the listing and uploaded PDFs reaches the model; the model is told to reply `NOT_FOUND` otherwise; unsupported answers are replaced by the refusal; the key is read from the environment and never logged. Limits: matching is lexical, so unusual paraphrases may be refused (a safe failure).

## 10. Document workflow

Organizer uploads → `documents.save_document`: extension must be `pdf`, size ≤ `MAX_UPLOAD_MB`, first bytes must be `%PDF-`, filename passed through `secure_filename` and prefixed with event ID and a random token, saved under `uploads/documents/`, text extracted (unreadable or encrypted PDFs are rejected and the file removed). Downloads go through `/documents/<id>` which checks the role and resolves the path inside the upload root. Cover images are verified with Pillow and served publicly from `/media/covers/`.

## 11. Certificate workflow

`certificates.issue_certificates` (owner organizer or faculty, published event only) creates one `Certificate` per attendee that has none. `certificate_pdf` draws a landscape A4 PDF with ReportLab (name, event, date, certificate ID, signer role, QR to `/verify/<code>`). Students download only their own; `/verify/<code>` is public.

## 12. Templates and static files

- `base.html` loads fonts, Bootstrap 5.3.3, Bootstrap Icons, `css/app.css`, Tailwind CDN (prefix `tw-`, preflight off so it cannot fight Bootstrap) and `js/app.js`.
- `layouts/public.html` (top navbar + footer), `layouts/app.html` (sidebar + top bar).
- `components/macros.html`: `stat_card`, `status_badge`, `event_card`, `empty_state`, `meter`, `field`, `select_field`, `post_button`, `pager`, and more.
- `static/css/app.css` is the design system: tokens (colour, type, spacing), then components. Change colours in the `:root` block only.
- JS: `app.js` (confirm dialogs, loading buttons, copy), `assistant.js` (chat), `scanner.js` (scanner). Server text is inserted with `textContent`, never `innerHTML`.

## 13. Seed system

`app/seed.py::seed_demo_data` builds users, clubs, 8 events (one per interesting state, past/future), two official PDFs generated with ReportLab and run through the real extractor, registrations, attendance, certificates, tasks, volunteering, announcements and achievements. It is idempotent (skips if the demo faculty exists); `--reset` rebuilds. Demo usernames and the password come from `DEMO_*` settings, never from hard-coded real credentials. `flask create-faculty` creates the first Faculty account on a real deployment (password prompted).

## 14. Testing

`python -m pytest -q`. Fixtures in `tests/conftest.py` create an in-memory app and a user of every role. Files: auth, authorization, events (validation + state machine), registration, attendance (QR), logistics + certificates, AI + documents (including mocked provider answers and fabricated-answer blocking). Set `TEST_DATABASE_URL` to run against PostgreSQL on an *empty* database.

## 15. Debugging

- `flask --app wsgi run --debug` shows tracebacks and reloads on change; production shows the friendly 500 page.
- `flask --app wsgi shell` opens a Python shell with the app context.
- A page shows "Access denied": check the logged-in role and the route's `role_required`.
- A form POST returns "Session expired": the CSRF token is missing from the form.
- Assistant refuses everything: open the event's *Documents* tab; "No text found" means a scanned PDF.
- QR camera will not open: needs HTTPS or `localhost`; check the browser permission; try manual entry.
- Reset local data: stop the server, delete `instance/collegehub.db`, run `flask --app wsgi seed`. A schema change (like this version's) always needs this.
- Tests: `python -m pytest -q` (241). Note: the test fixture keeps one app context open, so tests that switch between clients clear `g._login_user` first.

## 16. Environment variables

See the table in `README.md` and the commented `.env.example`. Variables are read once at start-up in `app/config.py`.

## 17. Coding conventions

PEP 8, type hints on service functions, docstrings on modules and public functions, no business logic in templates, every POST protected by CSRF, every mutating route behind `role_required`, user-facing strings in services/routes (not scattered in templates). Run `python -m pyflakes app tests` before committing.
