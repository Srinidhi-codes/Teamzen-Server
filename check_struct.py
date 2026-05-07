from payroll.models import SalaryStructure, SalaryStructureComponent
struct = SalaryStructure.objects.get(name='Example Professional Structure')
for sc in SalaryStructureComponent.objects.filter(salary_structure=struct):
    print(f'Component: {sc.component.code}, Type: {sc.calculation_type}, Value: {sc.value}, Base: {sc.base_component.code if sc.base_component else " None\}')
