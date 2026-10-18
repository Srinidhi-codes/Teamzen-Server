from .base_template import (
    get_base_template,
    button_html,
    status_badge_html,
    card_table_html,
    alert_box_html,
    hero_section_html,
    sanitize_portal_url,
)


def get_payroll_email_html(
    employee_name: str,
    month: str = "Current Month",
    employee_id: str = "",
    designation: str = "",
    department: str = "",
    basic_salary: str = "",
    hra: str = "",
    special_allowance: str = "",
    other_earnings: str = "",
    gross_salary: str = "",
    pf_deduction: str = "",
    tax_deduction: str = "",
    other_deductions: str = "",
    total_deductions: str = "",
    net_salary: str = "",
    payment_date: str = "",
    payment_mode: str = "Bank Transfer",
    payslip_url: str = "",
    logo_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "",
) -> str:
    """Generate the Payroll/Salary notification HTML email with clean executive styling."""
    accent = "#0F766E"  # Teamzen Teal
    hero_bg = "#CCFBF1"  # Soft mint
    safe_payslip_url = sanitize_portal_url(payslip_url, "payslips")
    safe_company_url = sanitize_portal_url(company_url)

    earnings_rows = ""
    if basic_salary:
        earnings_rows += f"""<tr>
            <td style="padding: 8px 0; font-size: 13px; color: #475569; border-bottom: 1px solid #F1F5F9;">Basic Salary</td>
            <td style="padding: 8px 0; font-size: 13px; color: #1E293B; font-weight: 600; text-align: right; border-bottom: 1px solid #F1F5F9;">{basic_salary}</td>
        </tr>"""
    if hra:
        earnings_rows += f"""<tr>
            <td style="padding: 8px 0; font-size: 13px; color: #475569; border-bottom: 1px solid #F1F5F9;">HRA</td>
            <td style="padding: 8px 0; font-size: 13px; color: #1E293B; font-weight: 600; text-align: right; border-bottom: 1px solid #F1F5F9;">{hra}</td>
        </tr>"""
    if special_allowance:
        earnings_rows += f"""<tr>
            <td style="padding: 8px 0; font-size: 13px; color: #475569; border-bottom: 1px solid #F1F5F9;">Special Allowance</td>
            <td style="padding: 8px 0; font-size: 13px; color: #1E293B; font-weight: 600; text-align: right; border-bottom: 1px solid #F1F5F9;">{special_allowance}</td>
        </tr>"""
    if other_earnings:
        earnings_rows += f"""<tr>
            <td style="padding: 8px 0; font-size: 13px; color: #475569; border-bottom: 1px solid #F1F5F9;">Other Earnings</td>
            <td style="padding: 8px 0; font-size: 13px; color: #1E293B; font-weight: 600; text-align: right; border-bottom: 1px solid #F1F5F9;">{other_earnings}</td>
        </tr>"""

    deductions_rows = ""
    if pf_deduction:
        deductions_rows += f"""<tr>
            <td style="padding: 8px 0; font-size: 13px; color: #475569; border-bottom: 1px solid #F1F5F9;">Provident Fund</td>
            <td style="padding: 8px 0; font-size: 13px; color: #DC2626; font-weight: 600; text-align: right; border-bottom: 1px solid #F1F5F9;">- {pf_deduction}</td>
        </tr>"""
    if tax_deduction:
        deductions_rows += f"""<tr>
            <td style="padding: 8px 0; font-size: 13px; color: #475569; border-bottom: 1px solid #F1F5F9;">Income Tax (TDS)</td>
            <td style="padding: 8px 0; font-size: 13px; color: #DC2626; font-weight: 600; text-align: right; border-bottom: 1px solid #F1F5F9;">- {tax_deduction}</td>
        </tr>"""
    if other_deductions:
        deductions_rows += f"""<tr>
            <td style="padding: 8px 0; font-size: 13px; color: #475569; border-bottom: 1px solid #F1F5F9;">Other Deductions</td>
            <td style="padding: 8px 0; font-size: 13px; color: #DC2626; font-weight: 600; text-align: right; border-bottom: 1px solid #F1F5F9;">- {other_deductions}</td>
        </tr>"""

    info_rows = []
    if employee_id:
        info_rows.append(("Employee ID", employee_id))
    if designation:
        info_rows.append(("Designation", designation))
    if department:
        info_rows.append(("Department", department))
    if payment_date:
        info_rows.append(("Disbursement Date", payment_date))
    info_rows.append(("Payment Method", payment_mode))

    info_card_markup = ""
    if info_rows:
        info_card_markup = f"""
        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 20px 36px; background-color: #FFFFFF;">
                {card_table_html(info_rows, card_title="Disbursement Information")}
            </td>
        </tr>
        """

    net_display = net_salary or "Processed"
    net_card_markup = f"""
    <tr>
        <td bgcolor="#FFFFFF" style="padding: 0 36px 24px 36px; background-color: #FFFFFF;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" bgcolor="#047857" style="background-color: #047857; border-radius: 12px; text-align: center;">
                <tr>
                    <td style="padding: 24px 20px; text-align: center;">
                        <p style="margin: 0 0 6px 0; font-size: 12px; font-weight: 700; color: #A7F3D0; text-transform: uppercase; letter-spacing: 0.08em;">
                            Net Salary Credited
                        </p>
                        <p style="margin: 0; font-size: 32px; font-weight: 800; color: #FFFFFF; letter-spacing: -0.5px;">
                            {net_display}
                        </p>
                        <p style="margin: 6px 0 0 0; font-size: 13px; color: #D1FAE5;">
                            {month} &bull; {payment_mode}
                        </p>
                    </td>
                </tr>
            </table>
        </td>
    </tr>
    """

    breakdown_markup = ""
    if earnings_rows or deductions_rows:
        earnings_table = ""
        if earnings_rows:
            earnings_table = f"""
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" bgcolor="#F8FAFC" style="background-color: #F8FAFC; border-radius: 10px; border: 1px solid #E2E8F0; margin-bottom: 16px;">
                <tr>
                    <td style="padding: 16px 20px;">
                        <p style="margin: 0 0 8px 0; font-size: 11px; font-weight: 700; color: #047857; text-transform: uppercase; letter-spacing: 0.06em;">Earnings Breakdown</p>
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                            {earnings_rows}
                            {f'<tr><td style="padding: 10px 0 0 0; font-size: 13px; font-weight: 700; color: #0F172A;">Gross Earnings</td><td style="padding: 10px 0 0 0; font-size: 13px; font-weight: 800; color: #047857; text-align: right;">{gross_salary}</td></tr>' if gross_salary else ''}
                        </table>
                    </td>
                </tr>
            </table>
            """

        deductions_table = ""
        if deductions_rows:
            deductions_table = f"""
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" bgcolor="#F8FAFC" style="background-color: #F8FAFC; border-radius: 10px; border: 1px solid #E2E8F0;">
                <tr>
                    <td style="padding: 16px 20px;">
                        <p style="margin: 0 0 8px 0; font-size: 11px; font-weight: 700; color: #B91C1C; text-transform: uppercase; letter-spacing: 0.06em;">Deductions Breakdown</p>
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                            {deductions_rows}
                            {f'<tr><td style="padding: 10px 0 0 0; font-size: 13px; font-weight: 700; color: #0F172A;">Total Deductions</td><td style="padding: 10px 0 0 0; font-size: 13px; font-weight: 800; color: #B91C1C; text-align: right;">- {total_deductions}</td></tr>' if total_deductions else ''}
                        </table>
                    </td>
                </tr>
            </table>
            """

        breakdown_markup = f"""
        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 24px 36px; background-color: #FFFFFF;">
                {earnings_table}
                {deductions_table}
            </td>
        </tr>
        """

    body = f"""
        {hero_section_html(
            headline="Salary Processed",
            subtitle=f"Payroll statement for {month}",
            badge_label="PAYROLL DISBURSED",
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
                    Your salary for <strong>{month}</strong> has been processed successfully. You can review your detailed payslip and tax calculations below.
                </p>
            </td>
        </tr>

        {net_card_markup}
        {info_card_markup}
        {breakdown_markup}

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 28px 36px; background-color: #FFFFFF;">
                {alert_box_html(
                    "This salary advice contains confidential compensation information. If you have any inquiries regarding your statement, please contact the payroll department.",
                    title="Confidential Statement",
                    level="neutral",
                )}
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 4px 36px 36px 36px; background-color: #FFFFFF; text-align: center;">
                {button_html("View Payslip Online", safe_payslip_url, accent)}
            </td>
        </tr>
    """

    return get_base_template(
        title=f"Salary Processed - {month}",
        body_content=body,
        accent_color=accent,
        accent_light=hero_bg,
        logo_url=logo_url,
        footer_text=company_name,
        company_url=safe_company_url,
        show_header_title=False,
    )
