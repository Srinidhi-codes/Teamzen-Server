import subprocess
import time
import sys

def check_for_updates():
    try:
        # Fetch latest from remote
        subprocess.run(["git", "fetch"], check=True, capture_output=True)
        
        # Check if local is behind remote
        status_result = subprocess.run(
            ["git", "status", "-uno"], 
            check=True, 
            capture_output=True, 
            text=True
        )
        
        if "Your branch is behind" in status_result.stdout:
            print("Updates found! Triggering update process...")
            # Trigger update script
            subprocess.Popen(['update.bat'], shell=True)
            return True
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] No updates found.")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"Error checking for updates: {e}")
        return False

def main():
    print("Auto-updater started. Checking for updates every 2 minutes...")
    while True:
        if check_for_updates():
            # Give update.bat time to kill this process
            time.sleep(60)
        else:
            # Check every 2 minutes
            time.sleep(120)

if __name__ == "__main__":
    main()
