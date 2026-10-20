from datetime import timedelta

import pytest

from app import constants as C
from app.extensions import db
from app.models import Event, LogisticsTask
from app.services import events as svc
from app.services.errors import ServiceError
from app.utils import now
from tests.conftest import login, make_event


def form_data(**over):
    day = now().date() + timedelta(days=10)
    data = {
        "title": "Robotics Bootcamp", "description": "Learn to build and program a small robot.",
        "category": "Workshop", "venue": "Lab 3", "event_date": day.isoformat(),
        "start_time": "10:00", "end_time": "13:00", "capacity": "30",
        "registration_deadline": f"{(day - timedelta(days=1)).isoformat()}T09:00",
    }
    data.update(over)
    return data


def test_organizer_creates_draft_event(client, users):
    login(client, users["organizer"])
    resp = client.post("/organizer/events/new", data=form_data(action="draft"))
    assert resp.status_code == 302
    event = Event.query.filter_by(title="Robotics Bootcamp").one()
    assert event.status == C.DRAFT and event.organizer_id == users["organizer"].id


def test_create_and_submit_in_one_step(client, users):
    login(client, users["organizer"])
    client.post("/organizer/events/new", data=form_data(action="submit"))
    assert Event.query.filter_by(title="Robotics Bootcamp").one().status == C.SUBMITTED


@pytest.mark.parametrize("field,value", [
    ("title", "abc"), ("description", "short"), ("category", "Nonsense"),
    ("capacity", "0"), ("capacity", "abc"), ("end_time", "09:00"),
    ("event_date", "2001-01-01"),
])
def test_event_validation_rejects_bad_input(client, users, field, value):
    login(client, users["organizer"])
    resp = client.post("/organizer/events/new", data=form_data(**{field: value}))
    assert resp.status_code == 400
    assert Event.query.count() == 0


def test_deadline_must_be_before_event_start(client, users):
    day = now().date() + timedelta(days=10)
    login(client, users["organizer"])
    resp = client.post("/organizer/events/new",
                       data=form_data(registration_deadline=f"{day.isoformat()}T23:00"))
    assert resp.status_code == 400


def test_full_lifecycle_draft_to_published(app, users):
    event = make_event(users["organizer"])
    svc.change_status(event, C.SUBMITTED, users["organizer"])
    assert event.status == C.SUBMITTED
    svc.change_status(event, C.APPROVED, users["faculty"], "Looks good")
    assert event.status == C.APPROVED and event.reviewed_by_id == users["faculty"].id
    svc.change_status(event, C.PUBLISHED, users["organizer"])
    assert event.status == C.PUBLISHED and event.published_at is not None


def test_faculty_rejection_requires_remarks(app, users):
    event = make_event(users["organizer"], C.SUBMITTED)
    with pytest.raises(ServiceError) as err:
        svc.change_status(event, C.REJECTED, users["faculty"], "  ")
    assert err.value.code == "remarks_required"
    svc.change_status(event, C.REJECTED, users["faculty"], "Add a safety plan")
    assert event.status == C.REJECTED and event.faculty_remarks == "Add a safety plan"


def test_rejected_event_can_be_resubmitted(app, users):
    event = make_event(users["organizer"], C.REJECTED)
    svc.change_status(event, C.SUBMITTED, users["organizer"])
    assert event.status == C.SUBMITTED


@pytest.mark.parametrize("start,target", [
    (C.DRAFT, C.APPROVED), (C.DRAFT, C.PUBLISHED), (C.SUBMITTED, C.PUBLISHED),
    (C.PUBLISHED, C.APPROVED), (C.REJECTED, C.PUBLISHED), (C.APPROVED, C.REJECTED),
])
def test_illegal_transitions_are_blocked(app, users, start, target):
    event = make_event(users["organizer"], start)
    actor = users["faculty"] if target in (C.APPROVED, C.REJECTED) else users["organizer"]
    with pytest.raises(ServiceError):
        svc.change_status(event, target, actor, "remarks")
    assert event.status == start


def test_only_faculty_can_approve_and_only_owner_can_submit(app, users):
    event = make_event(users["organizer"], C.SUBMITTED)
    for role in ("student", "organizer", "logistics"):
        with pytest.raises(ServiceError) as err:
            svc.change_status(event, C.APPROVED, users[role])
        assert err.value.code == "forbidden"
    draft = make_event(users["organizer"], C.DRAFT)
    with pytest.raises(ServiceError):
        svc.change_status(draft, C.SUBMITTED, users["logistics"])
    with pytest.raises(ServiceError):
        svc.change_status(draft, C.SUBMITTED, users["faculty"])


def test_approval_creates_logistics_checklist(app, users):
    event = make_event(users["organizer"], C.SUBMITTED)
    svc.change_status(event, C.APPROVED, users["faculty"])
    assert LogisticsTask.query.filter_by(event_id=event.id).count() == len(C.DEFAULT_TASKS)
    assert event.readiness_percent == 0


def test_submitted_events_are_not_editable(app, users):
    event = make_event(users["organizer"], C.SUBMITTED)
    assert not svc.can_edit(event, users["organizer"])
    with pytest.raises(ServiceError):
        svc.update_event(event, users["organizer"], {"title": "Changed title here"})


def test_faculty_review_flow_over_http(client, users):
    event = make_event(users["organizer"], C.SUBMITTED)
    login(client, users["faculty"])
    assert client.get(f"/faculty/events/{event.id}/review").status_code == 200
    client.post(f"/faculty/events/{event.id}/decide", data={"decision": "reject", "remarks": ""})
    assert db.session.get(Event, event.id).status == C.SUBMITTED  # no remarks, no rejection
    client.post(f"/faculty/events/{event.id}/decide", data={"decision": "approve", "remarks": "OK"})
    assert db.session.get(Event, event.id).status == C.APPROVED
