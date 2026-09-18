from django.urls import path
from attendance.api_views import AttendanceSelfieUploadView, FaceExtractView

urlpatterns = [
    path("attendance/selfie/", AttendanceSelfieUploadView.as_view(), name="attendance_selfie_upload"),
    path("attendance/face/extract/", FaceExtractView.as_view(), name="attendance_face_extract"),
]
