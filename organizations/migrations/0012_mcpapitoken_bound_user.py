# Generated for Sequence 5 identity binding

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("organizations", "0011_mcpapitoken_mcpauditlog"),
    ]

    operations = [
        migrations.AddField(
            model_name="mcpapitoken",
            name="bound_user",
            field=models.ForeignKey(
                blank=True,
                help_text="If set, all tool calls run as this user (user_id args are overwritten).",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="mcp_bound_tokens",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
