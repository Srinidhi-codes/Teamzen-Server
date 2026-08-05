from django.contrib import admin
from .models import (
    SalaryComponent,
    SalaryStructure,
    SalaryStructureComponent,
    EmployeeSalaryStructure,
    PayrollRun,
    Payslip,
    PayslipComponent,
    PayrollAdjustment,
    SalaryAdvance,
    DataImportJob,
    PayslipTemplate,
)

admin.site.register(SalaryComponent)
admin.site.register(SalaryStructure)
admin.site.register(SalaryStructureComponent)
admin.site.register(EmployeeSalaryStructure)
admin.site.register(PayrollRun)
admin.site.register(Payslip)
admin.site.register(PayslipComponent)
admin.site.register(PayrollAdjustment)
admin.site.register(SalaryAdvance)
admin.site.register(DataImportJob)
admin.site.register(PayslipTemplate)
