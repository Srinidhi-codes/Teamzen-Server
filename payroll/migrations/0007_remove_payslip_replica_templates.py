from django.db import migrations, models


def remove_replica_templates(apps, schema_editor):
    PayslipTemplate = apps.get_model("payroll", "PayslipTemplate")
    PayslipTemplate.objects.filter(source="cloned").delete()
    PayslipTemplate.objects.filter(layout_key__in=["uploaded", "networth"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0006_data_import_and_payslip_templates"),
    ]

    operations = [
        migrations.RunPython(remove_replica_templates, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="paysliptemplate",
            name="preview_notes",
        ),
        migrations.RemoveField(
            model_name="paysliptemplate",
            name="source_file",
        ),
        migrations.AlterField(
            model_name="paysliptemplate",
            name="layout_key",
            field=models.CharField(
                choices=[
                    ("classic", "Classic"),
                    ("modern", "Modern"),
                    ("compact", "Compact"),
                    ("minimal", "Minimal"),
                ],
                default="classic",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="paysliptemplate",
            name="source",
            field=models.CharField(
                choices=[
                    ("system", "System gallery"),
                    ("custom", "Custom"),
                ],
                default="custom",
                max_length=20,
            ),
        ),
    ]
