from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Organization, Department, Designation

@receiver(post_save, sender=Organization)
def populate_default_org_data(sender, instance, created, **kwargs):
    """
    Automatically populate a new organization with default departments and designations.
    """
    if created:
        # Default Departments
        admin_depts = [
            {'name': 'Administration', 'description': 'Core administrative and operational support.'},
            {'name': 'Human Resources', 'description': 'Talent management, payroll, and employee relations.'},
            {'name': 'IT & Infrastructure', 'description': 'Management of digital assets and technical support.'},
            {'name': 'Finance', 'description': 'Financial planning, accounting, and budgeting.'},
            {'name': 'Executive Office', 'description': 'Leadership and strategic management.'}
        ]
        
        # Default Designations
        admin_desigs = [
            {'name': 'System Administrator', 'description': 'Responsible for managing and maintaining internal systems.'},
            {'name': 'HR Manager', 'description': 'Oversees human resources operations.'},
            {'name': 'Operations Lead', 'description': 'Coordinates organizational operations and workflows.'},
            {'name': 'Finance Controller', 'description': 'Manages financial reporting and compliance.'},
            {'name': 'IT Support Specialist', 'description': 'Provides technical assistance and infrastructure maintenance.'},
            {'name': 'Executive Assistant', 'description': 'Supports executive leadership in daily operations.'}
        ]

        # Create Departments
        for dept_data in admin_depts:
            Department.objects.get_or_create(
                organization=instance,
                name=dept_data['name'],
                defaults={'description': dept_data['description']}
            )

        # Create Designations
        for desig_data in admin_desigs:
            Designation.objects.get_or_create(
                organization=instance,
                name=desig_data['name'],
                defaults={'description': desig_data['description']}
            )
