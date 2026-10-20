"""Registration, usernames, login, logout, password reset and change."""
import pytest

from app import constants as C
from app.extensions import db
from app.models import User
from app.services import accounts
from tests.conftest import PASSWORD, login, make_user

GOOD = {"username": "rahul.sharma", "email": "rahul@test.example",
        "password": "Abcdef12", "confirm_password": "Abcdef12"}


def register(client, **overrides):
    return client.post("/register", data={**GOOD, **overrides})


def test_password_is_hashed_not_plaintext(users):
    user = users["student"]
    assert user.password_hash != PASSWORD and PASSWORD not in user.password_hash
    assert user.check_password(PASSWORD) and not user.check_password("wrong-password")


def test_short_name_skips_titles(app):
    assert User(name="Dr. Farhana Qureshi").short_name == "Farhana"
    assert User(name="Aisha Khan").short_name == "Aisha"


# ---- registration ---------------------------------------------------------
def test_register_creates_active_pending_student(client, app):
    resp = register(client, role="faculty", verification_status="VERIFIED",
                    account_status="SUSPENDED")
    assert resp.status_code == 302
    user = User.query.filter_by(username="rahul.sharma").one()
    assert user.role == C.STUDENT                       # posted "role" ignored
    assert user.account_status == C.ACCOUNT_ACTIVE
    assert user.verification_status == C.VERIFY_PENDING  # posted status ignored
    assert not user.is_verified
    assert user.name == "Rahul Sharma" and user.profile is not None
    assert user.password_hash != GOOD["password"]


@pytest.mark.parametrize("username", [
    "rahul.sharma", "student.one", "aarif.mushtaq", "aarif.mushtaq01", "ab.cd99"])
def test_valid_username_patterns(username):
    assert accounts.USERNAME_RE.match(username)


@pytest.mark.parametrize("username", [
    "rahul sharma", "rahul", "rahul.sharma.x", "rahul_sharma",
    "rahul.sharma1", "rahul.sharma00", "rahul.sharma001", "r.s", ".sharma", "rahul.",
    "rahul.sharma!", "rahül.sharma", "a" * 30 + ".sharma"])
def test_invalid_username_patterns_rejected_by_backend(client, app, username):
    resp = register(client, username=username)
    assert resp.status_code == 400
    assert User.query.filter_by(email=GOOD["email"]).first() is None
    assert "firstname.lastname" in resp.get_data(as_text=True)


def test_username_is_lowercased_before_validation(client, app):
    assert register(client, username="Rahul.Sharma").status_code == 302
    assert User.query.filter_by(username="rahul.sharma").count() == 1


def test_duplicate_username_is_explained_with_a_suggestion(client, users):
    taken = make_user(C.STUDENT, username="rahul.sharma")
    resp = register(client)
    assert resp.status_code == 400
    page = resp.get_data(as_text=True)
    assert "already taken" in page and "rahul.sharma01" in page
    assert User.query.filter_by(username="rahul.sharma").count() == 1 and taken


def test_suffixed_username_works_when_base_is_taken(client, app):
    make_user(C.STUDENT, username="rahul.sharma")
    assert register(client, username="rahul.sharma01").status_code == 302


def test_duplicate_email_rejected(client, users):
    resp = register(client, email=users["student"].email.upper())
    assert resp.status_code == 400 and "already exists" in resp.get_data(as_text=True)


def test_weak_password_and_mismatch_rejected(client, app):
    assert register(client, password="short", confirm_password="short").status_code == 400
    assert register(client, password="NoNumbersHere", confirm_password="NoNumbersHere").status_code == 400
    assert register(client, confirm_password="Different12").status_code == 400
    assert User.query.count() == 0


def test_registration_race_is_handled_by_the_database(app, monkeypatch):
    make_user(C.STUDENT, username="rahul.sharma")
    # Pretend two requests passed the friendly check at the same moment.
    monkeypatch.setattr(accounts, "student_username_problem", lambda _u: None)
    user, errors = accounts.register_student(**{
        "username": "rahul.sharma", "email": "other@test.example",
        "password": "Abcdef12", "confirm": "Abcdef12"})
    assert user is None and "username" in errors
    assert User.query.filter_by(username="rahul.sharma").count() == 1


def test_registration_form_shows_the_format(client):
    page = client.get("/register").get_data(as_text=True)
    assert "firstname.lastname" in page and "rahul.sharma" in page
    assert 'name="role"' not in page


def test_there_is_no_organizer_registration_page(client, users):
    for path in ("/organizer/register", "/register/organizer", "/logistics/register"):
        assert client.get(path).status_code == 404


# ---- login / logout -------------------------------------------------------
def test_login_with_username_or_email_any_case(client, users):
    student = users["student"]
    for identifier in (student.username, student.username.upper(), student.email,
                       student.email.upper()):
        resp = client.post("/login", data={"identifier": identifier, "password": PASSWORD})
        assert resp.status_code == 302, identifier
        client.post("/logout")


def test_login_logout_flow(client, users):
    bad = client.post("/login", data={"identifier": users["student"].email, "password": "nope"})
    assert bad.status_code == 401
    login(client, users["student"])
    assert client.get("/student/").status_code == 200
    assert client.post("/logout").status_code == 302
    assert client.get("/student/").status_code == 302


