from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny
from rest_framework import status

from onboarding.models import EmployeeDocument, EmployeeOnboarding
from onboarding.services import get_invite_by_token, suggest_document_category


class EmployeeDocumentUploadView(APIView):
    """
    Multipart upload for employee KYC docs.
    Auth: JWT OR invite token via form field / X-Preboarding-Token header.
    """

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        if upload.size and upload.size > 10 * 1024 * 1024:
            return Response(
                {"error": "File too large (max 10MB)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invite_token = (
            request.data.get("invite_token")
            or request.headers.get("X-Preboarding-Token")
            or ""
        )
        onboarding_id = request.data.get("onboarding_id")
        category = (request.data.get("category") or "").strip()
        title = (request.data.get("title") or "").strip()

        onboarding = None
        actor = None

        if invite_token:
            invite = get_invite_by_token(invite_token)
            if not invite:
                return Response(
                    {"error": "Invalid or expired invite"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            onboarding = invite.onboarding
            actor = onboarding.user
        else:
            user = request.user
            if not user or not user.is_authenticated:
                return Response(
                    {"error": "Authentication required"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            actor = user
            if onboarding_id:
                onboarding = EmployeeOnboarding.objects.filter(id=onboarding_id).first()
            else:
                onboarding = (
                    EmployeeOnboarding.objects.filter(user=user)
                    .exclude(status="cancelled")
                    .first()
                )
            if not onboarding:
                return Response(
                    {"error": "Onboarding not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            is_hr = getattr(user, "role", None) in ("superadmin", "admin", "hr")
            if onboarding.user_id != user.id and not is_hr:
                return Response(
                    {"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN
                )

        suggested, confidence = suggest_document_category(
            file_name=getattr(upload, "name", ""), title=title
        )
        if not category:
            category = suggested

        doc = EmployeeDocument.objects.create(
            organization=onboarding.organization,
            user=onboarding.user,
            onboarding=onboarding,
            category=category or "other",
            title=title or getattr(upload, "name", "")[:255],
            file=upload,
            file_name=getattr(upload, "name", "")[:255],
            uploaded_by=actor,
            ai_suggested_category=suggested,
            ai_confidence=confidence,
            verification_status="pending",
        )

        return Response(
            {
                "success": True,
                "id": str(doc.id),
                "category": doc.category,
                "file_name": doc.file_name,
                "file_url": doc.file.url if doc.file else None,
                "ai_suggested_category": doc.ai_suggested_category,
                "ai_confidence": doc.ai_confidence,
                "verification_status": doc.verification_status,
            }
        )
