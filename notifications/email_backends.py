import json
import urllib.request
from urllib.error import HTTPError, URLError
from django.core.mail.backends.base import BaseEmailBackend
from django.conf import settings

class BrevoHTTPBackend(BaseEmailBackend):
    """
    A custom Django Email Backend that uses Brevo's v3 REST API over HTTP (Port 443) 
    instead of standard SMTP (Port 587) to bypass Render's strict outbound firewall rules.
    """
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.api_key = getattr(settings, 'BREVO_API_KEY', None)
        self.api_url = 'https://api.brevo.com/v3/smtp/email'

    def send_messages(self, email_messages):
        if not email_messages or not self.api_key:
            return 0
        
        num_sent = 0
        for email in email_messages:
            payload = {
                "sender": {"email": email.from_email},
                "to": [{"email": to} for to in email.to],
                "subject": email.subject,
                "htmlContent": email.body.replace('\n', '<br>') if email.content_subtype == 'html' else None,
                "textContent": email.body if email.content_subtype != 'html' else None
            }
            
            # Clean up None values
            if payload["htmlContent"] is None:
                del payload["htmlContent"]
            if payload["textContent"] is None:
                del payload["textContent"]

            req = urllib.request.Request(
                self.api_url, 
                data=json.dumps(payload).encode('utf-8'),
                headers={
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'api-key': self.api_key
                },
                method='POST'
            )

            try:
                response = urllib.request.urlopen(req, timeout=10)
                if response.getcode() in [200, 201]:
                    num_sent += 1
            except HTTPError as e:
                error_msg = e.read().decode()
                if not self.fail_silently:
                    raise Exception(f"Brevo API HTTP Error: {e.code} - {error_msg}")
            except URLError as e:
                if not self.fail_silently:
                    raise Exception(f"Brevo API Connection Error: {str(e.reason)}")
            except Exception as e:
                if not self.fail_silently:
                    raise
        
        return num_sent
