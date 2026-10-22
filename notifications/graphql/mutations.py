import strawberry
from typing import Optional
from notifications.models import Notification
from .types import NotificationType

@strawberry.type
class NotificationMutation:
    @strawberry.mutation
    def mark_notification_as_read(self, info, id: strawberry.ID) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
        
        try:
            notification = Notification.objects.get(id=id, recipient=user)
            notification.is_read = True
            notification.save()
            return True
        except Notification.DoesNotExist:
            return False

    @strawberry.mutation
    def delete_notification(self, info, id: strawberry.ID) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
        
        try:
            notification = Notification.objects.get(id=id, recipient=user)
            notification.delete()
            return True
        except Notification.DoesNotExist:
            return False

    @strawberry.mutation
    def delete_all_read_notifications(self, info) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
        
        Notification.objects.filter(recipient=user, is_read=True).delete()
        return True

    @strawberry.mutation
    def mark_all_notifications_as_read(self, info) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
        
        Notification.objects.filter(recipient=user, is_read=False).update(is_read=True)
        return True

    @strawberry.mutation
    def send_custom_notification(
        self, 
        info, 
        recipient_id: strawberry.ID, 
        message: str, 
        verb: str = "announcement",
        notification_type: str = "BOTH"
    ) -> bool:
        user = info.context.request.user
        # In a real app, check if user is admin/hr
        if not user.is_authenticated or user.role not in ['admin', 'superadmin', 'hr']:
            return False
        
        from notifications.tasks import send_notification
        send_notification.delay(
            recipient_id=recipient_id,
            verb=verb,
            message=message,
            actor_id=user.id,
            notification_type=notification_type,
            level='personal'
        )
        return True

    @strawberry.mutation
    def send_broadcast_notification(
        self,
        info,
        message: str,
        verb: str = "broadcast",
        notification_type: str = "PUSH",
        send_to_bots: bool = False,
        image_base64: str | None = None
    ) -> bool:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            return False
        
        from users.models import CustomUser
        from notifications.tasks import send_notification
        
        image_url = None
        if image_base64:
            import base64
            import re
            import uuid
            import cloudinary.uploader
            
            # Extract base64 data
            raw = image_base64
            match = re.match(r"^data:image/(png|jpeg|jpg|webp|gif);base64,(.+)$", raw, re.I | re.S)
            if match:
                ext = "jpg" if match.group(1).lower() in ("jpeg", "jpg") else match.group(1).lower()
                raw = match.group(2)
            else:
                ext = "jpg"
            
            try:
                data = base64.b64decode(raw)
                public_id = f"broadcast_{user.id}_{uuid.uuid4().hex[:8]}"
                upload_result = cloudinary.uploader.upload(
                    data,
                    public_id=public_id,
                    folder="media/broadcasts",
                    resource_type="image",
                    overwrite=True,
                    format=ext,
                )
                image_url = upload_result.get("secure_url")
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Cloudinary upload failed: {e}")
        
        # In a real large-scale app, this should be a single task that iterates in background
        recipients = CustomUser.objects.filter(organization=user.organization, is_active=True) if user.organization_id else CustomUser.objects.filter(is_active=True)
        for recipient in recipients:
            send_notification.delay(
                recipient_id=recipient.id,
                verb=verb,
                message=message,
                actor_id=user.id,
                notification_type=notification_type,
                target_type="Announcement" if verb == "announcement" else None,
                level='personal',
                extra_context={"image_url": image_url} if image_url else None
            )
            
        if send_to_bots:
            from notifications.tasks import broadcast_to_bots
            import json
            
            bot_title = verb.title()
            bot_body = message
            bot_footer = ""
            try:
                data = json.loads(message)
                if isinstance(data, dict):
                    bot_title = data.get("title") or bot_title
                    bot_body = data.get("body", message)
                    bot_footer = data.get("footer", "")
            except Exception:
                pass
                
            html_message = f"<b>{bot_title}</b>\n\n{bot_body}"
            if bot_footer:
                html_message += f"\n\n_ {bot_footer} _"
                
            broadcast_to_bots.delay(html_message=html_message, image_url=image_url)
            
        return True

    @strawberry.mutation
    def update_email_template(
        self,
        info,
        template_key: str,
        is_enabled: bool,
        custom_category: Optional[str] = None,
        custom_subject: Optional[str] = None,
        custom_headline: Optional[str] = None,
        custom_body: Optional[str] = None,
        custom_cta_text: Optional[str] = None,
        custom_cta_url: Optional[str] = None,
        custom_footer: Optional[str] = None,
        is_raw_html_mode: Optional[bool] = False,
        custom_full_html: Optional[str] = None,
    ) -> bool:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized to edit email templates. Requires Admin or Superadmin role.")

        from notifications.models import EmailTemplateSetting
        org = user.organization if getattr(user, 'organization_id', None) else None

        setting, _ = EmailTemplateSetting.objects.get_or_create(
            organization=org,
            template_key=template_key,
            defaults={"is_enabled": is_enabled}
        )
        setting.is_enabled = is_enabled
        setting.custom_category = custom_category.strip() if custom_category else None
        setting.custom_subject = custom_subject.strip() if custom_subject else None
        setting.custom_headline = custom_headline.strip() if custom_headline else None
        setting.custom_body = custom_body.strip() if custom_body else None
        setting.custom_cta_text = custom_cta_text.strip() if custom_cta_text else None
        setting.custom_cta_url = custom_cta_url.strip() if custom_cta_url else None
        setting.custom_footer = custom_footer.strip() if custom_footer else None
        setting.is_raw_html_mode = bool(is_raw_html_mode)
        setting.custom_full_html = custom_full_html.strip() if custom_full_html else None
        setting.updated_by = user
        setting.save()
        return True

    @strawberry.mutation
    def toggle_email_template(
        self,
        info,
        template_key: str,
        is_enabled: bool
    ) -> bool:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized. Requires Admin or Superadmin role.")

        from notifications.models import EmailTemplateSetting
        org = user.organization if getattr(user, 'organization_id', None) else None

        setting, _ = EmailTemplateSetting.objects.get_or_create(
            organization=org,
            template_key=template_key,
            defaults={"is_enabled": is_enabled}
        )
        setting.is_enabled = is_enabled
        setting.updated_by = user
        setting.save(update_fields=['is_enabled', 'updated_by', 'updated_at'])
        return True

    @strawberry.mutation
    def reset_email_template(
        self,
        info,
        template_key: str
    ) -> bool:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized. Requires Admin or Superadmin role.")

        from notifications.models import EmailTemplateSetting
        org = user.organization if getattr(user, 'organization_id', None) else None

        setting = EmailTemplateSetting.objects.filter(
            organization=org,
            template_key=template_key
        ).first()
        if setting:
            setting.custom_category = None
            setting.custom_subject = None
            setting.custom_headline = None
            setting.custom_body = None
            setting.custom_cta_text = None
            setting.custom_cta_url = None
            setting.custom_footer = None
            setting.custom_full_html = None
            setting.is_raw_html_mode = False
            setting.updated_by = user
            setting.save()
        return True

    @strawberry.mutation
    def send_test_email(
        self,
        info,
        template_key: str,
        recipient_email: str
    ) -> bool:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized. Requires Admin or Superadmin role.")

        from django.core.mail import EmailMultiAlternatives
        from django.conf import settings
        from notifications.models import EmailTemplateSetting
        from notifications.email_templates_registry import DEFAULT_EMAIL_TEMPLATES, render_email_html, substitute_tokens
        from notifications.email_backends import BrevoHTTPBackend

        spec = DEFAULT_EMAIL_TEMPLATES.get(template_key)
        if not spec:
            raise Exception("Invalid template key")

        org = user.organization if getattr(user, 'organization_id', None) else None
        setting = EmailTemplateSetting.get_setting_or_default(org, template_key)

        sample_ctx = dict(spec.get("sample_context", {}))
        if org:
            sample_ctx["company_name"] = org.name

        active_subject = (setting.custom_subject if setting and setting.custom_subject else spec["default_subject"])
        subject = f"[Test Preview] " + substitute_tokens(active_subject, sample_ctx)

        html_content = render_email_html(
            setting or spec,
            sample_ctx,
            company_name=org.name if org else "Teamzen"
        )

        email = EmailMultiAlternatives(
            subject=subject,
            body="This is a test preview of your customized Teamzen email template.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email],
            connection=BrevoHTTPBackend()
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)
        return True
