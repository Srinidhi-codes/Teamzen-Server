import base64
import json
import urllib.request
from email.mime.base import MIMEBase
from urllib.error import HTTPError, URLError
from django.core.mail.backends.base import BaseEmailBackend
from django.conf import settings


class BrevoHTTPBackend(BaseEmailBackend):
    """
    Django email backend using Brevo's v3 REST API over HTTPS (port 443)
    so Render's outbound SMTP restrictions do not block delivery.
    """

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.api_key = getattr(settings, "BREVO_API_KEY", None)
        self.api_url = "https://api.brevo.com/v3/smtp/email"

    def _collect_attachments(self, email):
        attachments = []

        # Prefer public URL attachments (Brevo fetches them — avoids huge base64 payloads)
        for item in getattr(email, "brevo_attachment_urls", None) or []:
            url = (item.get("url") or "").strip()
            name = (item.get("name") or "attachment.pdf").strip()
            if url.startswith("http"):
                attachments.append({"url": url, "name": name})

        if hasattr(email, "attachments"):
            for attachment in email.attachments:
                if isinstance(attachment, MIMEBase):
                    payload = attachment.get_payload(decode=True)
                    filename = attachment.get_filename() or "attachment"
                    if payload:
                        attachments.append(
                            {
                                "name": filename,
                                "content": base64.b64encode(payload).decode("ascii"),
                            }
                        )
                    continue

                if isinstance(attachment, tuple) and len(attachment) >= 2:
                    filename, content = attachment[0], attachment[1]
                    if content is None:
                        continue
                    if isinstance(content, str):
                        content = content.encode("utf-8")
                    attachments.append(
                        {
                            "name": filename or "attachment",
                            "content": base64.b64encode(content).decode("ascii"),
                        }
                    )

        return attachments

    def _build_payload(self, email, include_attachments=True):
        html_content = None
        text_content = email.body if email.content_subtype != "html" else None

        if getattr(email, "content_subtype", "") == "html":
            html_content = email.body

        if hasattr(email, "alternatives"):
            for alt_content, alt_mimetype in email.alternatives:
                if alt_mimetype == "text/html":
                    html_content = alt_content

        attachments = self._collect_attachments(email) if include_attachments else []

        from_email = email.from_email or ""
        # Brevo expects sender as {email, name?}; strip display-name form if present
        sender_email = from_email
        sender_name = None
        if "<" in from_email and ">" in from_email:
            # e.g. "Teamzen <noreply@example.com>"
            sender_name = from_email.split("<", 1)[0].strip().strip('"') or None
            sender_email = from_email.split("<", 1)[1].split(">", 1)[0].strip()

        sender = {"email": sender_email}
        if sender_name:
            sender["name"] = sender_name

        payload = {
            "sender": sender,
            "to": [{"email": to} for to in email.to],
            "subject": email.subject,
        }

        if html_content:
            payload["htmlContent"] = html_content
        else:
            payload["textContent"] = text_content or getattr(email, "body", "")

        if attachments:
            payload["attachment"] = attachments

        return payload

    def _post(self, payload, timeout=30):
        req = urllib.request.Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "api-key": self.api_key,
            },
            method="POST",
        )
        response = urllib.request.urlopen(req, timeout=timeout)
        return response.getcode()

    def send_messages(self, email_messages):
        if not email_messages or not self.api_key:
            return 0

        num_sent = 0
        for email in email_messages:
            payload = None
            try:
                payload = self._build_payload(email, include_attachments=True)
                timeout = 45 if payload.get("attachment") else 15
                code = self._post(payload, timeout=timeout)
                if code in (200, 201):
                    num_sent += 1
                    continue
            except HTTPError as e:
                error_body = e.read().decode(errors="replace")
                print(f"Brevo HTTP {e.code}: {error_body[:500]}")
                # Only strip attachments as last resort so the invite still arrives
                if payload and payload.get("attachment"):
                    try:
                        payload_no_att = self._build_payload(email, include_attachments=False)
                        code = self._post(payload_no_att, timeout=15)
                        if code in (200, 201):
                            print(
                                "WARNING: Brevo accepted email WITHOUT attachment. "
                                f"Original error ({e.code}): {error_body[:300]}"
                            )
                            num_sent += 1
                            continue
                    except Exception as retry_err:
                        if not self.fail_silently:
                            raise Exception(
                                f"Brevo API HTTP Error: {e.code} - {error_body}; "
                                f"retry without attachment also failed: {retry_err}"
                            ) from retry_err
                if not self.fail_silently:
                    raise Exception(f"Brevo API HTTP Error: {e.code} - {error_body}")
            except URLError as e:
                if not self.fail_silently:
                    raise Exception(f"Brevo API Connection Error: {str(e.reason)}")
            except Exception:
                if not self.fail_silently:
                    raise

        return num_sent
