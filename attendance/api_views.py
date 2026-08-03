from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance.models import AttendanceRecord


class AttendanceSelfieUploadView(APIView):
    """Upload check-in/out selfie after a successful face punch (multipart)."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        record_id = request.data.get("attendance_record_id")
        kind = (request.data.get("kind") or "check_in").strip().lower()
        selfie = request.FILES.get("selfie")

        if not record_id or not selfie:
            return Response(
                {"error": "attendance_record_id and selfie are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if kind not in ("check_in", "check_out"):
            return Response(
                {"error": "kind must be check_in or check_out"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            record = AttendanceRecord.objects.get(id=record_id)
        except AttendanceRecord.DoesNotExist:
            return Response({"error": "Attendance record not found"}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if str(record.user_id) != str(user.id) and user.role not in (
            "admin",
            "superadmin",
            "hr",
        ):
            return Response({"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)

        if kind == "check_in":
            record.check_in_selfie = selfie
        else:
            record.check_out_selfie = selfie
        record.save(update_fields=["check_in_selfie", "check_out_selfie", "updated_at"])

        url = (
            record.check_in_selfie.url
            if kind == "check_in" and record.check_in_selfie
            else record.check_out_selfie.url
            if record.check_out_selfie
            else None
        )
        return Response({"success": True, "selfie_url": url})
