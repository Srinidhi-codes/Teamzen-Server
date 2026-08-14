"""Publish official TRACES Form 16 PDFs into the employee vault."""
from __future__ import annotations

import zipfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from documents.api_views import _hr
from documents.form16 import extract_pan_from_filename, parse_financial_year
from documents.services import publish_issued_document

User = get_user_model()


def _match_user_for_file(actor, filename: str, organization_id=None):
    pan = extract_pan_from_filename(filename)
    qs = User.objects.all()
    if actor.role != "superadmin":
        qs = qs.filter(organization_id=actor.organization_id)
    elif organization_id:
        qs = qs.filter(organization_id=organization_id)

    if pan:
        hit = qs.filter(pan_number__iexact=pan).first()
        if hit:
            return hit, "pan"

    stem = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = stem.rsplit(".", 1)[0]
    for candidate in (stem, stem.split("_")[0], stem.split("-")[0]):
        hit = qs.filter(employee_id__iexact=candidate).first()
        if hit:
            return hit, "employee_id"
    return None, None


class Form16BulkPublishView(APIView):
    """
    Multipart: financial_year, files[] and/or a .zip of official Form 16 PDFs.
    Match by PAN in filename (e.g. MSXPS6972G_PARTB_…) or employee_id.
    """

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _hr(request.user):
            return Response({"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)

        financial_year = (request.data.get("financial_year") or "").strip()
        if not financial_year:
            return Response(
                {"error": "financial_year is required (e.g. 2025-26)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            _, _, _, fy_label = parse_financial_year(financial_year)
        except Exception:
            fy_label = financial_year

        uploads = []
        for f in request.FILES.getlist("files") or request.FILES.getlist("file"):
            uploads.append(f)
        zip_file = request.FILES.get("zip") or request.FILES.get("archive")
        if zip_file:
            try:
                with zipfile.ZipFile(zip_file) as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        name = info.filename
                        if not name.lower().endswith(".pdf"):
                            continue
                        data = zf.read(info)
                        uploads.append(
                            ContentFile(data, name=name.rsplit("/", 1)[-1])
                        )
            except zipfile.BadZipFile:
                return Response(
                    {"error": "Invalid zip file"}, status=status.HTTP_400_BAD_REQUEST
                )

        if not uploads:
            return Response(
                {"error": "Provide PDF files or a zip"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        matched, unmatched, errors = [], [], []
        for upload in uploads:
            fname = getattr(upload, "name", "document.pdf") or "document.pdf"
            user, how = _match_user_for_file(request.user, fname)
            if not user:
                unmatched.append({"filename": fname, "reason": "No employee match"})
                continue
            try:
                doc = publish_issued_document(
                    actor=request.user,
                    user=user,
                    organization=user.organization,
                    title=f"Form 16 FY {fy_label}",
                    category="form_16",
                    financial_year=fy_label,
                    file=upload,
                    file_name=fname[:255],
                    notes=f"Official TRACES Form 16 matched by {how}",
                )
                matched.append(
                    {
                        "filename": fname,
                        "user_id": str(user.id),
                        "user_name": f"{user.first_name} {user.last_name}".strip(),
                        "document_id": str(doc.id),
                        "matched_by": how,
                    }
                )
            except Exception as e:
                errors.append({"filename": fname, "error": str(e)})

        return Response(
            {
                "success": True,
                "financial_year": fy_label,
                "matched": matched,
                "unmatched": unmatched,
                "errors": errors,
            }
        )


class Form16PreviewMatchView(APIView):
    """Preview filename → employee matches without publishing."""

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _hr(request.user):
            return Response({"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)

        rows = []
        for f in request.FILES.getlist("files") or request.FILES.getlist("file"):
            fname = getattr(f, "name", "") or ""
            user, how = _match_user_for_file(request.user, fname)
            rows.append(
                {
                    "filename": fname,
                    "matched": bool(user),
                    "matched_by": how,
                    "user_id": str(user.id) if user else None,
                    "user_name": (
                        f"{user.first_name} {user.last_name}".strip() if user else None
                    ),
                    "pan": extract_pan_from_filename(fname),
                }
            )
        zip_file = request.FILES.get("zip")
        if zip_file:
            try:
                with zipfile.ZipFile(zip_file) as zf:
                    for info in zf.infolist():
                        if info.is_dir() or not info.filename.lower().endswith(".pdf"):
                            continue
                        fname = info.filename.rsplit("/", 1)[-1]
                        user, how = _match_user_for_file(request.user, fname)
                        rows.append(
                            {
                                "filename": fname,
                                "matched": bool(user),
                                "matched_by": how,
                                "user_id": str(user.id) if user else None,
                                "user_name": (
                                    f"{user.first_name} {user.last_name}".strip()
                                    if user
                                    else None
                                ),
                                "pan": extract_pan_from_filename(fname),
                            }
                        )
            except zipfile.BadZipFile:
                return Response({"error": "Invalid zip"}, status=400)

        return Response({"success": True, "rows": rows})
