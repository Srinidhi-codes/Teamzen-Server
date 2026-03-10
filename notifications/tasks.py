from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
from .models import Notification

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
    import socket
    try:
        recipient = User.objects.get(id=recipient_id)
        
        # Free Render IPs are frequently heavily rate-limited or blocked by smtp.gmail.com.
        # We must enforce a strict connection timeout so the Celery worker doesn't hang for 135 seconds.
        from django.core.mail import EmailMessage
        from django.template.loader import render_to_string
        
        html_content = None
        
        # Determine the correct template based on target_type
        if target_type == "Leave Request" and target_id:
            from leaves.models import LeaveRequest
            try:
                req = LeaveRequest.objects.select_related('user').get(id=int(target_id))
                context = {
                    'employeeName': f"{req.user.first_name} {req.user.last_name}",
                    'managerName': recipient.first_name or "Manager",
                    'status': req._status,
                    'dates': f"{req.from_date.strftime('%b %d, %Y')} to {req.to_date.strftime('%b %d, %Y')}",
                    'duration': str(req.duration_days).rstrip('0').rstrip('.') if '.' in str(req.duration_days) else str(req.duration_days),
                    'leaveType': req.leave_type.name,
                    'dashboardUrl': "https://teamzen-client.vercel.app/leaves" if recipient.role == 'employee' else "https://teamzen-admin.vercel.app/leaves"
                }

                if req._status == 'rejected':
                    if req.approval_comments:
                        context['reason'] = req.approval_comments
                    if actor_id:
                        actor = User.objects.filter(id=actor_id).first()
                        if actor:
                            context['rejectedBy'] = f"{actor.first_name} {actor.last_name}"
                    template_name = 'LeaveRejectedAlert.html'
                elif req._status == 'approved':
                    if req.approval_comments:
                        context['remarks'] = req.approval_comments
                    if actor_id:
                        actor = User.objects.filter(id=actor_id).first()
                        if actor:
                            context['approvedBy'] = f"{actor.first_name} {actor.last_name}"
                    template_name = 'LeaveApprovedAlert.html'
                else:
                    if req.reason:
                        context['reason'] = req.reason
                    template_name = 'LeaveRequestAlert.html'

                import re
                import os
                from django.conf import settings
                
                admin_dir = settings.BASE_DIR.parent / "admin"
                template_path = os.path.join(admin_dir, template_name)
                
                with open(template_path, 'r', encoding='utf-8') as f:
                    raw_html = f.read()

                # Native logic to inject string bindings by mimicking Django engine variables
                clean_html = re.sub(r'{{.*?}}', lambda m: m.group(0).replace('<!-- -->', ''), raw_html, flags=re.DOTALL)
                html_content = re.sub(r'{{\s*(.*?)\s*}}', r'{{\1}}', clean_html, flags=re.DOTALL)
                html_content = re.sub(r'{%.*?%}', '', html_content, flags=re.DOTALL)
                
                for key, value in context.items():
                    html_content = html_content.replace(f'{{{{{key}}}}}', str(value))
                    
            except Exception as e:
                print(f"Failed to route Leave Request {target_id}: {e}")
                
        elif target_type == "Welcome":
            from temp_email.welcome_email import get_welcome_email_html
            # In a real scenario we'd pass kwargs securely or handle kwargs out of message, 
            # but routing framework ensures target_type fires appropriately
            html_content = get_welcome_email_html(
                employee_name=f"{recipient.first_name} {recipient.last_name}",
                employee_email=recipient.email,
                login_url="https://teamzen-client.vercel.app/login",
                logo_url="https://teamzen-admin.vercel.app/logo.png"
            )
            
        elif target_type == "Password Reset":
            from temp_email.password_reset_email import get_password_reset_email_html
            # Target ID holds the token in this architectural design mapping
            html_content = get_password_reset_email_html(
                employee_name=f"{recipient.first_name} {recipient.last_name}",
                reset_url=f"https://teamzen-client.vercel.app/reset-password?token={target_id}" if target_id else "#",
                logo_url="https://teamzen-admin.vercel.app/logo.png"
            )
            
        elif target_type == "Payroll":
            from temp_email.payroll_email import get_payroll_email_html
            # Target ID holds the payslip reference id or month index
            html_content = get_payroll_email_html(
                employee_name=f"{recipient.first_name} {recipient.last_name}",
                month=target_id if target_id else "Current Month",
                net_salary="Confidential", 
                payslip_url="https://teamzen-client.vercel.app/payslips",
                logo_url="https://teamzen-admin.vercel.app/logo.png"
            )

        from django.core.mail import EmailMultiAlternatives
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=message, # Plain text fallback strictly for spam filter compliance
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient.email],
        )
        
        if html_content:
            email.attach_alternative(html_content, "text/html")

        # 10 second timeout to fail fast if connection drops
        socket.setdefaulttimeout(10)
        
        email.send(fail_silently=False)
        return f"Email sent successfully to {recipient.email}"
    except socket.timeout:
        return f"CRITICAL: Email to {recipient.email} FAILED. {settings.EMAIL_HOST}:{settings.EMAIL_PORT} blocked the Render IP (10s Connection Timeout)."
    except Exception as e:
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
