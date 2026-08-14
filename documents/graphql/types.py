from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

import strawberry


@strawberry.type
class DocumentsPayload:
    success: bool = False
    error: Optional[str] = None
    id: Optional[strawberry.ID] = None


@strawberry.type
class IssuedDocumentType:
    id: strawberry.ID
    category: str
    title: str
    financial_year: str
    file_name: str
    download_url: Optional[str]
    notes: str
    published_at: Optional[datetime]
    visible_to_employee: bool
    user_id: strawberry.ID
    user_name: str


@strawberry.type
class DocumentRequestType:
    id: strawberry.ID
    category: str
    title: str
    description: str
    status: str
    due_at: Optional[date]
    created_at: datetime
    fulfilled_at: Optional[datetime]
    user_id: strawberry.ID
    user_name: str
    file_url: Optional[str] = None
    verification_status: Optional[str] = None
    fulfilled_document_id: Optional[strawberry.ID] = None


@strawberry.type
class VaultEmployeeDocumentType:
    id: strawberry.ID
    category: str
    title: str
    file_name: str
    file_url: Optional[str]
    verification_status: str
    rejection_reason: str
    source: str
    created_at: datetime
