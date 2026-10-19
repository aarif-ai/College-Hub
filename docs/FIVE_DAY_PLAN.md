# Five-day plan and file ownership

> The five days follow the stages in the project brief (foundation, core events, registration/QR/logistics, AI/volunteering/certificates/announcements, integration/testing/docs/demo). The CollegeHub roadmap document itself was not available when this plan was written, so check the tasks below against it and adjust names or order if the roadmap differs.

The repository already contains a working first version of every feature. **Use the five days to understand, run, review, improve and demonstrate it as your own project**: each person works through their area, makes real changes with real commits, and presents what they own. Do not copy this plan's checkboxes as finished commits; tick them when you have genuinely done them.

## Team and areas

| Member | Branch | Area |
|--------|--------|------|
| **Aarif** | `feature/aarif-backend` | Backend, database, security, AI assistant, QR, certificates, tests |
| **Abrar** | `feature/abrar-frontend` | Design system, shared templates, public pages, student experience |
| **Mishar** | `feature/mishar-organizer` | Organizer experience, logistics experience, volunteering |
| **Hameem** | `feature/hameem-faculty` | Faculty experience, announcements, analytics, documentation |

> **Update:** the account hierarchy (Faculty → Organizer → Logistics), student self-registration, member verification, password management, audit log and the COMPLETED event state were added afterwards. Aarif owns the services and tests for them; Abrar the auth/profile templates; Mishar the member-verification and Logistics-account pages; Hameem the Organizer-account page and these docs.

## File ownership map

Edit only your own files directly. For a file you do not own, ask the owner or open a small PR they review.

| Owner | Files |
|-------|-------|
| **Aarif** | `app/__init__.py`, `app/config.py`, `app/constants.py`, `app/extensions.py`, `app/models.py`, `app/decorators.py`, `app/utils.py`, `app/cli.py`, `app/seed.py`, `app/routes/auth.py`, `app/routes/main.py`, `app/routes/api.py`, `app/services/{errors,events,registration,qr,attendance,documents,certificates,notifications,achievements,accounts,verification,audit,throttle,mailer}.py`, `app/services/ai/*`, `tests/*`, `wsgi.py`, `requirements.txt`, `.env.example`, `.gitignore`, `.github/workflows/*` |
| **Abrar** | `app/static/css/app.css`, `app/static/js/app.js`, `app/static/js/assistant.js`, `app/static/img/*`, `app/templates/base.html`, `app/templates/layouts/*`, `app/templates/partials/*`, `app/templates/components/macros.html`, `app/templates/public/*`, `app/templates/auth/*`, `app/templates/errors/*`, `app/templates/shared/*`, `app/templates/student/*`, `app/routes/student.py` |
| **Mishar** | `app/routes/organizer.py` (member verification, Logistics account), `app/templates/organizer/*`, `app/routes/logistics.py`, `app/templates/logistics/*`, `app/static/js/scanner.js`, `app/services/logistics.py`, `app/services/volunteering.py` |
| **Hameem** | `app/routes/faculty.py` (Organizer account), `app/templates/faculty/*`, `app/services/announcements.py`, `app/services/analytics.py`, `README.md`, `docs/*`, `.github/ISSUE_TEMPLATE/*`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/CODEOWNERS` |

Shared hot spots (`app.css`, `macros.html`, `models.py`, `constants.py`): keep changes small, merge `main` into your branch daily, and announce them in the group chat.

## Day 1: Foundation

**Goal**: everyone can run the project, and the skeleton is understood.

- All: clone, create a virtual environment, install, copy `.env.example`, run `flask --app wsgi seed`, log in as each role, read `docs/DEVELOPER_MANUAL.md`.
- Aarif: explain the application factory, config, models and `role_required`; create the GitHub repo, protect `main`, enable the CI workflow.
- Abrar: review the design system tokens in `app.css`; adjust brand colours/typography if the team wants; check base layout and navigation on desktop and phone.
- Mishar: walk through the organizer event form and logistics checklist; list gaps as GitHub issues.
- Hameem: set up the issue labels and PR template; start the document set; walk through the faculty review page.
- **End of day**: everyone has pushed one commit on their branch; five issues are open.

## Day 2: Core event system

**Goal**: the proposal → approval → publication flow is solid.

- Aarif: review `services/events.py` (validation, transitions); add tests for any rule you change; check permission checks on every organizer/faculty route.
- Abrar: polish landing, event discovery (search/filter/pagination), event detail, empty states.
- Mishar: organizer dashboard, event create/edit/submit/withdraw/publish, cover image upload, status messages.
- Hameem: faculty dashboard, proposal review, approve/reject with remarks, monitor page.
- **End of day**: demo the full lifecycle with seeded data; open PRs, review each other's.

## Day 3: Registration, QR, attendance and logistics

**Goal**: the door-to-door story works reliably.

- Aarif: registration rules (duplicate, deadline, capacity), QR signing, `record_attendance`; try forged, duplicate, wrong-event and cancelled scans.
- Abrar: student registration page and QR display, "My registrations", responsive checks on a phone.
- Mishar: logistics dashboard and checklist, readiness percentage, scanner page (camera + manual fallback, clear success/duplicate/invalid states).
- Hameem: readiness view for faculty, event report page, participation monitoring.
- **End of day**: rehearse "register → show QR → scan → duplicate warning" on a real phone.

## Day 4: AI, volunteering, certificates, announcements

**Goal**: the signature features are trustworthy.

- Aarif: AI pipeline (extraction, retrieval, validation, offline mode), certificates PDF; write extra refusal tests with questions your audience might ask.
- Abrar: AI chat UI, certificates page, profile/achievements, announcements page.
- Mishar: PDF upload for events, volunteer opportunities and approvals, certificate issuing tab.
- Hameem: announcements (faculty and organizer), analytics wording, clubs page; start the user manual screenshots.
- **End of day**: ask the assistant one answerable and one unanswerable question for each seeded event.

## Day 5: Integration, testing, documentation, demo

- Morning: merge all branches into `main` through PRs; run `python -m pytest -q`; walk through `docs/TESTING_CHECKLIST.md` together on a clean database (`flask --app wsgi seed --reset`).
- Midday: fix what the checklist finds; update README, user manual and screenshots; deploy (local is safest) and rehearse `docs/DEMO_SCRIPT.md` twice with timings.
- Afternoon: complete `docs/SUBMISSION_CHECKLIST.md`; tag the release (`git tag v1.0`); prepare answers for "why this design?" for the part you own.

## Presentation split (suggestion, 10 minutes)

Abrar: landing, student journey (2 min) → Mishar: organizer + logistics + scanner (3 min) → Aarif: QR validation, AI grounding, security, tests (3 min) → Hameem: faculty oversight, analytics, GitHub evidence (2 min).
