from django.urls import path, include
from rest_framework.routers import DefaultRouter
from payroll.api_views import (
    DataImportUploadView,
    PayslipTemplateCloneView,
    PayslipTemplateDemoDownloadView,
    PayslipTemplatePreviewView,
    BankPayoutExportView,
)

router = DefaultRouter()

urlpatterns = [
    path("payroll/import/upload/", DataImportUploadView.as_view(), name="payroll-import-upload"),
    path(
        "payroll/payslip-templates/clone/",
        PayslipTemplateCloneView.as_view(),
        name="payroll-payslip-template-clone",
    ),
    path(
        "payroll/payslip-templates/<int:template_id>/demo/",
        PayslipTemplateDemoDownloadView.as_view(),
        name="payroll-payslip-template-demo",
    ),
    path(
        "payroll/payslip-templates/<int:template_id>/preview/",
        PayslipTemplatePreviewView.as_view(),
        name="payroll-payslip-template-preview",
    ),
    path(
        "payroll/runs/<int:run_id>/bank-export/",
        BankPayoutExportView.as_view(),
        name="payroll-bank-export",
    ),
    path("", include(router.urls)),
]
