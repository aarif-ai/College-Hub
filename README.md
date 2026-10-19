# CollegeHub

**A College Event, Student Engagement, Operations and AI Platform.**

CollegeHub manages the complete life of a campus event: proposal, faculty approval, publication, registration, QR attendance, logistics, participation and certificates. It also connects students with volunteering, achievements and announcements, and includes a **document-grounded AI Event Assistant** that never guesses.

> Built with Flask, Jinja2, Bootstrap 5, Tailwind CSS (layout utilities), custom CSS and vanilla JavaScript. No React, no TypeScript, no Docker.

---

## 1. The problem

Most campus events run on WhatsApp groups, paper forms and spreadsheets. Proposals are not tracked, attendance is on paper and can be faked, logistics are forgotten until the morning of the event, certificates take weeks, and students keep asking the same questions ("what time does it start?").

## 2. The solution

One platform with exactly four roles, each with a focused workspace:

| Role | Purpose |
|------|---------|
| **Student** | Discover events, register, show a personal QR code, ask the AI assistant, collect certificates and achievements, volunteer |
| **Organizer** (one account) | Verifies students, proposes and manages events, assigns volunteers, issues certificates, manages the Logistics account |
| **Logistics Team** (one account) | Work the event-day checklist, track readiness, scan QR codes at the door |
| **Faculty Mentor** | Institutional oversight: manages the Organizer account, approves or rejects proposals, monitors events, publishes announcements |

**Hierarchy:** Faculty Mentor → the one Organizer account → the one Logistics account. Students register themselves. Faculty is the institutional oversight role; there is no fifth "admin" role and no Organizer registration page.

## 3. Features

- **Accounts and hierarchy**: students self-register with a `firstname.lastname` username; Faculty create/reset/activate/deactivate the one Organizer account; the Organizer does the same for the one Logistics account. The database enforces "exactly one" with partial unique indexes.
- **Member verification**: the Organizer approves, rejects (with reason), requests corrections or suspends students; history is kept in an audit log. Verified students get the blue **Verified CollegeHub Member** badge, decided only on the server. Unverified students can browse and edit their profile but cannot register, volunteer or get certificates.
- **Password management**: change password for every role, secure expiring forgot-password links for students, staff passwords set or reset by their manager (forced change at next sign-in).
- **Event lifecycle**: Draft → Submitted → Approved/Rejected → Published → **Completed**. Certificates are issued only after completion, only to verified attendees. Every transition is checked on the server (who may do it, and from which state). Events carry department, faculty coordinator, eligibility, schedule, rules and contact info.
- **Registration**: unique registration ID (e.g. `CH-2026-004-7K2QX`), duplicate, deadline, capacity and unpublished-event protection, cancellation.
- **QR attendance**: each registration gets a *signed* QR token. The scanner sends the text to the server, which checks that the token is genuine, the registration exists and belongs to this event, is confirmed, and has no earlier check-in. A database `UNIQUE` constraint makes duplicate attendance impossible even under a race.
- **AI Event Assistant**: answers only from the official event listing and uploaded PDFs, cites the source file and page, and says "I couldn't find that" instead of guessing. Works with no API key (offline demo mode).
- **Logistics**: default checklist (venue, projector, microphone, speakers, seating, refreshments, registration desk, internet, power, volunteers, certificates) with a readiness percentage.
- **Certificates**: PDF certificates with a certificate ID and a QR code that opens a public verification page.
- **Volunteering, announcements, achievements, notifications, analytics** for each role.
- **Security**: hashed passwords, CSRF protection, role-based access on every route, safe uploads, login throttling, safe redirects, security headers, no stack traces shown to users.

## 4. Technology stack

| Layer | Choice |
|-------|--------|
| Backend | Python 3.11+, Flask 3, Flask-SQLAlchemy, Flask-Login, Flask-WTF (CSRF) |
| Database | SQLite (local demo), PostgreSQL-ready (tested on PostgreSQL 16) |
| Frontend | Jinja2, HTML5, Bootstrap 5.3, Bootstrap Icons, Tailwind CSS (CDN, `tw-` prefix), custom CSS design system, vanilla JavaScript |
| QR | `qrcode` (generate), `html5-qrcode` (browser camera scan) |
| PDF | `reportlab` (certificates), `pypdf` (text extraction) |
| AI | Optional provider via environment variables (Anthropic or any OpenAI-compatible API) |
| Config | `python-dotenv`, environment variables |
| Tests | `pytest` |

