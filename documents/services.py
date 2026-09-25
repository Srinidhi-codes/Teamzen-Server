from django.utils import timezone

from documents.models import DocumentRequest, IssuedDocument, EmployeeDocumentRequest


def publish_issued_document(
    *,
    actor,
    user,
    organization,
    title: str,
    category: str = "other",
    financial_year: str = "",
    file=None,
    file_url: str = "",
    file_name: str = "",
    notes: str = "",
    notify: bool = True,
) -> IssuedDocument:
    if not file and not file_url:
        raise ValueError("file or file_url is required")

    doc = IssuedDocument(
        organization=organization,
        user=user,
        category=category or "other",
        title=title.strip() or "Document",
        financial_year=(financial_year or "").strip(),
        file_name=file_name or (getattr(file, "name", "") if file else "")[:255],
        file_url=file_url or "",
        notes=notes or "",
        visible_to_employee=True,
        published_at=timezone.now(),
        published_by=actor,
    )
    if file:
        doc.file = file
        if not doc.file_name:
            doc.file_name = getattr(file, "name", "")[:255]
    doc.save()

    if notify:
        try:
            from notifications.utils import notify_user

            notify_user(
                recipient_id=user.id,
                verb="New document available",
                message=f'"{doc.title}" is ready to download in Documents.',
                actor_id=getattr(actor, "id", None),
                target_type="IssuedDocument",
                target_id=str(doc.id),
                level="personal",
                notification_type="BOTH",
            )
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Issued document notify failed doc_id=%s", doc.id
            )
    return doc


def create_document_request(
    *,
    actor,
    user,
    organization,
    title: str,
    category: str = "hr_request",
    description: str = "",
    due_at=None,
    notify: bool = True,
) -> DocumentRequest:
    req = DocumentRequest.objects.create(
        organization=organization,
        user=user,
        category=category or "hr_request",
        title=title.strip() or "Document request",
        description=description or "",
        due_at=due_at,
        created_by=actor,
        status="open",
    )
    if notify:
        try:
            from notifications.utils import notify_user

            notify_user(
                recipient_id=user.id,
                verb="Document requested",
                message=f'HR requested "{req.title}". Upload it from Documents.',
                actor_id=getattr(actor, "id", None),
                target_type="DocumentRequest",
                target_id=str(req.id),
                level="personal",
                notification_type="BOTH",
            )
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Document request notify failed req_id=%s", req.id
            )
    return req


def fulfill_document_request(req: DocumentRequest, document, *, actor=None) -> DocumentRequest:
    req.fulfilled_document = document
    req.fulfilled_at = timezone.now()
    req.status = "fulfilled"
    req.save(update_fields=["fulfilled_document", "fulfilled_at", "status", "updated_at"])

    try:
        from notifications.utils import get_management_ids, notify_management, notify_user

        employee = req.user
        emp_name = (
            f"{employee.first_name or ''} {employee.last_name or ''}".strip()
            or employee.email
        )
        message = f'{emp_name} uploaded "{req.title}" for your document request.'
        notify_management(
            employee,
            verb="Document uploaded",
            message=message,
            target_type="DocumentRequest",
            target_id=str(req.id),
        )
        created_by_id = getattr(req, "created_by_id", None)
        management_ids = set(get_management_ids(employee) or [])
        if created_by_id and created_by_id not in management_ids:
            notify_user(
                recipient_id=created_by_id,
                verb="Document uploaded",
                message=message,
                actor_id=getattr(actor, "id", None) or employee.id,
                target_type="DocumentRequest",
                target_id=str(req.id),
                level="admin",
                notification_type="BOTH",
            )
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "Document fulfill notify failed req_id=%s", req.id
        )

    return req

def create_employee_document_request(
    *,
    user,
    organization,
    category: str,
    custom_title: str = "",
    reason: str = "",
) -> EmployeeDocumentRequest:
    req = EmployeeDocumentRequest.objects.create(
        organization=organization,
        user=user,
        category=category,
        custom_title=custom_title,
        reason=reason,
        status="pending",
    )
    
    # Notify HR/Admins
    try:
        from notifications.utils import notify_management
        emp_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email
        title = custom_title if category == "other" else req.get_category_display()
        notify_management(
            user,
            verb="Document requested",
            message=f'{emp_name} requested a {title}.',
            target_type="EmployeeDocumentRequest",
            target_id=str(req.id),
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Failed to notify management of employee document request")
        
    return req

def issue_employee_document_request(
    req: EmployeeDocumentRequest,
    issued_document: IssuedDocument,
) -> EmployeeDocumentRequest:
    req.issued_document = issued_document
    req.issued_at = timezone.now()
    req.status = "issued"
    req.save(update_fields=["issued_document", "issued_at", "status", "updated_at"])
    
    # Notify Employee
    try:
        from notifications.utils import notify_user
        title = req.custom_title if req.category == "other" else req.get_category_display()
        notify_user(
            recipient_id=req.user_id,
            verb="Document issued",
            message=f'Your requested {title} has been issued and is ready to download.',
            target_type="EmployeeDocumentRequest",
            target_id=str(req.id),
            level="personal",
            notification_type="BOTH",
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Failed to notify user of issued document")

    return req

def reject_employee_document_request(
    req: EmployeeDocumentRequest,
    reason: str,
) -> EmployeeDocumentRequest:
    req.status = "rejected"
    req.rejected_reason = reason
    req.save(update_fields=["status", "rejected_reason", "updated_at"])
    
    # Notify Employee
    try:
        from notifications.utils import notify_user
        title = req.custom_title if req.category == "other" else req.get_category_display()
        notify_user(
            recipient_id=req.user_id,
            verb="Document request rejected",
            message=f'Your request for {title} was rejected: {reason}',
            target_type="EmployeeDocumentRequest",
            target_id=str(req.id),
            level="personal",
            notification_type="BOTH",
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Failed to notify user of rejected document request")

    return req
