# Notifications: in-app always; email (SendGrid) + SMS (Africa's Talking) when configured.
import json
import urllib.parse
import urllib.request

import config
from deps import notify as _inapp


def _post_json(url, headers, payload, timeout=15):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status


def send_email(to, subject, html):
    if not (config.SENDGRID_API_KEY and to):
        return False
    try:
        _post_json("https://api.sendgrid.com/v3/mail/send",
                   {"Authorization": "Bearer " + config.SENDGRID_API_KEY, "Content-Type": "application/json"},
                   {"personalizations": [{"to": [{"email": to}]}],
                    "from": {"email": config.SENDGRID_FROM_EMAIL, "name": config.SENDGRID_FROM_NAME},
                    "subject": subject, "content": [{"type": "text/html", "value": html}]})
        return True
    except Exception:
        return False


def send_sms(to, message):
    if not (config.AT_API_KEY and to):
        return False
    phone = "".join(c for c in to if c.isdigit() or c == "+")
    if phone.startswith("0"):
        phone = "+233" + phone[1:]
    try:
        body = urllib.parse.urlencode({"username": config.AT_USERNAME, "to": phone,
                                       "message": message[:470], "from": config.AT_SENDER_ID}).encode()
        req = urllib.request.Request("https://api.africastalking.com/version1/messaging", data=body, method="POST",
                                     headers={"apiKey": config.AT_API_KEY, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status in (200, 201)
    except Exception:
        return False


def send_notification(db, user_id, title, body="", email="", phone=""):
    """In-app always; email + SMS fire-and-forget when services are configured."""
    _inapp(db, user_id, title, body)
    if email:
        send_email(email, f"{title} - GovFood", f"<h3>{title}</h3><p>{body}</p><p>GovFood · Ministry of Agriculture partnership</p>")
    if phone:
        send_sms(phone, f"{title}: {body}")
