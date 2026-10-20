import io

import pytest
from pypdf import PdfReader

from app import constants as C
from app.extensions import db
from app.models import Certificate, LogisticsTask
from app.services import certificates as certs
from app.services import logistics as logi
from app.services import qr
from app.services.attendance import record_attendance
from app.services.errors import ServiceError
from app.services.registration import register_student
from tests.conftest import login, make_event


@pytest.fixture()
def approved(app, users):
    event = make_event(users["organizer"], C.APPROVED)
    logi.create_default_tasks(event)
    from app.extensions import db
    db.session.commit()
    return event


def test_readiness_percentage(app, users, approved):
    assert approved.readiness_percent == 0
    total = len(approved.tasks)
    for task in approved.tasks[: total // 2]:
        logi.update_task(task, users["logistics"], C.TASK_COMPLETED, None, None)
    assert approved.readiness_percent == round((total // 2) * 100 / total)
    for task in approved.tasks:
        logi.update_task(task, users["logistics"], C.TASK_COMPLETED, None, None)
    assert approved.readiness_percent == 100


def test_logistics_updates_task_over_http(client, users, approved):
    task = approved.tasks[0]
    login(client, users["logistics"])
    client.post(f"/logistics/tasks/{task.id}", data={
        "status": "in_progress", "notes": "Projector arrives at 9", "assigned_to": "AV team"})
    task = db.session.get(LogisticsTask, task.id)
    assert task.status == C.TASK_IN_PROGRESS and task.notes == "Projector arrives at 9"
    assert task.updated_by_id == users["logistics"].id


def test_invalid_task_status_rejected(app, users, approved):
    with pytest.raises(ServiceError):
        logi.update_task(approved.tasks[0], users["logistics"], "done-ish", None, None)


def test_logistics_cannot_open_draft_event(client, users):
    draft = make_event(users["organizer"], C.DRAFT)
    login(client, users["logistics"])
    assert client.get(f"/logistics/events/{draft.id}").status_code == 404
    assert client.get(f"/logistics/events/{draft.id}/scan").status_code == 404


def test_add_custom_task(app, users, approved):
    task = logi.add_task(approved, users["logistics"], "Bring spare cables", "Equipment", "AV")
    assert task in approved.tasks
    with pytest.raises(ServiceError):
        logi.add_task(approved, users["logistics"], "x", "", "")


@pytest.fixture()
def attended(app, users):
    event = make_event(users["organizer"], C.PUBLISHED)
    reg = register_student(users["student"], event)
    register_student(users["student2"], event)  # registered but never scanned
    record_attendance(qr.make_token(reg.reg_code), event.id, users["logistics"])
    event.status = C.COMPLETED  # certificates are only issued after completion
    db.session.commit()
    return event


def test_certificates_only_for_attendees(app, users, attended):
    created = certs.issue_certificates(attended, users["organizer"])
    assert created == 1
    cert = Certificate.query.one()
    assert cert.student_id == users["student"].id and cert.cert_code.startswith("CERT-")
    assert certs.issue_certificates(attended, users["organizer"]) == 0  # idempotent


def test_certificate_issue_requires_attendance_and_permission(app, users):
    event = make_event(users["organizer"], C.COMPLETED, days_ahead=-2)
    with pytest.raises(ServiceError) as err:
        certs.issue_certificates(event, users["organizer"])
    assert err.value.code == "no_attendance"
    with pytest.raises(ServiceError) as err:
        certs.issue_certificates(event, users["logistics"])
    assert err.value.code == "forbidden"
    with pytest.raises(ServiceError):
        certs.issue_certificates(event, users["student"])


def test_certificate_pdf_contents(app, users, attended):
    certs.issue_certificates(attended, users["organizer"])
    cert = Certificate.query.one()
    pdf = certs.certificate_pdf(cert, "http://localhost/verify/" + cert.cert_code)
    assert pdf.startswith(b"%PDF")
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    for expected in ("CollegeHub", "Certificate of Participation", users["student"].name,
                     attended.title, cert.cert_code):
        assert expected in text


def test_student_downloads_own_certificate_only(client, users, attended):
    certs.issue_certificates(attended, users["organizer"])
    cert = Certificate.query.one()
    login(client, users["student"])
    resp = client.get(f"/student/certificates/{cert.id}/download")
    assert resp.status_code == 200 and resp.mimetype == "application/pdf"
    client.post("/logout")
    login(client, users["student2"])
    assert client.get(f"/student/certificates/{cert.id}/download").status_code == 403


def test_public_certificate_verification(client, users, attended):
    certs.issue_certificates(attended, users["organizer"])
    cert = Certificate.query.one()
    ok = client.get(f"/verify/{cert.cert_code}")
    assert ok.status_code == 200 and b"Certificate verified" in ok.data
    assert client.get("/verify/CERT-0000-FAKE").status_code == 404
