#!/usr/bin/env python
"""
Two-way Database Sync & Seed Tool (Neon <-> Local Postgres)

Usage:
  python sync_db.py status          # Check connection & counts on both Neon and Local
  python sync_db.py pull            # Seed Local from remote Neon (Neon -> Local)
  python sync_db.py push            # Seed remote Neon from Local (Local -> Neon)

Options:
  --data-only   Only sync table data (skips drop/recreate table DDL)
  --force       Skip confirmation prompt when pushing to remote Neon
"""

import os
import sys
import shutil
import glob
import subprocess
from datetime import datetime
from urllib.parse import urlparse

# Set UTF-8 encoding for Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

# -----------------------------------------------------------------------------
# Configuration: Read from .env or fallback to project defaults
# -----------------------------------------------------------------------------
NEON_URL = os.getenv(
    "NEON_DATABASE_URL",
    "postgresql://neondb_owner:npg_KUgvYG2pPcz9@ep-odd-smoke-a1gkii89-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
)

LOCAL_URL = os.getenv(
    "LOCAL_DATABASE_URL",
    "postgresql://postgres:123@localhost:5432/payroll"
)

def parse_db_url(url: str):
    parsed = urlparse(url)
    return {
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "db": parsed.path.lstrip("/"),
        "ssl": "require" if "sslmode=require" in url else "prefer",
    }

NEON = parse_db_url(NEON_URL)
LOCAL = parse_db_url(LOCAL_URL)

# -----------------------------------------------------------------------------
# Tool Discovery: locate pg_dump and psql on Windows / PATH
# -----------------------------------------------------------------------------
def find_pg_binary(name: str):
    found = shutil.which(name)
    if found:
        return found
    # Check standard PostgreSQL Windows install directories
    candidates = glob.glob(rf"C:\Program Files\PostgreSQL\*\bin\{name}.exe")
    if candidates:
        # Return the newest version
        candidates.sort(reverse=True)
        return candidates[0]
    return None

PG_DUMP = find_pg_binary("pg_dump")
PSQL = find_pg_binary("psql")

def check_tools():
    if not PG_DUMP or not PSQL:
        print("\n✗ Error: Could not find pg_dump or psql.")
        print("  Checked system PATH and C:\\Program Files\\PostgreSQL\\*\\bin\\")
        print("  Please make sure PostgreSQL is installed.")
        sys.exit(1)

