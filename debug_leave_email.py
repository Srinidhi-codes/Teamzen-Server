import os
import sys
import django

from leaves.models import LeaveRequest
from notifications.tasks import send_email_notification
from django.conf import settings
import re
from users.models import CustomUser

def debug_leave_email():
    User = CustomUser
    req = LeaveRequest.objects.last()
    target_id = str(req.id)
    recipient = req.user
    
    html_content = None
    
    try:
        context = {
            'employeeName': f"{req.user.first_name} {req.user.last_name}",
            'managerName': recipient.first_name or "Manager",
            'status': req._status,
            'dates': f"{req.from_date.strftime('%b %d, %Y')} to {req.to_date.strftime('%b %d, %Y')}",
            'duration': str(req.duration_days).rstrip('0').rstrip('.') if '.' in str(req.duration_days) else str(req.duration_days),
            'leaveType': req.leave_type.name,
            'dashboardUrl': "https://teamzen-client.vercel.app/leaves" if recipient.role == 'employee' else "https://teamzen-admin.vercel.app/leaves"
        }

        if req._status == 'rejected':
            if req.approval_comments:
                context['reason'] = req.approval_comments
            template_name = 'LeaveRejectedAlert.html'
        elif req._status == 'approved':
            if req.approval_comments:
                context['remarks'] = req.approval_comments
            template_name = 'LeaveApprovedAlert.html'
        else:
            if req.reason:
                context['reason'] = req.reason
            template_name = 'LeaveRequestAlert.html'

        admin_dir = settings.BASE_DIR.parent / "admin"
        template_path = os.path.join(admin_dir, template_name)
        
        print(f"Looking for template at: {template_path}")
        
        with open(template_path, 'r', encoding='utf-8') as f:
            raw_html = f.read()

        clean_html = re.sub(r'{{.*?}}', lambda m: m.group(0).replace('<!-- -->', ''), raw_html, flags=re.DOTALL)
        html_content = re.sub(r'{{\s*(.*?)\s*}}', r'{{\1}}', clean_html, flags=re.DOTALL)
        html_content = re.sub(r'{%.*?%}', '', html_content, flags=re.DOTALL)
        
        for key, value in context.items():
            html_content = html_content.replace(f'{{{{{key}}}}}', str(value))
            
        print("HTML content length:", len(html_content) if html_content else "None")
        if html_content:
            print("Preview of HTML:", html_content[:200])
            
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_leave_email()
