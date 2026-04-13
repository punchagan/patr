import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email(gmail, sender, to_email, subject, html_body, plain_body) -> None:
    """Send an email with both plain-text and HTML parts.

    Attaches plain_body first (text/plain), then html_body (text/html), so
    clients that support HTML prefer it while plain-text clients get readable
    markdown. Having both parts improves deliverability/spam scoring.
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    gmail.users().messages().send(userId="me", body={"raw": raw}).execute()
