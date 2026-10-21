"""The author credit is shown on public and signed-in pages."""
from tests.conftest import login


def test_public_footer_has_author_credit(client):
    html = client.get("/").get_data(as_text=True)
    assert "Made with" in html and "Aarif Mushtaq" in html


def test_signed_in_pages_have_author_credit(client, users):
    login(client, users["organizer"])
    html = client.get("/organizer/").get_data(as_text=True)
    assert "Aarif Mushtaq" in html


def test_no_team_names_remain():
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    banned = ("Abrar", "Mishar", "Hameem")
    for path in list(root.glob("**/*.md")) + list(root.glob("app/**/*.html")) + list(root.glob(".github/**/*")):
        if path.is_file() and "instance" not in path.parts:
            text = path.read_text(errors="ignore")
            assert not any(name in text for name in banned), path
