from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404

from documents.models import DocumentRequest, IssuedDocument
from documents.services import fulfill_document_request, publish_issued_document
from onboarding.models import EmployeeDocument


def _hr(user) -> bool:
    return getattr(user, "role", None) in ("superadmin", "admin", "hr")


class VaultDocumentUploadView(APIView):
    """
    Employee upload for an open HR document request (or general vault upload).
    Auth: JWT, or exit invite token via form / X-Exit-Token.
    """

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response({"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size and upload.size > 10 * 1024 * 1024:
            return Response(
                {"error": "File too large (max 10MB)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_id = request.data.get("request_id")
        category = (request.data.get("category") or "").strip()
        title = (request.data.get("title") or "").strip()
        exit_token = (
            request.data.get("exit_token")
            or request.headers.get("X-Exit-Token")
            or ""
        )

        actor = None
        target_user = None
        organization = None
        source = "self"

        if exit_token:
            from offboarding.services import get_exit_invite_by_token

            invite = get_exit_invite_by_token(exit_token)
            if not invite:
                return Response(
                    {"error": "Invalid or expired exit invite"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            offboarding = invite.offboarding
            actor = offboarding.user
            target_user = offboarding.user
            organization = offboarding.organization
            source = "offboarding"
        else:
            user = request.user
            if not user or not user.is_authenticated:
                return Response(
                    {"error": "Authentication required"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            actor = user
            if request_id:
                req = DocumentRequest.objects.filter(id=request_id).first()
                if not req:
                    return Response(
                        {"error": "Document request not found"},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                if req.user_id != user.id and not _hr(user):
                    return Response(
                        {"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN
                    )
                if req.status != "open":
                    return Response(
                        {"error": "Request is not open"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                target_user = req.user
                organization = req.organization
                category = category or req.category
                title = title or req.title
                source = "hr_request"
            else:
                target_user = user
                organization = user.organization
                if not organization:
                    return Response(
                        {"error": "No organization"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                source = "self"

        try:
            doc = EmployeeDocument.objects.create(
                organization=organization,
                user=target_user,
                onboarding=None,
                category=category or "other",
                title=title or getattr(upload, "name", "")[:255],
                file=upload,
                file_name=getattr(upload, "name", "")[:255],
                uploaded_by=actor,
                source=source,
            )
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Vault document upload failed")
            return Response(
                {"error": "Upload failed. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if request_id:
            req = DocumentRequest.objects.filter(id=request_id).first()
            if req:
                fulfill_document_request(req, doc, actor=actor)

        file_url = ""
        try:
            file_url = doc.file.url if doc.file else ""
        except Exception:
            file_url = ""

        return Response(
            {
                "success": True,
                "id": str(doc.id),
                "file_url": file_url,
                "verification_status": doc.verification_status,
            },
            status=status.HTTP_201_CREATED,
        )


class PublishIssuedDocumentView(APIView):
    """HR multipart publish of Form 16 / certificates into the vault."""

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _hr(request.user):
            return Response({"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)

        upload = request.FILES.get("file")
        user_id = request.data.get("user_id")
        title = (request.data.get("title") or "").strip()
        category = (request.data.get("category") or "other").strip()
        financial_year = (request.data.get("financial_year") or "").strip()
        notes = (request.data.get("notes") or "").strip()

        if not user_id:
            return Response({"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not upload and not request.data.get("file_url"):
            return Response(
                {"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        if upload and upload.size and upload.size > 15 * 1024 * 1024:
            return Response(
                {"error": "File too large (max 15MB)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.contrib.auth import get_user_model

        User = get_user_model()
        target = User.objects.filter(id=user_id).first()
        if not target:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        org = target.organization
        if request.user.role != "superadmin" and target.organization_id != request.user.organization_id:
            return Response({"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)

        try:
            doc = publish_issued_document(
                actor=request.user,
                user=target,
                organization=org,
                title=title or getattr(upload, "name", "Document"),
                category=category,
                financial_year=financial_year,
                file=upload,
                file_url=(request.data.get("file_url") or "").strip(),
                notes=notes,
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "success": True,
                "id": str(doc.id),
                "download_url": doc.download_url,
            },
            status=status.HTTP_201_CREATED,
        )


class IssuedDocumentDownloadView(APIView):
    """Authenticated redirect to issued document file (own docs or HR)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, document_id):
        doc = get_object_or_404(IssuedDocument, id=document_id)
        user = request.user
        is_owner = doc.user_id == user.id and doc.visible_to_employee
        is_hr = _hr(user) and (
            user.role == "superadmin" or doc.organization_id == user.organization_id
        )
        if not is_owner and not is_hr:
            return Response({"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)
        url = doc.download_url
        if not url:
            return Response({"error": "File not available"}, status=status.HTTP_404_NOT_FOUND)
        return HttpResponseRedirect(url)
