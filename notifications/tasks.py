from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model
from datetime import timedelta
import socket
import re
import os

from .models import Notification
from .email_backends import BrevoHTTPBackend

# Lazy imports for models to avoid circular dependencies if any
def get_leave_request_model():
    from leaves.models import LeaveRequest
    return LeaveRequest

User = get_user_model()

@shared_task(name="notifications.tasks.send_notification")
def send_notification(recipient_id, verb, message, actor_id=None, notification_type='BOTH', target_type=None, target_id=None, level='personal'):
    """
    Asynchronous task to send notifications via multiple channels.
    """
    try:
        recipient = User.objects.get(id=recipient_id)
        actor = User.objects.get(id=actor_id) if actor_id else None
        
        # 1. Create Notification record in DB for push/tracking
        notification = Notification.objects.create(
            recipient=recipient,
            actor=actor,
            verb=verb,
            message=message,
            notification_type=notification_type,
            target_type=target_type,
            target_id=target_id,
            level=level
        )

        # 2. Send Push if requested (Implementation for Channels)
        if notification_type in ['PUSH', 'BOTH']:
            import asyncio
            from channels.layers import get_channel_layer
            
            async def push_to_channel():
                channel_layer = get_channel_layer()
                await channel_layer.group_send(
                    f"user_{recipient_id}",
                    {
                        "type": "send_notification",
                        "message": {
                            "id": str(notification.id),
                            "verb": verb,
                            "message": message,
                            "level": level,
                            "createdAt": notification.created_at.isoformat(),
                            "isRead": notification.is_read,
                            "actor": {
                                "id": str(actor.id) if actor else None,
                                "firstName": actor.first_name if actor else "System",
                                "lastName": actor.last_name if actor else ""
                            }
                        }
                    }
                )
            
            try:
                # Use native asyncio to avoid asgiref thread-deadlocks inside Celery
                asyncio.run(push_to_channel())
            except RuntimeError:
                # If an event loop is already running (e.g., in some test environments or specific worker pools),
                # fallback to asgiref as a last resort.
                from asgiref.sync import async_to_sync
                async_to_sync(push_to_channel)()
                
        # 3. Send Email if requested
        if notification_type in ['EMAIL', 'BOTH']:
            # Dispatch to a separate background worker to prevent slow SMTP connections from blocking this thread
            send_email_notification.delay(recipient_id, "Notification: " + verb, message, target_type, target_id, actor_id=actor_id)
            
        return f"Notification {notification.id} processed for {recipient.email}"
    except Exception as e:
        return f"Error sending notification: {str(e)}"

