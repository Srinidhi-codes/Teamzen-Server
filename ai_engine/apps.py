"""
AI Engine App Configuration
"""
from django.apps import AppConfig


class AiEngineConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ai_engine'
    verbose_name = 'AI Engine'
    
    def ready(self):
        """Import signals when app is ready"""
        import ai_engine.signals
