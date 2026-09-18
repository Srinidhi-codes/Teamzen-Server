from django.urls import path, include
from rest_framework.routers import DefaultRouter
from payroll.api_views import (
    DataImportUploadView,
    PayslipBulkUploadView,
    PayslipTemplateDemoDownloadView,
    PayslipTemplatePreviewView,
    BankPayoutExportView,
)

router = DefaultRouter()

urlpatterns = [
    path("payroll/import/upload/", DataImportUploadView.as_view(), name="payroll-import-upload"),
    path(
        "payroll/payslips/bulk-upload/",
        PayslipBulkUploadView.as_view(),
        name="payroll-payslip-bulk-upload",
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
