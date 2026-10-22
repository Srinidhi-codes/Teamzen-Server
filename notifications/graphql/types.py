import strawberry
from datetime import datetime
from typing import Optional, List
from notifications.models import Notification
from users.graphql.types import UserType

@strawberry.django.type(Notification)
class NotificationType:
    id: strawberry.ID
    recipient: 'UserType'
    actor: Optional['UserType']
    verb: str
    target_type: Optional[str]
    target_id: Optional[str]
    image_url: Optional[str]
    message: str
    notification_type: str
    level: str
    is_read: bool
    created_at: datetime
    updated_at: datetime

@strawberry.type
class PaginatedNotificationResponse:
    results: List[NotificationType]
    total: int
    page: int
    page_size: int


@strawberry.type
class EmailTemplateSettingType:
    key: str
    name: str
    category: str
    description: str
    is_enabled: bool

    default_subject: str
    default_headline: str
    default_body: str
    default_cta_text: str
    default_cta_url: str
    default_footer: str

    custom_category: Optional[str] = None
    custom_subject: Optional[str] = None
    custom_headline: Optional[str] = None
    custom_body: Optional[str] = None
    custom_cta_text: Optional[str] = None
    custom_cta_url: Optional[str] = None
    custom_footer: Optional[str] = None
    is_raw_html_mode: bool = False
    custom_full_html: Optional[str] = None

    active_subject: str
    active_headline: str
    active_body: str
    active_cta_text: str
    active_cta_url: str
    active_footer: str

    available_tokens: List[str]
    sample_context_json: str
    preview_html: str
    is_customized: bool
    updated_at: Optional[str] = None


