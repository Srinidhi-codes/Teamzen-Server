
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ai_engine.tools import search_policies

def test_policy_search():
    # Test for FreshMart (should be gone)
    print("Testing search for 'FreshMart'...")
    res = search_policies.invoke({"query": "FreshMart", "organization_id": 1})
    print(f"Result: {res}")
    
    # Test for something generic (should be filtered by threshold if not found)
    print("\nTesting search for 'Sugar price'...")
    res = search_policies.invoke({"query": "Sugar price", "organization_id": 1})
    print(f"Result: {res}")

if __name__ == "__main__":
    test_policy_search()
