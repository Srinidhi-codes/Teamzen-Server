import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from users.models import CustomUser
from graphql_api.dashboard_queries import DashboardQuery
user=CustomUser.objects.first()
class Info:
    class Context:
        class Request:
            pass
        request = Request()
    context = Context()
info=Info()
info.context.request.user=user
stats = DashboardQuery().user_dashboard_stats(info)
for t in stats.attendance_trend:
    print(f"Month: {t.month}, Value: {t.value}")
