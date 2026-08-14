from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from feedback.models import Feedback, FeedbackAttachment


class FeedbackAttachmentUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        feedback_id = request.data.get("feedback_id")
        upload = request.FILES.get("file")
        if not feedback_id or not upload:
            return Response(
                {"error": "feedback_id and file are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            item = Feedback.objects.get(id=feedback_id)
        except Feedback.DoesNotExist:
            return Response({"error": "Feedback not found"}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        is_admin = getattr(user, "role", None) in ("admin", "superadmin", "hr")
        if item.author_id != user.id and not is_admin:
            return Response({"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)
        if user.role != "superadmin" and item.organization_id != getattr(user, "organization_id", None):
            return Response({"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)
        if (
            user.role == "superadmin"
            and not item.escalated_to_platform
            and item.category != "admin_share"
            and item.author_id != user.id
        ):
            return Response({"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)

        if upload.size and upload.size > 10 * 1024 * 1024:
            return Response({"error": "File too large (max 10MB)"}, status=status.HTTP_400_BAD_REQUEST)

        attachment = FeedbackAttachment.objects.create(
            feedback=item,
            file=upload,
            file_name=getattr(upload, "name", "")[:255],
            uploaded_by=user,
        )
        return Response(
            {
                "success": True,
                "id": str(attachment.id),
                "file_name": attachment.file_name,
                "file_url": attachment.file.url if attachment.file else None,
            }
        )
