"""Certificate issuing and PDF generation."""
import io
import secrets

import qrcode
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app import constants as C
from app.extensions import db
from app.models import Attendance, Certificate, Event
from app.services import achievements
from app.services.errors import ServiceError
from app.services.notifications import notify
from app.utils import now

NAVY = HexColor("#12263f")
GOLD = HexColor("#a67c2d")
GREY = HexColor("#5b6675")
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_cert_code() -> str:
    while True:
        suffix = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        code = f"CERT-{now().year}-{suffix}"
        if not Certificate.query.filter_by(cert_code=code).first():
            return code


def issue_certificates(event: Event, issuer) -> int:
    """Issue a certificate to every attendee who does not have one yet.

    The event must be completed, and only verified students whose attendance
    was recorded are eligible. Returns the number of new certificates.
    """
    is_owner = issuer.role == C.ORGANIZER and event.organizer_id == issuer.id
    if not (is_owner or issuer.role == C.FACULTY):
        raise ServiceError("You cannot issue certificates for this event.", "forbidden")
    if event.status != C.COMPLETED:
        raise ServiceError("Certificates can only be issued after the event is marked completed.",
                           "invalid_state")

    attendees = Attendance.query.filter_by(event_id=event.id).all()
    if not attendees:
        raise ServiceError("No attendance has been recorded yet.", "no_attendance")

    created = 0
    attendees = [a for a in attendees if a.student.is_verified]
    for attendance in attendees:
        exists = Certificate.query.filter_by(
            student_id=attendance.student_id, event_id=event.id
        ).first()
        if exists:
            continue
        db.session.add(Certificate(
            cert_code=generate_cert_code(),
            student_id=attendance.student_id,
            event_id=event.id,
            issued_by_id=issuer.id,
        ))
        db.session.flush()
        notify(attendance.student,
               f"Your certificate for '{event.title}' is ready to download.",
               "/student/certificates")
        created += 1
        db.session.flush()
    db.session.flush()
    for attendance in attendees:
        achievements.evaluate_student(attendance.student)
    db.session.commit()
    return created


def certificate_pdf(certificate: Certificate, verify_url: str) -> bytes:
    """Render a landscape A4 certificate of participation as PDF bytes."""
    event = certificate.event
    width, height = landscape(A4)
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(width, height))
    pdf.setTitle(f"Certificate of Participation - {event.title}")
    pdf.setAuthor("CollegeHub")

    # Border
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(3)
    pdf.rect(24, 24, width - 48, height - 48)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1)
    pdf.rect(34, 34, width - 68, height - 68)

    centre = width / 2
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawCentredString(centre, height - 88, "CollegeHub")
    pdf.setFillColor(GREY)
    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(centre, height - 104, "COLLEGE EVENT, ENGAGEMENT AND OPERATIONS PLATFORM")

    pdf.setFillColor(NAVY)
    pdf.setFont("Times-Bold", 38)
    pdf.drawCentredString(centre, height - 165, "Certificate of Participation")
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1.5)
    pdf.line(centre - 90, height - 180, centre + 90, height - 180)

    pdf.setFillColor(GREY)
    pdf.setFont("Times-Italic", 15)
    pdf.drawCentredString(centre, height - 215, "This is to certify that")

    # Student name, shrunk to fit the page if it is long
    name = certificate.student.name
    size = 34
    while stringWidth(name, "Times-BoldItalic", size) > width - 140 and size > 16:
        size -= 1
    pdf.setFillColor(NAVY)
    pdf.setFont("Times-BoldItalic", size)
    pdf.drawCentredString(centre, height - 258, name)

    pdf.setFillColor(GREY)
    pdf.setFont("Times-Italic", 15)
    pdf.drawCentredString(centre, height - 290, "has successfully participated in")

    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 20)
    y = height - 322
    for line in simpleSplit(event.title, "Helvetica-Bold", 20, width - 160)[:2]:
        pdf.drawCentredString(centre, y, line)
        y -= 26

    pdf.setFillColor(GREY)
    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(
        centre, y - 6,
        f"held on {event.event_date.strftime('%d %B %Y')} at {event.venue}"[:110],
    )

    # Footer: certificate ID, QR verification, signature
    pdf.setFont("Helvetica", 9)
    pdf.drawString(70, 78, f"Certificate ID: {certificate.cert_code}")
    pdf.drawString(70, 64, f"Issued on: {certificate.issued_at.strftime('%d %B %Y')}")

    qr_img = qrcode.make(verify_url)
    qr_buf = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)
    pdf.drawImage(ImageReader(qr_buf), centre - 28, 52, 56, 56)
    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(centre, 44, "Scan to verify")

    issuer = certificate.issued_by
    signer = issuer.name if issuer else event.organizer.name
    role = C.ROLE_LABELS.get(issuer.role, "Organizer") if issuer else "Organizer"
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(0.8)
    pdf.line(width - 270, 92, width - 70, 92)
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawCentredString(width - 170, 78, signer)
    pdf.setFillColor(GREY)
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(width - 170, 64, f"Authorized by {role}, CollegeHub")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
