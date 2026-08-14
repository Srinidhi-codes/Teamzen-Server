from __future__ import annotations

from datetime import date
from typing import Optional

import strawberry
from strawberry.types import Info

from documents.graphql.types import DocumentsPayload
from documents.services import create_document_request, publish_issued_document
from documents.models import DocumentRequest, IssuedDocument
from onboarding.auth import require_hr, resolve_org
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
