
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ai_engine.models import PolicyFile

def delete_bad_policy():
    try:
        pf = PolicyFile.objects.get(id=5)
        print(f"Deleting PolicyFile ID 5: {pf.title}")
        pf.delete()
        print("Successfully deleted.")
    except PolicyFile.DoesNotExist:
        print("PolicyFile ID 5 not found.")

if __name__ == "__main__":
    delete_bad_policy()
