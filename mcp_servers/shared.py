"""
Django bootstrap helper.
Called once at MCP server process startup before any tool is invoked.
"""
import os
import django

_bootstrapped = False

def bootstrap_django():
    global _bootstrapped
    if _bootstrapped:
        return
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
    django.setup()
    _bootstrapped = True
