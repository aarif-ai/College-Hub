"""Realistic demo data for CollegeHub.

Run with ``flask seed`` (add ``--reset`` to wipe the database first).
All accounts use the ``demo.collegehub.test`` domain and the password from
``DEMO_PASSWORD``. They are clearly fictional and flagged ``is_demo``.
"""
import io
from datetime import datetime, timedelta

from flask import current_app
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from app import constants as C
from app.extensions import db
from app.models import (
    Announcement, Attendance, Certificate, Club, Event, EventDocument,
    Registration, StudentProfile, User, VolunteerApplication,
    VolunteerOpportunity,
)
from app.services import achievements, audit
from app.services.ai.extraction import extract_pdf_text
from app.services.certificates import generate_cert_code
from app.services.logistics import create_default_tasks
from app.services.registration import generate_reg_code
from app.utils import now

DOMAIN = "demo.collegehub.test"

# The hierarchy: ONE faculty mentor -> ONE organizer -> ONE logistics account.
# Usernames/emails come from configuration (see .env.example); the password is
# DEMO_PASSWORD. Nothing here is a real credential.
FACULTY_NAME = ("Dr. Farhana Qureshi", "Computer Science & Engineering")
ORGANIZER_NAME = ("CollegeHub Organizing Committee", "Artificial Intelligence & Data Science")
LOGISTICS_NAME = ("CollegeHub Logistics Team", "Mechanical Engineering")

# (full name, username, department, branch, semester, skills, interests, state)
# state: V verified, P pending, R rejected (with reason), S suspended
STUDENTS = [
    ("Aisha Khan", "aisha.khan", "Artificial Intelligence & Data Science", "B.Tech", 5, "Python, statistics", "AI, writing", "V"),
    ("Rayyan Dar", "rayyan.dar", "Computer Science & Engineering", "B.Tech", 3, "Flask, robotics", "Hackathons, robotics", "V"),
    ("Mehak Lone", "mehak.lone", "Electronics & Communication", "B.Tech", 5, "Arduino, C", "IoT, photography", "V"),
    ("Umar Sheikh", "umar.sheikh", "Mechanical Engineering", "B.Tech", 7, "CAD, thermodynamics", "Cricket, CAD", "V"),
    ("Hiba Mir", "hiba.mir", "Humanities", "B.A.", 1, "Public speaking", "Debate, poetry", "V"),
    ("Tariq Ganai", "tariq.ganai", "Civil Engineering", "B.Tech", 3, "Surveying", "Surveying, football", "V"),
    ("Insha Nabi", "insha.nabi", "Management Studies", "BBA", 3, "Marketing", "Entrepreneurship", "V"),
    ("Faizan Yousuf", "faizan.yousuf", "Computer Science & Engineering", "B.Tech", 5, "JavaScript, Git", "Web, open source", "V"),
    ("Naveed Rashid", "naveed.rashid", "Artificial Intelligence & Data Science", "B.Tech", 3, "Machine learning", "ML, chess", "P"),
    ("Student One", "student.one", None, None, None, None, None, "P"),
    ("Sumaira Hamid", "sumaira.hamid", "Electronics & Communication", "B.Tech", 7, "Embedded systems", "Embedded systems", "R"),
    ("Irfan Peer", "irfan.peer", "Mechanical Engineering", "B.Tech", 5, "Workshop practice", "Football", "S"),
]

CLUBS = [
    ("Coding & AI Society", "Technical", "bi-cpu", "Workshops, hackathons and study groups on code and AI."),
    ("Debate & Communication Club", "Cultural", "bi-mic", "Debates, public speaking and critical thinking."),
    ("Entrepreneurship Cell", "Career", "bi-lightbulb", "Startup talks, pitch nights and mentoring."),
    ("Sports Council", "Sports", "bi-trophy", "Inter-department tournaments and fitness drives."),
    ("Cultural Forum", "Cultural", "bi-music-note-beamed", "Music, poetry and the annual cultural fest."),
    ("Community Service Wing", "Community", "bi-heart", "Campus clean-up, blood donation and outreach."),
]


