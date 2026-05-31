"""Email service — Resend integration for transactional emails."""

from __future__ import annotations

from app.config import settings


def send_report_ready_email(*, to_email: str, address: str, property_id: str) -> None:
    """Send an email notifying the user their report is ready.

    Uses the Resend API.  In development the API key may be blank,
    in which case this is a no-op.
    """
    if not settings.RESEND_API_KEY:
        return

    import resend

    resend.api_key = settings.RESEND_API_KEY
    resend.Emails.send(
        {
            "from": "OZ Property Report <reports@ozpropertyreport.com>",
            "to": [to_email],
            "subject": f"Your OZ Property Report is Ready — {address}",
            "html": f"""
                <h2>Your report is ready!</h2>
                <p>The full property report for <strong>{address}</strong> is now available.</p>
                <p><a href="https://ozpropertyreport.com/property/{property_id}">View Report</a></p>
            """,
        }
    )
