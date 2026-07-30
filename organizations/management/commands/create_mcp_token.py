"""
Create an org-scoped MCP API token for external clients.

Usage:
  python manage.py create_mcp_token --org 1 --user 5 --name "Cursor" \\
    --scopes attendance:read,leaves:read,payroll:read,policy:read,hr:read,attendance:write,leaves:write
"""
from __future__ import annotations

import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from mcp_servers.shared import hash_token
from organizations.models import MCP_SCOPE_CHOICES, MCPApiToken, Organization


class Command(BaseCommand):
    help = "Create an MCP API token (optionally user-bound). Prints plaintext once."

    def add_arguments(self, parser):
        parser.add_argument("--org", type=int, required=True, help="Organization ID")
        parser.add_argument(
            "--user",
            type=int,
            default=None,
            help="Bind token to this user ID (recommended — forces user_id on all tools)",
        )
        parser.add_argument("--name", type=str, default="MCP client", help="Token label")
        parser.add_argument(
            "--scopes",
            type=str,
            default=",".join(MCP_SCOPE_CHOICES),
            help="Comma-separated scopes",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=0,
            help="Optional expiry in days (0 = never)",
        )

    def handle(self, *args, **options):
        org_id = options["org"]
        try:
            org = Organization.objects.get(id=org_id)
        except Organization.DoesNotExist:
            raise CommandError(f"Organization {org_id} not found")

        bound_user = None
        user_id = options.get("user")
        if user_id:
            User = get_user_model()
            try:
                bound_user = User.objects.get(id=user_id, is_active=True)
            except User.DoesNotExist:
                raise CommandError(f"User {user_id} not found or inactive")
            if bound_user.organization_id != org.id:
                raise CommandError(
                    f"User {user_id} belongs to org {bound_user.organization_id}, not {org.id}"
                )

        scopes = [s.strip() for s in options["scopes"].split(",") if s.strip()]
        invalid = [s for s in scopes if s not in MCP_SCOPE_CHOICES]
        if invalid:
            raise CommandError(
                f"Invalid scopes: {invalid}. Allowed: {MCP_SCOPE_CHOICES}"
            )

        plaintext = f"tzm_{secrets.token_urlsafe(32)}"
        expires_at = None
        if options["days"] and options["days"] > 0:
            expires_at = timezone.now() + timedelta(days=options["days"])

        token = MCPApiToken.objects.create(
            organization=org,
            name=options["name"],
            token_prefix=plaintext[:12],
            token_hash=hash_token(plaintext),
            scopes=scopes,
            expires_at=expires_at,
            bound_user=bound_user,
        )

        self.stdout.write(self.style.SUCCESS("MCP API token created."))
        self.stdout.write(f"  id:     {token.id}")
        self.stdout.write(f"  org:    {org.id} ({org.name})")
        if bound_user:
            self.stdout.write(
                f"  user:   {bound_user.id} ({bound_user.email})"
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "  user:   (none — user-scoped tools need --user or X-MCP-Acting-User-Id)"
                )
            )
        self.stdout.write(f"  name:   {token.name}")
        self.stdout.write(f"  scopes: {', '.join(scopes)}")
        self.stdout.write(self.style.WARNING(f"  token:  {plaintext}"))
        self.stdout.write("Store this token now — it will not be shown again.")
