"""Sign in, student sign up, password reset/change and sign out."""
from flask import (
    Blueprint, current_app, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app import constants as C
from app.services import accounts, throttle
from app.services.mailer import send_mail
from app.utils import is_safe_redirect

bp = Blueprint("auth", __name__)

MAX_FAILURES = 5
WINDOW_SECONDS = 10 * 60


def _login_key(identifier: str) -> str:
    return f"login|{request.remote_addr}|{identifier}"


def _login_page(identifier, next_url, status):
    return render_template("auth/login.html", identifier=identifier, next_url=next_url), status


@bp.route("/login", methods=["GET", "POST"])
def login():
    from app import home_endpoint
    if current_user.is_authenticated:
        return redirect(url_for(home_endpoint(current_user)))

    next_url = request.values.get("next", "")
    if request.method == "POST":
        identifier = (request.form.get("identifier") or "").strip().lower()
        password = request.form.get("password") or ""
        key = _login_key(identifier)

        if throttle.is_limited(key, MAX_FAILURES, WINDOW_SECONDS):
            flash("Too many failed attempts. Please wait a few minutes and try again.", "danger")
            return _login_page(identifier, next_url, 429)

        user = accounts.find_by_login(identifier)
        if user is None or not user.check_password(password):
            throttle.hit(key, WINDOW_SECONDS)
            flash("Incorrect username/email or password.", "danger")
            return _login_page(identifier, next_url, 401)
        if not user.is_active:
            # Only said after the password is right, so it does not reveal accounts.
            flash("This account is not active. Please contact the CollegeHub "
                  "Organizing Committee or your faculty mentor.", "danger")
            return _login_page(identifier, next_url, 403)

        throttle.clear(key)
        login_user(user, remember=bool(request.form.get("remember")))
        flash(f"Welcome back, {user.short_name}.", "success")
        if user.must_change_password:
            return redirect(url_for("auth.change_password"))
        if next_url and is_safe_redirect(next_url):
            return redirect(next_url)
        return redirect(url_for(home_endpoint(user)))

    return _login_page("", next_url, 200)


@bp.route("/register", methods=["GET", "POST"])
def register():
    """Self-service sign up. Always creates a Student account (never staff)."""
    from app import home_endpoint
    if current_user.is_authenticated:
        return redirect(url_for(home_endpoint(current_user)))

    form, errors = {}, {}
    if request.method == "POST":
        form = {"username": (request.form.get("username") or "").strip().lower(),
                "email": accounts.normalise_email(request.form.get("email"))}
        user, errors = accounts.register_student(
            form["username"], form["email"],
            request.form.get("password") or "", request.form.get("confirm_password") or "")
        if user is not None:
            login_user(user)
            flash("Your CollegeHub account is ready. Complete your profile so the "
                  "Organizing Committee can verify you.", "success")
            return redirect(url_for("student.profile"))
        flash("Please fix the highlighted fields.", "danger")

    return render_template("auth/register.html", form=form, errors=errors), (
        400 if errors else 200)


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Students request a reset link. The answer is identical whether or not the
    account exists, so the form cannot be used to discover accounts."""
    demo_link = None
    submitted = False
    if request.method == "POST":
        submitted = True
        key = f"forgot|{request.remote_addr}"
        if throttle.is_limited(key, MAX_FAILURES, WINDOW_SECONDS):
            flash("Too many requests. Please wait a few minutes and try again.", "danger")
            return render_template("auth/forgot_password.html", submitted=False), 429
        throttle.hit(key, WINDOW_SECONDS)

        user = accounts.find_by_login(request.form.get("identifier"))
        # Staff passwords are managed by the hierarchy (Faculty / Organizer).
        if user is not None and user.role == C.STUDENT and user.is_active:
            link = url_for("auth.reset_password", token=accounts.make_reset_token(user),
                           _external=True)
            minutes = current_app.config["RESET_TOKEN_MAX_AGE"] // 60
            send_mail(user.email, "Reset your CollegeHub password",
                      f"Hello {user.short_name},\n\nUse this link to choose a new password "
                      f"(valid for {minutes} minutes):\n{link}\n\n"
                      "If you did not ask for this, you can ignore this message.")
            if current_app.config["DEMO_SHOW_RESET_LINK"]:
                demo_link = link
    return render_template("auth/forgot_password.html", submitted=submitted,
                           demo_link=demo_link)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = accounts.user_from_reset_token(token)
    if user is None:
        return render_template("auth/reset_password.html", token=token, invalid=True,
                               errors={}), 400
    errors = {}
    if request.method == "POST":
        _user, errors = accounts.reset_password_with_token(
            token, request.form.get("password") or "", request.form.get("confirm_password") or "")
        if not errors:
            flash("Your password was changed. Please log in with the new one.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", token=token, invalid=False,
                           errors=errors), (400 if errors else 200)


@bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    """Every role can change its own password (current password required)."""
    errors = {}
    if request.method == "POST":
        errors = accounts.change_own_password(
            current_user, request.form.get("current_password") or "",
            request.form.get("new_password") or "", request.form.get("confirm_password") or "")
        if not errors:
            # The password hash changed, which signed out every session. Keep this one.
            login_user(current_user._get_current_object())
            flash("Your password was changed.", "success")
            from app import home_endpoint
            return redirect(url_for(home_endpoint(current_user)))
        flash("Please fix the highlighted fields.", "danger")
    return render_template("auth/change_password.html", errors=errors), (
        400 if errors else 200)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.landing"))
