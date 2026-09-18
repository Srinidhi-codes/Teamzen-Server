from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0007_remove_payslip_replica_templates"),
    ]

    operations = [
        migrations.AddField(
            model_name="payslip",
            name="pdf_source",
            field=models.CharField(
                choices=[
                    ("generated", "Generated from template"),
                    ("uploaded", "Admin uploaded PDF"),
                ],
                default="generated",
                help_text="Uploaded PDFs are published as-is and are not regenerated.",
                max_length=20,
            ),
        ),
    ]
