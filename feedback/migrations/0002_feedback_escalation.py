from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("feedback", "0001_initial_feedback"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="feedback",
            name="escalated_to_platform",
            field=models.BooleanField(
                default=False,
                help_text="True after company admin forwards this item to platform superadmin.",
            ),
        ),
        migrations.AddField(
            model_name="feedback",
            name="escalated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="feedback",
            name="escalation_note",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="feedback",
            name="escalated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="feedback_escalations",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="feedback",
            index=models.Index(fields=["escalated_to_platform"], name="feedback_fe_escalat_7c1a2b_idx"),
        ),
    ]
