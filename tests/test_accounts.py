"""The staff hierarchy: Faculty -> ONE Organizer -> ONE Logistics, plus DB integrity."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import constants as C
from app.extensions import db
from app.models import AuditLog, User
from app.services import accounts
from app.services.errors import ServiceError
from tests.conftest import PASSWORD, login, make_user


def audit_actions(target):
    return [a.action for a in AuditLog.query.filter_by(target_id=target.id).order_by(AuditLog.id)]


# ---- Faculty manages the Organizer -------------------------------------------
def test_faculty_changes_organizer_details_and_password(client, users):
    login(client, users["faculty"])
    org = users["organizer"]
    assert client.get("/faculty/organizer-account").status_code == 200
    resp = client.post("/faculty/organizer-account", data={
        "action": "details", "username": "committee_main", "email": "committee@test.example"})
    assert resp.status_code == 302
    db.session.refresh(org)
    assert org.username == "committee_main" and org.email == "committee@test.example"

    client.post("/faculty/organizer-account", data={
        "action": "password", "new_password": "Fresh1234", "confirm_password": "Fresh1234"})
    db.session.refresh(org)
    assert org.check_password("Fresh1234") and org.must_change_password
    assert audit_actions(org) == ["organizer.updated", "organizer.password_set"]
    entry = AuditLog.query.filter_by(action="organizer.password_set").one()
    assert entry.actor_id == users["faculty"].id and entry.target_id == org.id and entry.created_at


def test_faculty_reset_gives_a_working_temporary_password_once(client, users):
    login(client, users["faculty"])
    resp = client.post("/faculty/organizer-account", data={"action": "reset"})
    page = resp.get_data(as_text=True)
    assert "Temporary password" in page
    org = users["organizer"]
    db.session.refresh(org)
    assert not org.check_password(PASSWORD) and org.must_change_password
    assert "organizer.password_reset" in audit_actions(org)
    assert "Temporary password" not in client.get("/faculty/organizer-account").get_data(as_text=True)


def test_organizer_must_change_a_reset_password_before_working(app, users):
    accounts.set_staff_password(users["faculty"], C.ORGANIZER, "Fresh1234", "Fresh1234")
    client = app.test_client()
    resp = client.post("/login", data={"identifier": users["organizer"].username, "password": "Fresh1234"})
    assert resp.headers["Location"].endswith("/account/password")
    assert client.get("/organizer/").headers["Location"].endswith("/account/password")
    ok = client.post("/account/password", data={
        "current_password": "Fresh1234", "new_password": "Mine54321", "confirm_password": "Mine54321"})
    assert ok.status_code == 302
    assert client.get("/organizer/").status_code == 200


def test_faculty_deactivates_and_reactivates_organizer(client, app, users):
    login(client, users["faculty"])
    client.post("/faculty/organizer-account", data={"action": "deactivate"})
    org = users["organizer"]
    db.session.refresh(org)
    assert org.account_status == C.ACCOUNT_INACTIVE
    from flask import g
    g.pop("_login_user", None)  # test app context outlives requests
    other = app.test_client()
    resp = other.post("/login", data={"identifier": org.username, "password": PASSWORD})
    assert resp.status_code == 403
    g.pop("_login_user", None)
    client.post("/faculty/organizer-account", data={"action": "activate"})
    db.session.refresh(org)
    assert org.is_active
    assert audit_actions(org) == ["organizer.deactivated", "organizer.activated"]


def test_deactivating_the_organizer_signs_out_their_session(app, users):
    org_client = app.test_client()
    login(org_client, users["organizer"])
    assert org_client.get("/organizer/").status_code == 200
    accounts.set_staff_active(users["faculty"], C.ORGANIZER, False)
    from flask import g
    g.pop("_login_user", None)  # test app context outlives requests
    assert org_client.get("/organizer/").status_code == 302


@pytest.mark.parametrize("role", ["student", "organizer", "logistics"])
def test_only_faculty_can_open_organizer_management(client, users, role):
    login(client, users[role])
    assert client.get("/faculty/organizer-account").status_code == 403
    assert client.post("/faculty/organizer-account", data={"action": "reset"}).status_code == 403


def test_organizer_service_calls_need_faculty(app, users):
    for actor in ("student", "organizer", "logistics"):
        with pytest.raises(ServiceError) as err:
            accounts.set_staff_password(users[actor], C.ORGANIZER, "Fresh1234", "Fresh1234")
        assert err.value.code == "forbidden"
    with pytest.raises(ServiceError):
        accounts.set_staff_active(users["organizer"], C.ORGANIZER, False)


def test_staff_username_validation_and_duplicates(app, users):
    with pytest.raises(ServiceError):
        accounts.update_staff_details(users["faculty"], C.ORGANIZER, "Bad Name!", "x@test.example")
    with pytest.raises(ServiceError):
        accounts.update_staff_details(users["faculty"], C.ORGANIZER, "okay_name", users["student"].email)
    with pytest.raises(ServiceError):
        accounts.update_staff_details(users["faculty"], C.ORGANIZER, users["student"].username, "x@test.example")


# ---- Organizer manages Logistics -------------------------------------------------
def test_organizer_manages_logistics_account(client, users):
    login(client, users["organizer"])
    logi = users["logistics"]
    assert client.get("/organizer/logistics-account").status_code == 200
    client.post("/organizer/logistics-account", data={
        "action": "details", "username": "gate_team", "email": "gate@test.example"})
    client.post("/organizer/logistics-account", data={
        "action": "password", "new_password": "Fresh1234", "confirm_password": "Fresh1234"})
    client.post("/organizer/logistics-account", data={"action": "deactivate"})
    db.session.refresh(logi)
    assert logi.username == "gate_team" and logi.account_status == C.ACCOUNT_INACTIVE
    client.post("/organizer/logistics-account", data={"action": "activate"})
    resp = client.post("/organizer/logistics-account", data={"action": "reset"})
    assert "Temporary password" in resp.get_data(as_text=True)
    assert audit_actions(logi) == [
        "logistics.updated", "logistics.password_set", "logistics.deactivated",
        "logistics.activated", "logistics.password_reset"]


@pytest.mark.parametrize("role", ["student", "logistics", "faculty"])
def test_only_organizer_can_manage_logistics(client, users, role):
    login(client, users[role])
    assert client.get("/organizer/logistics-account").status_code == 403
    assert client.post("/organizer/logistics-account", data={"action": "reset"}).status_code == 403


def test_faculty_cannot_manage_logistics_directly_and_logistics_cannot_touch_credentials(app, users):
    with pytest.raises(ServiceError):
        accounts.set_staff_password(users["faculty"], C.LOGISTICS, "Fresh1234", "Fresh1234")
    for role in (C.ORGANIZER, C.LOGISTICS):
        with pytest.raises(ServiceError):
            accounts.set_staff_password(users["logistics"], role, "Fresh1234", "Fresh1234")


def test_logistics_cannot_open_organizer_member_pages(client, users):
    login(client, users["logistics"])
    assert client.get("/organizer/members").status_code == 403
    assert client.post(f"/organizer/members/{users['student'].id}/approve").status_code == 403


def test_organizer_cannot_open_faculty_only_pages(client, users):
    login(client, users["organizer"])
    for path in ("/faculty/", "/faculty/proposals", "/faculty/organizer-account"):
        assert client.get(path).status_code == 403


def test_logistics_cannot_open_faculty_or_organizer_pages(client, users):
    login(client, users["logistics"])
    for path in ("/faculty/", "/organizer/", "/faculty/organizer-account",
                 "/organizer/logistics-account"):
        assert client.get(path).status_code == 403


# ---- exactly one Organizer / one Logistics ------------------------------------------
def test_second_organizer_or_logistics_is_refused_by_the_service(app, users):
    for role in (C.ORGANIZER, C.LOGISTICS):
        with pytest.raises(ServiceError) as err:
            accounts.provision_staff_account(role, "another_one", "another@test.example", "Abcdef12")
        assert err.value.code == "duplicate"
    with pytest.raises(ServiceError):
        accounts.create_staff_account(users["faculty"], C.ORGANIZER, "another_one", "a@test.example", "Abcdef12")


def test_database_allows_exactly_one_organizer_and_one_logistics(app, users):
    for role in (C.ORGANIZER, C.LOGISTICS):
        with pytest.raises(IntegrityError):
            make_user(role, username=f"extra_{role}", email=f"extra_{role}@test.example")
        db.session.rollback()
    assert User.query.filter_by(role=C.ORGANIZER).count() == 1
    assert User.query.filter_by(role=C.LOGISTICS).count() == 1


def test_role_can_not_be_changed_into_a_second_organizer(app, users):
    users["student"].role = C.ORGANIZER
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_faculty_creates_the_organizer_when_none_exists(client, app, users):
    db.session.delete(users["organizer"])
    db.session.commit()
    login(client, users["faculty"])
    resp = client.post("/faculty/organizer-account", data={
        "action": "create", "username": "collegehub_org", "email": "org@test.example",
        "password": "Abcdef12", "name": "Organizing Committee"})
    assert resp.status_code == 302
    assert User.query.filter_by(role=C.ORGANIZER).one().username == "collegehub_org"
    again = client.post("/faculty/organizer-account", data={
        "action": "create", "username": "second_org", "email": "o2@test.example", "password": "Abcdef12"})
    assert again.status_code == 400 and User.query.filter_by(role=C.ORGANIZER).count() == 1


# ---- database constraints ----------------------------------------------------------------
def test_unique_username_and_email_in_database(app, users):
    for kwargs in ({"username": users["student"].username, "email": "fresh1@test.example"},
                   {"username": "fresh_user", "email": users["student"].email}):
        with pytest.raises(IntegrityError):
            make_user(C.STUDENT, **kwargs)
        db.session.rollback()


@pytest.mark.parametrize("sql", [
    "UPDATE users SET role = 'admin' WHERE role = 'faculty'",
    "UPDATE users SET account_status = 'BANNED'",
    "UPDATE users SET verification_status = 'MAYBE' WHERE role = 'student'",
    "UPDATE users SET verification_status = NULL WHERE role = 'student'",
])
def test_database_rejects_invalid_values(app, users, sql):
    with pytest.raises(IntegrityError):
        db.session.execute(text(sql))
        db.session.commit()
    db.session.rollback()


def test_model_validators_reject_bad_values(app):
    user = User(name="x", username="x_user", email="x@t.example", role=C.STUDENT)
    for attr, value in (("role", "admin"), ("account_status", "BANNED"),
                        ("verification_status", "MAYBE")):
        with pytest.raises(ValueError):
            setattr(user, attr, value)


def test_no_fifth_role_exists():
    assert set(C.ROLES) == {"student", "organizer", "logistics", "faculty"}