def _doc_pdf(title: str, sections: list[tuple[str, str]]) -> bytes:
    """Build a small official-information PDF with real, selectable text."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 60
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, y, title)
    y -= 34
    for heading, body in sections:
        if y < 130:
            pdf.showPage()
            y = height - 60
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(50, y, heading)
        y -= 18
        pdf.setFont("Helvetica", 10.5)
        for line in simpleSplit(body, "Helvetica", 10.5, width - 100):
            pdf.drawString(50, y, line)
            y -= 14
        y -= 12
    pdf.save()
    return buffer.getvalue()


def _attach_pdf(event, uploader, filename, title, sections):
    import uuid
    from app.services.documents import absolute_path
    stored = f"event{event.id}_{uuid.uuid4().hex[:10]}_{filename}"
    relative = f"documents/{stored}"
    target = absolute_path(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = _doc_pdf(title, sections)
    target.write_bytes(data)
    text, pages = extract_pdf_text(target)
    db.session.add(EventDocument(
        event_id=event.id, uploader_id=uploader.id, original_filename=filename,
        stored_filename=stored, file_path=relative, size_bytes=len(data),
        page_count=pages, extracted_text=text,
    ))


def seed_demo_data() -> str:
    cfg = current_app.config
    if User.query.filter_by(username=cfg["DEMO_FACULTY_USERNAME"]).first():
        return "Demo data already present. Use `flask seed --reset` to rebuild it."

    password = cfg["DEMO_PASSWORD"]
    today = now().date()

    def staff(role, name, department, username, email):
        user = User(name=name, username=username, email=email, role=role,
                    department=department, is_demo=True)
        user.set_password(password)
        db.session.add(user)
        return user

    farhana = staff(C.FACULTY, FACULTY_NAME[0], FACULTY_NAME[1],
                    cfg["DEMO_FACULTY_USERNAME"], cfg["DEMO_FACULTY_EMAIL"])
    org = staff(C.ORGANIZER, ORGANIZER_NAME[0], ORGANIZER_NAME[1],
                cfg["DEMO_ORGANIZER_USERNAME"], cfg["DEMO_ORGANIZER_EMAIL"])
    logi = staff(C.LOGISTICS, LOGISTICS_NAME[0], LOGISTICS_NAME[1],
                 cfg["DEMO_LOGISTICS_USERNAME"], cfg["DEMO_LOGISTICS_EMAIL"])
    db.session.flush()

    students = []
    rejected_reason = ("Your profile has no phone number and the bio is empty. Please complete "
                       "both so we can confirm you are a CollegeHub member, then resubmit.")
    suspended_reason = "Repeated no-shows after registering for seats at capacity-limited events."
    for index, (name, username, dept, branch, sem, skills, interests, state) in enumerate(STUDENTS, 1):
        student = User(name=name, username=username, email=f"{username.replace('.', '_')}@{DOMAIN}",
                       role=C.STUDENT, department=dept, is_demo=True)
        student.set_password(password)
        complete = state != "R" and dept is not None
        student.profile = StudentProfile(
            branch=branch, semester=sem, skills=skills, interests=interests,
            phone=f"+91 98000 {10000 + index}" if complete else None,
            section="A" if complete else None,
            enrollment_no=f"2024-DEMO-{index:03d}" if index % 3 else None,
            bio=("Demo student account for the CollegeHub showcase." if complete else None),
            github_url=f"https://github.com/demo-{username.replace('.', '-')}" if index == 1 else None)
        verified_at = now() - timedelta(days=30 - index)
        if state in ("V", "S"):
            student.verified_at, student.verified_by_id = verified_at, org.id
        if state == "V":
            student.verification_status = C.VERIFY_VERIFIED
            student.verification_updated_at = verified_at
        elif state == "R":
            student.verification_status = C.VERIFY_REJECTED
            student.correction_requested = True
            student.verification_reason = rejected_reason
            student.verification_updated_at = now() - timedelta(days=2)
        elif state == "S":
            student.account_status = C.ACCOUNT_SUSPENDED
            student.verification_status = C.VERIFY_SUSPENDED
            student.verification_reason = suspended_reason
            student.verification_updated_at = now() - timedelta(days=3)
        db.session.add(student)
        students.append((student, state))
    db.session.flush()
    verified = [s_ for s_, state in students if state == "V"]
    students = [s_ for s_, _state in students]

    # Audit trail that matches the states above.
    def log(actor, action, target, reason=None, days_ago=0):
        entry = audit.record(actor, action, target, reason)
        entry.created_at = now() - timedelta(days=days_ago)
    log(farhana, "organizer.password_set", org, days_ago=40)
    log(org, "logistics.password_set", logi, days_ago=39)
    for index, student in enumerate(verified, 1):
        log(org, "student.verified", student, days_ago=30 - index)
    log(org, "student.correction_requested", students[10], rejected_reason, days_ago=2)
    log(org, "student.verified", students[11], days_ago=25)
    log(org, "student.suspended", students[11], suspended_reason, days_ago=3)

    achievements.seed_achievements()
    clubs = []
    for name, category, icon, description in CLUBS:
        club = Club(name=name, category=category, icon=icon, description=description)
        db.session.add(club)
        clubs.append(club)
    db.session.flush()
    ai_club, debate, ecell, sports, cultural, service = clubs
    # Event contact line and coordinator are shared by the demo events.
    coordinator = farhana.name
    contact = "collegehub.org@demo.collegehub.test"

    def make_event(**kw):
        kw.setdefault("faculty_coordinator", coordinator)
        kw.setdefault("contact_info", contact)
        kw.setdefault("eligibility", "Open to all verified CollegeHub members.")
        event = Event(**kw)
        db.session.add(event)
        db.session.flush()
        return event

    def at(day_offset, hour, minute=0):
        d = today + timedelta(days=day_offset)
        return d, datetime.combine(d, datetime.min.time()).replace(hour=hour, minute=minute)

    # --- 1. Past, published event with attendance and certificates ----------
    d, _ = at(-12, 10)
    past = make_event(
        title="Intro to Machine Learning Workshop",
        description=("A hands-on introduction to machine learning for first and second year students. "
                     "We build a simple classifier in Python, learn how to evaluate a model and "
                     "discuss where ML is used in real projects."),
        category="Workshop", venue="Computer Lab 2, North Campus", event_date=d,
        start_time=datetime(2000, 1, 1, 10, 0).time(), end_time=datetime(2000, 1, 1, 13, 0).time(),
        capacity=40, registration_deadline=datetime.combine(d, datetime.min.time()) - timedelta(days=1),
        status=C.COMPLETED, organizer_id=org.id, club_id=ai_club.id,
        reviewed_by_id=farhana.id, reviewed_at=now() - timedelta(days=20),
        submitted_at=now() - timedelta(days=22), published_at=now() - timedelta(days=18),
        completed_at=now() - timedelta(days=11),
        faculty_remarks="Approved. Please keep the lab capacity within limits.")

    # --- 2. Upcoming flagship event with a rich official PDF ----------------
    d, deadline = at(9, 9, 30)
    ai_summit = make_event(
        title="AI for Everyone: Campus Tech Summit",
        description=("A one-day summit with talks, a live demo session and a student project showcase "
                     "on how artificial intelligence is changing study, work and research. Open to all "
                     "departments."),
        category="Seminar", venue="Main Auditorium, North Campus", event_date=d,
        start_time=datetime(2000, 1, 1, 10, 0).time(), end_time=datetime(2000, 1, 1, 16, 30).time(),
        capacity=120, registration_deadline=deadline - timedelta(hours=12),
        status=C.PUBLISHED, organizer_id=org.id, club_id=ai_club.id,
        reviewed_by_id=farhana.id, reviewed_at=now() - timedelta(days=6),
        submitted_at=now() - timedelta(days=8), published_at=now() - timedelta(days=5),
        faculty_remarks="Approved. Coordinate seating with logistics.")

    ai_summit.department = "Artificial Intelligence & Data Science"
    ai_summit.schedule = ("09:30 Check-in | 10:00 Opening | 10:30 Keynote | 12:00 Live demos | "
                          "14:30 Project showcase | 16:00 Closing")
    ai_summit.rules = "Carry your college ID. Recording the keynote is not permitted."

    # --- 3. Upcoming hackathon ----------------------------------------------
    d, deadline = at(16, 9)
    hackathon = make_event(
        title="CodeSprint 24-Hour Hackathon",
        description=("Teams of up to four build a working prototype in 24 hours around the theme "
                     "'Technology for Campus Life'. Mentors, meals and prizes included."),
        category="Hackathon", venue="Innovation Lab, Block C", event_date=d,
        start_time=datetime(2000, 1, 1, 9, 0).time(), end_time=datetime(2000, 1, 1, 18, 0).time(),
        capacity=60, registration_deadline=deadline - timedelta(days=1),
        status=C.PUBLISHED, organizer_id=org.id, club_id=ai_club.id,
        reviewed_by_id=farhana.id, reviewed_at=now() - timedelta(days=4),
        submitted_at=now() - timedelta(days=6), published_at=now() - timedelta(days=3))

    # --- 4. Upcoming debate (published) ------------------------------------
    d, deadline = at(5, 14)
    debate_ev = make_event(
        title="Inter-Department Debate Championship",
        description=("Teams from every department compete in a parliamentary-style debate on "
                     "technology and society. Judges are faculty from the Humanities department."),
        category="Competition", venue="Seminar Hall, Block B", event_date=d,
        start_time=datetime(2000, 1, 1, 14, 0).time(), end_time=datetime(2000, 1, 1, 17, 30).time(),
        capacity=80, registration_deadline=deadline - timedelta(days=1),
        status=C.PUBLISHED, organizer_id=org.id, club_id=debate.id,
        reviewed_by_id=farhana.id, reviewed_at=now() - timedelta(days=3),
        submitted_at=now() - timedelta(days=5), published_at=now() - timedelta(days=2))

    # --- 5. Approved but not yet published ---------------------------------
    d, deadline = at(24, 11)
    startup = make_event(
        title="Startup Pitch Night",
        description=("Student founders pitch ideas to a panel of local entrepreneurs and mentors. "
                     "Audience members vote for the people's choice award."),
        category="Career", venue="Conference Room, Admin Block", event_date=d,
        start_time=datetime(2000, 1, 1, 17, 0).time(), end_time=datetime(2000, 1, 1, 19, 30).time(),
        capacity=70, registration_deadline=deadline,
        status=C.APPROVED, organizer_id=org.id, club_id=ecell.id,
        reviewed_by_id=farhana.id, reviewed_at=now() - timedelta(days=1),
        submitted_at=now() - timedelta(days=3), faculty_remarks="Approved. Publish when the panel is confirmed.")
    create_default_tasks(startup)

    # --- 6. Submitted, awaiting faculty ------------------------------------
    d, deadline = at(30, 10)
    make_event(
        title="Kashmir Cultural Evening",
        description=("An evening of poetry, folk music and student performances celebrating local "
                     "culture, with refreshments for all attendees."),
        category="Cultural", venue="Open Air Theatre", event_date=d,
        start_time=datetime(2000, 1, 1, 16, 30).time(), end_time=datetime(2000, 1, 1, 20, 0).time(),
        capacity=300, registration_deadline=deadline,
        status=C.SUBMITTED, organizer_id=org.id, club_id=cultural.id,
        submitted_at=now() - timedelta(hours=20))

    # --- 7. Draft and 8. Rejected -------------------------------------------
    d, deadline = at(40, 9)
    make_event(
        title="Inter-Department Cricket Tournament",
        description="Knockout cricket tournament between departments, played over two weekends.",
        category="Sports", venue="University Cricket Ground", event_date=d,
        start_time=datetime(2000, 1, 1, 9, 0).time(), end_time=datetime(2000, 1, 1, 17, 0).time(),
        capacity=200, registration_deadline=deadline, status=C.DRAFT,
        organizer_id=org.id, club_id=sports.id)
    d, deadline = at(20, 10)
    make_event(
        title="Overnight Campus Camping Trip",
        description="A two-day camping trip for students to a hill site outside the city.",
        category="Community", venue="Off campus site", event_date=d,
        start_time=datetime(2000, 1, 1, 8, 0).time(), end_time=datetime(2000, 1, 1, 18, 0).time(),
        capacity=40, registration_deadline=deadline, status=C.REJECTED,
        organizer_id=org.id, club_id=service.id, reviewed_by_id=farhana.id,
        reviewed_at=now() - timedelta(days=2), submitted_at=now() - timedelta(days=4),
        faculty_remarks="Off-campus overnight travel needs a safety plan and guardian consent forms. Please resubmit with these attached.")

    # --- Official PDFs (for the AI assistant demo) ----------------------------
    _attach_pdf(ai_summit, org, "AI-Summit-Official-Information.pdf",
                "AI for Everyone: Campus Tech Summit - Official Information", [
        ("Schedule", "Registration and check-in opens at 9:30 AM. The opening session begins at 10:00 AM. "
                     "The keynote talk on responsible AI starts at 10:30 AM. The live demo session runs from "
                     "12:00 PM to 1:00 PM. The student project showcase begins at 2:30 PM. The closing "
                     "ceremony is at 4:00 PM and the event ends at 4:30 PM."),
        ("Venue and entry", "The summit is held in the Main Auditorium, North Campus. Students must show "
                            "their CollegeHub QR code at the registration desk. Entry closes at 10:15 AM."),
        ("Lunch and refreshments", "Lunch is provided free of charge to all registered attendees from "
                                   "1:00 PM to 2:00 PM in the auditorium foyer. Tea and snacks are available "
                                   "during the morning break."),
        ("Speakers", "The keynote speaker is Dr. Farhana Qureshi from the Department of Computer Science. "
                     "The live demo is led by the Coding and AI Society."),
        ("Certificates", "Every attendee whose attendance is recorded by QR scan receives a certificate of "
                         "participation within one week of the event."),
        ("Rules", "Photography is allowed in the auditorium but recording of the keynote is not permitted. "
                  "Students should carry their college identity card. Laptops are optional."),
        ("Contact", "For questions contact the CollegeHub Organizing Committee through CollegeHub."),
    ])
    _attach_pdf(hackathon, org, "CodeSprint-Rules-and-Prizes.pdf",
                "CodeSprint 24-Hour Hackathon - Rules and Prizes", [
        ("Teams", "Teams must have between two and four members. Solo participation is not allowed."),
        ("Timeline", "The hackathon starts at 9:00 AM. Hacking begins at 10:00 AM and project submission "
                     "closes at 10:00 AM the next day. Final presentations begin at 12:00 PM."),
        ("Prizes", "The first prize is 20000 rupees, the second prize is 10000 rupees and the third prize "
                   "is 5000 rupees. All finalists receive certificates."),
        ("What to bring", "Bring your own laptop, charger and extension board. Internet access and meals "
                          "are provided by the organizers."),
    ])

    # --- Registrations, attendance, certificates ----------------------------
    def register(student, event, attended=False, minutes_after_start=5):
        reg = Registration(reg_code=generate_reg_code(event.id), student_id=student.id,
                           event_id=event.id,
                           created_at=min(now(), event.start_datetime) - timedelta(days=2))
        db.session.add(reg)
        db.session.flush()
        if attended:
            db.session.add(Attendance(
                registration_id=reg.id, event_id=event.id, student_id=student.id,
                scanned_by_id=logi.id, method="qr",
                scanned_at=event.start_datetime + timedelta(minutes=minutes_after_start)))
        return reg

    for i, student in enumerate(verified[:8]):
        register(student, past, attended=i < 6, minutes_after_start=3 + i)
    for student in verified[:7]:
        register(student, ai_summit)
    for student in verified[2:6]:
        register(student, hackathon)
    for student in verified[:3]:
        register(student, debate_ev)
    db.session.flush()

    for student in verified[:6]:
        db.session.add(Certificate(
            cert_code=generate_cert_code(), student_id=student.id, event_id=past.id,
            issued_by_id=org.id))
        db.session.flush()

    # --- Logistics tasks (approved/published events) -----------------------------
    for event, done in ((past, 11), (ai_summit, 7), (hackathon, 4), (debate_ev, 2)):
        create_default_tasks(event)
        db.session.flush()
        for index, task in enumerate(event.tasks):
            if index < done:
                task.status = C.TASK_COMPLETED
            elif index == done:
                task.status = C.TASK_IN_PROGRESS
                task.notes = "Being arranged today."
            task.updated_by_id = logi.id
    startup.tasks[0].status = C.TASK_IN_PROGRESS

    # --- Volunteering ------------------------------------------------------------
    opp1 = VolunteerOpportunity(event_id=ai_summit.id, title="Registration desk helper",
        description="Check students in at the entrance, guide them to seats and help the logistics team.",
        slots=4, created_by_id=org.id)
    opp2 = VolunteerOpportunity(event_id=ai_summit.id, title="Demo session assistant",
        description="Help presenters set up equipment and manage the audience Q&A microphones.",
        slots=3, created_by_id=org.id)
    opp3 = VolunteerOpportunity(event_id=hackathon.id, title="Hackathon mentor",
        description="Guide teams on design, code quality and presenting their final project.",
        slots=6, created_by_id=org.id)
    db.session.add_all([opp1, opp2, opp3])
    db.session.flush()
    db.session.add_all([
        VolunteerApplication(opportunity_id=opp1.id, student_id=verified[0].id,
            message="I helped at the ML workshop and would love to help again.",
            status=C.APP_APPROVED, decided_at=now(), decided_by_id=org.id,
            assignment="Registration desk - check-in"),
        VolunteerApplication(opportunity_id=opp1.id, student_id=verified[1].id,
            message="Happy to help at the desk.", status=C.APP_PENDING),
        VolunteerApplication(opportunity_id=opp3.id, student_id=verified[7].id,
            message="Can mentor web projects.", status=C.APP_PENDING),
    ])

    # --- Announcements ----------------------------------------------------------------
    db.session.add_all([
        Announcement(title="Welcome to CollegeHub",
            message="CollegeHub is now the single place for events, registration, QR attendance and certificates. Update your profile to unlock achievements.",
            audience="all", author_id=farhana.id, created_at=now() - timedelta(days=10)),
        Announcement(title="Summit seating plan",
            message="Seating for the AI Summit is first come, first served. Please arrive before 10:15 AM with your QR code ready.",
            event_id=ai_summit.id, audience="students", author_id=org.id, created_at=now() - timedelta(days=1)),
        Announcement(title="Logistics briefing",
            message="All logistics volunteers: briefing for upcoming events is on Friday at 4 PM in the Admin Block.",
            audience="logistics", author_id=farhana.id, created_at=now() - timedelta(days=2)),
    ])

    # --- Achievements & notifications -----------------------------------------------------
    db.session.flush()
    for student in students:
        achievements.evaluate_student(student)
    db.session.commit()

    return (f"Seeded 1 faculty, 1 organizer, 1 logistics, {len(students)} students "
            f"({len(verified)} verified, 2 pending, 1 rejected, 1 suspended), "
            f"{Event.query.count()} events. Password for every demo account: {password}")
