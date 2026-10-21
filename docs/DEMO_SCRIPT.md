# Final demo script (about 10 minutes)

## Before you start (5 minutes earlier)

```bash
flask --app wsgi seed --reset
flask --app wsgi run
```

Open two browser windows: a normal one (student) and a private one (staff). Keep a phone ready with the student's QR page. If using a hosted site, open it once to wake it. Password for all demo accounts: your `DEMO_PASSWORD` (default `CollegeHub@2026`). Accounts: faculty `collegehub_faculty`, organizer `collegehub_org`, logistics `collegehub_logistics`, students `aisha.khan` (verified), `naveed.rashid` (pending), `sumaira.hamid` (rejected), `irfan.peer` (suspended).

Seed highlights: **"AI for Everyone: Campus Tech Summit"** (published, 120 seats, official PDF), **"CodeSprint Hackathon"** and **"Debate Championship"** (published), **"Startup Pitch Night"** (approved), **"Kashmir Cultural Evening"** (waiting for faculty), a draft and a rejected event, and a past workshop with attendance and certificates.

## Script

| # | Show | Say / do | Role |
|---|------|----------|------|
| 1 | **Landing page** | "CollegeHub is one platform from proposal to certificate, with a verified member community." Scroll quickly. | – |
| 2 | **Registration rules** | *Create account*: show the `firstname.lastname` format and example. Type `Rahul_Sharma` → clear error. Type `aisha.khan` → "already taken, try aisha.khan01". Register `demo.student` with a password. | Student |
| 3 | **Unverified experience** | New student lands on the dashboard with a "verification pending" banner. Browse events; press **Register** → professional explanation, not an error page. Open *Profile*: Edit Profile, Change Password, Verification Status buttons. Fill and save the profile. | Student |
| 4 | **Organizer verifies** | Private window: log in as `collegehub_org` → *Member verification* → Pending → open the new student → **Approve** (confirm dialog). Show **Reject** needing a reason and **Request correction**. | Organizer |
| 5 | **Blue badge** | Student window: refresh. Blue **Verified CollegeHub Member** badge appears on the profile and header. | Student |
| 6 | **Hierarchy** | Log in as `collegehub_faculty` → *Organizer account*: show status, change password, reset (one-time temporary password), deactivate/activate. Then as the Organizer → *Logistics account*: same controls. Point out Logistics has no member-verification menu. | Faculty, Organizer |
| 7 | **Student registers** | As `aisha.khan` (verified): open the Summit, **Register**; show Registration ID + QR. | Student |
| 8 | **AI answerable / refuses** | *AI Event Assistant* → "When does the keynote start?" (cited) then "Who is the chief guest?" ("I couldn't find that… I won't guess"). | Student |
| 9 | **Logistics scanning** | `collegehub_logistics` → Summit → **Open QR scanner** → green **Checked in**; scan again → amber duplicate; `garbage` → red invalid. | Logistics |
| 10 | **Faculty approval** | `collegehub_faculty` → *Event proposals* → *Kashmir Cultural Evening* → **Approve** (reject needs remarks). | Faculty |
| 11 | **Volunteers** | Student applies to a volunteer role; Organizer approves/assigns; student sees *Approved*. | Student, Organizer |
| 12 | **Completion and certificate** | Organizer: published event → **Mark completed** (only after it started) → **Issue certificates**. Student `aisha.khan`: *Certificates* → PDF → **Verify**. | Organizer, Student |
| 13 | **Forgot password** | Login page → *Forgot password* → enter an e-mail → generic message. (Dev only: the reset link shows when `DEMO_SHOW_RESET_LINK=1`.) Set a new password; the old link no longer works. | Student |
| 14 | **Suspended / rejected** | Log in as `irfan.peer` (suspended: cannot sign in) and `sumaira.hamid` (rejected: sees the correction reason and **Resubmit**). | Student |
| 15 | **Audit log** | Organizer member detail → *History*: actor, action, reason, time. | Organizer |
| 16 | **Tests** | Terminal: `python -m pytest -q` → "244 passed" (run it before the demo to be sure of the current number). | – |
| 17 | **GitHub evidence** | Show real Issues, branches, merged pull requests, Contributors. Only show what actually exists. | – |

## Questions to expect

- *How do you stop fake or duplicate QR codes?* Signed token (forgery fails) + server checks + `UNIQUE` constraint on attendance.
- *Does the AI ever make things up?* It only sees the official listing and uploaded PDFs, is told to reply NOT_FOUND otherwise, and its answer is checked against those texts. With no API key it quotes the sources directly.
- *Why four roles, no admin?* Faculty is the institutional oversight role. Faculty manage the one Organizer account, and the Organizer manages the one Logistics account; students register themselves and are verified by the Organizer.
- *Can a student fake the blue badge or change their role?* No. The badge is computed on the server from `verification_status`; profile forms ignore those fields; tests cover this.
- *Can there be two Organizers?* No. A partial unique index makes a second Organizer row impossible in the database.
- *What is not done yet?* See "Known limitations" in the README.

## If something goes wrong

- Camera will not open → use **Manual entry** with the Registration ID.
- Site slow on free hosting → it was asleep; wait a minute and say so.
- Wrong state in the data → `flask --app wsgi seed --reset`.
