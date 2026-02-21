import os
import django
from django.conf import settings

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ai_engine.graph import app
from langchain_core.messages import HumanMessage
from django.contrib.auth import get_user_model

def test_agent_flow(query, user_id):
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
        org_id = user.organization.id if user.organization else 0
        
        print(f"\n--- Testing Query: '{query}' ---")
        initial_state = {
            "messages": [HumanMessage(content=query)],
            "user_id": user_id,
            "organization_id": org_id
        }
        
        # Run the graph
        final_state = app.invoke(initial_state)
        
        # Print results
        print("\nConversation Flow:")
        for msg in final_state["messages"]:
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            print(f"[{role}]: {msg.content}")
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                print(f"   [Tool Call]: {msg.tool_calls[0]['name']} with {msg.tool_calls[0]['args']}")
                
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Get a test user
    User = get_user_model()
    test_user = User.objects.filter(is_superuser=False).first()
    if not test_user:
        test_user = User.objects.first()
        
    if test_user:
        print(f"Testing with User: {test_user.username} (ID: {test_user.id})")
        
        # Test 1: Balance check
        test_agent_flow("What is my sick leave balance?", test_user.id)
        
        # Test 2: Attendance check
        test_agent_flow("Did I check in today?", test_user.id)

        # Test 3: Policy search
        test_agent_flow("What is the leave policy for sick leaves?", test_user.id)
    else:
        print("No user found in database for testing.")

