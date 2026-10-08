#!/usr/bin/env python
"""
Migrate data from Neon Postgres (cloud) to Local Postgres (Docker).

Usage:
  1. Make sure Docker is running and postgres is up:
       docker compose up -d postgres
  2. Run:
       python migrate_neon_to_local.py

This script automatically detects whether local `pg_dump`/`psql` or Docker is available
and performs the dump and restore seamlessly.
"""

import subprocess
import shutil
import sys
import os

# ── Source: Neon (Cloud) ──────────────────────────────────────────────────────
NEON_HOST = "ep-odd-smoke-a1gkii89-pooler.ap-southeast-1.aws.neon.tech"
NEON_DB = "neondb"
NEON_USER = "neondb_owner"
NEON_PASSWORD = "npg_KUgvYG2pPcz9"
NEON_PORT = "5432"

# ── Target: Local Docker Postgres ─────────────────────────────────────────────
LOCAL_CONTAINER = "payroll_postgres"
LOCAL_HOST = "localhost"
LOCAL_DB = "payroll"
LOCAL_USER = "postgres"
LOCAL_PASSWORD = "postgres123"
LOCAL_PORT = "5432"

DUMP_FILE = "neon_backup.sql"


def run_cmd(cmd, env=None, stdin_data=None):
    """Run a command, optionally piping stdin, and print status."""
    merged_env = {**os.environ, **(env or {})}
    print(f"  → Running: {' '.join(str(c) for c in cmd[:4])}...")
    result = subprocess.run(
        cmd,
        env=merged_env,
        input=stdin_data,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    if result.returncode != 0:
        print(f"  ✗ Error: {result.stderr[:500] if result.stderr else result.stdout[:500]}")
        return False, result.stdout, result.stderr
    return True, result.stdout, result.stderr


def main():
    print("=" * 60)
    print("  Neon → Local Postgres Migration")
    print("=" * 60)

    has_pg_dump = shutil.which("pg_dump") is not None
    has_psql = shutil.which("psql") is not None
    has_docker = shutil.which("docker") is not None

    print(f"  Environment detection:")
    print(f"    - Local pg_dump: {'Available' if has_pg_dump else 'Not found'}")
    print(f"    - Local psql:    {'Available' if has_psql else 'Not found'}")
    print(f"    - Docker:        {'Available' if has_docker else 'Not found'}")

    if not has_pg_dump and not has_docker:
        print("\n✗ Error: Neither pg_dump nor Docker is available.")
        print("  Please install PostgreSQL client tools or start Docker Desktop.")
        sys.exit(1)

    # Step 1: Dump from Neon
    print("\n[1/3] Dumping data from Neon Postgres...")
    if has_pg_dump:
        dump_env = {"PGPASSWORD": NEON_PASSWORD}
        dump_cmd = [
            "pg_dump",
            f"--host={NEON_HOST}",
            f"--port={NEON_PORT}",
            f"--username={NEON_USER}",
            f"--dbname={NEON_DB}",
            "--no-owner",
            "--no-privileges",
            "--format=plain",
            "--clean",
            "--if-exists",
            f"--file={DUMP_FILE}",
            "sslmode=require",
        ]
        ok, _, _ = run_cmd(dump_cmd, dump_env)
    else:
        print("  (Using postgres:16-alpine container for pg_dump)")
        dump_cmd = [
            "docker", "run", "--rm",
            "-e", f"PGPASSWORD={NEON_PASSWORD}",
            "pgvector/pgvector:pg16",
            "pg_dump",
            "-h", NEON_HOST,
            "-p", NEON_PORT,
            "-U", NEON_USER,
            "-d", NEON_DB,
            "--no-owner",
            "--no-privileges",
            "--format=plain",
            "--clean",
            "--if-exists",
            "sslmode=require",
        ]
        ok, stdout, _ = run_cmd(dump_cmd)
        if ok:
            with open(DUMP_FILE, "w", encoding="utf-8") as f:
                f.write(stdout)

    if not os.path.exists(DUMP_FILE) or os.path.getsize(DUMP_FILE) == 0:
        print(f"\n✗ Failed to produce {DUMP_FILE}.")
        sys.exit(1)

    size_mb = os.path.getsize(DUMP_FILE) / (1024 * 1024)
    print(f"  ✓ Dump complete: {DUMP_FILE} ({size_mb:.2f} MB)")

    # Step 2: Restore to local Postgres
    print("\n[2/3] Restoring to local Postgres...")
    with open(DUMP_FILE, "r", encoding="utf-8") as f:
        dump_content = f.read()

    if has_psql:
        restore_env = {"PGPASSWORD": LOCAL_PASSWORD}
        restore_cmd = [
            "psql",
            f"--host={LOCAL_HOST}",
            f"--port={LOCAL_PORT}",
            f"--username={LOCAL_USER}",
            f"--dbname={LOCAL_DB}",
        ]
        ok, _, _ = run_cmd(restore_cmd, env=restore_env, stdin_data=dump_content)
    else:
        print("  (Piping dump into Docker container payroll_postgres)")
        restore_cmd = [
            "docker", "exec", "-i",
            LOCAL_CONTAINER,
            "psql",
            "-U", LOCAL_USER,
            "-d", LOCAL_DB,
        ]
        ok, _, _ = run_cmd(restore_cmd, stdin_data=dump_content)

    if not ok:
        print("\n⚠ Restore reported an issue. Please verify database container status.")
        sys.exit(1)

    print("  ✓ Restore complete!")

    # Step 3: Verify
    print("\n[3/3] Verifying migration...")
    if has_psql:
        verify_env = {"PGPASSWORD": LOCAL_PASSWORD}
        verify_cmd = [
            "psql",
            f"--host={LOCAL_HOST}",
            f"--port={LOCAL_PORT}",
            f"--username={LOCAL_USER}",
            f"--dbname={LOCAL_DB}",
            "-c", "SELECT count(*) AS user_count FROM users_customuser;",
        ]
        ok, out, _ = run_cmd(verify_cmd, env=verify_env)
        if ok and out:
            print(f"  {out.strip()}")
    else:
        verify_cmd = [
            "docker", "exec", "-i",
            LOCAL_CONTAINER,
            "psql",
            "-U", LOCAL_USER,
            "-d", LOCAL_DB,
            "-c", "SELECT count(*) AS user_count FROM users_customuser;",
        ]
        ok, out, _ = run_cmd(verify_cmd)
        if ok and out:
            print(f"  {out.strip()}")

    print("\n" + "=" * 60)
    print("  ✓ Migration complete!")
    print("  Your local Postgres now has all data from Neon.")
    print("=" * 60)


if __name__ == "__main__":
    main()
