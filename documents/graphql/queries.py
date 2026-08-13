from __future__ import annotations

from typing import List, Optional

import strawberry
from strawberry.types import Info

from documents.models import DocumentRequest, IssuedDocument
from documents.graphql.types import (
    DocumentRequestType,
    IssuedDocumentType,
    VaultEmployeeDocumentType,
)
from onboarding.auth import require_auth, require_hr, resolve_org
from onboarding.models import EmployeeDocument


def _issued_type(d: IssuedDocument) -> IssuedDocumentType:
    user = d.user
    return IssuedDocumentType(
        id=strawberry.ID(str(d.id)),
        category=d.category,
        title=d.title,
        financial_year=d.financial_year or "",
        file_name=d.file_name or "",
        download_url=d.download_url or None,
        notes=d.notes or "",
        published_at=d.published_at,
        visible_to_employee=d.visible_to_employee,
        user_id=strawberry.ID(str(d.user_id)),
        user_name=f"{user.first_name} {user.last_name}".strip() or user.email,
    )


def _request_type(r: DocumentRequest) -> DocumentRequestType:
    user = r.user
    file_url = None
    verification_status = None
    if r.fulfilled_document_id:
        doc = r.fulfilled_document
        try:
            file_url = doc.file.url if doc.file else None
        except Exception:
            file_url = None
        verification_status = doc.verification_status
    return DocumentRequestType(
        id=strawberry.ID(str(r.id)),
        category=r.category,
        title=r.title,
        description=r.description or "",
        status=r.status,
        due_at=r.due_at,
        created_at=r.created_at,
        fulfilled_at=r.fulfilled_at,
        user_id=strawberry.ID(str(r.user_id)),
        user_name=f"{user.first_name} {user.last_name}".strip() or user.email,
        file_url=file_url,
        verification_status=verification_status,
        fulfilled_document_id=(
            strawberry.ID(str(r.fulfilled_document_id))
            if r.fulfilled_document_id
            else None
        ),
    )


def _vault_doc_type(d: EmployeeDocument) -> VaultEmployeeDocumentType:
    file_url = None
    try:
        file_url = d.file.url if d.file else None
    except Exception:
        file_url = None
    return VaultEmployeeDocumentType(
        id=strawberry.ID(str(d.id)),
        category=d.category,
        title=d.title or "",
        file_name=d.file_name or "",
        file_url=file_url,
        verification_status=d.verification_status,
        rejection_reason=d.rejection_reason or "",
        source=getattr(d, "source", "") or "onboarding",
        created_at=d.created_at,
    )


@strawberry.type
class DocumentsQuery:
    @strawberry.field
    def my_issued_documents(self, info: Info) -> List[IssuedDocumentType]:
        user = info.context.request.user
        require_auth(user)
        qs = IssuedDocument.objects.filter(
            user=user, visible_to_employee=True
        ).select_related("user")
        return [_issued_type(d) for d in qs]

    @strawberry.field
    def my_document_requests(
        self, info: Info, status: Optional[str] = None
    ) -> List[DocumentRequestType]:
        user = info.context.request.user
        require_auth(user)
        qs = DocumentRequest.objects.filter(user=user).select_related(
            "user", "fulfilled_document"
        )
        if status:
            qs = qs.filter(status=status)
        return [_request_type(r) for r in qs]

    @strawberry.field
    def my_vault_uploads(self, info: Info) -> List[VaultEmployeeDocumentType]:
        user = info.context.request.user
        require_auth(user)
        qs = EmployeeDocument.objects.filter(user=user).order_by("-created_at")[:100]
        return [_vault_doc_type(d) for d in qs]

    @strawberry.field
    def employee_issued_documents(
        self, info: Info, user_id: strawberry.ID
    ) -> List[IssuedDocumentType]:
        user = info.context.request.user
        require_hr(user)
        org = resolve_org(user)
        qs = IssuedDocument.objects.filter(
            user_id=user_id, organization=org
        ).select_related("user")
        if user.role == "superadmin":
            qs = IssuedDocument.objects.filter(user_id=user_id).select_related("user")
        return [_issued_type(d) for d in qs]

    @strawberry.field
    def employee_document_requests(
        self, info: Info, user_id: strawberry.ID, status: Optional[str] = None
    ) -> List[DocumentRequestType]:
        user = info.context.request.user
        require_hr(user)
        org = resolve_org(user)
        qs = DocumentRequest.objects.filter(
            user_id=user_id, organization=org
        ).select_related("user", "fulfilled_document")
        if user.role == "superadmin":
            qs = DocumentRequest.objects.filter(user_id=user_id).select_related(
                "user", "fulfilled_document"
            )
        if status:
            qs = qs.filter(status=status)
        return [_request_type(r) for r in qs]

    @strawberry.field
    def organization_document_requests(
        self, info: Info, status: Optional[str] = None
    ) -> List[DocumentRequestType]:
        """Org-wide inbox of HR document requests (open / fulfilled / cancelled)."""
        user = info.context.request.user
        require_hr(user)
        org = resolve_org(user)
        qs = DocumentRequest.objects.select_related("user", "fulfilled_document")
        if user.role != "superadmin":
            qs = qs.filter(organization=org)
        if status:
            qs = qs.filter(status=status)
        return [_request_type(r) for r in qs.order_by("-created_at")[:200]]
