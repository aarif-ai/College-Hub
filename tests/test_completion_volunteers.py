"""COMPLETED lifecycle state, certificate rules and volunteer assignment."""
import pytest

from app import constants as C
from app.extensions import db
from app.models import Certificate, VolunteerApplication, VolunteerOpportunity
from app.services import certificates as certs
from app.services import events as svc
from app.services import qr, volunteering
from app.services.attendance import NOT_OPEN, record_attendance
from app.services.errors import ServiceError
from app.services.registration import register_student
from tests.conftest import login, make_event


def test_event_statuses_match_the_spec():
    assert set(C.EVENT_STATUSES) == {"draft", "submitted", "approved", "rejected", "published", "completed"}


def test_organizer_and_faculty_can_complete_a_started_published_event(app, users):
    for actor in ("organizer", "faculty"):
        event = make_event(users["organizer"], C.PUBLISHED, days_ahead=-1)
        svc.change_status(event, C.COMPLETED, users[actor])
        assert event.status == C.COMPLETED and event.completed_at


def test_completion_rules(app, users):
    future = make_event(users["organizer"], C.PUBLISHED, days_ahead=5)
    with pytest.raises(ServiceError) as err:
        svc.change_status(future, C.COMPLETED, users["organizer"])
    assert err.value.code == "invalid_state"                    # has not started
    for status in (C.DRAFT, C.SUBMITTED, C.APPROVED, C.REJECTED):
        event = make_event(users["organizer"], status, days_ahead=-1)
        with pytest.raises(ServiceError):
            svc.change_status(event, C.COMPLETED, users["organizer"])
    past = make_event(users["organizer"], C.PUBLISHED, days_ahead=-1)
    for role in ("student", "logistics"):
        with pytest.raises(ServiceError) as err:
            svc.change_status(past, C.COMPLETED, users[role])
        assert err.value.code == "forbidden"
    svc.change_status(past, C.COMPLETED, users["organizer"])
    with pytest.raises(ServiceError):
        svc.change_status(past, C.PUBLISHED, users["faculty"])   # completed is final


def test_complete_route_and_permissions(client, users):
    event = make_event(users["organizer"], C.PUBLISHED, days_ahead=-1)
    login(client, users["logistics"])
    assert client.post(f"/organizer/events/{event.id}/complete").status_code == 403
    client.post("/logout")
    login(client, users["organizer"])
    assert client.post(f"/organizer/events/{event.id}/complete").status_code == 302
    db.session.refresh(event)
    assert event.status == C.COMPLETED


def _attended(users, event):
    reg = register_student(users["student"], event)
    record_attendance(qr.make_token(reg.reg_code), event.id, users["logistics"])


def test_certificates_need_a_completed_event(app, users):
    event = make_event(users["organizer"], C.PUBLISHED)
    _attended(users, event)
    with pytest.raises(ServiceError) as err:
        certs.issue_certificates(event, users["organizer"])
    assert err.value.code == "invalid_state"
    assert Certificate.query.count() == 0
    event.status = C.COMPLETED
    assert certs.issue_certificates(event, users["organizer"]) == 1


def test_certificate_route_blocked_until_completed(client, users):
    event = make_event(users["organizer"], C.PUBLISHED)
    _attended(users, event)
    login(client, users["organizer"])
    client.post(f"/organizer/events/{event.id}/certificates")
    assert Certificate.query.count() == 0


def test_attendance_closes_when_event_is_completed(app, users):
    event = make_event(users["organizer"], C.PUBLISHED)
    reg = register_student(users["student"], event)
    event.status = C.COMPLETED
    db.session.commit()
    assert record_attendance(qr.make_token(reg.reg_code), event.id, users["logistics"])["status"] == NOT_OPEN


def test_completed_events_stay_visible_but_closed_for_registration(client, users):
    event = make_event(users["organizer"], C.COMPLETED, days_ahead=-3, title="Finished Workshop")
    assert client.get(f"/events/{event.id}").status_code == 200
    assert "Finished Workshop" in client.get("/events?when=all").get_data(as_text=True)
    with pytest.raises(ServiceError):
        register_student(users["student"], event)


# ---- volunteer assignment -----------------------------------------------------------------
@pytest.fixture()
def application(app, users):
    event = make_event(users["organizer"], C.PUBLISHED)
    opp = VolunteerOpportunity(event_id=event.id, title="Desk helper", description="Help at the desk.",
                               slots=2, created_by_id=users["organizer"].id)
    db.session.add(opp)
    db.session.commit()
    return volunteering.apply_for_opportunity(users["student"], opp, "I can help")


def test_organizer_approves_and_assigns_a_responsibility(app, users, application):
    volunteering.decide_application(application, users["organizer"], "approve", "Registration desk")
    assert application.status == C.APP_APPROVED and application.assignment == "Registration desk"
    volunteering.assign_volunteer(application, users["organizer"], "Stage coordination")
    assert application.assignment == "Stage coordination"


def test_default_assignment_is_the_role_title(app, users, application):
    volunteering.decide_application(application, users["organizer"], "approve")
    assert application.assignment == "Desk helper"


def test_assignment_needs_approval_and_the_organizer(app, users, application):
    with pytest.raises(ServiceError) as err:
        volunteering.assign_volunteer(application, users["organizer"], "Stage team")
    assert err.value.code == "invalid_state"
    volunteering.decide_application(application, users["organizer"], "approve")
    for role in ("student", "logistics", "faculty"):
        with pytest.raises(ServiceError):
            volunteering.assign_volunteer(application, users[role], "Stage team")
    with pytest.raises(ServiceError):
        volunteering.assign_volunteer(application, users["organizer"], "x")


def test_assign_route(client, users, application):
    volunteering.decide_application(application, users["organizer"], "approve")
    login(client, users["logistics"])
    assert client.post(f"/organizer/applications/{application.id}/assign",
                       data={"assignment": "Hijack"}).status_code == 403
    client.post("/logout")
    login(client, users["organizer"])
    client.post(f"/organizer/applications/{application.id}/assign", data={"assignment": "Hospitality desk"})
    assert db.session.get(VolunteerApplication, application.id).assignment == "Hospitality desk"
    page = client.get(f"/organizer/events/{application.opportunity.event_id}?tab=volunteers").get_data(as_text=True)
    assert "Hospitality desk" in page


def test_logistics_account_is_not_involved_in_volunteer_assignment(app, users, application):
    volunteering.decide_application(application, users["organizer"], "approve")
    with pytest.raises(ServiceError):
        volunteering.decide_application(application, users["logistics"], "reject")
