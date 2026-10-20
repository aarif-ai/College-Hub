"""Flask CLI commands: ``flask init-db`` and ``flask seed``."""
import click

from app.extensions import db


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create all database tables."""
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("seed")
    @click.option("--reset", is_flag=True, help="Drop all tables first (deletes data).")
    def seed(reset):
        """Fill the database with realistic demo data."""
        from app.seed import seed_demo_data
        if reset:
            db.drop_all()
            db.create_all()
        summary = seed_demo_data()
        click.echo(summary)


def register_account_cli(app):
    """Provision the staff accounts that students can never create."""

    @app.cli.command("create-faculty")
    @click.option("--username", prompt=True)
    @click.option("--email", prompt=True)
    @click.option("--name", prompt="Full name")
    @click.password_option()
    def create_faculty(username, email, name, password):
        """Create a Faculty Mentor account (not available through the website)."""
        from app import constants as C
        from app.models import User
        from app.services import accounts
        username = username.strip().lower()
        email = accounts.normalise_email(email)
        problem = (accounts._staff_username_problem(username) or accounts.email_problem(email)
                   or accounts.password_problem(password))
        if problem:
            raise click.ClickException(problem)
        user = User(username=username, email=email, name=name.strip(), role=C.FACULTY)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Faculty account '{username}' created.")