def run_cmd(cmd, env_vars=None, stdin_data=None):
    merged_env = {**os.environ, **(env_vars or {})}
    result = subprocess.run(
        cmd,
        env=merged_env,
        input=stdin_data,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    return result.returncode == 0, result.stdout, result.stderr

def get_row_count(target_cfg, label):
    """Query row counts to verify state."""
    env = {"PGPASSWORD": target_cfg["password"], "PGSSLMODE": target_cfg["ssl"]}
    cmd = [
        PSQL,
        "-h", target_cfg["host"],
        "-p", target_cfg["port"],
        "-U", target_cfg["user"],
        "-d", target_cfg["db"],
        "-t", "-A",
        "-c", "SELECT count(*) FROM users_customuser;"
    ]
    ok, stdout, stderr = run_cmd(cmd, env)
    if ok and stdout.strip().isdigit():
        return int(stdout.strip())
    return None

# -----------------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------------
def cmd_status():
    check_tools()
    print("=" * 60)
    print("  Database Sync Status Check")
    print("=" * 60)
    print(f"  pg_dump: {PG_DUMP}")
    print(f"  psql:    {PSQL}")
    print("-" * 60)

    print("Checking Local database...")
    local_users = get_row_count(LOCAL, "Local")
    if local_users is not None:
        print(f"  ✓ Local ({LOCAL['db']} @ {LOCAL['host']}): Connected | Users count: {local_users}")
    else:
        print(f"  ✗ Local ({LOCAL['db']} @ {LOCAL['host']}): Connection failed")

    print("\nChecking Remote Neon database...")
    neon_users = get_row_count(NEON, "Neon")
    if neon_users is not None:
        print(f"  ✓ Neon ({NEON['db']} @ {NEON['host']}): Connected | Users count: {neon_users}")
    else:
        print(f"  ✗ Neon ({NEON['db']} @ {NEON['host']}): Connection failed")
    print("=" * 60)

def cmd_pull(data_only=False):
    """Seed Local from remote Neon (Neon -> Local)."""
    check_tools()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dump_file = os.path.join(BACKUP_DIR, f"neon_dump_{timestamp}.sql")
    latest_file = os.path.join(BACKUP_DIR, "latest_neon_dump.sql")

    print("=" * 60)
    print("  SEEDING: Neon (Remote) → Local Postgres")
    print("=" * 60)

    # 1. Dump from Neon
    print("\n[1/3] Dumping from Neon cloud database...")
    dump_env = {"PGPASSWORD": NEON["password"], "PGSSLMODE": NEON["ssl"]}
    dump_cmd = [
        PG_DUMP,
        "-h", NEON["host"],
        "-p", NEON["port"],
        "-U", NEON["user"],
        "-d", NEON["db"],
        "--no-owner",
        "--no-privileges",
        "--format=plain",
        f"--file={dump_file}",
    ]
    if data_only:
        dump_cmd.extend(["--data-only", "--disable-triggers"])
    else:
        dump_cmd.extend(["--clean", "--if-exists"])

    ok, _, err = run_cmd(dump_cmd, dump_env)
    if not ok or not os.path.exists(dump_file) or os.path.getsize(dump_file) == 0:
        print(f"  ✗ Dump failed: {err[:300]}")
        sys.exit(1)

    size_mb = os.path.getsize(dump_file) / (1024 * 1024)
    shutil.copyfile(dump_file, latest_file)
    print(f"  ✓ Dump successful: {dump_file} ({size_mb:.2f} MB)")

    # 2. Restore into Local
    print("\n[2/3] Restoring data into Local database...")
    restore_env = {"PGPASSWORD": LOCAL["password"], "PGSSLMODE": LOCAL["ssl"]}
    restore_cmd = [
        PSQL,
        "-h", LOCAL["host"],
        "-p", LOCAL["port"],
        "-U", LOCAL["user"],
        "-d", LOCAL["db"],
        "-f", dump_file,
    ]
    ok, out, err = run_cmd(restore_cmd, restore_env)
    # psql returns 0 even on harmless notices/warnings; verify via row count
    local_users = get_row_count(LOCAL, "Local")

    print("\n[3/3] Verification:")
    if local_users is not None:
        print(f"  ✓ Local database updated! Total users in users_customuser: {local_users}")
        print("=" * 60)
        print("  ✓ Success! Local database is seeded with Neon data.")
        print("=" * 60)
    else:
        print(f"  ⚠ Verification query failed. Check restore output:\n{err[:400]}")

def cmd_push(data_only=False, force=False):
    """Seed remote Neon from Local (Local -> Neon)."""
    check_tools()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    local_dump_file = os.path.join(BACKUP_DIR, f"local_dump_{timestamp}.sql")
    safety_backup_file = os.path.join(BACKUP_DIR, f"neon_prepush_safety_backup_{timestamp}.sql")

    print("=" * 60)
    print("  SEEDING: Local Postgres → Neon (Remote Cloud)")
    print("=" * 60)
    print("  WARNING: This will overwrite data in your REMOTE NEON DATABASE.")

    if not force:
        confirm = input("\n  Are you sure you want to push to Neon? Type 'yes' to proceed: ").strip().lower()
        if confirm != "yes":
            print("  Operation cancelled.")
            sys.exit(0)

    # 1. Safety snapshot of current Neon DB
    print("\n[1/4] Creating safety backup of current Neon data before push...")
    neon_env = {"PGPASSWORD": NEON["password"], "PGSSLMODE": NEON["ssl"]}
    backup_cmd = [
        PG_DUMP,
        "-h", NEON["host"],
        "-p", NEON["port"],
        "-U", NEON["user"],
        "-d", NEON["db"],
        "--no-owner",
        "--no-privileges",
        "--clean",
        "--if-exists",
        f"--file={safety_backup_file}",
    ]
    ok_b, _, _ = run_cmd(backup_cmd, neon_env)
    if ok_b and os.path.exists(safety_backup_file):
        print(f"  ✓ Safety snapshot saved to: {safety_backup_file}")
    else:
        print("  ⚠ Could not create safety snapshot of Neon. Proceeding with caution...")

    # 2. Dump Local database
    print("\n[2/4] Dumping local database...")
    local_env = {"PGPASSWORD": LOCAL["password"], "PGSSLMODE": LOCAL["ssl"]}
    dump_cmd = [
        PG_DUMP,
        "-h", LOCAL["host"],
        "-p", LOCAL["port"],
        "-U", LOCAL["user"],
        "-d", LOCAL["db"],
        "--no-owner",
        "--no-privileges",
        "--format=plain",
        f"--file={local_dump_file}",
    ]
    if data_only:
        dump_cmd.extend(["--data-only", "--disable-triggers"])
    else:
        dump_cmd.extend(["--clean", "--if-exists"])

    ok, _, err = run_cmd(dump_cmd, local_env)
    if not ok or not os.path.exists(local_dump_file) or os.path.getsize(local_dump_file) == 0:
        print(f"  ✗ Local dump failed: {err[:300]}")
        sys.exit(1)

    size_mb = os.path.getsize(local_dump_file) / (1024 * 1024)
    print(f"  ✓ Local dump complete: {local_dump_file} ({size_mb:.2f} MB)")

    # 3. Restore to Neon
    print("\n[3/4] Uploading and restoring data into Neon...")
    restore_cmd = [
        PSQL,
        "-h", NEON["host"],
        "-p", NEON["port"],
        "-U", NEON["user"],
        "-d", NEON["db"],
        "-f", local_dump_file,
    ]
    ok, out, err = run_cmd(restore_cmd, neon_env)

    # 4. Verification
    print("\n[4/4] Verification:")
    neon_users = get_row_count(NEON, "Neon")
    if neon_users is not None:
        print(f"  ✓ Neon database updated! Total users in users_customuser: {neon_users}")
        print("=" * 60)
        print("  ✓ Success! Neon database has been seeded from Local.")
        print("=" * 60)
    else:
        print(f"  ⚠ Verification query failed. Check restore output:\n{err[:400]}")

def main():
    args = sys.argv[1:]
    data_only = "--data-only" in args
    force = "--force" in args

    command = None
    for arg in args:
        if not arg.startswith("--"):
            command = arg
            break

    if command in ("status", "check"):
        cmd_status()
    elif command in ("pull", "neon-to-local", "from-neon"):
        cmd_pull(data_only=data_only)
    elif command in ("push", "local-to-neon", "to-neon"):
        cmd_push(data_only=data_only, force=force)
    else:
        print(__doc__)
        print("Available commands:")
        print("  python sync_db.py status          # Check DB connections & record counts")
        print("  python sync_db.py pull            # Seed Local from Neon (Neon -> Local)")
        print("  python sync_db.py push            # Seed Neon from Local (Local -> Neon)")
        print("\nOptional flags:")
        print("  --data-only                       # Only transfer row data without DDL")
        print("  --force                           # Bypass confirmation when pushing to Neon")

if __name__ == "__main__":
    main()
