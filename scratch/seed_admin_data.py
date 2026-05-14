
import os
import sys
import django

# Add the backend directory to sys.path
sys.path.append(r"d:\Web Development\LMS\payroll-system\backend")

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from organizations.models import Organization, Department, Designation

def seed_admin_defaults():
    organizations = Organization.objects.all()
    
    admin_departments = [
        {"name": "Administration", "description": "Core administrative and operational support."},
        {"name": "Human Resources", "description": "Talent management, payroll, and employee relations."},
        {"name": "IT & Infrastructure", "description": "Management of digital assets and technical support."},
        {"name": "Finance", "description": "Financial planning, accounting, and budgeting."},
        {"name": "Executive Office", "description": "Leadership and strategic management."}
    ]
    
    admin_designations = [
        {"name": "System Administrator", "description": "Responsible for managing and maintaining internal systems."},
        {"name": "HR Manager", "description": "Oversees human resources operations."},
        {"name": "Operations Lead", "description": "Coordinates organizational operations and workflows."},
        {"name": "Finance Controller", "description": "Manages financial reporting and compliance."},
        {"name": "IT Support Specialist", "description": "Provides technical assistance and infrastructure maintenance."},
        {"name": "Executive Assistant", "description": "Supports executive leadership in daily operations."}
    ]

    for org in organizations:
        print(f"Seeding for Organization: {org.name}")
        
        # Seed Departments
        for dept_data in admin_departments:
            dept, created = Department.objects.get_or_create(
                organization=org,
                name=dept_data["name"],
                defaults={"description": dept_data["description"]}
            )
            if created:
                print(f"  - Created Department: {dept.name}")
            else:
                print(f"  - Department already exists: {dept.name}")

        # Seed Designations
        for desig_data in admin_designations:
            desig, created = Designation.objects.get_or_create(
                organization=org,
                name=desig_data["name"],
                defaults={"description": desig_data["description"]}
            )
            if created:
                print(f"  - Created Designation: {desig.name}")
            else:
                print(f"  - Designation already exists: {desig.name}")

if __name__ == "__main__":
    seed_admin_defaults()
    print("\nSeeding completed.")
