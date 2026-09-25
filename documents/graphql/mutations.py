from __future__ import annotations

from datetime import date
from typing import Optional

import strawberry
from strawberry.types import Info

from documents.graphql.types import DocumentsPayload
from documents.services import (
    create_document_request, 
    publish_issued_document,
    create_employee_document_request,
    issue_employee_document_request,
    reject_employee_document_request,
)
from documents.models import DocumentRequest, IssuedDocument, EmployeeDocumentRequest
from onboarding.auth import require_hr, require_auth, resolve_org
from onboarding.models import EmployeeDocument
from onboarding.services import verify_document


@strawberry.input
class PublishIssuedDocumentInput:
    user_id: strawberry.ID
    title: str
    category: str = "other"
    financial_year: str = ""
    file_url: str = ""
    notes: str = ""


@strawberry.input
class RequestEmployeeDocumentInput:
    user_id: strawberry.ID
    title: str
    category: str = "hr_request"
    description: str = ""
    due_at: Optional[date] = None

@strawberry.input
class CreateEmployeeDocumentRequestInput:
    category: str
    custom_title: str = ""
    reason: str = ""

@strawberry.input
class IssueEmployeeDocumentInput:
    request_id: strawberry.ID
    template_id: Optional[strawberry.ID] = None
    file_url: str = ""
    file_name: str = ""

@strawberry.input
class RejectEmployeeDocumentInput:
    request_id: strawberry.ID
    reason: str = ""


