from .base_template import (
    get_base_template,
    button_html,
    info_row_html,
    status_badge_html,
    card_table_html,
    alert_box_html,
    hero_section_html,
    resolve_portal_url,
    sanitize_portal_url,
)


def get_onboarding_task_reminder_email_html(
    recipient_name: str,
    task_title: str = "Onboarding Task",
    hire_name: str = "",
    days_overdue: int = 0,
    message: str = "",
    is_overdue: bool = False,
    action_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "",
    logo_url: str = "",
) -> str:
    """
    Dedicated production-ready email template for onboarding task reminders and overdue notices.
    Directly prevents plain-text delivery for daily onboarding reminders.
    """
    safe_action_url = sanitize_portal_url(action_url, "onboarding")
    safe_company_url = sanitize_portal_url(company_url)

    overdue = is_overdue or days_overdue > 0 or "overdue" in task_title.lower() or "overdue" in message.lower()

    accent = "#0F766E"  # Teamzen Teal
    hero_bg = "#CCFBF1"  # Soft mint

    if overdue:
        badge_label = "OVERDUE ONBOARDING TASK"
        badge_color = "#0F766E"
        badge_bg = "#FFFFFF"
        headline = "Action Required: Overdue Onboarding Task"
        default_message = (
            f'The onboarding task "{task_title}" requires immediate attention. '
            f'Please review and complete this requirement in the Onboarding portal.'
        )
    else:
        badge_label = "ONBOARDING TASK ASSIGNED"
        badge_color = "#0F766E"
        badge_bg = "#FFFFFF"
        headline = "New Onboarding Task Assigned"
        default_message = (
            f'You have been assigned the task "{task_title}". '
            f'Please complete it to ensure timely onboarding progress.'
        )

    display_message = message or default_message

    rows = [
        ("Task Name", task_title),
    ]
    if hire_name:
        rows.append(("Employee", hire_name))
    if days_overdue > 0:
        rows.append(("Overdue Duration", f"{days_overdue} day(s) overdue"))
    rows.append(("Status", "Action Required" if overdue else "Pending"))

    body = f"""
        {hero_section_html(
            headline=headline,
            badge_label=badge_label,
            badge_color=badge_color,
            badge_bg=badge_bg,
            hero_bg=hero_bg,
        )}

        <tr>
            <td class="content-block" bgcolor="#FFFFFF" style="padding: 28px 36px 16px 36px; background-color: #FFFFFF;">
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    Hi <strong style="color: #0F172A;">{recipient_name or 'there'}</strong>,
                </p>
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    {display_message}
                </p>
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 24px 36px; background-color: #FFFFFF;">
                {card_table_html(rows, card_title="Task Details")}
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 28px 36px; background-color: #FFFFFF;">
                {alert_box_html(
                    "Completing onboarding tasks on time ensures complete employee records, swift IT provisioning, and verified payroll setup.",
                    title="Important Notice",
                    level="danger" if overdue else "info",
                )}
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 4px 36px 36px 36px; background-color: #FFFFFF; text-align: center;">
                {button_html("Complete in Onboarding", safe_action_url, accent)}
            </td>
        </tr>
    """

    return get_base_template(
        title=headline,
        body_content=body,
        accent_color=accent,
        accent_light=hero_bg,
        logo_url=logo_url,
        footer_text=company_name,
        company_url=safe_company_url,
        show_header_title=False,
    )


