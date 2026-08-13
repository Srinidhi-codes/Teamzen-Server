from django.urls import path

from documents.api_views import (
    IssuedDocumentDownloadView,
    PublishIssuedDocumentView,
    VaultDocumentUploadView,
)
from documents.form16_api import (
    Form16BulkPublishView,
    Form16GenerateView,
    Form16PreviewMatchView,
)

urlpatterns = [
    path(
        "documents/upload/",
        VaultDocumentUploadView.as_view(),
        name="vault-document-upload",
    ),
    path(
        "documents/issued/publish/",
        PublishIssuedDocumentView.as_view(),
        name="issued-document-publish",
    ),
    path(
        "documents/issued/<int:document_id>/download/",
        IssuedDocumentDownloadView.as_view(),
        name="issued-document-download",
    ),
    path(
        "documents/form16/bulk-publish/",
        Form16BulkPublishView.as_view(),
        name="form16-bulk-publish",
    ),
    path(
        "documents/form16/generate/",
        Form16GenerateView.as_view(),
        name="form16-generate",
    ),
    path(
        "documents/form16/preview-match/",
        Form16PreviewMatchView.as_view(),
        name="form16-preview-match",
    ),
]
