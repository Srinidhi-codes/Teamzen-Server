from django.urls import path
from feedback.api_views import FeedbackAttachmentUploadView

urlpatterns = [
    path(
        "feedback/attachments/",
        FeedbackAttachmentUploadView.as_view(),
        name="feedback_attachment_upload",
    ),
]
