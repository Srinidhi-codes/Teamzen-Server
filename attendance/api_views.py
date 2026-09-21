import base64
import re
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.core.files.base import ContentFile

from attendance.models import AttendanceRecord
from attendance.face_engine import extract_face_descriptor_from_bytes, match_faces


def _get_image_bytes_and_file(request, file_key="photo", base64_key="photo_base64"):
    """Extract raw image bytes and a Django ContentFile from either multipart file or JSON base64."""
    if file_key in request.FILES:
        f = request.FILES[file_key]
        return f.read(), f

    raw = request.data.get(base64_key) or request.data.get(file_key)
    if isinstance(raw, str) and len(raw) > 50:
        match = re.match(r"^data:image/(png|jpeg|jpg|webp);base64,(.+)$", raw, re.I | re.S)
        if match:
            ext = "jpg" if match.group(1).lower() in ("jpeg", "jpg") else match.group(1).lower()
            b64_str = match.group(2)
        else:
            ext = "jpg"
            b64_str = raw
        try:
            img_bytes = base64.b64decode(b64_str)
            content_file = ContentFile(img_bytes, name=f"upload.{ext}")
            return img_bytes, content_file
        except Exception:
            return None, None

    return None, None


class AttendanceSelfieUploadView(APIView):
    """Upload check-in/out selfie after a successful face punch (multipart or JSON base64)."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        record_id = request.data.get("attendance_record_id")
        kind = (request.data.get("kind") or "check_in").strip().lower()
        _, selfie_file = _get_image_bytes_and_file(request, "selfie", "selfie_base64")

        if not record_id or not selfie_file:
            return Response(
                {"error": "attendance_record_id and selfie (file or selfie_base64) are required"},
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

        filename = f"selfie_{record.id}_{kind}.jpg"
        if kind == "check_in":
            record.check_in_selfie.save(filename, selfie_file, save=False)
            record.save(update_fields=["check_in_selfie", "updated_at"])
        else:
            record.check_out_selfie.save(filename, selfie_file, save=False)
            record.save(update_fields=["check_out_selfie", "updated_at"])

        url = (
            record.check_in_selfie.url
            if kind == "check_in" and record.check_in_selfie
            else record.check_out_selfie.url
            if record.check_out_selfie
            else None
        )
        return Response({"success": True, "selfie_url": url})


class FaceExtractView(APIView):
    """
    Extract 128-d face descriptor from an uploaded photo or verify it against the user's enrollment.
    Supports both multipart ('photo') and JSON ('photo_base64').
    Optionally accepts 'verify': true to compare against request.user's enrolled face.
    Optionally accepts 'enroll': true to enroll the face for request.user.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        image_bytes, photo_file = _get_image_bytes_and_file(request, "photo", "photo_base64")
        if not image_bytes:
            return Response(
                {"error": "A photo file ('photo') or 'photo_base64' string is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            descriptor, confidence = extract_face_descriptor_from_bytes(image_bytes)
        except ValueError as ve:
            return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Face extraction error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        should_verify = str(request.data.get("verify", "")).lower() in ("true", "1", "yes")
        should_enroll = str(request.data.get("enroll", "")).lower() in ("true", "1", "yes")

        user = request.user

        if should_enroll:
            user.face_descriptor = descriptor
            user.face_enrolled_at = timezone.now()
            # Save enrollment image
            if photo_file:
                user.face_enrollment_image.save(f"face_{user.id}.jpg", photo_file, save=False)
            user.save(update_fields=["face_descriptor", "face_enrolled_at", "face_enrollment_image"])
            return Response({
                "success": True,
                "message": "Face enrolled successfully.",
                "descriptor": descriptor,
                "detection_confidence": confidence,
            })

        verified = True
        match_score = 1.0
        distance = 0.0

        if should_verify:
            if not user.face_descriptor or len(user.face_descriptor) != 128:
                return Response(
                    {"error": "User has not enrolled a face yet. Please enroll first."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            distance, match_score, is_match = match_faces(descriptor, user.face_descriptor)
            verified = is_match
            if not is_match:
                return Response({
                    "verified": False,
                    "distance": round(distance, 3),
                    "match_score": round(match_score, 3),
                    "error": f"Face does not match enrolled profile (distance {distance:.2f}).",
                }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "success": True,
            "descriptor": descriptor,
            "detection_confidence": confidence,
            "verified": verified,
            "distance": round(distance, 3),
            "match_score": round(match_score, 3),
        })
