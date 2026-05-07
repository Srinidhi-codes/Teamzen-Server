
import os
import django
from decimal import Decimal
import datetime

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from users.models import CustomUser
from organizations.models import Organization
from payroll.models import SalaryComponent, SalaryStructure, SalaryStructureComponent, EmployeeSalaryStructure, PayrollRun
from payroll.services import PayrollService

def create_example_payroll():
    # 1. Get Organization and Employee
    org = Organization.objects.get(id=1)
    admin = CustomUser.objects.filter(organization=org, role='admin').first()
    employee = CustomUser.objects.get(id=2) # srinidhiachar2002@gmail.com
    
    print(f"Creating payroll for {employee.email} in {org.name}")

    # 2. Create Components
    basic, _ = SalaryComponent.objects.get_or_create(
        organization=org,
        code='BASIC',
        defaults={'name': 'Basic Pay', 'component_type': 'earning', 'is_taxable': True}
    )
    
    hra, _ = SalaryComponent.objects.get_or_create(
        organization=org,
        code='HRA',
        defaults={'name': 'House Rent Allowance', 'component_type': 'earning', 'is_taxable': True}
    )
    
    pt, _ = SalaryComponent.objects.get_or_create(
        organization=org,
        code='PT',
        defaults={'name': 'Professional Tax', 'component_type': 'deduction', 'is_statutory': True}
    )

    # 3. Create Structure
    struct, created = SalaryStructure.objects.get_or_create(
        organization=org,
        name='Example Professional Structure',
        defaults={'description': 'Auto-generated example structure for testing'}
    )
    
    # Always recreate components to be sure
    SalaryStructureComponent.objects.filter(salary_structure=struct).delete()
    
    # Basic: 25,000 Flat
    SalaryStructureComponent.objects.create(
        salary_structure=struct,
        component=basic,
        calculation_type='flat',
        value=Decimal('25000.00')
    )
    # HRA: 10,000 Flat
    SalaryStructureComponent.objects.create(
        salary_structure=struct,
        component=hra,
        calculation_type='flat',
        value=Decimal('10000.00')
    )
    # PT: 200 Flat
    SalaryStructureComponent.objects.create(
        salary_structure=struct,
        component=pt,
        calculation_type='flat',
        value=Decimal('200.00')
    )

    # 4. Assign to Employee
    # Annual CTC: 6,00,000 (50k/month)
    EmployeeSalaryStructure.objects.update_or_create(
        user=employee,
        defaults={
            'salary_structure': struct,
            'annual_ctc': Decimal('600000.00'),
            'effective_from': datetime.date(2026, 1, 1),
            'is_active': True
        }
    )

    # 5. Generate Payroll Run for May 2026
    # Cleanup existing if any to avoid duplicates for testing
    PayrollRun.objects.filter(organization=org, month=5, year=2026).delete()
    
    payroll_run = PayrollRun.objects.create(
        organization=org,
        month=5,
        year=2026,
        processed_by=admin
    )
    
    service = PayrollService()
    success = service.process_payroll(payroll_run.id)
    
    if success:
        payroll_run.refresh_from_db()
        print(f"Payroll Run Processed: ID {payroll_run.id}, Total Net: {payroll_run.total_net_pay}")
    else:
        print("Payroll processing failed")
    
    return payroll_run

if __name__ == "__main__":
    create_example_payroll()
