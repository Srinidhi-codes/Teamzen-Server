import calendar
from datetime import date
from decimal import Decimal
import os
from fpdf import FPDF
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from .models import (
    SalaryComponent, SalaryStructure, SalaryStructureComponent, EmployeeSalaryStructure,
    PayrollRun, Payslip, PayslipComponent, PayrollAdjustment
)
from attendance.models import AttendanceRecord
from leaves.models import LeaveRequest

class PayrollService:
    @staticmethod
    def get_days_in_month(year, month):
        return calendar.monthrange(year, month)[1]

    @staticmethod
    def calculate_lop_days(user, year, month):
        """
        Calculate Loss of Pay (LOP) days based on attendance and unpaid leaves.
        """
        # 1. Count 'absent' records in attendance
        absent_days = AttendanceRecord.objects.filter(
            user=user,
            attendance_date__year=year,
            attendance_date__month=month,
            status='absent'
        ).count()

        # 2. Add 'half_day' as 0.5
        half_days = AttendanceRecord.objects.filter(
            user=user,
            attendance_date__year=year,
            attendance_date__month=month,
            status='half_day'
        ).count()
        
        attendance_lop = absent_days + (half_days * 0.5)

        # 3. Count unpaid leaves from leaves app
        # NOTE: We only count leaves that are NOT marked as 'is_paid_leave'
        unpaid_leaves = LeaveRequest.objects.filter(
            user=user,
            _status='approved',
            leave_type__is_paid_leave=False,
            from_date__year=year,
            from_date__month=month
        )
        
        leave_lop = sum(leaf.duration_days for leaf in unpaid_leaves)

        return Decimal(attendance_lop) + Decimal(leave_lop)

    @transaction.atomic
    def process_payroll(self, payroll_run_id):
        payroll_run = PayrollRun.objects.select_for_update().get(id=payroll_run_id)
        
        payroll_run.status = 'processing'
        payroll_run.save()

        try:
            # Clear existing payslips for this run to allow recalculation
            Payslip.objects.filter(payroll_run=payroll_run).delete()
            
            # Reset adjustments status for this month so they can be re-applied
            PayrollAdjustment.objects.filter(
                organization=payroll_run.organization,
                month=payroll_run.month,
                year=payroll_run.year
            ).update(is_processed=False)

            # Get all active salary structures for users in this organization
            employee_structures = EmployeeSalaryStructure.objects.filter(
                user__organization=payroll_run.organization,
                is_active=True,
                effective_from__lte=date(payroll_run.year, payroll_run.month, 1)
            ).select_related('user', 'salary_structure')

            total_org_gross = Decimal('0.00')
            total_org_deduction = Decimal('0.00')
            total_org_net = Decimal('0.00')

            days_in_month = self.get_days_in_month(payroll_run.year, payroll_run.month)

            for emp_struct in employee_structures:
                user = emp_struct.user
                monthly_ctc = emp_struct.annual_ctc / 12
                
                lop_days = self.calculate_lop_days(user, payroll_run.year, payroll_run.month)
                worked_days = Decimal(days_in_month) - lop_days
                
                # Pro-rata adjustment based on LOP
                # gross_after_lop = (monthly_ctc / days_in_month) * worked_days
                lop_deduction_amount = (monthly_ctc / Decimal(days_in_month)) * lop_days
                
                payslip = Payslip.objects.create(
                    payroll_run=payroll_run,
                    user=user,
                    designation=getattr(user.designation, 'name', ''),
                    department=getattr(user.department, 'name', ''),
                    worked_days=worked_days,
                    lop_days=lop_days,
                    gross_earnings=0, # Will update
                    total_deductions=0, # Will update
                    net_pay=0, # Will update
                    status='draft'
                )

                gross_earnings = Decimal('0.00')
                total_deductions = Decimal('0.00')
                
                # Component Map to handle percentages (e.g. PF as % of Basic)
                # Initialize with 'CTC' to allow structures to be based on total cost
                calculated_components = {
                    'CTC': monthly_ctc
                }

                # 1. Processing Earnings
                earnings = emp_struct.salary_structure.components.filter(
                    component__component_type='earning'
                ).order_by('id')
                
                for sc in earnings:
                    amount = Decimal('0.00')
                    if sc.calculation_type == 'flat':
                        amount = sc.value
                    elif sc.calculation_type == 'percentage':
                        # Use specified base component, or default to CTC if none specified
                        base_code = sc.base_component.code if sc.base_component else 'CTC'
                        base_val = calculated_components.get(base_code, Decimal('0.00'))
                        amount = (base_val * sc.value) / 100
                    
                    # Method B: Keep full amount, LOP is handled as a separate deduction
                    # amount = (amount / Decimal(days_in_month)) * worked_days
                    amount = Decimal(amount).quantize(Decimal('0.01'))
                    
                    PayslipComponent.objects.create(
                        payslip=payslip,
                        component_name=sc.component.name,
                        component_code=sc.component.code,
                        component_type='earning',
                        amount=amount
                    )
                    gross_earnings += amount
                    calculated_components[sc.component.code] = amount

                # 2. Processing Deductions
                deductions = emp_struct.salary_structure.components.filter(
                    component__component_type='deduction'
                ).order_by('id')
                
                for sc in deductions:
                    amount = Decimal('0.00')
                    if sc.calculation_type == 'flat':
                        amount = sc.value
                    elif sc.calculation_type == 'percentage':
                        # Use specified base component, or default to CTC if none specified
                        base_code = sc.base_component.code if sc.base_component else 'CTC'
                        base_val = calculated_components.get(base_code, Decimal('0.00'))
                        amount = (base_val * sc.value) / 100
                    
                    PayslipComponent.objects.create(
                        payslip=payslip,
                        component_name=sc.component.name,
                        component_code=sc.component.code,
                        component_type='deduction',
                        amount=amount
                    )
                    total_deductions += amount
                    calculated_components[sc.component.code] = amount

                # 3. Process LOP Deduction (Method B)
                if lop_days > 0:
                    PayslipComponent.objects.create(
                        payslip=payslip,
                        component_name=f"LOP Deduction ({lop_days} days)",
                        component_code="LOP",
                        component_type='deduction',
                        amount=lop_deduction_amount
                    )
                    total_deductions += lop_deduction_amount

                # 3. Process Manual Adjustments
                adjustments = PayrollAdjustment.objects.filter(
                    user=user,
                    month=payroll_run.month,
                    year=payroll_run.year,
                    is_processed=False
                )
                
                for adj in adjustments:
                    PayslipComponent.objects.create(
                        payslip=payslip,
                        component_name=f"Adjustment: {adj.reason}",
                        component_code="ADJ",
                        component_type=adj.adjustment_type,
                        amount=adj.amount
                    )
                    if adj.adjustment_type == 'earning':
                        gross_earnings += adj.amount
                    else:
                        total_deductions += adj.amount
                    
                    # Mark as processed so it's not applied again in another run
                    adj.is_processed = True
                    adj.save()

                # Add LOP if it's considered a deduction head (optional, here we just reduced earnings)
                # But typically LOP is a deduction from Gross.
                # Let's keep it simple for now.

                payslip.gross_earnings = gross_earnings
                payslip.total_deductions = total_deductions
                payslip.net_pay = gross_earnings - total_deductions
                payslip.save()

                total_org_gross += gross_earnings
                total_org_deduction += total_deductions
                total_org_net += payslip.net_pay

            payroll_run.total_gross = total_org_gross
            payroll_run.total_deduction = total_org_deduction
            payroll_run.total_net_pay = total_org_net
            payroll_run.status = 'completed'
            payroll_run.save()
            return True

        except Exception as e:
            import traceback
            payroll_run.status = 'failed'
            payroll_run.save()
            print("--- PAYROLL ERROR ---")
            traceback.print_exc()
            print(f"Error details: {str(e)}")
            print("----------------------")
            return False

    @staticmethod
    def generate_payslip_pdf(payslip):
        """Generates a PDF for the payslip and saves it to the payslip_pdf field."""
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("helvetica", "B", 16)
        
        org_name = payslip.payroll_run.organization.name
        month_name = calendar.month_name[payslip.payroll_run.month]
        year = payslip.payroll_run.year
        
        # Header
        pdf.cell(0, 10, f"{org_name} - Payslip", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 12)
        pdf.cell(0, 10, f"For the month of {month_name} {year}", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(10)
        
        # Employee Details
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(50, 10, "Employee Name:", border=0)
        pdf.set_font("helvetica", "", 12)
        pdf.cell(0, 10, f"{payslip.user.first_name} {payslip.user.last_name}", border=0, new_x="LMARGIN", new_y="NEXT")
        
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(50, 10, "Designation:", border=0)
        pdf.set_font("helvetica", "", 12)
        pdf.cell(0, 10, payslip.designation, border=0, new_x="LMARGIN", new_y="NEXT")
        
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(50, 10, "Worked Days:", border=0)
        pdf.set_font("helvetica", "", 12)
        pdf.cell(0, 10, f"{payslip.worked_days} (LOP: {payslip.lop_days})", border=0, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(10)
        
        # Earnings & Deductions
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(95, 10, "Earnings", border=1, align="C")
        pdf.cell(95, 10, "Deductions", border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        
        pdf.set_font("helvetica", "", 9) # Smaller font to prevent overlapping
        earnings = payslip.components.filter(component_type='earning')
        deductions = payslip.components.filter(component_type='deduction')
        
        max_rows = max(len(earnings), len(deductions))
        
        for i in range(max_rows):
            earning = earnings[i] if i < len(earnings) else None
            deduction = deductions[i] if i < len(deductions) else None
            
            e_name = f"{earning.component_name}" if earning else ""
            e_amt = f"Rs {earning.amount}" if earning else ""
            
            d_name = f"{deduction.component_name}" if deduction else ""
            d_amt = f"Rs {deduction.amount}" if deduction else ""
            
            # Print row
            pdf.cell(65, 10, e_name, border=1)
            pdf.cell(30, 10, e_amt, border=1, align="R")
            
            pdf.cell(65, 10, d_name, border=1)
            pdf.cell(30, 10, d_amt, border=1, align="R", new_x="LMARGIN", new_y="NEXT")
            
        pdf.set_font("helvetica", "B", 9)
        pdf.cell(65, 10, "Total Earnings", border=1)
        pdf.cell(30, 10, f"Rs {payslip.gross_earnings}", border=1, align="R")
        pdf.cell(65, 10, "Total Deductions", border=1)
        pdf.cell(30, 10, f"Rs {payslip.total_deductions}", border=1, align="R", new_x="LMARGIN", new_y="NEXT")
        
        pdf.ln(5)
        pdf.set_font("helvetica", "B", 14)
        pdf.cell(95, 10, "Net Pay", border=1)
        pdf.cell(95, 10, f"Rs {payslip.net_pay}", border=1, align="R", new_x="LMARGIN", new_y="NEXT")
        
        pdf_bytes = pdf.output(dest="S")
        # Clean filename for Cloudinary
        safe_month = month_name.replace(" ", "_")
        public_id = f"payslip_{payslip.user.id}_{safe_month}_{year}.pdf"
        
        import cloudinary.uploader
        
        upload_result = cloudinary.uploader.upload(
            pdf_bytes,
            public_id=public_id,
            folder="media/payslips",
            resource_type="raw"
        )
        
        # Store the public ID in the FileField
        # Note: RawMediaCloudinaryStorage will prefix this with the folder if not already present
        payslip.payslip_pdf.name = upload_result['public_id']
        payslip.save()

    @staticmethod
    def process_payouts(payroll_run_id):
        """Processes payouts via Razorpay API."""
        import razorpay
        import os
        import requests
        
        payroll_run = PayrollRun.objects.get(id=payroll_run_id)
        if payroll_run.status != 'completed':
            raise Exception("Payroll must be completed before processing payouts.")
            
        payslips = Payslip.objects.filter(payroll_run=payroll_run, status='published')
        
        key_id = os.environ.get('RAZORPAY_KEY_ID', 'mock_key')
        key_id = os.environ.get('RAZORPAY_KEY_ID', 'mock_key')
        key_secret = os.environ.get('RAZORPAY_KEY_SECRET', 'mock_secret')
        x_account_number = os.environ.get('RAZORPAY_X_ACCOUNT_NUMBER', '')
        
        is_mock = key_id == 'mock_key'
        
        success_count = 0
        for payslip in payslips:
            user = payslip.user
            if not user.bank_account_number or not user.bank_ifsc_code:
                print(f"Skipping payout for {user.email} - missing bank details")
                continue
                
            amount_in_paise = int(payslip.net_pay * 100)
            
            if is_mock:
                print(f"Mocking Razorpay payout of Rs {payslip.net_pay} to {user.bank_account_number}")
                payslip.status = 'paid'
                payslip.save()
                success_count += 1
            else:
                try:
                    # 1. Ensure Contact exists on Razorpay
                    if not user.razorpay_contact_id:
                        contact_data = {
                            "name": f"{user.first_name} {user.last_name}",
                            "email": user.email,
                            "contact": user.phone_number or "0000000000",
                            "type": "employee",
                            "reference_id": str(user.id)
                        }
                        # RazorpayX Contact creation usually via direct API as client is mainly for PG
                        auth = (key_id, key_secret)
                        res = requests.post("https://api.razorpay.com/v1/contacts", json=contact_data, auth=auth)
                        if res.status_code in [200, 201]:
                            user.razorpay_contact_id = res.json()['id']
                            user.save()
                        else:
                            raise Exception(f"Failed to create Razorpay Contact: {res.text}")

                    # 2. Ensure Fund Account exists
                    if not user.razorpay_fund_account_id:
                        fa_data = {
                            "contact_id": user.razorpay_contact_id,
                            "account_type": "bank_account",
                            "bank_account": {
                                "name": f"{user.first_name} {user.last_name}",
                                "ifsc": user.bank_ifsc_code,
                                "account_number": user.bank_account_number
                            }
                        }
                        res = requests.post("https://api.razorpay.com/v1/fund_accounts", json=fa_data, auth=auth)
                        if res.status_code in [200, 201]:
                            user.razorpay_fund_account_id = res.json()['id']
                            user.save()
                        else:
                            raise Exception(f"Failed to create Razorpay Fund Account: {res.text}")

                    # 3. Create Payout
                    payout_data = {
                        "account_number": x_account_number,
                        "fund_account_id": user.razorpay_fund_account_id,
                        "amount": amount_in_paise,
                        "currency": "INR",
                        "mode": "IMPS",
                        "purpose": "salary",
                        "queue_if_low_balance": True,
                        "reference_id": f"PAYSLIP_{payslip.id}",
                        "narration": f"Salary {calendar.month_name[payslip.payroll_run.month]} {payslip.payroll_run.year}"
                    }
                    res = requests.post("https://api.razorpay.com/v1/payouts", json=payout_data, auth=auth)
                    if res.status_code in [200, 201]:
                        payslip.status = 'paid'
                        payslip.save()
                        success_count += 1
                    else:
                        raise Exception(f"Payout API failed: {res.text}")

                except Exception as e:
                    print(f"Payout failed for {user.email}: {str(e)}")
                    
        return success_count
