# Generated manually for Sequence 5 MCP tokens + audit

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("organizations", "0010_organization_plan_expires_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="MCPApiToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="Label, e.g. 'Cursor desktop'", max_length=100)),
                ("token_prefix", models.CharField(db_index=True, max_length=12)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("scopes", models.JSONField(default=list, help_text="List of scope strings")),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_mcp_tokens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mcp_api_tokens",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="MCPAuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("server_name", models.CharField(max_length=64)),
                ("tool_name", models.CharField(max_length=128)),
                ("actor_user_id", models.IntegerField(blank=True, null=True)),
                ("args_digest", models.CharField(blank=True, max_length=64)),
                ("success", models.BooleanField(default=True)),
                ("error_message", models.TextField(blank=True)),
                ("latency_ms", models.PositiveIntegerField(default=0)),
                (
                    "is_internal",
                    models.BooleanField(
                        default=False,
                        help_text="True when called via LangGraph internal secret",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mcp_audit_logs",
                        to="organizations.organization",
                    ),
                ),
                (
                    "token",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_logs",
                        to="organizations.mcpapitoken",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="mcpauditlog",
            index=models.Index(
                fields=["-created_at", "organization"],
                name="organizatio_created_a9cc50_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="mcpauditlog",
            index=models.Index(
                fields=["tool_name", "-created_at"],
                name="organizatio_tool_na_61fc9a_idx",
            ),
        ),
    ]
