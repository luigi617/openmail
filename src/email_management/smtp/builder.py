from __future__ import annotations
from email.message import EmailMessage as PyEmailMessage
from email.utils import make_msgid

from email_management.models import EmailMessage

def build_mime_message(msg: EmailMessage) -> PyEmailMessage:
    m = PyEmailMessage()
    m["Subject"] = msg.subject
    m["From"] = msg.from_email
    m["To"] = ", ".join(msg.to)
    if msg.cc:
        m["Cc"] = ", ".join(msg.cc)
    if msg.message_id:
        m["Message-ID"] = msg.message_id
    else:
        m["Message-ID"] = make_msgid()

    # headers
    for k, v in msg.headers.items():
        if k.lower() not in {"subject", "from", "to", "cc", "bcc", "message-id"}:
            m[k] = v

    # body
    if msg.text is not None and msg.html is not None:
        m.set_content(msg.text)
        m.add_alternative(msg.html, subtype="html")
    elif msg.html is not None:
        m.set_content("This email contains HTML content.")
        m.add_alternative(msg.html, subtype="html")
    else:
        m.set_content(msg.text or "")

    # attachments
    for a in msg.attachments:
        maintype, subtype = (a.content_type.split("/", 1) + ["octet-stream"])[:2]
        m.add_attachment(a.data, maintype=maintype, subtype=subtype, filename=a.filename)

    return m
