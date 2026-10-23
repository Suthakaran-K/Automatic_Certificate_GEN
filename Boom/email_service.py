import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

def send_certificate_email(to_email, participant_name, event_name, pdf_path):
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("MAIL_FROM", username)
    if not username or not password or not sender:
        raise RuntimeError("SMTP is not configured. Set SMTP_USERNAME, SMTP_PASSWORD, and MAIL_FROM.")
    message = EmailMessage()
    message["Subject"] = f"Your Digital Certificate – {event_name}"
    message["From"] = sender
    message["To"] = to_email
    message.set_content(
        f"Hello {participant_name},\n\nCongratulations! Thank you for participating in {event_name}. "
        "Your digital certificate is attached to this email.\n\nBest regards,\nCertificate Team"
    )
    path = Path(pdf_path)
    message.add_attachment(path.read_bytes(), maintype="application", subtype="pdf", filename=path.name)
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(username, password)
        refused = server.send_message(message)
        if refused:
            raise RuntimeError(f"SMTP server refused recipient(s): {', '.join(refused.keys())}")
