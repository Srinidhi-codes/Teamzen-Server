# Generated manually for P0: data import + payslip templates

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import cloudinary_storage.storage


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("organizations", "0001_initial"),
        ("payroll", "0005_employee_component_override"),
    ]

    operations = [
        migrations.CreateModel(
            name="DataImportJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("uploaded", "Uploaded"), ("mapped", "Mapped"), ("previewed", "Previewed"), ("committed", "Committed"), ("failed", "Failed")], default="uploaded", max_length=20)),
                ("source_type", models.CharField(choices=[("csv", "CSV"), ("xlsx", "Excel"), ("xls", "Excel legacy")], default="csv", max_length=10)),
                ("file_name", models.CharField(blank=True, default="", max_length=255)),
                ("file", models.FileField(blank=True, null=True, storage=cloudinary_storage.storage.RawMediaCloudinaryStorage(), upload_to="imports/")),
                ("headers", models.JSONField(blank=True, default=list)),
                ("sample_rows", models.JSONField(blank=True, default=list)),
                ("all_rows", models.JSONField(blank=True, default=list)),
                ("column_mapping", models.JSONField(blank=True, default=dict, help_text="Maps source header → target field key (or empty to skip)")),
                ("mapping_confidence", models.JSONField(blank=True, default=dict)),
                ("preview_result", models.JSONField(blank=True, default=dict)),
                ("commit_result", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="data_import_jobs", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="data_import_jobs", to="organizations.organization")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="PayslipTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(blank=True, default="", max_length=80)),
                ("description", models.TextField(blank=True, default="")),
                ("layout_key", models.CharField(choices=[("classic", "Classic"), ("modern", "Modern"), ("compact", "Compact"), ("minimal", "Minimal")], default="classic", max_length=20)),
                ("theme", models.JSONField(blank=True, default=dict, help_text="Colors and display flags used by PDF renderer")),
                ("source", models.CharField(choices=[("system", "System gallery"), ("custom", "Custom"), ("cloned", "Cloned from upload")], default="custom", max_length=20)),
                ("source_file", models.FileField(blank=True, null=True, storage=cloudinary_storage.storage.RawMediaCloudinaryStorage(), upload_to="payslip_templates/")),
                ("preview_notes", models.TextField(blank=True, default="", help_text="AI notes from clone-from-upload analysis")),
                ("is_default", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_payslip_templates", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(blank=True, help_text="Null = system gallery template available to all orgs", null=True, on_delete=django.db.models.deletion.CASCADE, related_name="payslip_templates", to="organizations.organization")),
            ],
            options={
                "ordering": ["-is_default", "name"],
            },
        ),
    ]
