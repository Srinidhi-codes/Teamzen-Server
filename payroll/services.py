import calendar
import os
import tempfile
import urllib.request
from datetime import date
from decimal import Decimal
from fpdf import FPDF
from django.db import transaction
from django.db.models import Prefetch
from .models import (
    EmployeeComponentOverride,
    EmployeeSalaryStructure,
    PayrollRun,
    Payslip,
    PayslipComponent,
    PayrollAdjustment,
    SalaryAdvance,
    SalaryStructureComponent,
)
from attendance.models import AttendanceRecord
from leaves.models import LeaveRequest


def _fmt_inr(amount) -> str:
    """Format amount like 14,418 (Indian grouping, no currency symbol)."""
    try:
        n = int(Decimal(str(amount)).quantize(Decimal("1")))
    except Exception:
        return str(amount)
    # Indian grouping: last 3 digits, then pairs (e.g. 12,34,567)
    neg = n < 0
    s = str(abs(n))
    if len(s) <= 3:
        out = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        parts = []
        while rest:
            parts.append(rest[-2:])
            rest = rest[:-2]
        out = ",".join(list(reversed(parts)) + [last3])
    return f"-{out}" if neg else out


def _download_image_to_temp(url: str, suffix: str = ".png") -> str | None:
    """Download a remote image URL to a temp file; return path or None."""
    if not url:
        return None
    try:
        if url.startswith("//"):
            url = "https:" + url
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.close()
        urllib.request.urlretrieve(url, tmp.name)
        return tmp.name
    except Exception:
        return None


def _resolve_logo_path(organization) -> tuple[str | None, bool]:
    """Return (local path, is_temp) for the org logo."""
    if not organization or not getattr(organization, "logo", None):
        return None, False
    logo = organization.logo
    try:
        path = logo.path
        if path and os.path.isfile(path):
            return path, False
    except Exception:
        pass
    try:
        url = logo.url
        if not url:
            return None, False
        if url.startswith("/"):
            from django.conf import settings

            candidate = os.path.join(settings.MEDIA_ROOT, logo.name)
            if os.path.isfile(candidate):
                return candidate, False
            return None, False
        suffix = os.path.splitext(logo.name or "logo.png")[1] or ".png"
        path = _download_image_to_temp(url, suffix=suffix)
        return path, bool(path)
    except Exception:
        return None, False


