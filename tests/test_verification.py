"""Student verification: Organizer decides, badge is server-side, restrictions apply."""
import pytest

from app import constants as C
from app.extensions import db
from app.models import AuditLog, VolunteerOpportunity
from app.services import certificates as certs
from app.services import verification as ver
from app.services.errors import ServiceError
from app.services.registration import register_student
from app.services.volunteering import apply_for_opportunity
from tests.conftest import PASSWORD, login, make_event, make_user

BADGE = "Verified CollegeHub Member"


def complete_profile(student):
    student.department = "Humanities"
    student.profile.branch, student.profile.semester = "B.A.", 3
    student.profile.phone, student.profile.bio = "+91 98000 12345", "Debate enthusiast."
    db.session.commit()


@pytest.fixture()
def pending(app, users):
    return make_user(C.STUDENT, "Pia Pending", verified=False, username="pia.pending")


def actions(student):
    return [a.action for a in AuditLog.query.filter_by(target_id=student.id).order_by(AuditLog.id)]


def test_new_students_are_active_and_pending(pending):
    assert pending.account_status == C.ACCOUNT_ACTIVE
    assert pending.verification_status == C.VERIFY_PENDING and not pending.is_verified


def test_pending_student_sees_pending_message_and_no_badge(client, pending):
    login(client, pending)
    page = client.get("/student/profile").get_data(as_text=True)
    assert "Verification Pending" in page
    assert "waiting for review by the CollegeHub Organizing Committee" in page
    assert BADGE not in page and "ch-verified" not in page


def test_organizer_approves_and_badge_appears(client, app, users, pending):
    login(client, users["organizer"])
    assert client.get("/organizer/members").status_code == 200
    resp = client.post(f"/organizer/members/{pending.id}/approve")
    assert resp.status_code == 302
    db.session.refresh(pending)
    assert pending.verification_status == C.VERIFY_VERIFIED and pending.is_verified
    assert pending.verified_at and pending.verified_by_id == users["organizer"].id
    assert actions(pending) == ["student.verified"]
    entry = AuditLog.query.one()
    assert entry.actor_id == users["organizer"].id and entry.target_id == pending.id

    student_client = app.test_client()
    from flask import g
    g.pop("_login_user", None)
    login(student_client, pending)
    page = student_client.get("/student/profile").get_data(as_text=True)
    assert BADGE in page and "ch-verified" in page and "Pia Pending" in page


def test_badge_is_rendered_only_for_verified_status(client, app, users):
    pia = make_user(C.STUDENT, "Pia Pending", verified=False, username="pia.pending")
    for status in (C.VERIFY_PENDING, C.VERIFY_REJECTED):
        pia.verification_status = status
        db.session.commit()
        assert not pia.is_verified
    login(client, users["organizer"])
    listing = client.get(f"/organizer/members/{pia.id}").get_data(as_text=True)
    assert 'aria-label="Verified CollegeHub Member"' not in listing
    pia.verification_status = C.VERIFY_VERIFIED
    db.session.commit()
    listing = client.get(f"/organizer/members/{pia.id}").get_data(as_text=True)
    assert 'aria-label="Verified CollegeHub Member"' in listing


def test_rejection_needs_a_reason_and_stores_it(client, users, pending):
    login(client, users["organizer"])
    client.post(f"/organizer/members/{pending.id}/reject", data={"reason": ""})
    db.session.refresh(pending)
    assert pending.verification_status == C.VERIFY_PENDING     # nothing happened
    client.post(f"/organizer/members/{pending.id}/reject", data={"reason": "Profile is empty."})
    db.session.refresh(pending)
    assert pending.verification_status == C.VERIFY_REJECTED
    assert pending.verification_reason == "Profile is empty."
    assert not pending.correction_requested
    entry = AuditLog.query.filter_by(action="student.rejected").one()
    assert entry.reason == "Profile is empty."


