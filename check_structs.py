from payroll.models import SalaryStructureComponent
for sc in SalaryStructureComponent.objects.all():
    print(f"Structure: {sc.salary_structure.name}, Component: {sc.component.code}, Type: {sc.calculation_type}, Value: {sc.value}, Base: {sc.base_component.code if sc.base_component else 'None'}")
