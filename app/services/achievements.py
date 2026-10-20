"""Simple achievement system for students."""
from app import constants as C
from app.extensions import db
from app.models import (
    Achievement, Attendance, Certificate, Registration, UserAchievement,
    VolunteerApplication,
)
from app.services.notifications import notify


def seed_achievements() -> None:
    """Create any missing achievement definitions (safe to call repeatedly)."""
    existing = {a.code for a in Achievement.query.all()}
    for code, title, description, icon in C.ACHIEVEMENTS:
        if code not in existing:
            db.session.add(
                Achievement(code=code, title=title, description=description, icon=icon)
            )
    db.session.flush()


def award(user, code: str, announce: bool = True) -> bool:
    """Give ``user`` an achievement once. Returns True if newly awarded."""
    achievement = Achievement.query.filter_by(code=code).first()
    if achievement is None:
        return False
    already = UserAchievement.query.filter_by(
        user_id=user.id, achievement_id=achievement.id
    ).first()
    if already:
        return False
    db.session.add(UserAchievement(user_id=user.id, achievement_id=achievement.id))
    if announce:
        notify(user, f"Achievement unlocked: {achievement.title}", "/student/profile")
    return True


def evaluate_student(user) -> None:
    """Award every achievement the student has earned so far."""
    db.session.flush()
    registered = Registration.query.filter_by(student_id=user.id).count()
    attended = Attendance.query.filter_by(student_id=user.id).count()
    certs = Certificate.query.filter_by(student_id=user.id).count()
    volunteered = VolunteerApplication.query.filter_by(
        student_id=user.id, status=C.APP_APPROVED
    ).count()

    if registered >= 1:
        award(user, "first_step")
    if attended >= 1:
        award(user, "showing_up")
    if attended >= 3:
        award(user, "regular")
    if certs >= 1:
        award(user, "certified")
    if volunteered >= 1:
        award(user, "volunteer")
    if user.profile and user.profile.is_complete:
        award(user, "profile_ready")
