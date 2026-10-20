from datetime import timedelta

import pytest

from app import constants as C
from app.models import Registration
from app.services.errors import ServiceError
from app.services.registration import cancel_registration, register_student
from app.utils import now
from tests.conftest import login, make_event


def test_registration_gets_unique_id(app, users):
    event = make_event(users["organizer"], C.PUBLISHED)
    a = register_student(users["student"], event)
    b = register_student(users["student2"], event)
    assert a.reg_code != b.reg_code
    assert a.reg_code.startswith("CH-") and a.status == C.REG_CONFIRMED


def test_duplicate_registration_prevented(app, users):
    event = make_event(users["organizer"], C.PUBLISHED)
    register_student(users["student"], event)
    with pytest.raises(ServiceError) as err:
        register_student(users["student"], event)
    assert err.value.code == "duplicate"
    assert Registration.query.filter_by(event_id=event.id).count() == 1


@pytest.mark.parametrize("status", [C.DRAFT, C.SUBMITTED, C.APPROVED, C.REJECTED])
def test_cannot_register_for_unpublished_event(app, users, status):
    event = make_event(users["organizer"], status)
    with pytest.raises(ServiceError) as err:
        register_student(users["student"], event)
    assert err.value.code == "closed"


def test_cannot_register_after_deadline(app, users):
    event = make_event(users["organizer"], C.PUBLISHED,
                       registration_deadline=now() - timedelta(hours=1))
    with pytest.raises(ServiceError) as err:
        register_student(users["student"], event)
    assert "deadline" in err.value.message.lower()


def test_cannot_register_when_full(app, users):
    event = make_event(users["organizer"], C.PUBLISHED, capacity=1)
    register_student(users["student"], event)
    with pytest.raises(ServiceError) as err:
        register_student(users["student2"], event)
    assert "full" in err.value.message.lower()


def test_only_students_can_register(app, users):
    event = make_event(users["organizer"], C.PUBLISHED)
    with pytest.raises(ServiceError):
        register_student(users["organizer"], event)


def test_cancel_frees_a_seat_and_allows_reregistering(app, users):
    event = make_event(users["organizer"], C.PUBLISHED, capacity=1)
    reg = register_student(users["student"], event)
    cancel_registration(reg, users["student"])
    assert event.registered_count == 0
    again = register_student(users["student2"], event)
    assert again.is_confirmed


def test_student_cannot_cancel_someone_elses_registration(app, users):
    event = make_event(users["organizer"], C.PUBLISHED)
    reg = register_student(users["student"], event)
    with pytest.raises(ServiceError):
        cancel_registration(reg, users["student2"])


def test_register_over_http_and_view_qr(client, users):
    event = make_event(users["organizer"], C.PUBLISHED)
    login(client, users["student"])
    resp = client.post(f"/student/events/{event.id}/register")
    assert resp.status_code == 302
    reg = Registration.query.one()
    page = client.get(f"/student/registrations/{reg.id}")
    assert page.status_code == 200 and reg.reg_code.encode() in page.data
    png = client.get(f"/student/registrations/{reg.id}/qr.png")
    assert png.status_code == 200 and png.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_student_cannot_view_another_students_qr(client, users):
    event = make_event(users["organizer"], C.PUBLISHED)
    reg = register_student(users["student"], event)
    login(client, users["student2"])
    assert client.get(f"/student/registrations/{reg.id}").status_code == 403
    assert client.get(f"/student/registrations/{reg.id}/qr.png").status_code == 403
