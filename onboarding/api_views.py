from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status

from onboarding.models import EmployeeDocument, EmployeeOnboarding
from onboarding.services import (
    attach_signed_offer_letter,
    attach_uploaded_offer_letter,
    get_invite_by_token,
    suggest_document_category,
)


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
            source="onboarding",
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


class OfferLetterUploadView(APIView):
    """HR uploads a custom offer letter PDF for an onboarding."""

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if getattr(user, "role", None) not in ("superadmin", "admin", "hr"):
            return Response(
                {"error": "HR access required"}, status=status.HTTP_403_FORBIDDEN
            )

        upload = request.FILES.get("file")
        onboarding_id = request.data.get("onboarding_id")
        subject = (request.data.get("subject") or "").strip()
        send_email = str(request.data.get("send_email") or "").lower() in (
            "1",
            "true",
            "yes",
        )

        if not upload:
            return Response(
                {"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        if not onboarding_id:
            return Response(
                {"error": "onboarding_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.size and upload.size > 15 * 1024 * 1024:
            return Response(
                {"error": "File too large (max 15MB)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        name = (getattr(upload, "name", "") or "").lower()
        content_type = (getattr(upload, "content_type", "") or "").lower()
        if not (name.endswith(".pdf") or "pdf" in content_type):
            return Response(
                {"error": "Only PDF offer letters are supported"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        onboarding = (
            EmployeeOnboarding.objects.select_related(
                "user", "organization", "offer_letter"
            )
            .filter(id=onboarding_id)
            .first()
        )
        if not onboarding:
            return Response(
                {"error": "Onboarding not found"}, status=status.HTTP_404_NOT_FOUND
            )
        if (
            user.role != "superadmin"
            and onboarding.organization_id != user.organization_id
        ):
            return Response(
                {"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN
            )

        try:
            offer = attach_uploaded_offer_letter(
                onboarding,
                file_bytes=upload.read(),
                filename=getattr(upload, "name", "offer.pdf")[:255],
                subject=subject,
                actor=user,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Always re-load so email + response use the fresh pdf_url
        offer.refresh_from_db()
        onboarding = EmployeeOnboarding.objects.select_related(
            "user", "organization", "offer_letter"
        ).get(id=onboarding.id)

        if send_email:
            try:
                from onboarding.graphql.mutations import _notify_offer_letter

                _notify_offer_letter(onboarding, actor=user)
            except Exception as e:
                return Response(
                    {
                        "success": True,
                        "warning": f"PDF saved (portal updated) but email failed: {e}",
                        "id": str(offer.id),
                        "pdf_url": offer.pdf_url,
                        "subject": offer.subject,
                        "source": offer.source,
                        "status": offer.status,
                    }
                )

        return Response(
            {
                "success": True,
                "id": str(offer.id),
                "pdf_url": offer.pdf_url,
                "subject": offer.subject,
                "source": offer.source,
                "status": offer.status,
                "portal_ready": bool(offer.pdf_url),
            }
        )


class SignedOfferLetterUploadView(APIView):
    """
    Upload a signed/scanned offer letter PDF.
    Auth: HR JWT, hire JWT, or preboarding invite token.
    """

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        if upload.size and upload.size > 15 * 1024 * 1024:
            return Response(
                {"error": "File too large (max 15MB)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        name = (getattr(upload, "name", "") or "").lower()
        content_type = (getattr(upload, "content_type", "") or "").lower()
        if not (name.endswith(".pdf") or "pdf" in content_type):
            return Response(
                {"error": "Only PDF files are supported"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invite_token = (
            request.data.get("invite_token")
            or request.headers.get("X-Preboarding-Token")
            or ""
        )
        onboarding_id = request.data.get("onboarding_id")
        accepted_name = (request.data.get("accepted_name") or "").strip()
        mark_accepted = str(request.data.get("mark_accepted") or "true").lower() not in (
            "0",
            "false",
            "no",
        )

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
                onboarding = (
                    EmployeeOnboarding.objects.select_related(
                        "user", "organization", "offer_letter"
                    )
                    .filter(id=onboarding_id)
                    .first()
                )
            else:
                onboarding = (
                    EmployeeOnboarding.objects.select_related(
                        "user", "organization", "offer_letter"
                    )
                    .filter(user=user)
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
            if (
                is_hr
                and user.role != "superadmin"
                and onboarding.organization_id != user.organization_id
            ):
                return Response(
                    {"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN
                )

        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = (
            forwarded.split(",")[0].strip()
            if forwarded
            else request.META.get("REMOTE_ADDR")
        )
        ua = request.META.get("HTTP_USER_AGENT", "")[:2000]

        try:
            offer = attach_signed_offer_letter(
                onboarding,
                file_bytes=upload.read(),
                filename=getattr(upload, "name", "signed_offer.pdf")[:255],
                actor=actor,
                mark_accepted=mark_accepted,
                accepted_name=accepted_name,
                ip=ip,
                ua=ua,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "success": True,
                "id": str(offer.id),
                "pdf_url": offer.pdf_url,
                "signed_pdf_url": offer.signed_pdf_url,
                "status": offer.status,
                "accepted_at": offer.accepted_at.isoformat() if offer.accepted_at else None,
            }
        )
