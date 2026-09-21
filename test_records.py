import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from users.models import CustomUser
from attendance.models import AttendanceRecord

user=CustomUser.objects.first()
records = AttendanceRecord.objects.filter(user=user)
print(f"Total attendance records for {user.email}: {records.count()}")
for r in records[:10]:
    print(r.attendance_date, r.status)