class PayrollService:
    @staticmethod
    def get_days_in_month(year, month):
        return calendar.monthrange(year, month)[1]

    @staticmethod
    def calculate_lop_days(user, year, month):
        """
        LOP = max(attendance-based LOP, unpaid-leave LOP) to avoid double-counting
        when unpaid leave days are also marked absent in attendance.
        """
        absent_days = AttendanceRecord.objects.filter(
            user=user,
            attendance_date__year=year,
            attendance_date__month=month,
            status="absent",
        ).count()

        half_days = AttendanceRecord.objects.filter(
            user=user,
            attendance_date__year=year,
            attendance_date__month=month,
            status="half_day",
        ).count()

        attendance_lop = Decimal(absent_days) + (Decimal(half_days) * Decimal("0.5"))

        unpaid_leaves = LeaveRequest.objects.filter(
            user=user,
            _status="approved",
            leave_type__is_paid_leave=False,
            from_date__year=year,
            from_date__month=month,
        )
        leave_lop = sum((Decimal(str(leaf.duration_days)) for leaf in unpaid_leaves), Decimal("0"))

        return max(attendance_lop, leave_lop)

    @staticmethod
    def estimate_lop_cost(user, unpaid_days, year=None, month=None):
        today = date.today()
        year = year or today.year
        month = month or today.month
        unpaid = Decimal(str(unpaid_days))
        if unpaid < 0:
            return {"error": "unpaid_days must be >= 0"}

        structure = (
            EmployeeSalaryStructure.objects.filter(user=user, is_active=True)
            .order_by("-effective_from")
            .first()
        )
        if not structure or not structure.annual_ctc:
            return {"error": "No active salary structure / CTC found for this employee."}

        days_in_month = PayrollService.get_days_in_month(year, month)
        monthly_ctc = Decimal(structure.annual_ctc) / Decimal(12)
        per_day = monthly_ctc / Decimal(days_in_month)
        estimated_loss = (per_day * unpaid).quantize(Decimal("0.01"))
        estimated_net_if_full = monthly_ctc.quantize(Decimal("0.01"))
        estimated_net_after = (monthly_ctc - estimated_loss).quantize(Decimal("0.01"))

        return {
            "year": year,
            "month": month,
            "unpaid_days": float(unpaid),
            "days_in_month": days_in_month,
            "annual_ctc": float(structure.annual_ctc),
            "monthly_ctc": float(monthly_ctc.quantize(Decimal("0.01"))),
            "per_day_rate": float(per_day.quantize(Decimal("0.01"))),
            "estimated_loss": float(estimated_loss),
            "estimated_monthly_gross_reference": float(estimated_net_if_full),
            "estimated_monthly_after_lop": float(estimated_net_after),
            "note": (
                "Estimate uses monthly CTC / calendar days × unpaid days "
                "(same LOP method as payroll). Actual net may differ after "
                "statutory deductions and adjustments."
            ),
        }

    @staticmethod
    def run_has_locked_payslips(payroll_run) -> bool:
        return Payslip.objects.filter(
            payroll_run=payroll_run, status__in=["published", "paid"]
        ).exists()

    @staticmethod
    def create_draft_run(organization, month: int, year: int, processed_by=None) -> PayrollRun:
        if month < 1 or month > 12:
            raise ValueError("Month must be between 1 and 12")
        run, created = PayrollRun.objects.get_or_create(
            organization=organization,
            month=month,
            year=year,
            defaults={"processed_by": processed_by, "status": "draft"},
        )
        if not created and run.status == "failed":
            run.status = "draft"
            run.processed_by = processed_by or run.processed_by
            run.save(update_fields=["status", "processed_by"])
        elif not created and run.status not in ("draft", "failed"):
            # Already processed — return existing (caller decides to process again)
            pass
        return run

    @staticmethod
    def preview_advance_recoveries(organization, user_ids=None):
        """Active advances that would be deducted on the next process."""
        qs = SalaryAdvance.objects.filter(
            organization=organization, status="active", remaining_balance__gt=0
        ).select_related("user")
        if user_ids is not None:
            qs = qs.filter(user_id__in=user_ids)
        rows = []
        for adv in qs:
            deduct = min(adv.installment_amount, adv.remaining_balance)
            rows.append(
                {
                    "advance_id": adv.id,
                    "user_id": adv.user_id,
                    "user_name": f"{adv.user.first_name} {adv.user.last_name}".strip()
                    or adv.user.email,
                    "deduct": deduct,
                    "remaining_after": adv.remaining_balance - deduct,
                }
            )
        return rows

    @transaction.atomic
    def process_payroll(self, payroll_run_id):
        payroll_run = PayrollRun.objects.select_for_update().get(id=payroll_run_id)

        if self.run_has_locked_payslips(payroll_run):
            raise Exception(
                "Cannot recalculate: one or more payslips are already published or paid."
            )

        payroll_run.status = "processing"
        payroll_run.save(update_fields=["status"])

        try:
            Payslip.objects.filter(payroll_run=payroll_run).delete()

            PayrollAdjustment.objects.filter(
                organization=payroll_run.organization,
                month=payroll_run.month,
                year=payroll_run.year,
            ).update(is_processed=False)

            # Include anyone whose CTC started on or before the end of this pay month
            # (mid-month joins / same-month CTC assignment should still appear).
            days_in_month = self.get_days_in_month(payroll_run.year, payroll_run.month)
            period_end = date(payroll_run.year, payroll_run.month, days_in_month)

            all_structs = (
                EmployeeSalaryStructure.objects.filter(
                    user__organization=payroll_run.organization,
                    is_active=True,
                    effective_from__lte=period_end,
                )
                .select_related("user", "salary_structure", "user__designation", "user__department")
                .prefetch_related(
                    Prefetch(
                        "salary_structure__components",
                        queryset=SalaryStructureComponent.objects.select_related(
                            "component", "base_component"
                        ),
                    )
                )
                .order_by("user_id", "-effective_from")
            )

            seen_users = set()
            employee_structures = []
            for emp_struct in all_structs:
                if emp_struct.user_id in seen_users:
                    continue
                seen_users.add(emp_struct.user_id)
                employee_structures.append(emp_struct)

            total_org_gross = Decimal("0.00")
            total_org_deduction = Decimal("0.00")
            total_org_net = Decimal("0.00")
            # days_in_month already computed above for period_end

            for emp_struct in employee_structures:
                user = emp_struct.user
                monthly_ctc = (emp_struct.annual_ctc / Decimal(12)).quantize(Decimal("0.01"))

                lop_days = self.calculate_lop_days(user, payroll_run.year, payroll_run.month)
                worked_days = Decimal(days_in_month) - lop_days
                lop_deduction_amount = (
                    (monthly_ctc / Decimal(days_in_month)) * lop_days
                ).quantize(Decimal("0.01"))

                payslip = Payslip.objects.create(
                    payroll_run=payroll_run,
                    user=user,
                    designation=getattr(user.designation, "name", "") or "",
                    department=getattr(user.department, "name", "") or "",
                    worked_days=worked_days,
                    lop_days=lop_days,
                    gross_earnings=0,
                    total_deductions=0,
                    net_pay=0,
                    status="draft",
                )

                # Build override lookup for this employee
                overrides = {
                    o.component_id: o
                    for o in emp_struct.component_overrides.select_related("component").all()
                }

                gross_earnings = Decimal("0.00")
                total_deductions = Decimal("0.00")
                calculated_components = {"CTC": monthly_ctc}

                def resolve_amount(sc):
                    ovr = overrides.get(sc.component_id)
                    if ovr and ovr.is_excluded:
                        return None  # skip
                    if ovr and ovr.override_value is not None:
                        return Decimal(ovr.override_value).quantize(Decimal("0.01")), True
                    if sc.calculation_type == "flat":
                        return Decimal(sc.value).quantize(Decimal("0.01")), True
                    if sc.calculation_type == "percentage":
                        base_code = sc.base_component.code if sc.base_component else "CTC"
                        # Wait until base component is calculated (except CTC which is always ready)
                        if base_code not in calculated_components:
                            return None, False
                        base_val = calculated_components[base_code]
                        amount = (base_val * sc.value) / Decimal(100)
                        return Decimal(amount).quantize(Decimal("0.01")), True
                    return Decimal("0.00"), True

                def process_components(components, component_type):
                    nonlocal gross_earnings, total_deductions
                    pending = [
                        sc for sc in components
                        if not ((ovr := overrides.get(sc.component_id)) and ovr.is_excluded)
                    ]
                    # Resolve % dependencies in order (e.g. HRA after BASIC)
                    max_passes = len(pending) + 1
                    for _ in range(max_passes):
                        if not pending:
                            break
                        next_pending = []
                        progressed = False
                        for sc in pending:
                            amount, ready = resolve_amount(sc)
                            if not ready:
                                next_pending.append(sc)
                                continue
                            progressed = True
                            if amount is None:
                                continue
                            PayslipComponent.objects.create(
                                payslip=payslip,
                                component_name=sc.component.name,
                                component_code=sc.component.code,
                                component_type=component_type,
                                amount=amount,
                            )
                            if component_type == "earning":
                                gross_earnings += amount
                            else:
                                total_deductions += amount
                            calculated_components[sc.component.code] = amount
                        pending = next_pending
                        if not progressed:
                            # Unresolved dependency — treat missing base as 0
                            for sc in pending:
                                ovr = overrides.get(sc.component_id)
                                if ovr and ovr.override_value is not None:
                                    amount = Decimal(ovr.override_value).quantize(Decimal("0.01"))
                                elif sc.calculation_type == "flat":
                                    amount = Decimal(sc.value).quantize(Decimal("0.01"))
                                else:
                                    amount = Decimal("0.00")
                                PayslipComponent.objects.create(
                                    payslip=payslip,
                                    component_name=sc.component.name,
                                    component_code=sc.component.code,
                                    component_type=component_type,
                                    amount=amount,
                                )
                                if component_type == "earning":
                                    gross_earnings += amount
                                else:
                                    total_deductions += amount
                                calculated_components[sc.component.code] = amount
                            break

                earnings = [
                    sc
                    for sc in emp_struct.salary_structure.components.all()
                    if sc.component.component_type == "earning"
                ]
                process_components(earnings, "earning")

                deductions = [
                    sc
                    for sc in emp_struct.salary_structure.components.all()
                    if sc.component.component_type == "deduction"
                ]
                process_components(deductions, "deduction")

                if lop_days > 0:
                    PayslipComponent.objects.create(
                        payslip=payslip,
                        component_name=f"LOP Deduction ({lop_days} days)",
                        component_code="LOP",
                        component_type="deduction",
                        amount=lop_deduction_amount,
                    )
                    total_deductions += lop_deduction_amount

                adjustments = PayrollAdjustment.objects.filter(
                    user=user,
                    month=payroll_run.month,
                    year=payroll_run.year,
                    is_processed=False,
                )
                for adj in adjustments:
                    amt = Decimal(adj.amount).quantize(Decimal("0.01"))
                    PayslipComponent.objects.create(
                        payslip=payslip,
                        component_name=f"Adjustment: {adj.reason}",
                        component_code="ADJ",
                        component_type=adj.adjustment_type,
                        amount=amt,
                    )
                    if adj.adjustment_type == "earning":
                        gross_earnings += amt
                    else:
                        total_deductions += amt
                    adj.is_processed = True
                    adj.save(update_fields=["is_processed"])

                # Salary advance recoveries
                advances = SalaryAdvance.objects.select_for_update().filter(
                    user=user,
                    organization=payroll_run.organization,
                    status="active",
                    remaining_balance__gt=0,
                )
                for adv in advances:
                    deduct = min(adv.installment_amount, adv.remaining_balance).quantize(
                        Decimal("0.01")
                    )
                    if deduct <= 0:
                        continue
                    PayslipComponent.objects.create(
                        payslip=payslip,
                        component_name="Salary advance recovery",
                        component_code="ADV",
                        component_type="deduction",
                        amount=deduct,
                    )
                    total_deductions += deduct
                    adv.remaining_balance = (adv.remaining_balance - deduct).quantize(
                        Decimal("0.01")
                    )
                    adv.recovered_so_far = (adv.recovered_so_far + deduct).quantize(
                        Decimal("0.01")
                    )
                    if adv.remaining_balance <= 0:
                        adv.remaining_balance = Decimal("0.00")
                        adv.status = "completed"
                    adv.save(
                        update_fields=[
                            "remaining_balance",
                            "recovered_so_far",
                            "status",
                            "updated_at",
                        ]
                    )

                payslip.gross_earnings = gross_earnings.quantize(Decimal("0.01"))
                payslip.total_deductions = total_deductions.quantize(Decimal("0.01"))
                payslip.net_pay = (gross_earnings - total_deductions).quantize(
                    Decimal("0.01")
                )
                payslip.save()

                total_org_gross += payslip.gross_earnings
                total_org_deduction += payslip.total_deductions
                total_org_net += payslip.net_pay

            payroll_run.total_gross = total_org_gross
            payroll_run.total_deduction = total_org_deduction
            payroll_run.total_net_pay = total_org_net
            payroll_run.status = "completed"
            payroll_run.save()

            try:
                from payroll.anomaly import scan_payroll_anomalies, format_anomaly_digest
                from notifications.utils import notify_user
                anomaly_flags = scan_payroll_anomalies(payroll_run.id)
                if anomaly_flags:
                    digest = format_anomaly_digest(anomaly_flags, payroll_run)
                    admins = CustomUser.objects.filter(
                        organization_id=payroll_run.organization_id,
                        role__in=["admin", "superadmin"],
                        is_active=True,
                    )
                    for admin in admins:
                        notify_user(
                            recipient_id=admin.id,
                            verb="payroll_anomaly",
                            message=digest,
                            target_type="Payroll Run",
                            target_id=str(payroll_run.id),
                            level="admin",
                        )
                    try:
                        from notifications.proactive import notify_bot_user
                        for admin in admins:
                            notify_bot_user(admin, digest)
                    except Exception:
                        pass
            except Exception:
                import logging
                logging.getLogger(__name__).exception("Anomaly scan failed for run=%s", payroll_run.id)

            return True

        except Exception as e:
            import traceback

            payroll_run.status = "failed"
            payroll_run.save(update_fields=["status"])
            print("--- PAYROLL ERROR ---")
            traceback.print_exc()
            print(f"Error details: {str(e)}")
            print("----------------------")
            if "published or paid" in str(e).lower() or "Cannot recalculate" in str(e):
                raise
            return False

    @staticmethod
    def generate_payslip_pdf(payslip, *, template_override=None, persist=True):
        """
        Payslip PDF styled like modern Indian payroll slips
        (org logo + company name header, net-pay hero, detail grid,
        earnings/deductions tables).

        template_override: optional PayslipTemplate to force theme/layout (demo).
        persist: if False, return PDF bytes without uploading to Cloudinary.

        If the org default (or override) is an uploaded PDF template, the slip
        is generated on top of that PDF as a full-page background.
        """
        from payroll.template_services import (
            theme_for_payslip,
            resolve_template_for_org,
            _template_uses_uploaded_pdf,
        )

        org = payslip.payroll_run.organization
        tpl = template_override or resolve_template_for_org(org)
        layout_key = getattr(tpl, "layout_key", None) if tpl else None
        theme = (getattr(tpl, "theme", None) or {}) if tpl else {}
        if (
            _template_uses_uploaded_pdf(tpl)
            or layout_key == "networth"
            or theme.get("renderer") == "networth_replica"
        ):
            return PayrollService._generate_payslip_on_uploaded_template(
                payslip, tpl, persist=persist
            )

        org_name = org.name
        month_name = calendar.month_name[payslip.payroll_run.month]
        year = payslip.payroll_run.year
        month_short = calendar.month_abbr[payslip.payroll_run.month]
        period_label = f"{month_short} {year}"

        from payroll.template_services import hex_to_rgb

        layout_key, theme = theme_for_payslip(
            payslip, template_override=template_override
        )
        c_primary = hex_to_rgb(theme.get("primary"), (33, 37, 41))
        c_muted = hex_to_rgb(theme.get("muted"), (108, 117, 125))
        c_accent = hex_to_rgb(theme.get("accent"), (13, 110, 253))
        c_hero = hex_to_rgb(theme.get("hero_bg"), (248, 249, 250))
        c_earn = hex_to_rgb(theme.get("earning_bg"), (240, 253, 244))
        c_ded = hex_to_rgb(theme.get("deduction_bg"), (254, 242, 242))
        c_th_bg = hex_to_rgb(theme.get("table_header_bg"), (33, 37, 41))
        c_th_fg = hex_to_rgb(theme.get("table_header_fg"), (255, 255, 255))
        show_logo = theme.get("show_logo", True)
        show_net_hero = theme.get("show_net_hero", True)
        show_teamzen = theme.get("show_teamzen_mark", True)
        # compact / minimal tweak spacing slightly
        compact = layout_key in ("compact", "minimal")

        user = payslip.user
        name = f"{user.first_name} {user.last_name}".strip() or user.email
        earnings = list(payslip.components.filter(component_type="earning"))
        deductions = list(payslip.components.filter(component_type="deduction"))

        emp_code = user.employee_id or str(user.id)
        pan = user.pan_number or "-"
        account_no = user.bank_account_number or "-"
        ifsc = user.bank_ifsc_code or "-"
        dob = user.date_of_birth
        doj = user.date_of_joining
        regime = "-"

        def _fmt_date(d):
            if not d:
                return "-"
            if hasattr(d, "strftime"):
                return d.strftime("%d/%m/%Y")
            return str(d)

        logo_path, logo_is_temp = (None, False)
        if show_logo:
            logo_path, logo_is_temp = _resolve_logo_path(org)
        tmp_paths: list[str] = []
        if logo_is_temp and logo_path:
            tmp_paths.append(logo_path)

        # Teamzen product mark (right side — matches "Generated by" branding)
        teamzen_logo = None
        if show_teamzen:
            try:
                from django.conf import settings

                teamzen_url = getattr(settings, "EMAIL_LOGO_URL", "") or ""
                teamzen_logo = _download_image_to_temp(teamzen_url, suffix=".png")
                if teamzen_logo:
                    tmp_paths.append(teamzen_logo)
            except Exception:
                teamzen_logo = None

        pdf = FPDF(unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=18)
        pdf.add_page()
        pdf.set_margins(14, 14, 14)

        # ── Header: org logo + company name | Payslip period + Teamzen mark ──
        header_y = 12
        text_x = 14
        if logo_path:
            try:
                pdf.image(logo_path, x=14, y=header_y, h=14)
                text_x = 34
            except Exception:
                text_x = 14

        pdf.set_xy(text_x, header_y + 1)
        pdf.set_font("helvetica", "B", 13)
        pdf.set_text_color(*c_primary)
        pdf.cell(90, 7, org_name[:40], align="L")

        pdf.set_xy(text_x, header_y + 8)
        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(*c_muted)
        pdf.cell(90, 5, "Payslip", align="L")

        pdf.set_xy(120, header_y)
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(*c_primary)
        pdf.cell(76, 6, f"Payslip: {period_label}", align="R")

        if teamzen_logo:
            try:
                pdf.set_xy(120, header_y + 8)
                pdf.set_font("helvetica", "", 7)
                pdf.set_text_color(*c_muted)
                pdf.cell(50, 5, "Generated by", align="R")
                pdf.image(teamzen_logo, x=172, y=header_y + 7, h=6)
            except Exception:
                pdf.set_xy(120, header_y + 8)
                pdf.set_font("helvetica", "", 8)
                pdf.set_text_color(*c_muted)
                pdf.cell(76, 5, "Generated by Teamzen", align="R")
        else:
            pdf.set_xy(120, header_y + 8)
            pdf.set_font("helvetica", "", 8)
            pdf.set_text_color(*c_muted)
            pdf.cell(76, 5, "Generated by Teamzen", align="R")

        # Divider under header
        pdf.set_draw_color(222, 226, 230)
        pdf.set_line_width(0.3)
        pdf.line(14, 30, 196, 30)

        # ── Net Pay hero ──
        y = 36
        if show_net_hero:
            pdf.set_fill_color(*c_hero)
            hero_h = 22 if compact else 28
            pdf.rect(14, y, 182, hero_h, "F")

            pdf.set_xy(18, y + 3)
            pdf.set_font("helvetica", "", 9)
            pdf.set_text_color(*c_muted)
            pdf.cell(40, 5, "Net Pay", align="L")

            pdf.set_xy(18, y + (8 if compact else 10))
            pdf.set_font("helvetica", "B", 18 if compact else 22)
            pdf.set_text_color(*c_primary)
            pdf.cell(50, 10 if compact else 12, _fmt_inr(payslip.net_pay), align="L")

            # Equation: Gross − Deductions
            eq_x = 85
            pdf.set_xy(eq_x, y + 5)
            pdf.set_font("helvetica", "", 8)
            pdf.set_text_color(*c_muted)
            pdf.cell(35, 4, "Gross Pay (A)", align="C")
            pdf.set_xy(eq_x + 40, y + 5)
            pdf.cell(35, 4, "Deductions (B)", align="C")

            pdf.set_xy(eq_x, y + (10 if compact else 12))
            pdf.set_font("helvetica", "B", 11 if compact else 12)
            pdf.set_text_color(*c_primary)
            pdf.cell(35, 8, f"+ {_fmt_inr(payslip.gross_earnings)}", align="C")

            pdf.set_xy(eq_x + 32, y + (10 if compact else 12))
            pdf.set_font("helvetica", "B", 14)
            pdf.set_text_color(173, 181, 189)
            pdf.cell(8, 8, "-", align="C")

            pdf.set_xy(eq_x + 40, y + (10 if compact else 12))
            pdf.set_font("helvetica", "B", 11 if compact else 12)
            pdf.set_text_color(*c_primary)
            pdf.cell(35, 8, f"- {_fmt_inr(payslip.total_deductions)}", align="C")

            pdf.set_xy(eq_x + 72, y + (10 if compact else 12))
            pdf.set_font("helvetica", "B", 14)
            pdf.set_text_color(173, 181, 189)
            pdf.cell(8, 8, "=", align="C")
            y = y + hero_h + 6
        else:
            y = 34

        # ── Employee details grid (2 columns × 5 rows) ──
        pdf.set_xy(14, y)
        pdf.set_font("helvetica", "B", 10)
        pdf.set_text_color(*c_primary)
        pdf.cell(0, 6, "Employee details", new_x="LMARGIN", new_y="NEXT")

        details = [
            ("Employee Code", str(emp_code)),
            ("Name", name),
            ("Designation", payslip.designation or "-"),
            ("Department", payslip.department or "-"),
            ("Date of birth", _fmt_date(dob)),
            ("PAN", str(pan)),
            ("Account no.", str(account_no)),
            ("IFSC code", str(ifsc)),
            ("Date of joining", _fmt_date(doj)),
            ("Worked / LOP days", f"{payslip.worked_days} / {payslip.lop_days}"),
            ("Regime Opted", str(regime)),
            ("Email", user.email or "-"),
        ]

        col_w = 91
        row_h = 9 if compact else 11
        start_y = y + 8
        for i, (label, value) in enumerate(details):
            col = i % 2
            row = i // 2
            x = 14 + col * col_w
            cy = start_y + row * row_h
            pdf.set_xy(x, cy)
            pdf.set_font("helvetica", "", 7)
            pdf.set_text_color(*c_muted)
            pdf.cell(col_w - 4, 4, label, align="L")
            pdf.set_xy(x, cy + 4)
            pdf.set_font("helvetica", "B", 9)
            pdf.set_text_color(*c_primary)
            pdf.cell(col_w - 4, 5, str(value)[:40], align="L")

        # ── Summary chips: Gross (A) | Deductions (B) ──
        y = start_y + ((len(details) + 1) // 2) * row_h + (4 if compact else 6)
        pdf.set_fill_color(*c_earn)
        pdf.rect(14, y, 88, 18, "F")
        pdf.set_xy(18, y + 3)
        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(22, 163, 74)
        pdf.cell(80, 4, "Gross Pay (A)", align="L")
        pdf.set_xy(18, y + 8)
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(*c_primary)
        pdf.cell(80, 7, f"+ {_fmt_inr(payslip.gross_earnings)}", align="L")

        pdf.set_fill_color(*c_ded)
        pdf.rect(108, y, 88, 18, "F")
        pdf.set_xy(112, y + 3)
        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(220, 38, 38)
        pdf.cell(80, 4, "Deductions (B)", align="L")
        pdf.set_xy(112, y + 8)
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(*c_primary)
        pdf.cell(80, 7, f"- {_fmt_inr(payslip.total_deductions)}", align="L")

        # ── Earnings table ──
        y = y + 24
        pdf.set_xy(14, y)
        pdf.set_font("helvetica", "B", 10)
        pdf.set_text_color(*c_primary)
        pdf.cell(0, 6, "Gross Pay (A)", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(*c_muted)
        pdf.cell(0, 5, "The total money you earned before the deductions", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

        # Table header
        pdf.set_fill_color(*c_th_bg)
        pdf.set_font("helvetica", "B", 8)
        pdf.set_text_color(*c_th_fg)
        pdf.cell(100, 7, "Earnings", border="B", fill=True)
        pdf.cell(41, 7, "Monthly", border="B", align="R", fill=True)
        pdf.cell(41, 7, "Total Amount", border="B", align="R", fill=True, new_x="LMARGIN", new_y="NEXT")

        pdf.set_text_color(*c_primary)
        pdf.set_font("helvetica", "", 9)
        for comp in earnings:
            amt = _fmt_inr(comp.amount)
            pdf.cell(100, 7, comp.component_name[:48], border="B")
            pdf.cell(41, 7, amt, border="B", align="R")
            pdf.cell(41, 7, amt, border="B", align="R", new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("helvetica", "B", 9)
        pdf.set_fill_color(*c_hero)
        pdf.cell(100, 8, "Gross Pay", border=0, fill=True)
        pdf.cell(41, 8, "", border=0, fill=True)
        pdf.cell(
            41,
            8,
            _fmt_inr(payslip.gross_earnings),
            border=0,
            align="R",
            fill=True,
            new_x="LMARGIN",
            new_y="NEXT",
        )

        # ── Deductions table ──
        pdf.ln(6)
        pdf.set_font("helvetica", "B", 10)
        pdf.set_text_color(*c_primary)
        pdf.cell(0, 6, "Deductions (B)", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(*c_muted)
        pdf.cell(
            0,
            5,
            "The amount deducted for taxes and other benefits",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.ln(1)

        pdf.set_fill_color(*c_th_bg)
        pdf.set_font("helvetica", "B", 8)
        pdf.set_text_color(*c_th_fg)
        pdf.cell(100, 7, "Deductions", border="B", fill=True)
        pdf.cell(41, 7, "Monthly", border="B", align="R", fill=True)
        pdf.cell(41, 7, "Total Amount", border="B", align="R", fill=True, new_x="LMARGIN", new_y="NEXT")

        pdf.set_text_color(*c_primary)
        pdf.set_font("helvetica", "", 9)
        if deductions:
            for comp in deductions:
                amt = _fmt_inr(comp.amount)
                pdf.cell(100, 7, comp.component_name[:48], border="B")
                pdf.cell(41, 7, amt, border="B", align="R")
                pdf.cell(41, 7, amt, border="B", align="R", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.cell(100, 7, "-", border="B")
            pdf.cell(41, 7, "0", border="B", align="R")
            pdf.cell(41, 7, "0", border="B", align="R", new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("helvetica", "B", 9)
        pdf.set_fill_color(*c_hero)
        pdf.cell(100, 8, "Total Deductions", border=0, fill=True)
        pdf.cell(41, 8, "", border=0, fill=True)
        pdf.cell(
            41,
            8,
            _fmt_inr(payslip.total_deductions),
            border=0,
            align="R",
            fill=True,
            new_x="LMARGIN",
            new_y="NEXT",
        )

        # ── Footer ──
        pdf.set_y(-18)
        pdf.set_draw_color(222, 226, 230)
        pdf.line(14, pdf.get_y(), 196, pdf.get_y())
        pdf.ln(2)
        pdf.set_font("helvetica", "", 7)
        pdf.set_text_color(148, 163, 184)
        pdf.cell(60, 5, "Page 1 of 1", align="L")
        pdf.cell(
            122,
            5,
            "This is a computer generated payslip and does not require a signature",
            align="R",
        )

        pdf_bytes = pdf.output(dest="S")
        for p in tmp_paths:
            try:
                os.unlink(p)
            except OSError:
                pass

        if not persist:
            if isinstance(pdf_bytes, str):
                return pdf_bytes.encode("latin-1")
            return bytes(pdf_bytes)

        safe_month = month_name.replace(" ", "_")
        # Include payslip id so recalculated slips do not reuse a stale Cloudinary URL
        public_id = f"payslip_{payslip.user.id}_{safe_month}_{year}_{payslip.id}"

        import cloudinary.uploader

        upload_result = cloudinary.uploader.upload(
            pdf_bytes,
            public_id=public_id,
            folder="media/payslips",
            resource_type="raw",
            overwrite=True,
            invalidate=True,
            format="pdf",
        )
        # Prefer secure versioned URL path when available
        payslip.payslip_pdf.name = upload_result.get("public_id") or public_id
        payslip.save(update_fields=["payslip_pdf"])
        return None

    @staticmethod
    def _generate_payslip_on_uploaded_template(payslip, template, *, persist=True):
        """
        Clean Networth-style replica — drawn from scratch (no PDF patching).
        """
        from payroll.networth_layout import render_networth_style_payslip

        month_name = calendar.month_name[payslip.payroll_run.month]
        year = payslip.payroll_run.year
        pdf_bytes = render_networth_style_payslip(payslip)

        if not persist:
            return pdf_bytes

        safe_month = month_name.replace(" ", "_")
        public_id = f"payslip_{payslip.user.id}_{safe_month}_{year}_{payslip.id}"
        import cloudinary.uploader

        upload_result = cloudinary.uploader.upload(
            pdf_bytes,
            public_id=public_id,
            folder="media/payslips",
            resource_type="raw",
            overwrite=True,
            invalidate=True,
            format="pdf",
        )
        payslip.payslip_pdf.name = upload_result.get("public_id") or public_id
        payslip.save(update_fields=["payslip_pdf"])
        return None

    @staticmethod
    def process_payouts(payroll_run_id):
        """Processes payouts via Razorpay API."""
        import os
        import requests

        payroll_run = PayrollRun.objects.get(id=payroll_run_id)
        if payroll_run.status != "completed":
            raise Exception("Payroll must be completed before processing payouts.")

        payslips = Payslip.objects.filter(payroll_run=payroll_run, status="published")

        key_id = os.environ.get("RAZORPAY_KEY_ID", "mock_key")
        key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "mock_secret")
        x_account_number = os.environ.get("RAZORPAY_X_ACCOUNT_NUMBER", "")

        is_mock = key_id == "mock_key"

        success_count = 0
        skipped = []
        for payslip in payslips:
            user = payslip.user
            if not user.bank_account_number or not user.bank_ifsc_code:
                skipped.append(user.email)
                print(f"Skipping payout for {user.email} - missing bank details")
                continue

            amount_in_paise = int(payslip.net_pay * 100)

            if is_mock:
                print(f"Mocking Razorpay payout of Rs {payslip.net_pay} to {user.bank_account_number}")
                payslip.status = "paid"
                payslip.save(update_fields=["status"])
                success_count += 1
            else:
                try:
                    auth = (key_id, key_secret)
                    if not user.razorpay_contact_id:
                        contact_data = {
                            "name": f"{user.first_name} {user.last_name}",
                            "email": user.email,
                            "contact": user.phone_number or "0000000000",
                            "type": "employee",
                            "reference_id": str(user.id),
                        }
                        res = requests.post(
                            "https://api.razorpay.com/v1/contacts",
                            json=contact_data,
                            auth=auth,
                        )
                        if res.status_code in [200, 201]:
                            user.razorpay_contact_id = res.json()["id"]
                            user.save(update_fields=["razorpay_contact_id"])
                        else:
                            raise Exception(f"Failed to create Razorpay Contact: {res.text}")

                    if not user.razorpay_fund_account_id:
                        fa_data = {
                            "contact_id": user.razorpay_contact_id,
                            "account_type": "bank_account",
                            "bank_account": {
                                "name": f"{user.first_name} {user.last_name}",
                                "ifsc": user.bank_ifsc_code,
                                "account_number": user.bank_account_number,
                            },
                        }
                        res = requests.post(
                            "https://api.razorpay.com/v1/fund_accounts",
                            json=fa_data,
                            auth=auth,
                        )
                        if res.status_code in [200, 201]:
                            user.razorpay_fund_account_id = res.json()["id"]
                            user.save(update_fields=["razorpay_fund_account_id"])
                        else:
                            raise Exception(
                                f"Failed to create Razorpay Fund Account: {res.text}"
                            )

                    payout_data = {
                        "account_number": x_account_number,
                        "fund_account_id": user.razorpay_fund_account_id,
                        "amount": amount_in_paise,
                        "currency": "INR",
                        "mode": "IMPS",
                        "purpose": "salary",
                        "queue_if_low_balance": True,
                        "reference_id": f"PAYSLIP_{payslip.id}",
                        "narration": (
                            f"Salary {calendar.month_name[payslip.payroll_run.month]} "
                            f"{payslip.payroll_run.year}"
                        ),
                    }
                    res = requests.post(
                        "https://api.razorpay.com/v1/payouts",
                        json=payout_data,
                        auth=auth,
                    )
                    if res.status_code in [200, 201]:
                        payslip.status = "paid"
                        payslip.save(update_fields=["status"])
                        success_count += 1
                    else:
                        raise Exception(f"Payout API failed: {res.text}")

                except Exception as e:
                    print(f"Payout failed for {user.email}: {str(e)}")

        return success_count
