# Five-day plan (solo)

Author: **Aarif Mushtaq**. The repository already contains a working version of every feature. Use the five days to **understand, run, review, improve and present it as your own project**. Tick a box only when you have really done it.

Each day ends with a commit pushed on a feature branch and a merged pull request (see `docs/GITHUB_MANUAL.md`).

## Day 1: Foundation
- [ ] Clone, create a virtual environment, install requirements, copy `.env.example` to `.env`, set `SECRET_KEY`
- [ ] `flask --app wsgi seed --reset`, then log in as every role (README section 12)
- [ ] Read `docs/DEVELOPER_MANUAL.md` and `docs/ARCHITECTURE.md`; be able to explain the app factory, config, models and `role_required`
- [ ] Create the GitHub repository, push the skeleton, protect `main`
- [ ] Review the design tokens at the top of `app/static/css/app.css`; check the layout on desktop and phone

## Day 2: Accounts and the event lifecycle
- [ ] Walk through registration, the `firstname.lastname` username rule, login, forgot and change password
- [ ] Walk through member verification as the Organizer; explain the two statuses (account and verification)
- [ ] Walk through Faculty → Organizer and Organizer → Logistics account management
- [ ] Read `services/events.py`: validation and the DRAFT → SUBMITTED → APPROVED → PUBLISHED → COMPLETED transitions
- [ ] Open a pull request for the day's work

## Day 3: Registration, QR, attendance, logistics
- [ ] Registration rules (duplicate, deadline, capacity, verification), QR signing, `record_attendance`
- [ ] Try forged, duplicate, wrong-event and cancelled scans
- [ ] Logistics checklist, readiness percentage, scanner page with the manual fallback
- [ ] Rehearse register → show QR → scan → duplicate warning on a real phone

## Day 4: AI, volunteering, certificates, tests
- [ ] AI pipeline: extraction, retrieval, validation, offline mode; ask one answerable and one unanswerable question per seeded event
- [ ] Volunteer opportunities and Organizer assignment; certificates only after an event is COMPLETED
- [ ] `python -m pyflakes app tests` and `python -m pytest -q`
- [ ] Walk through `docs/TESTING_CHECKLIST.md`; log bugs as GitHub issues and fix them

## Day 5: Documentation, deployment, demo
- [ ] Update README, user manual and screenshots with what you really see
- [ ] Deploy (`docs/DEPLOYMENT_MANUAL.md`) or prepare a safe local run
- [ ] Rehearse `docs/DEMO_SCRIPT.md` twice with timing
- [ ] Complete `docs/SUBMISSION_CHECKLIST.md`; tag the release (`git tag -a v1.0 -m "CollegeHub final"`)
- [ ] Prepare answers for "why this design?" for every module

Shared hot spots (`app.css`, `macros.html`, `models.py`, `constants.py`): change them in small, focused commits.
