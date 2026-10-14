import os
import subprocess
import sys
import time
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent

def run_git(args):
    """Run a git command in REPO_DIR and return stdout string."""
    result = subprocess.run(
        ["git"] + args,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip()

def check_for_updates():
    """
    Checks if origin has new commits that local does not have.
    Returns True if an update was applied, False otherwise.
    """
    try:
        # Fetch latest commit references from remote
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=REPO_DIR,
            check=True,
            capture_output=True,
            text=True
        )

        local_hash = run_git(["rev-parse", "HEAD"])
        
        # Try getting upstream tracking branch, fallback to origin/main
        try:
            remote_hash = run_git(["rev-parse", "@{u}"])
        except subprocess.CalledProcessError:
            remote_hash = run_git(["rev-parse", "origin/main"])

        # Check if local is already identical to remote
        if local_hash == remote_hash:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] Up to date ({local_hash[:7]}). No updates needed.")
            return False

        # Determine merge base
        base_hash = run_git(["merge-base", "HEAD", remote_hash])

        # If local_hash != base_hash, local is behind remote (fast-forward possible)
        if local_hash != base_hash:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] Local branch is ahead or diverged ({local_hash[:7]} vs {remote_hash[:7]}). Skipping auto-pull.")
            return False

        # New commits exist!
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] New commits found! ({local_hash[:7]} -> {remote_hash[:7]}). Triggering update...")
        
        # Run update.bat to pull code, run migrations, and relaunch services
        update_bat_path = REPO_DIR / "update.bat"
        result = subprocess.run(
            ["cmd.exe", "/c", str(update_bat_path)],
            cwd=REPO_DIR,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Services successfully updated and restarted!")
            if result.stdout:
                print(result.stdout)
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] update.bat reported an error (exit code {result.returncode}):")
            if result.stderr:
                print(result.stderr)

        # Check if auto_updater.py itself was modified in this update
        try:
            changed_files = run_git(["diff", "--name-only", local_hash, "HEAD"])
            if "auto_updater.py" in changed_files:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] auto_updater.py was updated! Reloading updater process...")
                os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            print(f"Note: Could not check changed files: {e}")

        return True

    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() if e.stderr else str(e)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error checking for updates: {err_msg}")
        return False
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Unexpected error: {e}")
        return False

def main():
    print("========================================================")
    print("Teamzen Auto-Updater started.")
    print("Checking for remote repository updates every 2 minutes...")
    print("========================================================")
    while True:
        try:
            check_for_updates()
        except KeyboardInterrupt:
            print("\nAuto-updater stopped by user.")
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
        time.sleep(120)

if __name__ == "__main__":
    main()
