import pytest

from app import constants as C
from app.models import Attendance
from app.services import qr
from app.services.attendance import (
    CANCELLED, DUPLICATE, INVALID, NOT_OPEN, SUCCESS, WRONG_EVENT, record_attendance,
)
from app.services.registration import cancel_registration, register_student
from tests.conftest import login, make_event


@pytest.fixture()
def setup(app, users):
    event = make_event(users["organizer"], C.PUBLISHED)
    reg = register_student(users["student"], event)
    return event, reg, users["logistics"]


def test_valid_qr_records_attendance(app, setup, users):
    event, reg, scanner = setup
    result = record_attendance(qr.make_token(reg.reg_code), event.id, scanner)
    assert result["status"] == SUCCESS and result["ok"]
    assert result["student_name"] == users["student"].name
    att = Attendance.query.one()
    assert att.student_id == users["student"].id and att.scanned_by_id == scanner.id


def test_duplicate_scan_is_rejected(app, setup):
    event, reg, scanner = setup
    token = qr.make_token(reg.reg_code)
    assert record_attendance(token, event.id, scanner)["status"] == SUCCESS
    again = record_attendance(token, event.id, scanner)
    assert again["status"] == DUPLICATE and "already" in again["message"].lower()
    assert Attendance.query.count() == 1


@pytest.mark.parametrize("value", ["", "garbage", "CH1.notarealtoken", "CH-2026-001-ZZZZZ", "x" * 600])
def test_invalid_values_are_rejected(app, setup, value):
    event, _reg, scanner = setup
    assert record_attendance(value, event.id, scanner)["status"] == INVALID
    assert Attendance.query.count() == 0


def test_forged_token_signature_is_rejected(app, setup):
    event, reg, scanner = setup
    token = qr.make_token(reg.reg_code)
    forged = token[:-3] + ("AAA" if not token.endswith("AAA") else "BBB")
    assert record_attendance(forged, event.id, scanner)["status"] == INVALID


def test_qr_for_another_event_is_rejected(app, setup, users):
    event, reg, scanner = setup
    other = make_event(users["organizer"], C.PUBLISHED, title="Second Event Here")
    result = record_attendance(qr.make_token(reg.reg_code), other.id, scanner)
    assert result["status"] == WRONG_EVENT
    assert Attendance.query.count() == 0


def test_cancelled_registration_is_rejected(app, setup, users):
    event, reg, scanner = setup
    cancel_registration(reg, users["student"])
    assert record_attendance(qr.make_token(reg.reg_code), event.id, scanner)["status"] == CANCELLED


def test_unpublished_or_missing_event_is_rejected(app, setup, users):
    event, reg, scanner = setup
    event.status = C.APPROVED
    assert record_attendance(qr.make_token(reg.reg_code), event.id, scanner)["status"] == NOT_OPEN
    assert record_attendance(qr.make_token(reg.reg_code), 99999, scanner)["status"] == INVALID


def test_manual_entry_with_registration_id(app, setup):
    event, reg, scanner = setup
    result = record_attendance(reg.reg_code.lower(), event.id, scanner)
    assert result["status"] == SUCCESS
    assert Attendance.query.one().method == "manual"


def test_scan_endpoint_status_codes(client, setup, users):
    event, reg, _ = setup
    login(client, users["logistics"])
    body = {"event_id": event.id, "value": qr.make_token(reg.reg_code)}
    ok = client.post("/logistics/scan", json=body)
    assert ok.status_code == 200 and ok.get_json()["attended"] == 1
    dup = client.post("/logistics/scan", json=body)
    assert dup.status_code == 409 and dup.get_json()["status"] == DUPLICATE
    bad = client.post("/logistics/scan", json={"event_id": event.id, "value": "nonsense"})
    assert bad.status_code == 400
    assert client.post("/logistics/scan", json={"value": "x"}).status_code == 400


def test_students_and_anonymous_cannot_use_scan_endpoint(client, setup, users):
    event, reg, _ = setup
    body = {"event_id": event.id, "value": qr.make_token(reg.reg_code)}
    assert client.post("/logistics/scan", json=body).status_code == 302
    login(client, users["student"])
    assert client.post("/logistics/scan", json=body).status_code == 403
    assert Attendance.query.count() == 0
