import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from users.models import CustomUser
from organizations.models import OfficeLocation

def run_diagnostic():
    users = CustomUser.objects.all()
    print(f"Total users: {users.count()}")
    for user in users:
        print(f"User: {user.email}, Office: {user.office_location}")
    
    offices = OfficeLocation.objects.all()
    print(f"Total offices: {offices.count()}")
    for office in offices:
        print(f"Office: {office.name} (ID: {office.id})")

if __name__ == "__main__":
    run_diagnostic()