@strawberry.type
class DocumentsMutation:
    @strawberry.mutation
    def publish_issued_document(
        self, info: Info, input: PublishIssuedDocumentInput
    ) -> DocumentsPayload:
        actor = info.context.request.user
        require_hr(actor)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        target = User.objects.filter(id=input.user_id).first()
        if not target:
            return DocumentsPayload(error="User not found")
        if actor.role != "superadmin" and target.organization_id != actor.organization_id:
            return DocumentsPayload(error="Not authorized")
        if not input.file_url:
            return DocumentsPayload(
                error="Use REST /api/documents/issued/publish/ for file upload, or pass fileUrl"
            )
        try:
            doc = publish_issued_document(
                actor=actor,
                user=target,
                organization=target.organization,
                title=input.title,
                category=input.category,
                financial_year=input.financial_year,
                file_url=input.file_url,
                notes=input.notes,
            )
            return DocumentsPayload(success=True, id=strawberry.ID(str(doc.id)))
        except Exception as e:
            return DocumentsPayload(error=str(e))

    @strawberry.mutation
    def request_employee_document(
        self, info: Info, input: RequestEmployeeDocumentInput
    ) -> DocumentsPayload:
        actor = info.context.request.user
        require_hr(actor)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        target = User.objects.filter(id=input.user_id).first()
        if not target:
            return DocumentsPayload(error="User not found")
        if actor.role != "superadmin" and target.organization_id != actor.organization_id:
            return DocumentsPayload(error="Not authorized")
        try:
            req = create_document_request(
                actor=actor,
                user=target,
                organization=target.organization,
                title=input.title,
                category=input.category,
                description=input.description,
                due_at=input.due_at,
            )
            return DocumentsPayload(success=True, id=strawberry.ID(str(req.id)))
        except Exception as e:
            return DocumentsPayload(error=str(e))

    @strawberry.mutation
    def cancel_document_request(
        self, info: Info, request_id: strawberry.ID
    ) -> DocumentsPayload:
        actor = info.context.request.user
        require_hr(actor)
        req = DocumentRequest.objects.filter(id=request_id).first()
        if not req:
            return DocumentsPayload(error="Request not found")
        if actor.role != "superadmin" and req.organization_id != actor.organization_id:
            return DocumentsPayload(error="Not authorized")
        req.status = "cancelled"
        req.save(update_fields=["status", "updated_at"])
        return DocumentsPayload(success=True, id=strawberry.ID(str(req.id)))

    @strawberry.mutation
    def verify_vault_document(
        self,
        info: Info,
        document_id: strawberry.ID,
        approve: bool,
        rejection_reason: str = "",
    ) -> DocumentsPayload:
        actor = info.context.request.user
        require_hr(actor)
        doc = EmployeeDocument.objects.filter(id=document_id).first()
        if not doc:
            return DocumentsPayload(error="Document not found")
        if actor.role != "superadmin" and doc.organization_id != actor.organization_id:
            return DocumentsPayload(error="Not authorized")
        verify_document(
            doc, verifier=actor, approve=approve, rejection_reason=rejection_reason
        )
        return DocumentsPayload(success=True, id=strawberry.ID(str(doc.id)))

    @strawberry.mutation
    def unpublish_issued_document(
        self, info: Info, document_id: strawberry.ID
    ) -> DocumentsPayload:
        actor = info.context.request.user
        require_hr(actor)
        doc = IssuedDocument.objects.filter(id=document_id).first()
        if not doc:
            return DocumentsPayload(error="Document not found")
        if actor.role != "superadmin" and doc.organization_id != actor.organization_id:
            return DocumentsPayload(error="Not authorized")
        doc.visible_to_employee = False
        doc.save(update_fields=["visible_to_employee", "updated_at"])
        return DocumentsPayload(success=True, id=strawberry.ID(str(doc.id)))

    @strawberry.mutation
    def create_employee_document_request(
        self, info: Info, input: CreateEmployeeDocumentRequestInput
    ) -> DocumentsPayload:
        actor = info.context.request.user
        require_auth(actor)
        try:
            org = resolve_org(actor)
        except Exception as e:
            return DocumentsPayload(error=str(e))
            
        try:
            req = create_employee_document_request(
                user=actor,
                organization=org,
                category=input.category,
                custom_title=input.custom_title,
                reason=input.reason,
            )
            return DocumentsPayload(success=True, id=strawberry.ID(str(req.id)))
        except Exception as e:
            return DocumentsPayload(error=str(e))

    @strawberry.mutation
    def issue_employee_document(
        self, info: Info, input: IssueEmployeeDocumentInput
    ) -> DocumentsPayload:
        actor = info.context.request.user
        require_hr(actor)
        
        req = EmployeeDocumentRequest.objects.filter(id=input.request_id).first()
        if not req:
            return DocumentsPayload(error="Request not found")
        if actor.role != "superadmin" and req.organization_id != actor.organization_id:
            return DocumentsPayload(error="Not authorized")
            
        try:
            file_url = input.file_url
            if input.template_id:
                from onboarding.models import LetterTemplate
                from onboarding.services import generate_letter_for_user
                template = LetterTemplate.objects.filter(id=input.template_id).first()
                if not template:
                    return DocumentsPayload(error="Template not found")
                pdf_bytes = generate_letter_for_user(template, req.user)
                
                from cloudinary.uploader import upload
                import uuid
                filename = f"{template.letter_type}_{uuid.uuid4().hex[:6]}.pdf"
                result = upload(
                    pdf_bytes,
                    resource_type="raw",
                    public_id=f"issued_docs/{req.organization_id}/{req.user_id}/{filename}",
                )
                file_url = result.get("secure_url")
            
            if not file_url:
                return DocumentsPayload(error="Must provide either file_url or a template_id to generate PDF.")
                
            title = req.custom_title if req.category == "other" else req.get_category_display()
            doc = publish_issued_document(
                actor=actor,
                user=req.user,
                organization=req.organization,
                title=title,
                category=req.category,
                file_url=file_url,
                file_name=input.file_name or f"{title}.pdf",
                notes="Generated from employee request",
                notify=False,
            )
            
            issue_employee_document_request(req, doc)
            return DocumentsPayload(success=True, id=strawberry.ID(str(req.id)))
        except Exception as e:
            return DocumentsPayload(error=str(e))

    @strawberry.mutation
    def reject_employee_document(
        self, info: Info, input: RejectEmployeeDocumentInput
    ) -> DocumentsPayload:
        actor = info.context.request.user
        require_hr(actor)
        
        req = EmployeeDocumentRequest.objects.filter(id=input.request_id).first()
        if not req:
            return DocumentsPayload(error="Request not found")
        if actor.role != "superadmin" and req.organization_id != actor.organization_id:
            return DocumentsPayload(error="Not authorized")
            
        try:
            reject_employee_document_request(req, input.reason)
            return DocumentsPayload(success=True, id=strawberry.ID(str(req.id)))
        except Exception as e:
            return DocumentsPayload(error=str(e))