## 5. Architecture

```
Browser ──► Flask routes (app/routes/*) ──► Services (app/services/*) ──► SQLAlchemy models ──► SQLite / PostgreSQL
              │  thin: parse input,           │  all business rules,
              │  check role, render           │  validation and permissions
              ▼
        Jinja templates (app/templates) + static CSS/JS (app/static)
```

Routes stay thin. Rules such as "who may approve" or "is this scan valid" live in services, so they are unit-tested without a browser. See `docs/DEVELOPER_MANUAL.md`.

## 6. Folder structure

```
collegehub/
├── app/
│   ├── __init__.py          # application factory, error handlers, security headers
│   ├── config.py            # configuration from environment variables
│   ├── constants.py         # roles, statuses, categories, default checklist
│   ├── extensions.py        # db, login manager, CSRF
│   ├── models.py            # all database models
│   ├── decorators.py        # role_required, verified_required
│   ├── utils.py             # time helpers, safe redirects, template filters
│   ├── cli.py               # `flask init-db`, `flask seed`, `flask create-faculty`
│   ├── seed.py              # realistic demo data
│   ├── routes/              # main, auth, student, organizer, faculty, logistics, api
│   ├── services/            # events, registration, qr, attendance, logistics, documents,
│   │   └── ai/              #   certificates, volunteering, announcements, analytics,
│   │                        #   accounts, verification, audit, throttle, mailer, ...
│   │                        # ai/: extraction, processing, retrieval, provider, validation, assistant
│   ├── templates/           # layouts, partials, components (macros), one folder per role
│   └── static/              # css/app.css (design system), js/, img/
├── tests/                   # pytest suite
├── docs/                    # manuals, plan, demo script, checklists
├── .github/                 # CI workflow, issue and PR templates, CODEOWNERS
├── uploads/                 # runtime uploads (git-ignored)
├── wsgi.py                  # production entry point
├── requirements.txt
└── .env.example
```

## 7. Installation

