import strawberry
from typing import List, Optional
from strawberry.types import Info
from notifications.models import Notification
from .types import NotificationType, PaginatedNotificationResponse, EmailTemplateSettingType
from graphql_utils.pagination import get_paginated_results

@strawberry.type
class NotificationQuery:
    @strawberry.field
    def my_notifications(
        self, 
        info: Info, 
        level: Optional[str] = None,
        is_read: Optional[bool] = None,
        page: int = 1,
        page_size: int = 10
    ) -> PaginatedNotificationResponse:
        user = info.context.request.user
        if not user.is_authenticated:
            return PaginatedNotificationResponse(results=[], total=0, page=page, page_size=page_size)
        
        queryset = Notification.objects.filter(recipient=user).order_by('-created_at')
        if level:
            queryset = queryset.filter(level=level)
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read)
            
        paginated = get_paginated_results(queryset, page, page_size)
        return PaginatedNotificationResponse(**paginated)


    @strawberry.field
    def unread_notification_count(self, info, level: Optional[str] = None) -> int:
        user = info.context.request.user
        if not user.is_authenticated:
            return 0
        
        queryset = Notification.objects.filter(recipient=user, is_read=False)
        if level:
            queryset = queryset.filter(level=level)
            
        return queryset.count()

    @strawberry.field
    def email_template_settings(
        self,
        info: Info,
        category: Optional[str] = None
    ) -> List[EmailTemplateSettingType]:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            return []

        import json
        from notifications.models import EmailTemplateSetting
        from notifications.email_templates_registry import DEFAULT_EMAIL_TEMPLATES, render_email_html

        org = user.organization if getattr(user, 'organization_id', None) else None
        
        db_settings = {}
        if org:
            for s in EmailTemplateSetting.objects.filter(organization=org):
                db_settings[s.template_key] = s
        else:
            for s in EmailTemplateSetting.objects.filter(organization__isnull=True):
                db_settings[s.template_key] = s

        def norm_cat(c: str) -> str:
            s = (c or "").lower().strip()
            if "leave" in s: return "leave"
            if "sec" in s or "auth" in s or "access" in s or "login" in s: return "auth"
            if "attend" in s: return "attendance"
            if "pay" in s or "salary" in s or "finance" in s: return "payroll"
            if "life" in s or "onboard" in s or "hr" in s: return "lifecycle"
            if "gen" in s: return "general"
            return s

        results = []
        for key, spec in DEFAULT_EMAIL_TEMPLATES.items():
            setting = db_settings.get(key)
            is_enabled = setting.is_enabled if setting is not None else True

            custom_category = (setting.custom_category if setting and setting.custom_category else None)
            active_category = custom_category.strip() if custom_category else spec.get("category", "General")

            if category and category.lower() != "all":
                req_norm = norm_cat(category)
                cur_norm = norm_cat(active_category)
                if req_norm != cur_norm and active_category.lower() != category.lower():
                    continue

            custom_subject = setting.custom_subject if setting else None
            custom_headline = setting.custom_headline if setting else None
            custom_body = setting.custom_body if setting else None
            custom_cta_text = setting.custom_cta_text if setting else None
            custom_cta_url = setting.custom_cta_url if setting else None
            custom_footer = setting.custom_footer if setting else None
            is_raw_html_mode = setting.is_raw_html_mode if setting else False
            custom_full_html = setting.custom_full_html if setting else None

            active_subject = custom_subject or spec["default_subject"]
            active_headline = custom_headline or spec["default_headline"]
            active_body = custom_body or spec["default_body"]
            active_cta_text = custom_cta_text or spec["default_cta_text"]
            active_cta_url = custom_cta_url or spec["default_cta_url"]
            active_footer = custom_footer or spec["default_footer"]

            is_customized = bool(
                custom_category or custom_subject or custom_headline or custom_body or custom_cta_text or custom_cta_url or custom_footer or (is_raw_html_mode and custom_full_html)
            )

            sample_ctx = dict(spec.get("sample_context", {}))
            if org:
                sample_ctx["company_name"] = org.name

            preview_html = render_email_html(
                setting or spec,
                sample_ctx,
                company_name=org.name if org else "Teamzen"
            )

            results.append(EmailTemplateSettingType(
                key=key,
                name=spec["name"],
                category=active_category,
                description=spec["description"],
                is_enabled=is_enabled,
                default_subject=spec["default_subject"],
                default_headline=spec["default_headline"],
                default_body=spec["default_body"],
                default_cta_text=spec["default_cta_text"],
                default_cta_url=spec["default_cta_url"],
                default_footer=spec["default_footer"],
                custom_category=custom_category,
                custom_subject=custom_subject,
                custom_headline=custom_headline,
                custom_body=custom_body,
                custom_cta_text=custom_cta_text,
                custom_cta_url=custom_cta_url,
                custom_footer=custom_footer,
                is_raw_html_mode=is_raw_html_mode,
                custom_full_html=custom_full_html,
                active_subject=active_subject,
                active_headline=active_headline,
                active_body=active_body,
                active_cta_text=active_cta_text,
                active_cta_url=active_cta_url,
                active_footer=active_footer,
                available_tokens=spec.get("available_tokens", []),
                sample_context_json=json.dumps(sample_ctx),
                preview_html=preview_html,
                is_customized=is_customized,
                updated_at=setting.updated_at.isoformat() if setting and setting.updated_at else None
            ))

        return results

    @strawberry.field
    def render_email_preview(
        self,
        info: Info,
        template_key: str,
        custom_headline: Optional[str] = None,
        custom_body: Optional[str] = None,
        custom_cta_text: Optional[str] = None,
        custom_cta_url: Optional[str] = None,
        custom_footer: Optional[str] = None,
        is_raw_html_mode: Optional[bool] = False,
        custom_full_html: Optional[str] = None,
    ) -> str:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            return ""

        from notifications.email_templates_registry import DEFAULT_EMAIL_TEMPLATES, render_email_html

        spec = DEFAULT_EMAIL_TEMPLATES.get(template_key)
        if not spec:
            return "<p>Template not found.</p>"

        org = user.organization if getattr(user, 'organization_id', None) else None
        sample_ctx = dict(spec.get("sample_context", {}))
        if org:
            sample_ctx["company_name"] = org.name

        mock_setting = {
            "key": template_key,
            "custom_headline": custom_headline,
            "custom_body": custom_body,
            "custom_cta_text": custom_cta_text,
            "custom_cta_url": custom_cta_url,
            "custom_footer": custom_footer,
            "is_raw_html_mode": is_raw_html_mode or False,
            "custom_full_html": custom_full_html,
        }

        return render_email_html(
            mock_setting,
            sample_ctx,
            company_name=org.name if org else "Teamzen"
        )
