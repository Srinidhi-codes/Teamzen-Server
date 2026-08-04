from .base_template import get_base_template, button_html, info_row_html


def get_preboarding_invite_email_html(
    employee_name: str,
    company_name: str = "Teamzen",
    join_date: str = "",
    invite_url: str = "#",
    designation: str = "",
    logo_url: str = "",
    company_url: str = "#",
) -> str:
    details = ""
    if designation:
        details += info_row_html("Role", designation, "💼")
    if join_date:
        details += info_row_html("Joining Date", join_date, "📅")

    body = f"""
                <tr>
                    <td style="padding: 48px 40px 24px 40px; text-align: center; background: linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 50%, #A7F3D0 100%);">
                        <div style="font-size: 48px; margin-bottom: 12px;">🚀</div>
                        <h1 style="margin: 0 0 8px 0; font-size: 24px; font-weight: 800; color: #064E3B;">
                            Let's get you ready for day one
                        </h1>
                        <p style="margin: 0; font-size: 15px; color: #047857;">
                            Hi <strong>{employee_name}</strong>, complete your preboarding with {company_name}.
                        </p>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 24px 40px;">
                        <p style="margin: 0 0 16px 0; font-size: 14px; color: #334155; line-height: 1.6;">
                            Before your first day, please upload required documents, fill bank/tax details,
                            and accept your offer letter.
                        </p>
                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom: 24px;">
                            {details}
                        </table>
                        {button_html(invite_url, "Open preboarding portal")}
                    </td>
                </tr>
    """
    return get_base_template(
        title=f"Complete your preboarding for {company_name}",
        body_content=body,
        logo_url=logo_url,
        accent_color="#059669",
        accent_light="#ECFDF5",
        footer_text=company_name,
        company_url=company_url,
    )


def get_document_rejected_email_html(
    employee_name: str,
    category: str = "document",
    reason: str = "",
    action_url: str = "#",
    logo_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "#",
) -> str:
    reason_row = info_row_html(
        "Reason", reason or "Please re-upload a clearer copy.", "ℹ️"
    )
    body = f"""
                <tr>
                    <td style="padding: 40px 40px 20px 40px; text-align: center; background: #FEF2F2;">
                        <div style="font-size: 40px; margin-bottom: 8px;">📄</div>
                        <h1 style="margin: 0; font-size: 22px; color: #991B1B;">Document needs attention</h1>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 24px 40px;">
                        <p style="font-size: 14px; color: #334155; line-height: 1.6;">
                            Hi {employee_name}, your <strong>{category}</strong> upload was rejected.
                        </p>
                        {reason_row}
                        <div style="margin-top: 20px;">
                            {button_html(action_url, "Re-upload document")}
                        </div>
                    </td>
                </tr>
    """
    return get_base_template(
        title="Your document was rejected — please re-upload",
        body_content=body,
        logo_url=logo_url,
        accent_color="#DC2626",
        accent_light="#FEF2F2",
        footer_text=company_name,
        company_url=company_url,
    )