```bash
git clone <your-repo-url> collegehub
cd collegehub
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`psycopg2-binary` is included for PostgreSQL. If it fails to install on your machine and you only use SQLite, you can remove that line.

## 8. Environment configuration

```bash
cp .env.example .env               # Windows: copy .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # paste into SECRET_KEY
```

| Variable | Meaning |
|----------|---------|
| `APP_ENV` | `development`, `production` or `testing` |
| `SECRET_KEY` | Required in production. Signs sessions and QR tokens |
| `DATABASE_URL` | Empty = SQLite file in `instance/`. Or `postgresql://user:pass@host/db` |
| `UPLOAD_FOLDER`, `MAX_UPLOAD_MB` | Where PDFs and covers go, and the size limit |
| `AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL`, `AI_BASE_URL` | Optional. Leave `AI_API_KEY` empty for offline demo mode |
| `DEMO_PASSWORD` | Password given to all seeded demo accounts (default `CollegeHub@2026`; change it for any public deployment) |
| `DEMO_FACULTY_USERNAME`, `DEMO_ORGANIZER_USERNAME`, `DEMO_LOGISTICS_USERNAME` | Optional overrides of the seeded staff usernames |
| `RESET_TOKEN_MAX_AGE` | Seconds a password-reset link stays valid (default 3600) |
| `DEMO_SHOW_RESET_LINK` | `1` shows the reset link on screen. **Development only, insecure.** Otherwise the link is e-mailed (SMTP) or written to the server log |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM` | Optional SMTP settings for reset e-mails |

Never commit `.env`. It is in `.gitignore`.

## 9. Database setup

Tables are created automatically on first start. To create them explicitly:

```bash
flask --app wsgi init-db
```

There are no migrations. After pulling a version that changes the schema (this one does: `username`, `account_status`, `verification_status`, audit log, partial unique indexes), run `flask --app wsgi seed --reset` on a demo database, or delete `instance/collegehub.db`.

On a real deployment there is no seeded Faculty account. Create the first one from the command line (the password is prompted, never stored in source code):

```bash
flask --app wsgi create-faculty --username dr_example --email faculty@your-college.example --name "Dr. Example"
```

The Faculty Mentor then creates the Organizer account from **Organizer account** in the sidebar, and the Organizer creates the Logistics account.

## 10. Seed instructions

```bash
flask --app wsgi seed            # adds demo data (does nothing if already seeded)
flask --app wsgi seed --reset    # wipes the database first, then seeds
```

The seed creates **1 faculty, 1 organizer, 1 logistics** account and 12 students in the four verification states (8 verified, 2 pending, 1 rejected with a correction reason, 1 suspended), 6 clubs, **8 events across the lifecycle** (including a completed one), registrations, attendance, logistics checklists, volunteer opportunities and applications, certificates, announcements, achievements, an audit trail and two official PDFs for the AI demo.

## 11. Run instructions

```bash
flask --app wsgi run --debug
```

Open <http://127.0.0.1:5000>. The QR **camera** works on `localhost` or HTTPS only (browser rule). Manual entry of the registration ID is always available as a fallback.

## 12. Demo accounts

All demo accounts are fictional, use the reserved `demo.collegehub.test` domain and share the password in `DEMO_PASSWORD` (default `CollegeHub@2026`). **Change `DEMO_PASSWORD` before seeding any public deployment.** Nothing here is a real credential.

| Role | Username (log in with username or e-mail) |
|------|----------|
| Faculty Mentor | `collegehub_faculty` |
| Organizer | `collegehub_org` |
| Logistics | `collegehub_logistics` |
| Student, verified | `aisha.khan`, `rayyan.dar`, `mehak.lone`, `umar.sheikh`, `hiba.mir`, `tariq.ganai`, `insha.nabi`, `faizan.yousuf` |
| Student, pending | `naveed.rashid`, `student.one` |
| Student, rejected (correction requested) | `sumaira.hamid` |
| Student, suspended | `irfan.peer` |

Student e-mails look like `aisha_khan@demo.collegehub.test`.

## 13. Testing

```bash
python -m pytest -q                         # 241 tests, in-memory SQLite
TEST_DATABASE_URL=postgresql://... python -m pytest -q   # same tests on PostgreSQL (use an empty database)
```

See `docs/TESTING_CHECKLIST.md` for the manual checklist.

## 14. Deployment

See `docs/DEPLOYMENT_MANUAL.md`: local deployment, Render (free web service) with a Neon free PostgreSQL database, and the limits of each. Short version: start command `gunicorn wsgi:app`, set `SECRET_KEY`, `APP_ENV=production`, `DATABASE_URL`.

## 15. GitHub workflow

Work on feature branches, open pull requests into a protected `main`, get one review, then merge. See `docs/GITHUB_MANUAL.md`.

## 16. Team members

| Member | Area | Branch |
|--------|------|--------|
| Aarif | Backend, database, AI, QR, certificates | `feature/aarif-backend` |
| Abrar | Frontend, design system, student experience | `feature/abrar-frontend` |
| Mishar | Organizer and logistics experience | `feature/mishar-organizer` |
| Hameem | Faculty, announcements, analytics, documentation | `feature/hameem-faculty` |

File ownership is in `docs/FIVE_DAY_PLAN.md`.

## 17. Known limitations and future scope

**Limitations (honest list)**
- The offline AI mode is *extractive*: it quotes the best matching official sentences using keyword and synonym matching. It does not understand paraphrase. With an API key the model reads the same retrieved text, and its answer is still checked against that text.
- Scanned PDFs without a text layer cannot be read by the assistant (the upload page warns the organizer).
- The login and password-reset throttles are in memory (per server process).
- There are no database migrations; a schema change needs a re-seed (demo) or Alembic (real data).
- Usernames are lower-cased before validation, so `Rahul.Sharma` is accepted as `rahul.sharma`.
- Reset links are e-mailed only if SMTP is configured; otherwise they are written to the server log. The on-screen link is a development switch.
- The Faculty account is created from the command line only; there is no Faculty self-service.
- Staff passwords set or reset by a manager are temporary: the holder must change them at the next sign-in.
- Verification rests on the Organizer's judgement of the profile; there is no automatic check against a college registry (by design).
- Tailwind is loaded from its CDN for layout utilities; for a production site, replace it with a Tailwind CLI build.
- On free hosting the uploaded PDFs and cover images are lost when the server restarts (see the deployment manual). Extracted PDF text is stored in the database, so the assistant keeps working.

**Future scope**: email notifications, bulk certificate templates, event feedback forms, waitlists, calendar export, a Tailwind build step, semantic search for the assistant, and object storage for uploads.
