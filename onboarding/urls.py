from django.urls import path

from onboarding.api_views import EmployeeDocumentUploadView

urlpatterns = [
    path(
        "onboarding/documents/upload/",
        EmployeeDocumentUploadView.as_view(),
        name="onboarding_document_upload",
    ),
]