def test_student_sees_reason_corrects_and_resubmits(app, client, users, pending):
    ver.reject(pending, users["organizer"], "Please add your phone number and bio.", correction=True)
    assert pending.correction_requested
    student_client = app.test_client()
    login(student_client, pending)
    page = student_client.get("/student/profile").get_data(as_text=True)
    assert "Changes requested" in page and "Please add your phone number and bio." in page

    # incomplete profile cannot be resubmitted
    resp = student_client.post("/student/verification/resubmit")
    assert resp.status_code == 302 and "/profile/edit" in resp.headers["Location"]
    db.session.refresh(pending)
    assert pending.verification_status == C.VERIFY_REJECTED

    complete_profile(pending)
    student_client.post("/student/verification/resubmit")
    db.session.refresh(pending)
    assert pending.verification_status == C.VERIFY_PENDING
    assert pending.verification_reason is None and not pending.correction_requested
    assert actions(pending) == ["student.correction_requested", "student.resubmitted"]


def test_only_a_rejected_student_can_resubmit(app, users, pending):
    with pytest.raises(ServiceError):
        ver.resubmit(pending)                    # pending
    with pytest.raises(ServiceError):
        ver.resubmit(users["student"])           # verified


def test_organizer_can_approve_after_a_rejection(app, users, pending):
    ver.reject(pending, users["organizer"], "Not enough detail.")
    ver.approve(pending, users["organizer"])
    assert pending.is_verified


def test_suspension_blocks_login_and_reinstatement_restores_status(app, client, users):
    student = users["student"]
    assert student.is_verified
    ver.suspend(student, users["organizer"], "Misuse of event seats.")
    assert student.account_status == C.ACCOUNT_SUSPENDED
    assert student.verification_status == C.VERIFY_SUSPENDED and not student.is_verified
    resp = app.test_client().post("/login", data={"identifier": student.email, "password": PASSWORD})
    assert resp.status_code == 403
    assert AuditLog.query.filter_by(action="student.suspended").one().reason == "Misuse of event seats."
    with pytest.raises(ServiceError):
        ver.approve(student, users["organizer"])          # must reinstate first
    ver.reinstate(student, users["organizer"])
    assert student.account_status == C.ACCOUNT_ACTIVE and student.is_verified   # was verified before


def test_reinstating_a_never_verified_student_returns_to_pending(app, users, pending):
    ver.suspend(pending, users["organizer"], "Spam sign-up.")
    ver.reinstate(pending, users["organizer"])
    assert pending.verification_status == C.VERIFY_PENDING


def test_account_status_and_verification_status_are_separate(app, users, pending):
    ver.suspend(users["student"], users["organizer"], "Suspended for testing.")
    assert (users["student"].account_status, users["student"].verification_status) == ("SUSPENDED", "SUSPENDED")
    assert (pending.account_status, pending.verification_status) == ("ACTIVE", "PENDING")
    ver.reject(pending, users["organizer"], "Needs changes please.")
    assert (pending.account_status, pending.verification_status) == ("ACTIVE", "REJECTED")


# ---- who may verify ------------------------------------------------------------------------
@pytest.mark.parametrize("role", ["student", "logistics", "faculty"])
def test_only_the_organizer_can_verify(client, users, pending, role):
    login(client, users[role])
    for action in ("approve", "reject", "suspend", "reinstate", "correction"):
        resp = client.post(f"/organizer/members/{pending.id}/{action}", data={"reason": "because"})
        assert resp.status_code == 403
    assert client.get("/organizer/members").status_code == 403
    db.session.refresh(pending)
    assert pending.verification_status == C.VERIFY_PENDING


def test_service_refuses_non_organizer_actors(app, users, pending):
    for role in ("student", "logistics", "faculty"):
        with pytest.raises(ServiceError) as err:
            ver.approve(pending, users[role])
        assert err.value.code == "forbidden"


def test_student_cannot_verify_or_promote_themselves_via_profile_form(app, client, users, pending):
    login(client, pending)
    resp = client.post("/student/profile/edit", data={
        "name": "Pia Pending", "department": "Humanities", "verification_status": "VERIFIED",
        "role": "organizer", "account_status": "ACTIVE", "verified_at": "2026-01-01",
        "verified_by_id": "1", "is_verified": "1", "username": "hacker.name"})
    assert resp.status_code == 302
    db.session.refresh(pending)
    assert pending.role == C.STUDENT and pending.verification_status == C.VERIFY_PENDING
    assert pending.verified_at is None and pending.verified_by_id is None
    assert pending.username == "pia.pending" and not pending.is_verified


