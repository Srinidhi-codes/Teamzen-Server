from django.db import migrations, models


def set_default_weekend_days(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    for org in Organization.objects.all():
        # Preserve historical leave logic: Sunday-only weekend
        if not org.weekend_days:
            org.weekend_days = [6]
            org.save(update_fields=["weekend_days"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0016_initial_feedback"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="weekend_days",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Weekly off days as Python weekday ints (Mon=0 … Sun=6). "
                    "Empty list means no weekly offs. Default after migrate is Sunday [6]."
                ),
            ),
        ),
        migrations.RunPython(set_default_weekend_days, noop_reverse),
    ]
