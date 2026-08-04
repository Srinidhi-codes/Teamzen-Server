from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="organizations.Organization")
def seed_onboarding_defaults(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from onboarding.services import ensure_default_template

        ensure_default_template(instance)
    except Exception:
        # Avoid blocking org creation if onboarding seed fails
        import logging

        logging.getLogger(__name__).exception(
            "Failed to seed onboarding defaults for org %s", instance.id
        )