def test_login_redirects_to_role_dashboard(client, users):
    for role, path in (("faculty", "/faculty/"), ("organizer", "/organizer/"),
                       ("logistics", "/logistics/"), ("student", "/student/")):
        resp = client.post("/login", data={"identifier": users[role].username, "password": PASSWORD})
        assert resp.headers["Location"].endswith(path)
        client.post("/logout")


def test_open_redirect_is_blocked(client, users):
    resp = client.post("/login", data={"identifier": users["student"].email, "password": PASSWORD,
                                       "next": "https://evil.example/phish"})
    assert "evil.example" not in resp.headers["Location"]


def test_login_throttle_after_repeated_failures(client, users):
    for _ in range(5):
        client.post("/login", data={"identifier": users["student"].email, "password": "bad"})
    resp = client.post("/login", data={"identifier": users["student"].email, "password": PASSWORD})
    assert resp.status_code == 429


@pytest.mark.parametrize("status", [C.ACCOUNT_INACTIVE, C.ACCOUNT_SUSPENDED])
def test_inactive_or_suspended_accounts_cannot_log_in(client, users, status):
    users["student"].account_status = status
    db.session.commit()
    resp = client.post("/login", data={"identifier": users["student"].email, "password": PASSWORD})
    assert resp.status_code == 403
    assert client.get("/student/").status_code == 302


def test_deactivating_signs_out_an_open_session(client, users):
    login(client, users["student"])
    assert client.get("/student/").status_code == 200
    users["student"].account_status = C.ACCOUNT_INACTIVE
    db.session.commit()
    assert client.get("/student/").status_code == 302


# ---- forgot / reset password ------------------------------------------------
def test_forgot_password_answer_does_not_reveal_accounts(client, users):
    known = client.post("/forgot-password", data={"identifier": users["student"].email})
    unknown = client.post("/forgot-password", data={"identifier": "nobody@test.example"})
    staff = client.post("/forgot-password", data={"identifier": users["organizer"].email})
    assert known.status_code == unknown.status_code == staff.status_code == 200
    for resp in (known, unknown, staff):
        assert "Check your email" in resp.get_data(as_text=True)
        assert "/reset-password/" not in resp.get_data(as_text=True)  # no link on screen


def test_forgot_password_demo_mode_shows_link_only_for_students(app, client, users):
    app.config["DEMO_SHOW_RESET_LINK"] = True
    page = client.post("/forgot-password", data={"identifier": users["student"].email}).get_data(as_text=True)
    assert "/reset-password/" in page
    page = client.post("/forgot-password", data={"identifier": users["organizer"].email}).get_data(as_text=True)
    assert "/reset-password/" not in page


def test_reset_password_with_valid_token(client, users):
    student = users["student"]
    token = accounts.make_reset_token(student)
    assert client.get(f"/reset-password/{token}").status_code == 200
    resp = client.post(f"/reset-password/{token}", data={
        "password": "Brandnew99", "confirm_password": "Brandnew99"})
    assert resp.status_code == 302
    db.session.refresh(student)
    assert student.check_password("Brandnew99") and not student.check_password(PASSWORD)


def test_reset_token_is_single_use(client, users):
    token = accounts.make_reset_token(users["student"])
    client.post(f"/reset-password/{token}", data={"password": "Brandnew99", "confirm_password": "Brandnew99"})
    assert client.get(f"/reset-password/{token}").status_code == 400
    assert client.post(f"/reset-password/{token}", data={
        "password": "Another123", "confirm_password": "Another123"}).status_code == 400


def test_reset_token_expires_and_rejects_garbage(app, client, users):
    token = accounts.make_reset_token(users["student"])
    app.config["RESET_TOKEN_MAX_AGE"] = -1
    assert client.get(f"/reset-password/{token}").status_code == 400
    app.config["RESET_TOKEN_MAX_AGE"] = 3600
    assert client.get("/reset-password/not-a-real-token").status_code == 400


def test_reset_token_rejects_weak_password_and_staff_tokens(client, users):
    token = accounts.make_reset_token(users["student"])
    assert client.post(f"/reset-password/{token}", data={
        "password": "weak", "confirm_password": "weak"}).status_code == 400
    staff_token = accounts.make_reset_token(users["organizer"])
    assert client.get(f"/reset-password/{staff_token}").status_code == 400


# ---- change password ------------------------------------------------------------
@pytest.mark.parametrize("role", ["student", "organizer", "logistics", "faculty"])
def test_every_role_can_change_its_own_password(client, users, role):
    login(client, users[role])
    bad = client.post("/account/password", data={
        "current_password": "wrong", "new_password": "Newpass123", "confirm_password": "Newpass123"})
    assert bad.status_code == 400
    ok = client.post("/account/password", data={
        "current_password": PASSWORD, "new_password": "Newpass123", "confirm_password": "Newpass123"})
    assert ok.status_code == 302
    db.session.refresh(users[role])
    assert users[role].check_password("Newpass123")


def test_changing_password_signs_out_other_sessions(app, users):
    first, second = app.test_client(), app.test_client()
    login(first, users["student"])
    login(second, users["student"])
    first.post("/account/password", data={
        "current_password": PASSWORD, "new_password": "Newpass123", "confirm_password": "Newpass123"})
    assert first.get("/student/").status_code == 200      # this device stays signed in
    # The test app context outlives requests, so drop Flask-Login's per-request cache.
    from flask import g
    g.pop("_login_user", None)
    assert second.get("/student/").status_code == 302     # the other one is signed out


def test_account_pages_require_login(client):
    assert client.get("/account/password").status_code == 302
