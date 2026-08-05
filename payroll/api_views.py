"""REST multipart endpoints for payroll data import and payslip template clone."""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.core.files.base import ContentFile
from django.http import HttpResponse

from payroll.graphql.auth import require_payroll_admin, require_org
from payroll.models import DataImportJob, PayslipTemplate, PayrollRun
from payroll.import_services import (
    parse_tabular_file,
    heuristic_column_mapping,
    ai_refine_column_mapping,
)
from payroll.template_services import (
    clone_template_from_upload,
    generate_demo_pdf_bytes,
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


class PayslipTemplateCloneView(APIView):
    """POST multipart: file (pdf), optional name, organization_id → cloned template."""

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
        if upload.size and upload.size > 10 * 1024 * 1024:
            return Response(
                {"error": "File too large (max 10MB)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_name = getattr(upload, "name", "payslip.pdf") or "payslip.pdf"
        file_bytes = upload.read()
        name = (request.data.get("name") or "").strip()

        try:
            tpl = clone_template_from_upload(
                org,
                file_bytes=file_bytes,
                file_name=file_name,
                name=name,
                created_by=user,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        source_url = ""
        try:
            if tpl.source_file:
                source_url = tpl.source_file.url
        except Exception:
            source_url = ""

        return Response(
            {
                "id": str(tpl.id),
                "name": tpl.name,
                "layoutKey": tpl.layout_key,
                "source": tpl.source,
                "theme": tpl.theme,
                "previewNotes": tpl.preview_notes,
                "isDefault": tpl.is_default,
                "sourceFileUrl": source_url,
            },
            status=status.HTTP_201_CREATED,
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