@shared_task(name="notifications.tasks.send_email_notification")
def send_email_notification(recipient_id, subject, message, target_type=None, target_id=None, actor_id=None):
    """
    Dedicated task for sending emails with a strict timeout to prevent SMTP freezes.
    Supports dynamic HTML templates if target_type is provided.
    """
    try:
        recipient = User.objects.get(id=recipient_id)
        html_content = None
        
        # 1. Generate HTML content based on target_type
        if target_type == "Leave Request" and target_id:
            LeaveRequest = get_leave_request_model()
            try:
                req = LeaveRequest.objects.select_related('user').get(id=int(target_id))
                employee_name = f"{req.user.first_name} {req.user.last_name}"
                manager_name = recipient.first_name or "Manager"
                start_date = req.from_date.strftime('%b %d, %Y')
                end_date = req.to_date.strftime('%b %d, %Y')
                duration_str = str(req.duration_days).rstrip('0').rstrip('.') if '.' in str(req.duration_days) else str(req.duration_days)
                leave_type = req.leave_type.name
                dashboard_url = "https://teamzen-client.vercel.app/leaves" if recipient.role == 'employee' else "https://teamzen-admin.vercel.app/leaves"
                
                actor_name = ""
                if actor_id:
                    actor = User.objects.filter(id=actor_id).first()
                    if actor:
                        actor_name = f"{actor.first_name} {actor.last_name}"

                if req._status == 'rejected':
                    from temp_email.leave_rejected_email import get_leave_rejected_email_html
                    reason = req.approval_comments if req.approval_comments else ""
                    html_content = get_leave_rejected_email_html(
                        employee_name=employee_name,
                        leave_type=leave_type,
                        start_date=start_date,
                        end_date=end_date,
                        duration=duration_str,
                        rejected_by=actor_name,
                        reason=reason,
                        dashboard_url=dashboard_url
                    )
                elif req._status == 'approved':
                    from temp_email.leave_approved_email import get_leave_approved_email_html
                    remarks = req.approval_comments if req.approval_comments else ""
                    html_content = get_leave_approved_email_html(
                        employee_name=employee_name,
                        leave_type=leave_type,
                        start_date=start_date,
                        end_date=end_date,
                        duration=duration_str,
                        approved_by=actor_name,
                        remarks=remarks,
                        dashboard_url=dashboard_url
                    )
                else: # pending
                    from temp_email.leave_request_email import get_leave_request_email_html
                    html_content = get_leave_request_email_html(
                        manager_name=manager_name,
                        employee_name=employee_name,
                        leave_type=leave_type,
                        start_date=start_date,
                        end_date=end_date,
                        duration=duration_str,
                        reason=req.reason,
                        approval_url=dashboard_url
                    )
            except Exception as e:
                print(f"Failed to route Leave Request {target_id}: {e}")
        
        elif target_type == "Announcement":
            try:
                from temp_email.announcement_email import get_announcement_email_html
                html_content = get_announcement_email_html(
                    employee_name=f"{recipient.first_name} {recipient.last_name}",
                    announcement_title=subject,
                    announcement_body=message,
                    posted_by="HR Department",
                    posted_date="Just Now"
                )
            except Exception as e:
                print(f"Failed to route Announcement: {e}")
                
        elif target_type == "Welcome":
            from temp_email.welcome_email import get_welcome_email_html
            html_content = get_welcome_email_html(
                employee_name=f"{recipient.first_name} {recipient.last_name}",
                employee_email=recipient.email,
                login_url="https://teamzen-client.vercel.app/login",
                logo_url="https://teamzen-admin.vercel.app/logo.png"
            )
            
        elif target_type == "Password Reset":
            from temp_email.password_reset_email import get_password_reset_email_html
            html_content = get_password_reset_email_html(
                employee_name=f"{recipient.first_name} {recipient.last_name}",
                reset_url=f"https://teamzen-client.vercel.app/reset-password?token={target_id}" if target_id else "#",
                logo_url="https://teamzen-admin.vercel.app/logo.png"
            )
            
        elif target_type == "Payroll":
            from temp_email.payroll_email import get_payroll_email_html
            html_content = get_payroll_email_html(
                employee_name=f"{recipient.first_name} {recipient.last_name}",
                month=target_id if target_id else "Current Month",
                net_salary="Confidential", 
                payslip_url="https://teamzen-client.vercel.app/payslips",
                logo_url="https://teamzen-admin.vercel.app/logo.png"
            )

        # 2. Build and send the email
        email = EmailMultiAlternatives(
            subject=subject,
            body=message, # Plain text fallback
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient.email],
            connection=BrevoHTTPBackend()
        )
        
        if html_content:
            email.attach_alternative(html_content, "text/html")
        
        # Setting a 15-second timeout on the standard socket module just in case
        socket.setdefaulttimeout(15)
        email.send(fail_silently=False)
        return f"Email sent successfully via Brevo HTTP to {recipient.email}"

    except socket.timeout:
        return f"CRITICAL: Email to {recipient.email} FAILED. {settings.EMAIL_HOST}:{settings.EMAIL_PORT} blocked the Render IP (Connection Timeout)."
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return f"Error sending email: {str(e)}"

@shared_task(name="notifications.tasks.cleanup_read_notifications")
def cleanup_read_notifications():
    """
    Delete notifications that have been read for more than 24 hours.
    """
    from django.utils import timezone
    from datetime import timedelta
    
    threshold = timezone.now() - timedelta(hours=24)
    # updated_at will change when is_read is set to True
    deleted_count, _ = Notification.objects.filter(is_read=True, updated_at__lte=threshold).delete()
    return f"Deleted {deleted_count} old notifications."
