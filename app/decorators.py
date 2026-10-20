"""Role-based access control for routes.

Every sensitive route is protected on the *server*; hiding a button in the
template is never treated as security.
"""
from functools import wraps

from flask import abort, render_template
from flask_login import current_user, login_required


def role_required(*roles):
    """Allow only signed-in users whose role is in ``roles`` (else 403)."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.has_role(*roles):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def verified_required(view):
    """Student-only routes that need a Verified CollegeHub Member.

    Unverified students are not blocked from the site; they get a clear page
    explaining what verification is and how to get it.
    """

    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_verified:
            if current_user.role != "student":
                abort(403)
            return render_template("student/verification_required.html"), 403
        return view(*args, **kwargs)

    return wrapped
