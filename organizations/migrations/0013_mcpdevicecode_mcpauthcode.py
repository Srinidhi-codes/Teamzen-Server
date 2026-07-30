# Generated for Sequence 5.1 MCP Sign-in OAuth

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("organizations", "0012_mcpapitoken_bound_user"),
    ]

    operations = [
        migrations.CreateModel(
            name="MCPDeviceCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("device_code", models.CharField(db_index=True, max_length=64, unique=True)),
                ("user_code", models.CharField(db_index=True, max_length=16, unique=True)),
                ("client_id", models.CharField(default="cursor", max_length=128)),
                ("scopes", models.JSONField(default=list)),
                ("interval", models.PositiveSmallIntegerField(default=5)),
                ("expires_at", models.DateTimeField()),
                ("status", models.CharField(
                    choices=[
                        ("pending", "Pending"),
                        ("approved", "Approved"),
                        ("denied", "Denied"),
                        ("expired", "Expired"),
                    ],
                    default="pending",
                    max_length=20,
                )),
                ("token_issued", models.BooleanField(
                    default=False,
                    help_text="True after the device client has polled and received the token once",
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "access_token",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="device_grants",
                        to="organizations.mcpapitoken",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mcp_device_codes",
                        to="organizations.organization",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mcp_device_codes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="MCPAuthCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(db_index=True, max_length=64, unique=True)),
                ("client_id", models.CharField(default="cursor", max_length=128)),
                ("redirect_uri", models.CharField(max_length=512)),
                ("scopes", models.JSONField(default=list)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mcp_auth_codes",
                        to="organizations.organization",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mcp_auth_codes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
