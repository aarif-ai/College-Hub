import pytest

from app import constants as C
from tests.conftest import login, make_event

AREAS = {
    "student": "/student/", "organizer": "/organizer/",
    "faculty": "/faculty/", "logistics": "/logistics/",
}


def test_anonymous_users_are_sent_to_login(client):
    for url in AREAS.values():
        assert client.get(url).status_code == 302


@pytest.mark.parametrize("role", list(AREAS))
def test_each_role_only_reaches_its_own_area(client, users, role):
    login(client, users[role])
    for other, url in AREAS.items():
        expected = 200 if other == role else 403
        assert client.get(url).status_code == expected, (role, url)


def test_student_cannot_approve_or_create_events(client, users):
    event = make_event(users["organizer"], C.SUBMITTED)
    login(client, users["student"])
    assert client.post(f"/faculty/events/{event.id}/decide", data={"decision": "approve"}).status_code == 403
    assert client.post("/organizer/events/new", data={}).status_code == 403


def test_organizer_cannot_approve(client, users):
    event = make_event(users["organizer"], C.SUBMITTED)
    login(client, users["organizer"])
    assert client.post(f"/faculty/events/{event.id}/decide", data={"decision": "approve"}).status_code == 403


def test_logistics_cannot_approve_or_publish(client, users):
    event = make_event(users["organizer"], C.SUBMITTED)
    login(client, users["logistics"])
    assert client.post(f"/faculty/events/{event.id}/decide", data={"decision": "approve"}).status_code == 403
    assert client.post(f"/organizer/events/{event.id}/publish").status_code == 403


@pytest.mark.parametrize("role", ["student", "logistics", "faculty"])
def test_only_the_organizer_manages_events(client, users, role):
    event = make_event(users["organizer"], C.DRAFT)
    login(client, users[role])
    assert client.get(f"/organizer/events/{event.id}").status_code == 403
    assert client.post(f"/organizer/events/{event.id}/submit").status_code == 403
    assert client.post(f"/organizer/events/{event.id}/delete").status_code == 403


def test_students_only_see_published_events(client, users):
    draft = make_event(users["organizer"], C.DRAFT, title="Secret Draft Event")
    published = make_event(users["organizer"], C.PUBLISHED, title="Open Public Event")
    page = client.get("/events").get_data(as_text=True)
    assert "Open Public Event" in page and "Secret Draft Event" not in page
    assert client.get(f"/events/{draft.id}").status_code == 404
    assert client.get(f"/events/{published.id}").status_code == 200
    login(client, users["student"])
    assert client.get(f"/events/{draft.id}").status_code == 404


def test_private_documents_are_protected(client, users):
    event = make_event(users["organizer"], C.PUBLISHED)
    from app.extensions import db
    from app.models import EventDocument
    doc = EventDocument(event_id=event.id, uploader_id=users["organizer"].id,
                        original_filename="a.pdf", stored_filename="a.pdf",
                        file_path="documents/a.pdf", size_bytes=1)
    db.session.add(doc)
    db.session.commit()
    assert client.get(f"/documents/{doc.id}").status_code == 302
    login(client, users["student"])
    assert client.get(f"/documents/{doc.id}").status_code == 403


def test_error_pages_render(client):
    assert client.get("/no-such-page").status_code == 404
    assert b"Page not found" in client.get("/no-such-page").data
