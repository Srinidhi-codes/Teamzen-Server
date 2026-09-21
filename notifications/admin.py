from django.contrib import admin
from django.urls import path
from django.http import HttpResponseRedirect
from django.core.mail import EmailMultiAlternatives
from django.contrib import messages
import traceback
from temp_email.welcome_email import get_welcome_email_html
from .models import Notification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'verb', 'created_at', 'is_read')
    change_list_template = "admin/notifications/notification_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('test-email/', self.admin_site.admin_view(self.test_email_view), name='test_email'),
        ]
        return custom_urls + urls

    def test_email_view(self, request):
        if request.method == "POST":
            email = request.POST.get("email")
            if email:
                try:
                    html_content = get_welcome_email_html(
                        employee_name="Admin User",
                        employee_email=email,
                        designation="System Admin",
                        joining_date="Today"
                    )
                    msg = EmailMultiAlternatives(
                        subject="[Test] Email Settings Validation",
                        body="Test email.",
                        from_email="no-reply@teamzen.com",
                        to=[email]
                    )
                    msg.attach_alternative(html_content, "text/html")
                    msg.send(fail_silently=False)
                    self.message_user(request, f"Successfully sent test email to {email}")
                except Exception as e:
                    self.message_user(request, f"Failed to send email: {e} \n {traceback.format_exc()}", level='ERROR')
            else:
                self.message_user(request, "Please provide an email address.", level='WARNING')
            return HttpResponseRedirect("../")
        return HttpResponseRedirect("../")
