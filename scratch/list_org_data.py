
import os
import sys
import django

# Add the backend directory to sys.path
sys.path.append(r"d:\Web Development\LMS\payroll-system\backend")

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from organizations.models import Organization, Department, Designation

print("--- Organizations ---")
for org in Organization.objects.all():
    print(f"ID: {org.id}, Name: {org.name}")

print("\n--- Departments ---")
for dept in Department.objects.all():
    print(f"ID: {dept.id}, Name: {dept.name}, Org: {dept.organization.name}")

print("\n--- Designations ---")
for desig in Designation.objects.all():
    print(f"ID: {desig.id}, Name: {desig.name}, Org: {desig.organization.name}")
