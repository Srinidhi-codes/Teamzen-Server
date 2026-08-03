from django.urls import path

from attendance.api_views import AttendanceSelfieUploadView

urlpatterns = [
    path("attendance/selfie/", AttendanceSelfieUploadView.as_view(), name="attendance_selfie_upload"),
]
