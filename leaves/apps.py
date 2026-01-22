from django.apps import AppConfig


class LeavesConfig(AppConfig):
    name = "leaves"

    def ready(self):
        import leaves.signals
