"""Shared fixtures: an in-memory app plus helpers to build users and events."""
from datetime import datetime, time, timedelta

import pytest

from app import constants as C
from app import create_app
from app.extensions import db
from app.models import Event, StudentProfile, User
from app.services.achievements import seed_achievements
from app.utils import now

PASSWORD = "Passw0rd!x"


@pytest.fixture()
def app(tmp_path):
    from app.services import throttle
    throttle.reset_all()
    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    with app.app_context():
        db.create_all()
        seed_achievements()
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


_COUNTER = {"n": 0}


def make_user(role, name=None, email=None, username=None, verified=True, **extra):
    """Create a user. Students are VERIFIED by default; pass ``verified=False``
    to get a PENDING student. Only one organizer and one logistics account can
    exist (the database enforces it)."""
    _COUNTER["n"] += 1
    n = _COUNTER["n"]
    name = name or f"Test {role.title()}"
    if username is None:
        username = (f"test.user{n:02d}".replace("0", "a") if role == C.STUDENT
                    else f"{role}_acct{n}")
    user = User(name=name, username=username,
                email=email or f"{role}{n}@test.example", role=role,
                department="Humanities", **extra)
    user.set_password(PASSWORD)
    if role == C.STUDENT:
        user.profile = StudentProfile()
        if verified:
            user.verification_status = C.VERIFY_VERIFIED
            user.verified_at = now()
    db.session.add(user)
    db.session.commit()
    return user


def make_event(organizer, status=C.DRAFT, days_ahead=7, capacity=50, **overrides):
    day = now().date() + timedelta(days=days_ahead)
    data = dict(
        title="Test Workshop Event", description="A long enough description for the test event.",
        category="Workshop", venue="Room 101", event_date=day,
        start_time=time(10, 0), end_time=time(12, 0), capacity=capacity,
        registration_deadline=datetime.combine(day, time(9, 0)) - timedelta(hours=2),
        status=status, organizer_id=organizer.id,
    )
    data.update(overrides)
    event = Event(**data)
    db.session.add(event)
    db.session.commit()
    return event


def login(client, user):
    resp = client.post("/login", data={"identifier": user.email, "password": PASSWORD})
    assert resp.status_code == 302
    return resp


@pytest.fixture()
def users(app):
    return {
        "student": make_user(C.STUDENT, "Sara Student"),
        "student2": make_user(C.STUDENT, "Omar Student"),
        "organizer": make_user(C.ORGANIZER, "Olive Organizer"),
        "logistics": make_user(C.LOGISTICS, "Leo Logistics"),
        "faculty": make_user(C.FACULTY, "Fiona Faculty"),
    }