def get_preboarding_invite_email_html(
    employee_name: str,
    company_name: str = "Teamzen",
    join_date: str = "",
    invite_url: str = "",
    designation: str = "",
    logo_url: str = "",
    company_url: str = "",
    has_offer_attachment: bool = False,
    offer_pdf_url: str = "",
) -> str:
    """Preboarding portal invitation email."""
    accent = "#0F766E"
    hero_bg = "#CCFBF1"
    safe_company_url = sanitize_portal_url(company_url)
    safe_invite_url = sanitize_portal_url(invite_url, "preboarding")

    rows = []
    if designation:
        rows.append(("Designation", designation))
    if join_date:
        rows.append(("Joining Date", join_date))
    rows.append(("Portal Access", "Active"))

    offer_callout = ""
    if has_offer_attachment or offer_pdf_url:
        offer_callout = f"""
        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 20px 36px; background-color: #FFFFFF;">
                {alert_box_html(
                    "Your official offer letter PDF is attached to this email. Please review the terms and accept it through the preboarding portal.",
                    title="Offer Letter Enclosed",
                    level="info",
                )}
            </td>
        </tr>
        """

    pdf_btn = ""
    if offer_pdf_url and offer_pdf_url.startswith("http"):
        pdf_btn = f"""
        <div style="margin-bottom: 14px;">
            {button_html("Download Offer Letter PDF", offer_pdf_url, accent)}
        </div>
        """

    safe_url = safe_invite_url or "#"
    link_fallback = f"""
    <p style="margin: 16px 0 0 0; font-size: 12px; color: #64748B; line-height: 1.5; word-break: break-all;">
        If the button does not open, visit: <a href="{safe_url}" style="color: {accent}; font-weight: 600;">{safe_url}</a>
    </p>
    """

    body = f"""
        {hero_section_html(
            headline="Welcome to the Team",
            subtitle=f"Complete your preboarding for {company_name}",
            badge_label="PREBOARDING INVITATION",
            badge_color="#0F766E",
            badge_bg="#FFFFFF",
            hero_bg=hero_bg,
        )}

        <tr>
            <td class="content-block" bgcolor="#FFFFFF" style="padding: 28px 36px 16px 36px; background-color: #FFFFFF;">
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    Hi <strong style="color: #0F172A;">{employee_name}</strong>,
                </p>
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    We are pleased to welcome you to <strong>{company_name}</strong>. Before your first day, please access our secure preboarding portal to submit required identification documents, tax details, and accept your offer.
                </p>
            </td>
        </tr>

        {offer_callout}

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 24px 36px; background-color: #FFFFFF;">
                {card_table_html(rows, card_title="Employment Overview")}
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 8px 36px 36px 36px; background-color: #FFFFFF; text-align: center;">
                {pdf_btn}
                {button_html("Open Preboarding Portal", safe_invite_url, accent)}
                {link_fallback}
            </td>
        </tr>
    """

    return get_base_template(
        title=f"Complete your preboarding for {company_name}",
        body_content=body,
        logo_url=logo_url,
        accent_color=accent,
        accent_light=hero_bg,
        footer_text=company_name,
        company_url=safe_company_url,
        show_header_title=False,
    )


def get_document_rejected_email_html(
    employee_name: str,
    category: str = "Document",
    reason: str = "",
    action_url: str = "",
    logo_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "",
) -> str:
    """Document revision requested notification."""
    accent = "#0F766E"
    hero_bg = "#CCFBF1"
    safe_company_url = sanitize_portal_url(company_url)
    safe_action_url = sanitize_portal_url(action_url, "onboarding")

    rows = [
        ("Document Type", category.replace("_", " ").title()),
        ("Review Status", "Revision Required"),
    ]
    if reason:
        rows.append(("Reviewer Feedback", reason))

    body = f"""
        {hero_section_html(
            headline="Document Attention Required",
            badge_label="DOCUMENT REVISION",
            badge_color="#0F766E",
            badge_bg="#FFFFFF",
            hero_bg=hero_bg,
        )}

        <tr>
            <td class="content-block" bgcolor="#FFFFFF" style="padding: 28px 36px 16px 36px; background-color: #FFFFFF;">
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    Hi <strong style="color: #0F172A;">{employee_name}</strong>,
                </p>
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    Your uploaded <strong>{category}</strong> document could not be verified. Please review the note below and upload a clear, valid copy through the employee portal.
                </p>
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 24px 36px; background-color: #FFFFFF;">
                {card_table_html(rows, card_title="Review Details")}
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 28px 36px; background-color: #FFFFFF;">
                {alert_box_html(
                    "Please ensure the document copy is clearly legible, all corners are visible, and the information matches your profile.",
                    title="Submission Guideline",
                    level="warning",
                )}
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 4px 36px 36px 36px; background-color: #FFFFFF; text-align: center;">
                {button_html("Re-upload Document", safe_action_url, accent)}
            </td>
        </tr>
    """

    return get_base_template(
        title="Document revision required",
        body_content=body,
        logo_url=logo_url,
        accent_color=accent,
        accent_light=hero_bg,
        footer_text=company_name,
        company_url=safe_company_url,
        show_header_title=False,
    )

