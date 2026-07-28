from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0008_organization_accent"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="plan_expires_at",
            field=models.DateField(
                blank=True,
                help_text="When the current paid plan ends. Null for free or lifetime.",
                null=True,
            ),
        ),
    ]
