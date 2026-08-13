"""Form 16 bulk publish + generate APIs."""
from __future__ import annotations

import io
import json
import zipfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from documents.api_views import _hr
from documents.form16 import (
    build_form16_summary,
    extract_pan_from_filename,
    parse_financial_year,
    render_form16_part_b_pdf,
)
from documents.services import publish_issued_document

User = get_user_model()


def _org_scope(actor, user):
    if actor.role == "superadmin":
        return True
    return user.organization_id and user.organization_id == actor.organization_id


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
    # employee_id exact match on stem or before underscore
    for candidate in (stem, stem.split("_")[0], stem.split("-")[0]):
        hit = qs.filter(employee_id__iexact=candidate).first()
        if hit:
            return hit, "employee_id"
    return None, None


class Form16BulkPublishView(APIView):
    """
    Multipart: financial_year, files[] and/or a .zip of PDFs.
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
                    notes=f"Bulk upload matched by {how}",
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


class Form16GenerateView(APIView):
    """
    JSON or multipart: financial_year, user_ids[] OR all_active=true,
    optional overrides JSON map { userId: { section_80c, hra_exempt, ... } }.
    """

    parser_classes = [JSONParser, MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _hr(request.user):
            return Response({"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        financial_year = (data.get("financial_year") or "").strip()
        if not financial_year:
            return Response(
                {"error": "financial_year is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _, _, _, fy_label = parse_financial_year(financial_year)

        overrides_raw = data.get("overrides") or {}
        if isinstance(overrides_raw, str):
            try:
                overrides_raw = json.loads(overrides_raw)
            except json.JSONDecodeError:
                overrides_raw = {}

        all_active = str(data.get("all_active") or "").lower() in ("1", "true", "yes")
        user_ids = data.get("user_ids") or data.getlist("user_ids") if hasattr(data, "getlist") else data.get("user_ids")
        if isinstance(user_ids, str):
            try:
                user_ids = json.loads(user_ids)
            except json.JSONDecodeError:
                user_ids = [x.strip() for x in user_ids.split(",") if x.strip()]

        qs = User.objects.filter(role="employee").select_related(
            "organization", "office_location"
        )
        if request.user.role != "superadmin":
            qs = qs.filter(organization_id=request.user.organization_id)

        if all_active:
            users = list(qs.filter(is_active=True))
        elif user_ids:
            users = list(qs.filter(id__in=user_ids))
        else:
            return Response(
                {"error": "Provide user_ids or all_active=true"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = []
        for user in users:
            ovr = overrides_raw.get(str(user.id)) or overrides_raw.get(user.id) or {}
            if not isinstance(ovr, dict):
                ovr = {}
            try:
                summary = build_form16_summary(
                    user, financial_year=fy_label, overrides=ovr
                )
                pdf_bytes = render_form16_part_b_pdf(summary)
                filename = f"{(user.pan_number or user.employee_id or user.id)}_PARTB_{fy_label}.pdf"
                content = ContentFile(pdf_bytes, name=filename)
                doc = publish_issued_document(
                    actor=request.user,
                    user=user,
                    organization=user.organization,
                    title=f"Form 16 Part B FY {fy_label}",
                    category="form_16",
                    financial_year=fy_label,
                    file=content,
                    file_name=filename[:255],
                    notes="Generated Part B from Teamzen payroll (not TRACES Part A)",
                )
                results.append(
                    {
                        "user_id": str(user.id),
                        "user_name": summary["employee_name"],
                        "success": True,
                        "document_id": str(doc.id),
                        "download_url": doc.download_url,
                        "payslip_count": summary["payslip_count"],
                        "gross_salary": summary["gross_salary"],
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "user_id": str(user.id),
                        "user_name": f"{user.first_name} {user.last_name}".strip(),
                        "success": False,
                        "error": str(e),
                    }
                )

        ok = sum(1 for r in results if r.get("success"))
        return Response(
            {
                "success": True,
                "financial_year": fy_label,
                "generated": ok,
                "failed": len(results) - ok,
                "results": results,
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
