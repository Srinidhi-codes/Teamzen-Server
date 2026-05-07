from payroll.models import EmployeeSalaryStructure
for ess in EmployeeSalaryStructure.objects.filter(is_active=True):
    print(f'User: {ess.user.username}, Structure: {ess.salary_structure.name}, CTC: {ess.annual_ctc}')
