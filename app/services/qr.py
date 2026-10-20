"""QR token creation, verification and image rendering.

The QR code holds a *signed* token containing the registration ID. Signing
means a printed or edited code that was not issued by CollegeHub fails
verification. The server still looks the registration up in the database
for every scan, so the token alone never grants attendance.
"""
import io

import qrcode
from flask import current_app
from itsdangerous import BadSignature, URLSafeSerializer

TOKEN_PREFIX = "CH1."
_SALT = "collegehub-attendance-qr"


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt=_SALT)


def make_token(reg_code: str) -> str:
    return TOKEN_PREFIX + _serializer().dumps(reg_code)


def read_token(token: str) -> str | None:
    """Return the registration code inside ``token`` or ``None`` if invalid."""
    token = (token or "").strip()
    if not token.startswith(TOKEN_PREFIX):
        return None
    try:
        value = _serializer().loads(token[len(TOKEN_PREFIX):])
    except BadSignature:
        return None
    return value if isinstance(value, str) else None


def qr_png(data: str) -> bytes:
    """Render ``data`` as a PNG QR code."""
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=3
    )
    qr.add_data(data)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#12263f", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
