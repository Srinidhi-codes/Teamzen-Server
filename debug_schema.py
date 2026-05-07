import os
import django
import sys

# Set up Django
sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from graphql_api.schema import schema

query = """
    query IntrospectionQuery {
      __type(name: "Query") {
        fields {
          name
        }
      }
    }
"""
result = schema.execute_sync(query)
print("--- Introspection Query Fields ---")
if result.data:
    for field in result.data['__type']['fields']:
        print(field['name'])
else:
    print(result.errors)
