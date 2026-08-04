from django.apps import AppConfig


class OnboardingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "onboarding"
    label = "onboarding"

    def ready(self):
        # noqa: F401 — register signals
        from onboarding import signals  # noqa: F401
