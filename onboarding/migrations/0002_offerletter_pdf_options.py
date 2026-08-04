from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("onboarding", "0001_initial_onboarding"),
    ]

    operations = [
        migrations.AddField(
            model_name="offerletter",
            name="annual_ctc",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=15, null=True
            ),
        ),
        migrations.AddField(
            model_name="offerletter",
            name="ctc_snapshot",
            field=models.JSONField(
                blank=True,
                help_text="Frozen CTC annexure payload used when generating the PDF",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="offerletter",
            name="include_ctc_annexure",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="offerletter",
            name="source",
            field=models.CharField(
                choices=[
                    ("generated", "System generated"),
                    ("uploaded", "HR uploaded"),
                ],
                default="generated",
                max_length=20,
            ),
        ),
    ]
