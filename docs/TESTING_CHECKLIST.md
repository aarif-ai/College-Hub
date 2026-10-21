# Manual testing checklist

Start from a clean database: `flask --app wsgi seed --reset`, then `flask --app wsgi run`. Tick each line as you verify it. Record problems as GitHub issues.

## Automated tests first
- [ ] `python -m pytest -q` passes (244 tests at the time of writing)
- [ ] `python -m pyflakes app tests` prints nothing

## Public pages
- [ ] Landing page loads; *Explore events* and *Log in* buttons work
- [ ] `/events`: search, category, club and When filters work; pagination appears when > 9 events
- [ ] A draft event URL (`/events/<id>`) shows 404 to anonymous users
- [ ] Unknown URL shows the styled 404 page
- [ ] `/healthz` returns `{"status":"ok"}`

## Accounts and security
- [ ] Register: wrong username format, taken username, duplicate email, weak password and mismatched confirm are each rejected with a clear message
- [ ] `Rahul.Sharma` is stored as `rahul.sharma`; `rahul_sharma`, `rahul`, `rahul.sharma.x` are rejected
- [ ] There is no Organizer or Logistics registration page; posting `role=organizer` to `/register` creates a student
- [ ] Log in with username and with e-mail; log out for all four roles; each lands on its own dashboard
- [ ] Wrong password shows an error; 5 wrong attempts show "Too many failed attempts"
- [ ] Forgot password gives the same message for known and unknown e-mails; a reset link works once, expires, and old links stop working after use
- [ ] Change password: wrong current password refused; other sessions are signed out
- [ ] Deactivated or suspended account cannot sign in and is signed out immediately
- [ ] Student opening `/faculty/` or `/organizer/` sees the styled 403 page
- [ ] Logged out, opening `/student/` redirects to login and returns afterwards

## Hierarchy and staff accounts
- [ ] Faculty → *Organizer account*: view, change username/email, set password, reset (temporary shown once), deactivate, activate
- [ ] Organizer → *Logistics account*: same controls; Organizer cannot manage the Faculty account
- [ ] Creating a second Organizer or Logistics account is refused
- [ ] Logistics cannot open member verification, account pages or any credential page (403)
- [ ] A staff user with a manager-set password is forced to change it at the next sign-in

## Member verification
- [ ] Pending / Verified / Rejected / Suspended tabs with counts; search, department filter, pagination
- [ ] Approve, reject (reason required), request correction, suspend (reason required), reinstate; confirmation dialogs appear
- [ ] Rejected student sees the reason and can resubmit; resubmitting returns them to Pending
- [ ] History shows actor, action, reason and time
- [ ] Blue **Verified CollegeHub Member** badge only for verified students; not on pending, rejected or suspended
- [ ] Unverified student can log in, edit profile, browse events and announcements, but registration, volunteering and certificates show the verification explanation
- [ ] A student cannot change role, verification or account status by posting extra fields to the profile form

## Student
- [ ] Dashboard shows stats, upcoming events, announcements, opportunities
- [ ] Register for a published event; Registration ID and QR image appear
- [ ] Registering again is refused; after the deadline is refused; full event is refused
- [ ] Cancel a registration; QR disappears; can register again
- [ ] Another student's registration URL returns 403
- [ ] Certificates list, PDF download opens, Verify page says *Certificate verified*
- [ ] Volunteering: apply once; second apply is refused
- [ ] Profile (photo, phone, department, branch, semester, section, optional student ID, skills, interests, bio, links) saves; invalid photos are refused; completing it unlocks *Profile Ready*
- [ ] History shows registrations, attendance, certificates

## AI Event Assistant
- [ ] "When does the keynote start?" → answer with source file and page
- [ ] "Where is the venue?" → answer from *Official event listing*
- [ ] "Who is the chief guest?" and "Is there parking?" → "couldn't find… won't guess"
- [ ] Works with `AI_API_KEY` empty (badge says *AI demo mode*)
- [ ] (Optional) With a real key, answers stay inside the document

## Organizer
- [ ] Create event with invalid data: errors appear beside fields
- [ ] Save draft; edit; submit; status becomes *Pending approval*
- [ ] After approval: publish; event appears on public list
- [ ] Rejected event shows faculty remarks; edit and resubmit works
- [ ] Upload a real PDF: "Readable by AI". Upload `.txt` / a fake PDF: refused
- [ ] Registrations tab lists students; CSV export opens in a spreadsheet
- [ ] Create a volunteer role; approve and reject applications
- [ ] Mark a published event completed (refused before it starts); only then issue certificates: only checked-in verified students receive one; a second click issues none
- [ ] Assign / approve volunteers; only verified students can be assigned
- [ ] Event form saves department, faculty coordinator, eligibility, schedule, rules and contact info

## Faculty
- [ ] Pending proposals listed; review page shows details and documents
- [ ] Reject without remarks is refused; with remarks works and notifies the organizer
- [ ] Approve creates the logistics checklist
- [ ] Monitor and Report pages show registered, attended, readiness
- [ ] Publish an announcement; the right audience sees it

## Logistics and QR
- [ ] Dashboard lists approved/published events with readiness bars
- [ ] Update a task status and notes; readiness changes
- [ ] Scanner: valid QR → green; same QR again → amber duplicate; garbage → red invalid
- [ ] QR from another event → amber *Wrong event*
- [ ] Cancelled registration → amber *cancelled*
- [ ] Manual entry works with a lowercase Registration ID
- [ ] Camera opens on `localhost` (allow permission); denial shows a helpful message
- [ ] Counters (checked in / registered) update after each scan

## Responsive and accessibility
For each width: **1440 px (desktop), 1024 px (laptop), 768 px (tablet), 390 px (phone)**
- [ ] Navigation: top bar on public pages; sidebar becomes a slide-in menu on phone
- [ ] Tables scroll sideways instead of breaking the page
- [ ] Forms are usable; buttons are full width where expected
- [ ] Dashboard cards stack neatly; event cards wrap
- [ ] Scanner stacks camera above result; event detail sidebar moves below
- [ ] Tab key reaches every control; focus ring visible; "Skip to main content" works
- [ ] No text is hard to read (contrast); errors are not shown by colour alone

## Deployment
- [ ] Production start works: `APP_ENV=production SECRET_KEY=... gunicorn wsgi:app`
- [ ] Production without `SECRET_KEY` refuses to start
- [ ] Debug pages / stack traces never appear (cause an error: you see the styled 500 page)
- [ ] No `.env`, database or uploads appear in `git status`
