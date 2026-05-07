from users.models import CustomUser
from payroll.models import EmployeeSalaryStructure

users = CustomUser.objects.all()
print(f"Total Users: {users.count()}")
for u in users:
    has_struct = EmployeeSalaryStructure.objects.filter(user=u, is_active=True).exists()
    print(f"User {u.email}: {has_struct}")