def test_students_cannot_hit_student_decision_urls(client, users, pending):
    login(client, pending)
    assert client.post(f"/organizer/members/{pending.id}/approve").status_code == 403


# ---- verification gates official participation ---------------------------------------------------
def test_unverified_student_cannot_register_for_events(client, app, users, pending):
    event = make_event(users["organizer"], C.PUBLISHED)
    with pytest.raises(ServiceError) as err:
        register_student(pending, event)
    assert err.value.code == "verification_required"
    login(client, pending)
    resp = client.post(f"/student/events/{event.id}/register")
    assert resp.status_code == 403
    assert "Verification" in resp.get_data(as_text=True)
    page = client.get(f"/events/{event.id}").get_data(as_text=True)
    assert "Verification required" in page and "Register for this event" not in page


def test_unverified_student_cannot_volunteer_or_open_certificates(client, users, pending):
    event = make_event(users["organizer"], C.PUBLISHED)
    opp = VolunteerOpportunity(event_id=event.id, title="Desk helper", description="Help at the desk.",
                               slots=2, created_by_id=users["organizer"].id)
    db.session.add(opp)
    db.session.commit()
    with pytest.raises(ServiceError) as err:
        apply_for_opportunity(pending, opp, "hi")
    assert err.value.code == "verification_required"
    login(client, pending)
    assert client.post(f"/student/volunteering/{opp.id}/apply").status_code == 403
    assert client.get("/student/certificates").status_code == 403


def test_unverified_student_can_still_browse_and_edit_profile(client, users, pending):
    make_event(users["organizer"], C.PUBLISHED)
    login(client, pending)
    for path in ("/student/", "/events", "/student/announcements", "/student/profile",
                 "/student/profile/edit", "/student/assistant", "/student/volunteering"):
        assert client.get(path).status_code == 200, path


def test_verified_student_can_register_and_volunteer(client, users):
    event = make_event(users["organizer"], C.PUBLISHED)
    login(client, users["student"])
    assert client.post(f"/student/events/{event.id}/register").status_code == 302


def test_certificates_skip_students_who_lost_verification(app, users):
    event = make_event(users["organizer"], C.PUBLISHED)
    from app.services import qr
    from app.services.attendance import record_attendance
    for key in ("student", "student2"):
        reg = register_student(users[key], event)
        record_attendance(qr.make_token(reg.reg_code), event.id, users["logistics"])
    event.status = C.COMPLETED
    ver.suspend(users["student2"], users["organizer"], "Suspended after the event.")
    assert certs.issue_certificates(event, users["organizer"]) == 1


# ---- member management UI --------------------------------------------------------------------
def test_member_lists_search_filter_and_paginate(client, app, users):
    for n in range(12):
        make_user(C.STUDENT, f"Bulk Person{chr(97+n)}", verified=False, username=f"bulk.person{chr(97+n)}")
    login(client, users["organizer"])
    first = client.get("/organizer/members?status=PENDING").get_data(as_text=True)
    assert "Page" not in first and "Next" in first          # 12 pending -> 2 pages
    second = client.get("/organizer/members?status=PENDING&page=2").get_data(as_text=True)
    assert "Bulk Person" in second
    found = client.get("/organizer/members?status=PENDING&q=personc").get_data(as_text=True)
    assert "Bulk Personc" in found and "Bulk Persona" not in found
    verified = client.get("/organizer/members?status=VERIFIED").get_data(as_text=True)
    assert users["student"].name in verified
    junk = client.get("/organizer/members?status=NONSENSE&page=-4").status_code
    assert junk == 200
    dept = client.get("/organizer/members?status=PENDING&department=Civil%20Engineering").get_data(as_text=True)
    assert "No students here" in dept


def test_member_detail_shows_history(client, users, pending):
    ver.reject(pending, users["organizer"], "Photo missing, please upload.")
    login(client, users["organizer"])
    page = client.get(f"/organizer/members/{pending.id}").get_data(as_text=True)
    assert "Student rejected" in page and "Photo missing, please upload." in page
    assert client.get(f"/organizer/members/{users['faculty'].id}").status_code == 404
