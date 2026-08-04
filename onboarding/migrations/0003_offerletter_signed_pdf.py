from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("onboarding", "0002_offerletter_pdf_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="offerletter",
            name="signed_pdf_url",
            field=models.URLField(blank=True, default="", max_length=1024),
        ),
        migrations.AddField(
            model_name="offerletter",
            name="signed_uploaded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="offerletter",
            name="signed_uploaded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="uploaded_signed_offer_letters",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
