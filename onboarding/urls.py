from django.urls import path

from onboarding.api_views import (
    EmployeeDocumentUploadView,
    OfferLetterUploadView,
    SignedOfferLetterUploadView,
)

urlpatterns = [
    path(
        "onboarding/documents/upload/",
        EmployeeDocumentUploadView.as_view(),
        name="onboarding_document_upload",
    ),
    path(
        "onboarding/offers/upload/",
        OfferLetterUploadView.as_view(),
        name="onboarding_offer_upload",
    ),
    path(
        "onboarding/offers/signed/upload/",
        SignedOfferLetterUploadView.as_view(),
        name="onboarding_signed_offer_upload",
    ),
]
