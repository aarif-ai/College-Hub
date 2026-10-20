"""Student profile editing, photo upload and validation."""
import io

import pytest
from PIL import Image

from app import constants as C
from app.extensions import db
from tests.conftest import login, make_user

VALID = {
    "name": "Aisha Khan", "department": "Humanities", "branch": "B.A.", "semester": "3",
    "section": "B", "phone": "+91 98000 12345", "enrollment_no": "2024-ABC-001",
    "skills": "Python, public speaking", "interests": "AI, debate", "bio": "Third year student.",
    "github_url": "https://github.com/aisha", "linkedin_url": "", "portfolio_url": "",
}


def png_bytes(size=(60, 40)):
    out = io.BytesIO()
    Image.new("RGB", size, "navy").save(out, "PNG")
    out.seek(0)
    return out


def test_profile_page_shows_all_sections_and_buttons(client, users):
    login(client, users["student"])
    page = client.get("/student/profile").get_data(as_text=True)
    for text in ("Edit profile", "Change password", "Verification status", users["student"].username,
                 "Verified CollegeHub Member", "Achievements"):
        assert text in page


def test_student_updates_profile(client, users):
    student = users["student"]
    login(client, student)
    resp = client.post("/student/profile/edit", data=VALID)
    assert resp.status_code == 302
    db.session.refresh(student)
    assert student.name == "Aisha Khan" and student.profile.phone == "+91 98000 12345"
    assert student.profile.semester == 3 and student.profile.skill_list == ["Python", "public speaking"]
    assert student.profile.github_url == "https://github.com/aisha"
    page = client.get("/student/profile").get_data(as_text=True)
    assert "Python" in page and "github.com/aisha" in page and "Third year student." in page
    # profile is now complete -> achievement unlocked
    assert any(ua.achievement.code == "profile_ready" for ua in student.achievements)


@pytest.mark.parametrize("field, value", [
    ("phone", "abc"), ("phone", "12"), ("semester", "9"), ("semester", "x"),
    ("branch", "Wizardry"), ("department", "Nowhere"), ("name", "A"),
    ("github_url", "javascript:alert(1)"), ("linkedin_url", "ftp://x.example"),
    ("section", "Section-Long-Name!"), ("bio", "x" * 601),
])
def test_invalid_profile_values_are_rejected(client, users, field, value):
    login(client, users["student"])
    resp = client.post("/student/profile/edit", data={**VALID, field: value})
    assert resp.status_code == 400
    db.session.refresh(users["student"])
    assert users["student"].profile.phone != "+91 98000 12345"


def test_enrollment_number_is_optional_but_unique(client, users):
    login(client, users["student"])
    assert client.post("/student/profile/edit", data={**VALID, "enrollment_no": ""}).status_code == 302
    other = users["student2"]
    other.profile.enrollment_no = "TAKEN-1"
    db.session.commit()
    assert client.post("/student/profile/edit", data={**VALID, "enrollment_no": "TAKEN-1"}).status_code == 400


def test_registration_does_not_need_an_enrollment_number(client, app):
    resp = client.post("/register", data={"username": "no.enrol", "email": "ne@test.example",
                                          "password": "Abcdef12", "confirm_password": "Abcdef12"})
    assert resp.status_code == 302


def test_photo_upload_is_validated_and_recompressed(app, client, users):
    student = users["student"]
    login(client, student)
    resp = client.post("/student/profile/edit", data={**VALID, "photo": (png_bytes((300, 120)), "me.png")},
                       content_type="multipart/form-data")
    assert resp.status_code == 302
    db.session.refresh(student)
    stored = student.profile.photo
    assert stored and stored.endswith(".jpg")
    served = client.get(f"/media/avatars/{stored}")
    assert served.status_code == 200
    assert Image.open(io.BytesIO(served.data)).size == (400, 400)


def test_bad_photos_are_rejected(client, users):
    login(client, users["student"])
    fake = client.post("/student/profile/edit", data={**VALID, "photo": (io.BytesIO(b"not an image"), "x.png")},
                       content_type="multipart/form-data")
    assert fake.status_code == 400
    wrong_type = client.post("/student/profile/edit", data={**VALID, "photo": (io.BytesIO(b"<script>"), "x.html")},
                             content_type="multipart/form-data")
    assert wrong_type.status_code == 400
    big = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * (3 * 1024 * 1024))
    assert client.post("/student/profile/edit", data={**VALID, "photo": (big, "big.png")},
                       content_type="multipart/form-data").status_code == 400


def test_avatars_are_only_for_signed_in_users(client, users):
    assert client.get("/media/avatars/anything.jpg").status_code == 302


def test_staff_cannot_open_student_profile_pages(client, users):
    login(client, users["organizer"])
    assert client.get("/student/profile").status_code == 403
    assert client.get("/student/profile/edit").status_code == 403


def test_password_hash_never_appears_in_pages(client, users):
    login(client, users["student"])
    for path in ("/student/profile", "/student/profile/edit", "/student/"):
        assert users["student"].password_hash not in client.get(path).get_data(as_text=True)
    other = make_user(C.STUDENT, verified=False)
    login_client = client
    login_client.post("/logout")
    login(login_client, users["organizer"])
    assert other.password_hash not in login_client.get(f"/organizer/members/{other.id}").get_data(as_text=True)
