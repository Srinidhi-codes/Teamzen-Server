"""REST multipart endpoints for payroll imports, payslip PDFs, and bank exports."""

import json
import re

from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.core.files.base import ContentFile
from django.http import HttpResponse

from payroll.graphql.auth import require_payroll_admin, require_org
from payroll.models import DataImportJob, Payslip, PayslipTemplate, PayrollRun
from payroll.import_services import (
    parse_tabular_file,
    heuristic_column_mapping,
    ai_refine_column_mapping,
)
from payroll.template_services import (
    generate_demo_pdf_bytes,
    render_pdf_first_page_to_png,
)
from payroll.bank_export import FORMATS, build_bank_export


class DataImportUploadView(APIView):
    """
    POST multipart: file (csv/xlsx), optional organization_id, use_ai (default true).
    Creates DataImportJob with headers, sample, suggested mapping.
    """

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        org_id = request.data.get("organization_id") or None
        try:
            require_payroll_admin(user, allow_hr=True)
            org = require_org(user, organization_id=org_id)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)

        upload = request.FILES.get("file")
        if not upload:
            return Response({"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size and upload.size > 15 * 1024 * 1024:
            return Response(
                {"error": "File too large (max 15MB)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_name = getattr(upload, "name", "upload.csv") or "upload.csv"
        file_bytes = upload.read()
        try:
            source_type, headers, rows = parse_tabular_file(file_bytes, file_name)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if not headers:
            return Response({"error": "No columns found"}, status=status.HTTP_400_BAD_REQUEST)
        if not rows:
            return Response({"error": "No data rows found"}, status=status.HTTP_400_BAD_REQUEST)

        use_ai = str(request.data.get("use_ai", "true")).lower() not in ("0", "false", "no")
        mapping, confidence = heuristic_column_mapping(headers)
        if use_ai:
            mapping, confidence = ai_refine_column_mapping(
                org.id, headers, rows[:8], current_mapping=mapping
            )

        job = DataImportJob(
            organization=org,
            created_by=user,
            status="mapped",
            source_type=source_type,
            file_name=file_name[:255],
            headers=headers,
            sample_rows=rows[:8],
            all_rows=rows[:2000],  # hard cap for P0
            column_mapping=mapping,
            mapping_confidence=confidence,
        )
        job.file.save(file_name, ContentFile(file_bytes), save=False)
        job.save()

        return Response(
            {
                "jobId": str(job.id),
                "fileName": job.file_name,
                "sourceType": job.source_type,
                "status": job.status,
                "headers": headers,
                "sampleRows": job.sample_rows,
                "rowCount": len(rows),
                "truncated": len(rows) > 2000,
                "columnMapping": mapping,
                "mappingConfidence": confidence,
            },
            status=status.HTTP_201_CREATED,
        )


def _normalized_file_token(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _match_uploaded_payslips(run, uploads):
    payslips = list(
        Payslip.objects.filter(payroll_run=run)
        .select_related("user")
        .order_by("user__employee_id", "user__first_name", "user__last_name")
    )
    name_counts = {}
    for payslip in payslips:
        full_name = _normalized_file_token(
            f"{payslip.user.first_name or ''}{payslip.user.last_name or ''}"
        )
        if full_name:
            name_counts[full_name] = name_counts.get(full_name, 0) + 1

    results = []
    claimed = set()
    for index, upload in enumerate(uploads):
        filename = getattr(upload, "name", f"payslip-{index + 1}.pdf")
        token = _normalized_file_token(filename.rsplit(".", 1)[0])
        candidates = []
        match_by = None

        # Employee ID is the strongest identifier and is checked first.
        for payslip in payslips:
            employee_id = _normalized_file_token(payslip.user.employee_id)
            if employee_id and employee_id in token:
                candidates.append(payslip)
        if len(candidates) > 1:
            longest = max(
                len(_normalized_file_token(item.user.employee_id))
                for item in candidates
            )
            candidates = [
                item
                for item in candidates
                if len(_normalized_file_token(item.user.employee_id)) == longest
            ]
        if len(candidates) == 1:
            match_by = "employee_id"
        else:
            candidates = []
            for payslip in payslips:
                full_name = _normalized_file_token(
                    f"{payslip.user.first_name or ''}{payslip.user.last_name or ''}"
                )
                if (
                    len(full_name) >= 4
                    and name_counts.get(full_name) == 1
                    and full_name in token
                ):
                    candidates.append(payslip)
            if len(candidates) == 1:
                match_by = "name"

        matched = candidates[0] if len(candidates) == 1 else None
        reason = ""
        if not matched:
            reason = "No unique employee ID or full-name match in filename"
        elif matched.id in claimed:
            reason = "Another PDF already matched this employee"
            matched = None
        else:
            claimed.add(matched.id)

        results.append(
            {
                "index": index,
                "fileName": filename,
                "matched": bool(matched),
                "matchBy": match_by if matched else None,
                "reason": reason,
                "payslipId": str(matched.id) if matched else None,
                "employeeId": matched.user.employee_id if matched else None,
                "employeeName": (
                    matched.user.get_full_name().strip() or matched.user.email
                    if matched
                    else None
                ),
                "currentStatus": matched.status if matched else None,
            }
        )
    return results


class PayslipBulkUploadView(APIView):
    """
    Preview or publish admin-provided payslip PDFs for an existing processed run.

    Files are matched from their filenames, employee ID first and then unique full
    name. Unmatched/ambiguous PDFs are never published.
    """

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        run_id = request.data.get("run_id")
        mode = (request.data.get("mode") or "preview").strip().lower()
        if mode not in ("preview", "publish"):
            return Response({"error": "mode must be preview or publish"}, status=400)
        if not run_id:
            return Response({"error": "run_id is required"}, status=400)

        try:
            require_payroll_admin(user, allow_hr=True)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)

        run = PayrollRun.objects.select_related("organization").filter(id=run_id).first()
        if not run:
            return Response({"error": "Payroll run not found"}, status=404)
        if (
            user.role != "superadmin"
            and run.organization_id != user.organization_id
        ) or (
            user.role == "superadmin"
            and user.organization_id
            and run.organization_id != user.organization_id
        ):
            return Response({"error": "Unauthorized"}, status=403)
        if run.status != "completed":
            return Response(
                {"error": "Process payroll before uploading and publishing payslips."},
                status=400,
            )

        uploads = request.FILES.getlist("files")
        if not uploads:
            return Response({"error": "Select at least one PDF"}, status=400)
        if len(uploads) > 200:
            return Response({"error": "Upload at most 200 PDFs per batch"}, status=400)

        total_size = 0
        for upload in uploads:
            filename = getattr(upload, "name", "")
            if not filename.lower().endswith(".pdf"):
                return Response({"error": f"{filename} is not a PDF"}, status=400)
            signature = upload.read(5)
            upload.seek(0)
            if signature != b"%PDF-":
                return Response({"error": f"{filename} is not a valid PDF"}, status=400)
            if upload.size and upload.size > 15 * 1024 * 1024:
                return Response({"error": f"{filename} exceeds 15MB"}, status=400)
            total_size += upload.size or 0
        if total_size > 150 * 1024 * 1024:
            return Response({"error": "Batch exceeds 150MB"}, status=400)

        matches = _match_uploaded_payslips(run, uploads)
        matched_count = sum(1 for item in matches if item["matched"])
        if mode == "preview":
            return Response(
                {
                    "runId": str(run.id),
                    "month": run.month,
                    "year": run.year,
                    "total": len(matches),
                    "matched": matched_count,
                    "unmatched": len(matches) - matched_count,
                    "files": matches,
                }
            )

        if matched_count == 0:
            return Response({"error": "No PDFs matched employees; nothing published"}, status=400)

        # Optional preview mapping protects against files changing between steps.
        raw_mapping = request.data.get("mapping")
        if not raw_mapping:
            return Response(
                {"error": "Preview this exact batch before publishing."},
                status=400,
            )
        expected = {}
        try:
            for row in json.loads(raw_mapping):
                expected[int(row["index"])] = str(row["payslipId"])
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            return Response({"error": "Invalid preview mapping"}, status=400)

        matched_by_index = {item["index"]: item for item in matches if item["matched"]}
        if set(expected) != set(matched_by_index):
            return Response(
                {"error": "Files no longer match the preview. Preview the batch again."},
                status=400,
            )
        for index, payslip_id in expected.items():
            current = matched_by_index.get(index)
            if not current or current["payslipId"] != payslip_id:
                return Response(
                    {"error": "Files no longer match the preview. Preview the batch again."},
                    status=400,
                )

        published = []
        with transaction.atomic():
            for item in matches:
                if not item["matched"]:
                    continue
                payslip = Payslip.objects.select_for_update().get(
                    id=item["payslipId"], payroll_run=run
                )
                if payslip.status == "paid":
                    continue
                upload = uploads[item["index"]]
                safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", upload.name)[:180]
                payslip.payslip_pdf.save(safe_name or "payslip.pdf", upload, save=False)
                payslip.status = "published"
                payslip.pdf_source = "uploaded"
                payslip.save(update_fields=["payslip_pdf", "status", "pdf_source"])
                published.append(item)

        return Response(
            {
                "success": True,
                "published": len(published),
                "skipped": len(matches) - len(published),
                "files": matches,
            }
        )


class PayslipTemplateDemoDownloadView(APIView):
    """
    GET: download a sample payslip PDF rendered with the chosen template.
    Query: organization_id (optional for superadmin).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, template_id):
        user = request.user
        org_id = request.query_params.get("organization_id") or None
        try:
            require_payroll_admin(user, allow_hr=True)
            org = require_org(user, organization_id=org_id)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)

        tpl = PayslipTemplate.objects.filter(id=template_id, is_active=True).first()
        if not tpl:
            return Response({"error": "Template not found"}, status=status.HTTP_404_NOT_FOUND)
        if tpl.organization_id and tpl.organization_id != org.id:
            if user.role != "superadmin" or (
                user.organization_id and user.organization_id != tpl.organization_id
            ):
                return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        try:
            pdf_bytes = generate_demo_pdf_bytes(org, tpl)
        except Exception as e:
            return Response(
                {"error": f"Could not generate demo PDF: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        safe_name = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in (tpl.name or "payslip")
        )[:60]
        filename = f"demo_payslip_{safe_name}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class PayslipTemplatePreviewView(APIView):
    """
    GET: PNG preview of page 1 for a template card.
    Uploaded templates → filled pin-to-pin demo (falls back to source PDF page).
    Query: organization_id (optional for superadmin).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, template_id):
        user = request.user
        org_id = request.query_params.get("organization_id") or None
        try:
            require_payroll_admin(user, allow_hr=True)
            org = require_org(user, organization_id=org_id)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)

        tpl = PayslipTemplate.objects.filter(id=template_id, is_active=True).first()
        if not tpl:
            return Response({"error": "Template not found"}, status=status.HTTP_404_NOT_FOUND)
        if tpl.organization_id and tpl.organization_id != org.id:
            if user.role != "superadmin" or (
                user.organization_id and user.organization_id != tpl.organization_id
            ):
                return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        pdf_bytes = None
        try:
            pdf_bytes = generate_demo_pdf_bytes(org, tpl)
        except Exception:
            pdf_bytes = None

        if not pdf_bytes:
            return Response(
                {"error": "No PDF available to preview"},
                status=status.HTTP_404_NOT_FOUND,
            )

        png = render_pdf_first_page_to_png(pdf_bytes, zoom=1.6)
        if not png:
            return Response(
                {"error": "Could not rasterize PDF preview"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = HttpResponse(png, content_type="image/png")
        # Avoid stale browser/CDN caches when a new PDF is uploaded
        response["Cache-Control"] = "private, no-store, max-age=0"
        updated = getattr(tpl, "updated_at", None)
        if updated:
            response["ETag"] = f'W/"tpl-{tpl.id}-{int(updated.timestamp())}"'
        return response


class BankPayoutExportView(APIView):
    """
    GET: CSV bank payout file for a payroll run.
    Query: bank_format=neft|imps|hdfc|icici (default neft)
           (Do not use ?format= — DRF reserves that for content negotiation.)
    Headers: X-Skipped-Count, X-Included-Count, X-Total-Amount
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, run_id):
        user = request.user
        try:
            require_payroll_admin(user)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)

        run = (
            PayrollRun.objects.select_related("organization")
            .filter(id=run_id)
            .first()
        )
        if not run:
            return Response({"error": "Payroll run not found"}, status=status.HTTP_404_NOT_FOUND)

        if user.role != "superadmin":
            if not user.organization_id or str(user.organization_id) != str(
                run.organization_id
            ):
                return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
        elif user.organization_id and str(user.organization_id) != str(run.organization_id):
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        fmt = (
            request.query_params.get("bank_format")
            or request.query_params.get("type")
            or "neft"
        ).strip().lower()
        if fmt not in FORMATS:
            return Response(
                {"error": f"Invalid bank_format. Use one of: {', '.join(FORMATS)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = build_bank_export(run, fmt)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"error": f"Could not build bank file: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = HttpResponse(result.csv_text, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{result.filename}"'
        response["X-Skipped-Count"] = str(result.skipped)
        response["X-Included-Count"] = str(result.included)
        response["X-Total-Amount"] = str(result.total_amount)
        response["Access-Control-Expose-Headers"] = (
            "Content-Disposition, X-Skipped-Count, X-Included-Count, X-Total-Amount"
        )
        return response
