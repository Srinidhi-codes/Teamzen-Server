from .base_template import get_base_template, button_html, info_row_html

def get_payroll_email_html(
    employee_name: str,
    month: str = "March 2026",
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
    payslip_url: str = "#",
    logo_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "#",
) -> str:
    """Generate the Payroll/Salary notification HTML email."""

    accent = "#16A34A"  # Green for money

    # Build earnings rows
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

    # Build deductions rows
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

    body = f"""
                <!-- Hero Section -->
                <tr>
                    <td class="hero-section" style="padding: 40px 40px 28px 40px; text-align: center; background: linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 50%, #BBF7D0 100%);">
                        <div style="font-size: 48px; line-height: 1; margin-bottom: 12px;">💰</div>
                        <h1 style="margin: 0 0 8px 0; font-size: 24px; font-weight: 800; color: #1E293B; letter-spacing: -0.5px;">
                            Salary Processed
                        </h1>
                        <p style="margin: 0; font-size: 14px; color: #64748B;">
                            {month}
                        </p>
                    </td>
                </tr>

                <!-- Net Salary Highlight -->
                <tr>
                    <td style="padding: 28px 40px 8px 40px; text-align: center;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background: linear-gradient(135deg, #065F46, #047857); border-radius: 16px;">
                            <tr>
                                <td style="padding: 28px 24px; text-align: center;">
                                    <p style="margin: 0 0 4px 0; font-size: 12px; font-weight: 600; color: #A7F3D0; text-transform: uppercase; letter-spacing: 1px;">Net Salary Credited</p>
                                    <p style="margin: 0; font-size: 36px; font-weight: 800; color: #FFFFFF; letter-spacing: -1px;">{net_salary}</p>
                                    {f'<p style="margin: 8px 0 0 0; font-size: 13px; color: #A7F3D0;">{payment_mode} · {payment_date}</p>' if payment_date else ""}
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>

                <!-- Snapshot Grid -->
                <tr>
                    <td style="padding: 8px 40px 8px 40px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                            <tr>
                                <td style="padding-right: 8px; vertical-align: top;">
                                    <div style="background: #FFFFFF; border: 1px solid #DCFCE7; border-radius: 14px; padding: 14px 16px;">
                                        <p style="margin: 0 0 6px 0; font-size: 11px; font-weight: 800; color: #16A34A; text-transform: uppercase; letter-spacing: 0.08em;">Gross</p>
                                        <p style="margin: 0; font-size: 18px; font-weight: 800; color: #0F172A;">{gross_salary or "—"}</p>
                                    </div>
                                </td>
                                <td style="padding-left: 8px; padding-right: 8px; vertical-align: top;">
                                    <div style="background: #FFFFFF; border: 1px solid #FEE2E2; border-radius: 14px; padding: 14px 16px;">
                                        <p style="margin: 0 0 6px 0; font-size: 11px; font-weight: 800; color: #DC2626; text-transform: uppercase; letter-spacing: 0.08em;">Deductions</p>
                                        <p style="margin: 0; font-size: 18px; font-weight: 800; color: #0F172A;">{total_deductions or "—"}</p>
                                    </div>
                                </td>
                                <td style="padding-left: 8px; vertical-align: top;">
                                    <div style="background: #FFFFFF; border: 1px solid #BFDBFE; border-radius: 14px; padding: 14px 16px;">
                                        <p style="margin: 0 0 6px 0; font-size: 11px; font-weight: 800; color: #2563EB; text-transform: uppercase; letter-spacing: 0.08em;">Payout</p>
                                        <p style="margin: 0; font-size: 18px; font-weight: 800; color: #0F172A;">{payment_mode}</p>
                                    </div>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>

                <!-- Message -->
                <tr>
                    <td class="content-block" style="padding: 24px 40px 16px 40px;">
                        <p style="margin: 0; font-size: 15px; color: #475569; line-height: 1.7;">
                            Hi <strong>{employee_name}</strong>, your salary for <strong>{month}</strong> has been processed successfully. Here's the breakdown:
                        </p>
                    </td>
                </tr>

                <!-- Employee Info -->
                {f'''
                <tr>
                    <td style="padding: 8px 40px 16px 40px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #F8FAFC; border-radius: 12px; border: 1px solid #E2E8F0;">
                            <tr>
                                <td style="padding: 16px 24px 8px 24px;">
                                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                        {info_row_html("Employee ID", employee_id, "🆔") if employee_id else ""}
                                        {info_row_html("Designation", designation, "💼") if designation else ""}
                                        {info_row_html("Department", department, "🏢") if department else ""}
                                    </table>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
                ''' if (employee_id or designation or department) else ""}

                <!-- Earnings -->
                {f'''
                <tr>
                    <td style="padding: 8px 40px 8px 40px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #F0FDF4; border-radius: 12px; border: 1px solid #BBF7D0;">
                            <tr>
                                <td style="padding: 16px 24px 8px 24px;">
                                    <p style="margin: 0 0 8px 0; font-size: 13px; font-weight: 700; color: #16A34A; text-transform: uppercase; letter-spacing: 1px;">💵 Earnings</p>
                                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                        {earnings_rows}
                                        <tr>
                                            <td style="padding: 10px 0; font-size: 14px; color: #1E293B; font-weight: 700;">Gross Salary</td>
                                            <td style="padding: 10px 0; font-size: 14px; color: #16A34A; font-weight: 800; text-align: right;">{gross_salary}</td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
                ''' if earnings_rows else ""}

                <!-- Deductions -->
                {f'''
                <tr>
                    <td style="padding: 8px 40px 24px 40px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #FEF2F2; border-radius: 12px; border: 1px solid #FECACA;">
                            <tr>
                                <td style="padding: 16px 24px 8px 24px;">
                                    <p style="margin: 0 0 8px 0; font-size: 13px; font-weight: 700; color: #DC2626; text-transform: uppercase; letter-spacing: 1px;">📉 Deductions</p>
                                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                        {deductions_rows}
                                        <tr>
                                            <td style="padding: 10px 0; font-size: 14px; color: #1E293B; font-weight: 700;">Total Deductions</td>
                                            <td style="padding: 10px 0; font-size: 14px; color: #DC2626; font-weight: 800; text-align: right;">- {total_deductions}</td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
                ''' if deductions_rows else ""}

                <!-- CTA -->
                <tr>
                    <td style="padding: 8px 40px 40px 40px; text-align: center;">
                        {button_html("📄 Download Payslip", payslip_url, accent)}
                        <p style="margin: 14px 0 0 0; font-size: 13px; color: #94A3B8;">
                            Review your detailed earnings, deductions, and payroll history inside Teamzen.
                        </p>
                    </td>
                </tr>
    """

    return get_base_template(
        title=f"Salary Processed - {month}",
        body_content=body,
        accent_color=accent,
        logo_url=logo_url,
        footer_text=company_name,
        company_url=company_url,
    )
