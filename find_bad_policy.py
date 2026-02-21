
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ai_engine.models import PolicyDocument, PolicyFile

def find_problematic_policy():
    print("Searching for 'FreshMart' or 'Sugar' in PolicyDocuments...")
    docs = PolicyDocument.objects.filter(content__icontains='FreshMart') | PolicyDocument.objects.filter(content__icontains='Sugar')
    
    if not docs.exists():
        print("No matches found.")
        return

    found_files = set()
    for doc in docs:
        print(f"Found match in Document ID: {doc.id}")
        print(f"Title: {doc.title}")
        if doc.policy_file:
            print(f"PolicyFile Title: {doc.policy_file.title}")
            print(f"Organization: {doc.policy_file.organization.name}")
            found_files.add(doc.policy_file)
        print(f"Content Snippet: {doc.content[:200]}...")
        print("-" * 20)

    for pf in found_files:
        print(f"Recommended action: Delete PolicyFile(id={pf.id}, title='{pf.title}')")

if __name__ == "__main__":
    find_problematic_policy()
